from __future__ import annotations

from math import radians, sin, cos, atan2, sqrt

from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth import models as django_auth_models
from django.core import exceptions
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    OTPCode,
    UserLocation,
    UserAddress,
    Category,
    Restaurant,
    Product,
    Cart,
    CartItem,
    Order,
    OrderItem,
    Payment,
)
from django.conf import settings


User = get_user_model()


# =========================
# Helpers
# =========================
def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    R = 6371000.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (sin(dlat / 2) ** 2
         + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2)
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


# =========================
# Signup (email+password)
# =========================
class RegisterSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("Email is already registered.")
        return email

    def validate(self, attrs):
        name = (attrs.get("name") or "").strip()
        email = (attrs.get("email") or "").strip().lower()
        attrs["name"] = name
        attrs["email"] = email

        # Run Django's password validators
        user_dummy = User(email=email, full_name=name)
        try:
            password_validation.validate_password(attrs["password"], user=user_dummy)
        except exceptions.ValidationError as e:
            raise serializers.ValidationError({"password": list(e.messages)})
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(
            email=validated_data["email"].lower(),
            password=validated_data["password"],
            full_name=validated_data["name"],
        )


class SendOTPSerializer(serializers.Serializer):
    """Send OTP for signup verification (purpose='signup')."""
    email = serializers.EmailField()

    def validate(self, attrs):
        email = attrs["email"].strip().lower()
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "User not found."})
        attrs["user"] = user
        attrs["email"] = email
        return attrs


class VerifyOTPSerializer(serializers.Serializer):
    """Verify signup OTP (4 digits)."""
    email = serializers.EmailField()
    code = serializers.CharField(min_length=4, max_length=4)

    def validate(self, attrs):
        email = attrs["email"].strip().lower()
        code = attrs["code"]

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "User not found."})

        otp = (
            OTPCode.objects.filter(user=user, purpose="signup", is_used=False)
            .order_by("-created_at")
            .first()
        )
        if not otp:
            raise serializers.ValidationError({"code": "No active OTP. Please request a new one."})

        if not otp.is_valid():
            otp.attempts += 1
            otp.save(update_fields=["attempts"])
            raise serializers.ValidationError({"code": "OTP expired or too many attempts."})

        if otp.code != code:
            otp.attempts += 1
            otp.save(update_fields=["attempts"])
            raise serializers.ValidationError({"code": "Incorrect OTP."})

        attrs["user"] = user
        attrs["otp"] = otp
        return attrs

    def save(self, **kwargs):
        otp = self.validated_data["otp"]
        user = self.validated_data["user"]
        otp.is_used = True
        otp.save(update_fields=["is_used"])
        return user


# =========================
# Location (used by RN app)
# =========================
class LocationUpsertSerializer(serializers.Serializer):
    email = serializers.EmailField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    # When true, also create/switch a nearby UserAddress and mark it primary
    save_address = serializers.BooleanField(required=False, default=False)

    @transaction.atomic
    def save(self, **kwargs):
        email = self.validated_data["email"].strip().lower()
        lat = float(self.validated_data["latitude"])
        lon = float(self.validated_data["longitude"])
        save_addr = bool(self.validated_data.get("save_address", False))

        user = User.objects.get(email__iexact=email)

        # 1) Upsert UserLocation
        loc, _ = UserLocation.objects.update_or_create(
            user=user,
            defaults={"latitude": lat, "longitude": lon},
        )

        addr_payload = None

        if save_addr:
            # 2) Switch to existing address within 50m or create a new one and make it primary
            NEAR_M = 50.0
            existing = None
            for a in user.addresses.all():
                if a.latitude is not None and a.longitude is not None:
                    if _haversine_m(lat, lon, a.latitude, a.longitude) <= NEAR_M:
                        existing = a
                        break

            def _clear_primaries(u) -> None:
                u.addresses.filter(is_primary=True).update(is_primary=False)

            if existing:
                _clear_primaries(user)
                existing.is_primary = True
                existing.save(update_fields=["is_primary"])
                addr = existing
            else:
                label = "Home" if not user.addresses.exists() else "Other"
                address_line = f"{lat:.5f}, {lon:.5f}"  # replace with reverse geocode if you add it
                _clear_primaries(user)
                addr = UserAddress.objects.create(
                    user=user,
                    label=label,
                    address=address_line,
                    latitude=lat,
                    longitude=lon,
                    is_primary=True,
                )

            addr_payload = {
                "id": addr.id,
                "label": addr.label,
                "address": addr.address,
                "latitude": addr.latitude,
                "longitude": addr.longitude,
                "is_primary": addr.is_primary,
            }

        return {
            "location": {"latitude": loc.latitude, "longitude": loc.longitude},
            "address": addr_payload,  # may be None if save_address=False
        }


class LocationGetSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def get_location(self):
        email = self.validated_data["email"].strip().lower()
        user = User.objects.get(email__iexact=email)
        try:
            loc = user.location
            return {
                "latitude": loc.latitude,
                "longitude": loc.longitude,
                "updated_at": loc.updated_at,
            }
        except UserLocation.DoesNotExist:
            return None


