from __future__ import annotations

from typing import Optional, Tuple

from django.contrib.auth import get_user_model, logout as django_logout
from django.contrib.auth.models import AbstractBaseUser
from django.core.mail import send_mail
from django.db.models import Q
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from rest_framework import viewsets, permissions, filters
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser


from .models import UserLocation, UserAddress, Category, Restaurant, OTPCode, Product
from .serializers import (
    # auth / otp / login
    RegisterSerializer, LoginSerializer,
    SendOTPSerializer, VerifyOTPSerializer,
    SendPasswordResetOTPSerializer, VerifyPasswordResetOTPSerializer, ResetPasswordSerializer,
    # location & feed & addresses
    LocationUpsertSerializer, LocationGetSerializer,
    UserAddressSerializer, CategorySerializer, RestaurantSerializer,
    ProductSerializer,
    # cart / orders / payments
    CartSerializer, AddToCartSerializer, UpdateCartItemSerializer,
    CreateOrderSerializer, OrderSerializer,
    PaymentSerializer, PaymentCreateSerializer,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_user_and_location(email: str) -> Tuple[Optional[AbstractBaseUser], Optional[Tuple[float, float]]]:
    """
    Return (user, (lat, lon)) if available:
      1) UserLocation
      2) primary/first UserAddress with coords (and mirror into UserLocation)
    """
    email = (email or "").strip().lower()
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return None, None

    # 1) explicit UserLocation
    try:
        loc = user.location  # OneToOne
        return user, (loc.latitude, loc.longitude)
    except UserLocation.DoesNotExist:
        pass

    # 2) fallback to primary / first address with coords
    addr = user.addresses.filter(is_primary=True).first() or user.addresses.first()
    if addr and addr.latitude is not None and addr.longitude is not None:
        # mirror into UserLocation for consistency
        UserLocation.objects.update_or_create(
            user=user,
            defaults={"latitude": addr.latitude, "longitude": addr.longitude},
        )
        return user, (addr.latitude, addr.longitude)

    return user, None


# ---------------------------------------------------------------------------
# Signup (email+password) + OTP for verification
# ---------------------------------------------------------------------------
class RegisterView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request):
        return Response({"message": "POST name, email, password to register a customer."})

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {"id": user.id, "email": user.email, "name": user.full_name},
            status=status.HTTP_201_CREATED,
        )


class SendOTPView(APIView):
    """Send signup OTP (purpose='signup')."""
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        ser = SendOTPSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.validated_data["user"]

        otp = OTPCode.create_for_user(user, minutes_valid=10, purpose="signup")
        send_mail(
            subject="Your verification code",
            message=f"Your OTP is {otp.code}. It expires in 10 minutes.",
            from_email=None,
            recipient_list=[user.email],
            fail_silently=True,
        )
        return Response({"message": "OTP sent."}, status=200)


class VerifyOTPView(APIView):
    """Verify signup OTP and issue JWTs."""
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        ser = VerifyOTPSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.save()  # marks OTP used

        refresh = RefreshToken.for_user(user)
        return Response({
            "message": "OTP verified",
            "email": user.email,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "email": user.email,
                "name": getattr(user, "full_name", "") or getattr(user, "name", ""),
            }
        }, status=200)


# ---------------------------------------------------------------------------
# Login / Logout (session & JWT)
# ---------------------------------------------------------------------------
class LoginView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        ser = LoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        tokens = ser.save()
        return Response(tokens, status=200)


class LogoutSessionView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        django_logout(request)
        resp = Response({"message": "Logged out"}, status=200)
        resp.delete_cookie("sessionid")
        resp.delete_cookie("csrftoken")
        return resp


class LogoutJWTView(APIView):
    """
    POST { "refresh": "<refresh_token>" } -> blacklist that refresh
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_str = request.data.get("refresh")
        if not refresh_str:
            return Response({"detail": "Missing 'refresh' token"}, status=400)
        try:
            token = RefreshToken(refresh_str)
            token.blacklist()
        except Exception:
            return Response({"detail": "Invalid or already blacklisted refresh token"}, status=400)
        return Response({"message": "Logged out"}, status=200)


class LogoutAllJWTView(APIView):
    """
    POST with valid access -> blacklist all outstanding tokens for this user
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        tokens = OutstandingToken.objects.filter(user=request.user)
        for t in tokens:
            BlacklistedToken.objects.get_or_create(token=t)
        return Response({"message": "Logged out from all devices"}, status=200)


# ---------------------------------------------------------------------------
# Forgot password (OTP)
# ---------------------------------------------------------------------------
class SendPasswordResetOTPView(APIView):
    """Send reset OTP (purpose='password_reset')."""
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        ser = SendPasswordResetOTPSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.validated_data["user"]

        otp = OTPCode.create_for_user(user, minutes_valid=10, purpose="password_reset")
        send_mail(
            subject="Reset password code",
            message=f"Your password reset OTP is {otp.code}. It expires in 10 minutes.",
            from_email=None,
            recipient_list=[user.email],
            fail_silently=True,
        )
        return Response({"message": "OTP sent."}, status=200)


class VerifyPasswordResetOTPView(APIView):
    """Verify reset OTP; does NOT consume or mint tokens."""
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        ser = VerifyPasswordResetOTPSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.validated_data["user"]
        return Response({"message": "OTP verified", "email": user.email}, status=200)


class ForgotPasswordResetView(APIView):
    """Reset password and consume OTP."""
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        ser = ResetPasswordSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response({"message": "Password updated successfully"}, status=200)


# ---------------------------------------------------------------------------
# Location (GPS upsert + get)
# ---------------------------------------------------------------------------
class LocationUpsertView(APIView):
    """
    POST /api/me/location/
    body:
      {
        "email": "<user email>",
        "latitude": <float>,
        "longitude": <float>,
        "save_address": true   # optional; if true, create/switch a primary UserAddress at this spot
      }
    returns:
      {
        "message": "Location saved",
        "latitude": ...,
        "longitude": ...,
        "address": {...} | null
      }
    """
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        ser = LocationUpsertSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        result = ser.save()  # dict: { location: {...}, address: {...}|None }
        return Response(
            {
                "message": "Location saved",
                "latitude": result["location"]["latitude"],
                "longitude": result["location"]["longitude"],
                "address": result["address"],
            },
            status=200,
        )


class LocationGetView(APIView):
    """
    GET /api/me/location/get/?email=...
    """
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request):
        ser = LocationGetSerializer(data=request.query_params)
        ser.is_valid(raise_exception=True)
        data = ser.get_location()
        if not data:
            return Response({"message": "No location on file"}, status=404)
        return Response(data, status=200)


# ---------------------------------------------------------------------------
# Addresses (list/create + detail/put/delete)
# ---------------------------------------------------------------------------
class AddressListCreate(APIView):
    """
    GET /api/addresses/?email=...
    POST /api/addresses/
      body: { email, label, address, latitude?, longitude?, make_primary? }
    """
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request):
        email = (request.query_params.get("email") or "").strip().lower()
        if not email:
            return Response({"detail": "email is required"}, status=400)
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response([], status=200)

        qs = user.addresses.order_by("-is_primary", "-created_at")
        return Response(UserAddressSerializer(qs, many=True).data, status=200)

    def post(self, request):
        ser = UserAddressSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        addr = ser.save()
        return Response(UserAddressSerializer(addr).data, status=201)