# =========================
# Login (no OTP)
# =========================
class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        email = (attrs.get("email") or "").strip().lower()
        password = attrs.get("password") or ""

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "Invalid email or password."})

        if not user.check_password(password):
            raise serializers.ValidationError({"email": "Invalid email or password."})

        if hasattr(user, "is_active") and not user.is_active:
            raise serializers.ValidationError({"email": "Account disabled."})

        attrs["user"] = user
        return attrs

    def create(self, validated_data):
        user = validated_data["user"]
        refresh = RefreshToken.for_user(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "email": user.email,
                "name": getattr(user, "full_name", "") or getattr(user, "name", ""),
            },
        }


# =========================
# Forgot password (OTP)
# =========================
class SendPasswordResetOTPSerializer(serializers.Serializer):
    """Send a reset OTP (purpose='password_reset')."""
    email = serializers.EmailField()

    def validate(self, attrs):
        email = attrs["email"].strip().lower()
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "User not found."})
        attrs["user"] = user
        attrs["email"] = email
        return attrs


class VerifyPasswordResetOTPSerializer(serializers.Serializer):
    """Just verifies the reset OTP exists and is valid; does NOT consume it."""
    email = serializers.EmailField()
    code = serializers.CharField(min_length=4, max_length=6)  # 4 or 6

    def validate(self, attrs):
        email = attrs["email"].strip().lower()
        code = attrs["code"]

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "User not found."})

        otp = (
            OTPCode.objects.filter(user=user, purpose="password_reset", is_used=False)
            .order_by("-created_at")
            .first()
        )
        if not otp:
            raise serializers.ValidationError({"code": "No active OTP. Please request a new one."})

        if not otp.is_valid():
            otp.attempts += 1
            otp.save(update_fields=["attempts"])
            raise serializers.ValidationError({"code": "OTP expired or too many attempts."})

        if otp.code != code:
            otp.attempts += 1
            otp.save(update_fields=["attempts"])
            raise serializers.ValidationError({"code": "Incorrect OTP."})

        attrs["user"] = user
        attrs["otp"] = otp
        return attrs


class ResetPasswordSerializer(serializers.Serializer):
    """Consumes a valid reset OTP and sets the new password."""
    email = serializers.EmailField()
    code = serializers.CharField(min_length=4, max_length=6)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        email = attrs["email"].strip().lower()
        code = attrs["code"]
        new_password = attrs["new_password"]

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "User not found."})

        # Password strength
        try:
            password_validation.validate_password(new_password, user=user)
        except exceptions.ValidationError as e:
            raise serializers.ValidationError({"new_password": list(e.messages)})

        otp = (
            OTPCode.objects.filter(user=user, purpose="password_reset", is_used=False)
            .order_by("-created_at")
            .first()
        )
        if not otp:
            raise serializers.ValidationError({"code": "No active OTP. Please request a new one."})
        if not otp.is_valid():
            otp.attempts += 1
            otp.save(update_fields=["attempts"])
            raise serializers.ValidationError({"code": "OTP expired or too many attempts."})
        if otp.code != code:
            otp.attempts += 1
            otp.save(update_fields=["attempts"])
            raise serializers.ValidationError({"code": "Incorrect OTP."})

        attrs["user"] = user
        attrs["otp"] = otp
        return attrs

    def save(self, **kwargs):
        user = self.validated_data["user"]
        otp = self.validated_data["otp"]
        new_password = self.validated_data["new_password"]

        user.set_password(new_password)
        user.save(update_fields=["password"])

        otp.is_used = True  # consume the code
        otp.save(update_fields=["is_used"])
        return user


# =========================
# Feed (Categories / Restaurants)
# =========================
class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "icon")


class RestaurantSerializer(serializers.ModelSerializer):
    eta = serializers.SerializerMethodField()
    free = serializers.SerializerMethodField()
    categoryIds = serializers.SerializerMethodField()
    image_src = serializers.SerializerMethodField()

    class Meta:
        model = Restaurant
        fields = (
            "id",
            "name",
            "tags",
            "rating",
            "eta",          # "20-30 min"
            "free",         # boolean
            "categoryIds",  # list of category IDs
             "image_url", "image",      # keep both for admin/API edits
            "image_src",  
        )

    def get_image_src(self, obj):
        request = self.context.get("request")
        # Prefer local upload if present
        if obj.image:
            try:
                url = obj.image.url
                if request is not None:
                    return request.build_absolute_uri(url)
                return url
            except Exception:
                pass
        # Fallback to remote URL field
        return obj.image_url or ""

    def get_eta(self, obj: Restaurant) -> str:
        return obj.eta_text()

    def get_free(self, obj: Restaurant) -> bool:
        return bool(obj.delivery_free)

    def get_categoryIds(self, obj: Restaurant):
        return list(obj.categories.values_list("id", flat=True))