class AddressDetail(APIView):
    """
    GET /api/addresses/<id>/
    PUT /api/addresses/<id>/
    DELETE /api/addresses/<id>/
    """
    authentication_classes: list = []
    permission_classes: list = []

    def get_object(self, pk: int) -> Optional[UserAddress]:
        try:
            return UserAddress.objects.get(pk=pk)
        except UserAddress.DoesNotExist:
            return None

    def get(self, request, pk: int):
        obj = self.get_object(pk)
        if not obj:
            return Response({"detail": "Not found."}, status=404)
        return Response(UserAddressSerializer(obj).data)

    def put(self, request, pk: int):
        obj = self.get_object(pk)
        if not obj:
            return Response({"detail": "Not found."}, status=404)
        ser = UserAddressSerializer(instance=obj, data=request.data, partial=False)
        ser.is_valid(raise_exception=True)
        obj = ser.save()
        return Response(UserAddressSerializer(obj).data)

    def delete(self, request, pk: int):
        obj = self.get_object(pk)
        if not obj:
            return Response({"detail": "Not found."}, status=404)
        obj.delete()
        return Response(status=204)


# ---------------------------------------------------------------------------
# Home Feed (nearby categories + restaurants)
# ---------------------------------------------------------------------------
class HomeFeedView(APIView):
    """
    GET /api/home/feed/?email=...
    Optional: &lat=<float>&lon=<float>&radius_km=10
    Returns:
      {
        "categories": [...],
        "restaurants": [...]
      }
    Uses: UserLocation (or primary address coords) to filter/sort nearby restaurants.
    """
    authentication_classes: list = []
    permission_classes: list = []

    MAX_RADIUS_KM = 10.0
    MAX_RESTAURANTS = 40

    @staticmethod
    def _distance_km(a_lat, a_lon, b_lat, b_lon):
        from math import radians, sin, cos, atan2, sqrt
        R = 6371.0
        dlat = radians(b_lat - a_lat)
        dlon = radians(b_lon - a_lon)
        aa = sin(dlat/2)**2 + cos(radians(a_lat)) * cos(radians(b_lat)) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(aa), sqrt(1-aa))
        return R * c

    def get(self, request):
        email = (request.query_params.get("email") or "").strip().lower()
        lat_q = request.query_params.get("lat")
        lon_q = request.query_params.get("lon")
        radius_km = float(request.query_params.get("radius_km") or self.MAX_RADIUS_KM)

        # resolve coordinates: explicit query > saved
        lat = lon = None
        if lat_q and lon_q:
            try:
                lat = float(lat_q)
                lon = float(lon_q)
            except Exception:
                lat = lon = None
        elif email:
            _, coords = _get_user_and_location(email)
            if coords:
                lat, lon = coords

        # categories + restaurants
        qs = Restaurant.objects.filter(is_open=True).prefetch_related("categories")
        rows = []
        if lat is not None and lon is not None:
            # quick bounding box to reduce candidates
            delta = radius_km / 111.0  # ~1 deg lat ~111km
            cand = qs.filter(
                latitude__gte=lat - delta, latitude__lte=lat + delta,
                longitude__gte=lon - delta, longitude__lte=lon + delta,
            )
            for r in cand:
                d = self._distance_km(lat, lon, r.latitude, r.longitude)
                if d <= radius_km:
                    rows.append((d, r))
            rows.sort(key=lambda t: (t[0], -float(t[1].rating)))
            restaurants = [r for _, r in rows[: self.MAX_RESTAURANTS]]
            cat_ids = set()
            for r in restaurants:
                cat_ids.update(r.categories.values_list("id", flat=True))
            cats = Category.objects.filter(id__in=cat_ids).order_by("name")
        else:
            restaurants = list(qs[: self.MAX_RESTAURANTS])
            cats = Category.objects.all().order_by("name")

        return Response(
            {
                "categories": CategorySerializer(
                    cats, many=True, context={"request": request}
                ).data,
                "restaurants": RestaurantSerializer(
                    restaurants, many=True, context={"request": request}
                ).data,
            },
            status=200,
        )



# server/accounts/views.py
from rest_framework import viewsets, permissions
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from .models import Restaurant, Category
from .serializers import RestaurantSerializer, CategorySerializer

class RestaurantViewSet(viewsets.ModelViewSet):
    queryset = Restaurant.objects.all().order_by("-created_at")
    serializer_class = RestaurantSerializer
    permission_classes = [permissions.AllowAny]  # tighten as needed
    parser_classes = (MultiPartParser, FormParser, JSONParser)

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by("name")
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]




# accounts/views.py

class ProductViewSet(viewsets.ModelViewSet):
    """
    /api/products/
      - ?restaurant=<id>    filter by restaurant
      - ?category=<id>      filter by category
      - ?search=<text>      search in title/subtitle
      - ?available=true     only available items
    Supports multipart for image upload.
    """
    queryset = Product.objects.select_related("restaurant").prefetch_related("categories").all().order_by("-created_at")
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    filter_backends = [filters.SearchFilter]
    search_fields = ["title", "subtitle", "restaurant__name", "description"]

    def get_queryset(self):
        qs = super().get_queryset()
        restaurant_id = self.request.query_params.get("restaurant")
        category_id = self.request.query_params.get("category")
        category_name  = self.request.query_params.get("category_name") 
        available = self.request.query_params.get("available")

        if restaurant_id:
            qs = qs.filter(restaurant_id=restaurant_id)
        if category_id:
            qs = qs.filter(categories__id=category_id)
        if category_name:
            qs = qs.filter(categories__name__iexact=category_name)  # <-- name filter
        if available in ("true", "1", "yes"):
            qs = qs.filter(is_available=True)
        return qs.distinct() 

    def get_serializer_context(self):
        # ensure absolute image_src
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx



# ---------- Cart / Orders / Payments views ----------

from decimal import Decimal
from django.db import transaction
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from .models import Cart, CartItem, Order, OrderItem, Payment

# ---------- Cart helpers ----------
from django.db import transaction

def _get_or_create_active_cart(user) -> Cart:
    """
    Return a single active cart.
    If multiple active carts exist (legacy/bug), merge them into one.
    """
    with transaction.atomic():
        qs = Cart.objects.select_for_update().filter(user=user, is_active=True).order_by("-updated_at", "-id")
        if qs.exists():
            primary = qs.first()
            duplicates = list(qs[1:])  # others
            if duplicates:
                # Merge items from duplicates into primary
                for dup in duplicates:
                    for it in dup.items.select_related("product"):
                        # get_or_create per-product in the primary cart
                        merged, created = CartItem.objects.get_or_create(
                            cart=primary,
                            product=it.product,
                            defaults={
                                "qty": it.qty,
                                "title": it.title,
                                "unit_price": it.unit_price,
                            },
                        )
                        if not created:
                            merged.qty += it.qty
                            merged.save(update_fields=["qty"])
                    # deactivate duplicate cart
                    dup.is_active = False
                    dup.save(update_fields=["is_active"])
            return primary

        # none exist: create a fresh one
        return Cart.objects.create(user=user, is_active=True)



@api_view(["GET"])
@permission_classes([AllowAny])
def cart_get(request):
    email = (request.query_params.get("email") or "").strip().lower()
    if not email:
        return Response({"detail": "email is required"}, status=400)
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return Response({"detail": "User not found."}, status=404)
    cart = _get_or_create_active_cart(user)
    return Response(CartSerializer(cart).data)


@api_view(["POST"])
@permission_classes([AllowAny])
def cart_add(request):
    ser = AddToCartSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    user = ser.validated_data["user"]
    product = ser.validated_data["product"]
    qty = int(ser.validated_data["qty"])

    cart = _get_or_create_active_cart(user)

    item, created = CartItem.objects.get_or_create(
        cart=cart, product=product,
        defaults={"qty": qty, "title": product.title, "unit_price": product.price},
    )
    if not created:
        item.qty += qty
        item.save(update_fields=["qty"])

    return Response(CartSerializer(cart).data, status=201)