# ---------------------------
# Address
# ---------------------------
class UserAddressSerializer(serializers.ModelSerializer):
    # email is only required on create; we’ll associate the address with that user
    email = serializers.EmailField(write_only=True, required=False)
    make_primary = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = UserAddress
        fields = (
            "id",
            "email",          # write-only (create)
            "label",
            "address",
            "latitude",
            "longitude",
            "is_primary",
            "make_primary",   # write-only
            "created_at",
        )
        read_only_fields = ("id", "is_primary", "created_at")

    def validate_email(self, value):
        email = (value or "").strip().lower()
        if not email:
            raise serializers.ValidationError("Email is required.")
        if not User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("User not found.")
        return email

    @transaction.atomic
    def create(self, validated_data):
        email = validated_data.pop("email").strip().lower()
        make_primary = bool(validated_data.pop("make_primary", False))
        user = User.objects.get(email__iexact=email)

        # default label for first address = Home
        if not user.addresses.exists() and not validated_data.get("label"):
            validated_data["label"] = "Home"

        # if user asks to make primary, clear previous primaries
        if make_primary or not user.addresses.filter(is_primary=True).exists():
            user.addresses.filter(is_primary=True).update(is_primary=False)
            validated_data["is_primary"] = True

        addr = UserAddress.objects.create(user=user, **validated_data)
        return addr

    @transaction.atomic
    def update(self, instance, validated_data):
        make_primary = bool(validated_data.pop("make_primary", False))
        # normal updates
        for f in ("label", "address", "latitude", "longitude"):
            if f in validated_data:
                setattr(instance, f, validated_data[f])
        instance.save()

        # optionally switch primary
        if make_primary and not instance.is_primary:
            instance.user.addresses.filter(is_primary=True).update(is_primary=False)
            instance.is_primary = True
            instance.save(update_fields=["is_primary"])

        return instance




class ProductSerializer(serializers.ModelSerializer):
    price_text = serializers.SerializerMethodField()
    image_src  = serializers.SerializerMethodField()
    restaurant_id = serializers.IntegerField(source="restaurant.id", read_only=True)
    restaurant_name = serializers.CharField(source="restaurant.name", read_only=True)
    categoryIds = serializers.SerializerMethodField()
    categoryNames = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "restaurant_id",
            "restaurant_name",
            "title",
            "subtitle",
            "description",
            "price",        # numeric (for checkout math)
            "price_text",   # "$40" (for display like your RN page)
            "image_url",
            "image",
            "image_src",    # unified absolute URL (use this in RN)
            "is_available",
            "is_veg",
            "is_spicy",
            "categoryIds",
            "categoryNames",  
            "created_at",
        )
        read_only_fields = ("created_at",)

    def get_price_text(self, obj):
        return obj.price_text

    def get_image_src(self, obj):
        request = self.context.get("request")
        src = obj.image_best()
        if not src:
            return ""
        if src.startswith("http://") or src.startswith("https://"):
            return src
        if request is not None:
            return request.build_absolute_uri(src)
        return src

    def get_categoryIds(self, obj):
        return list(obj.categories.values_list("id", flat=True))
    
    def get_categoryNames(self, obj):               # <-- new
        return list(obj.categories.values_list("name", flat=True))



# ---------- Cart / Orders / Payments serializers ----------

from decimal import Decimal

class CartItemSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(source="product.id", read_only=True)
    class Meta:
        model = CartItem
        fields = ("id", "product_id", "title", "unit_price", "qty", "subtotal")

class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Cart
        fields = ("id", "is_active", "items", "total", "created_at", "updated_at")


class AddToCartSerializer(serializers.Serializer):
    email = serializers.EmailField()
    product_id = serializers.IntegerField()
    qty = serializers.IntegerField(min_value=1, default=1)

    def validate(self, attrs):
        email = attrs["email"].strip().lower()
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "User not found."})
        try:
            product = Product.objects.get(pk=attrs["product_id"], is_available=True)
        except Product.DoesNotExist:
            raise serializers.ValidationError({"product_id": "Product not found or unavailable."})
        attrs["user"] = user
        attrs["product"] = product
        return attrs


class UpdateCartItemSerializer(serializers.Serializer):
    qty = serializers.IntegerField(min_value=1)


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ("product", "title", "unit_price", "qty", "subtotal")


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    class Meta:
        model = Order
        fields = (
            "id","status","address_text","subtotal","delivery_fee","total",
            "created_at","items"
        )


class CreateOrderSerializer(serializers.Serializer):
    email = serializers.EmailField()
    address_text = serializers.CharField(max_length=255, allow_blank=True, required=False)
    delivery_fee = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=Decimal("0.00"))

    def validate(self, attrs):
        email = attrs["email"].strip().lower()
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "User not found."})
        # must have active cart with items
        cart = Cart.objects.filter(user=user, is_active=True).first()
        if not cart or cart.items.count() == 0:
            raise serializers.ValidationError("Cart is empty.")
        attrs["user"] = user
        attrs["cart"] = cart
        return attrs


class PaymentCreateSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()
    method = serializers.ChoiceField(choices=[("card","card"),("cash","cash")], default="card")

    def validate(self, attrs):
        try:
            order = Order.objects.get(pk=attrs["order_id"], status=Order.STATUS_PENDING)
        except Order.DoesNotExist:
            raise serializers.ValidationError("Order not found or not pending.")
        attrs["order"] = order
        return attrs


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ("order","method","amount","status","reference","created_at")