@api_view(["PATCH", "DELETE"])
@permission_classes([AllowAny])
def cart_item_update_delete(request, item_id: int):
    try:
        item = CartItem.objects.select_related("cart").get(pk=item_id, cart__is_active=True)
    except CartItem.DoesNotExist:
        return Response({"detail": "Item not found."}, status=404)

    if request.method == "DELETE":
        cart = item.cart
        item.delete()
        return Response(CartSerializer(cart).data)

    # PATCH qty
    ser = UpdateCartItemSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    item.qty = ser.validated_data["qty"]
    item.save(update_fields=["qty"])
    return Response(CartSerializer(item.cart).data)


@api_view(["POST"])
@permission_classes([AllowAny])
def cart_clear(request):
    email = (request.data.get("email") or "").strip().lower()
    if not email:
        return Response({"detail": "email is required"}, status=400)
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return Response({"detail": "User not found."}, status=404)
    cart = Cart.objects.filter(user=user, is_active=True).first()
    if cart:
        cart.items.all().delete()
    return Response({"message": "Cleared."})
    

@api_view(["POST"])
@permission_classes([AllowAny])
@transaction.atomic
def checkout_create_order(request):
    """
    Turns the active cart into an Order (status=pending), snapshots prices,
    closes the cart, creates a Payment record (status=created).
    """
    ser = CreateOrderSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    user = ser.validated_data["user"]
    cart = ser.validated_data["cart"]
    address_text = ser.validated_data.get("address_text", "")
    delivery_fee = Decimal(ser.validated_data.get("delivery_fee") or "0.00")

    if cart.items.count() == 0:
        return Response({"detail": "Cart is empty."}, status=400)

    # snapshot items
    subtotal = cart.total
    total = subtotal + delivery_fee

    order = Order.objects.create(
        user=user,
        status=Order.STATUS_PENDING,
        address_text=address_text,
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        total=total,
    )
    bulk = []
    for ci in cart.items.select_related("product"):
        bulk.append(OrderItem(
            order=order,
            product=ci.product,
            title=ci.title,
            unit_price=ci.unit_price,
            qty=ci.qty,
            subtotal=ci.subtotal,
        ))
    OrderItem.objects.bulk_create(bulk)

    # create payment placeholder
    Payment.objects.create(order=order, method=Payment.METHOD_CARD, amount=total, status=Payment.STATUS_CREATED)

    # close cart
    cart.is_active = False
    cart.save(update_fields=["is_active"])

    # create a fresh empty cart for convenience
    Cart.objects.get_or_create(user=user, is_active=True)

    return Response(OrderSerializer(order).data, status=201)


@api_view(["POST"])
@permission_classes([AllowAny])
@transaction.atomic
def payment_confirm(request):
    """
    Mock payment success/fail. Body:
      { "order_id": <id>, "method": "card"|"cash", "success": true, "reference": "xyz" }
    """
    pser = PaymentCreateSerializer(data=request.data)
    pser.is_valid(raise_exception=True)
    order: Order = pser.validated_data["order"]
    method = pser.validated_data["method"]
    success = bool(request.data.get("success", True))
    reference = (request.data.get("reference") or "")[:64]

    pay = order.payment
    pay.method = method
    pay.reference = reference
    pay.status = Payment.STATUS_SUCCESS if success else Payment.STATUS_FAILED
    pay.save(update_fields=["method","reference","status"])

    if success:
        order.status = Order.STATUS_PAID
        order.save(update_fields=["status"])

    return Response(PaymentSerializer(pay).data)
    

@api_view(["GET"])
@permission_classes([AllowAny])
def orders_list(request):
    email = (request.query_params.get("email") or "").strip().lower()
    if not email:
        return Response({"detail": "email is required"}, status=400)
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return Response([], status=200)
    qs = Order.objects.filter(user=user).prefetch_related("items")
    return Response(OrderSerializer(qs, many=True).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def orders_detail(request, pk: int):
    try:
        obj = Order.objects.prefetch_related("items").get(pk=pk)
    except Order.DoesNotExist:
        return Response({"detail": "Not found."}, status=404)
    return Response(OrderSerializer(obj).data)
