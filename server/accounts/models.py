# accounts/models.py
from __future__ import annotations

from datetime import timedelta
import math
import secrets

from django.conf import settings
from django.contrib.auth.models import (
    AbstractBaseUser,
    PermissionsMixin,
    BaseUserManager,
)
from django.db import models
from django.utils import timezone


# =========================
# Custom User
# =========================
class AppUserManager(BaseUserManager):
    """Manager for our custom user."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Email must be provided")
        if not password:
            raise ValueError("Password must be provided")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)  # hashes
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("is_active", True)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class AbstractAppUser(AbstractBaseUser, PermissionsMixin):
    """
    Abstract user with your required fields.
    """

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    objects = AppUserManager()

    class Meta:
        abstract = True

    def __str__(self):
        return self.email


class CustomerUser(AbstractAppUser):
    """
    Concrete user for customers.
    Add customer-only fields here if needed.
    """
    pass


# =========================
# OTP & Single User Location
# =========================
def _generate_otp() -> str:
    # 4-digit OTP, zero-padded
    return f"{secrets.randbelow(10**4):04d}"  # 0000–9999


class OTPCode(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="otps")
    code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=32, default="signup")  # e.g., "signup", "password_reset"
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
    is_used = models.BooleanField(default=False)

    @classmethod
    def create_for_user(cls, user, minutes_valid=10, purpose="signup"):
        return cls.objects.create(
            user=user,
            code=_generate_otp(),
            purpose=purpose,
            expires_at=timezone.now() + timedelta(minutes=minutes_valid),
        )

    def is_valid(self):
        return not self.is_used and timezone.now() <= self.expires_at and self.attempts < 5

    def __str__(self):
        return f"OTP<{self.user.email}, {self.purpose}, used={self.is_used}>"


class UserLocation(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="location")
    latitude = models.FloatField()
    longitude = models.FloatField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Location<{self.user.email}: {self.latitude},{self.longitude}>"


# =========================
# Addresses, Categories, Restaurants
# =========================
class UserAddress(models.Model):
    LABEL_HOME = "Home"
    LABEL_WORK = "Work"
    LABEL_OTHER = "Other"
    LABEL_CHOICES = (
        (LABEL_HOME, "Home"),
        (LABEL_WORK, "Work"),
        (LABEL_OTHER, "Other"),
    )

    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses")
    label      = models.CharField(max_length=20, choices=LABEL_CHOICES, default=LABEL_HOME)
    address    = models.CharField(max_length=255)
    latitude   = models.FloatField(null=True, blank=True)
    longitude  = models.FloatField(null=True, blank=True)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-is_primary", "-created_at"]

    def __str__(self) -> str:
        return f"{self.user} - {self.label} - {self.address[:40]}"


class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)
    icon = models.CharField(max_length=40, default="fast-food")  # Ionicons name used by your UI

    def __str__(self) -> str:
        return self.name


class Restaurant(models.Model):
    name          = models.CharField(max_length=140)
    tags          = models.CharField(max_length=200, blank=True, default="")
    rating        = models.DecimalField(max_digits=3, decimal_places=1, default=4.5)
    eta_min       = models.PositiveIntegerField(default=15)   # minutes
    eta_max       = models.PositiveIntegerField(default=30)   # minutes
    delivery_free = models.BooleanField(default=True)
    is_open       = models.BooleanField(default=True)

    # Geo
    latitude      = models.FloatField()
    longitude     = models.FloatField()

    # Relations
    categories    = models.ManyToManyField(Category, related_name="restaurants", blank=True)

    # Optional image URL if you want to serve real images
    # Keep remote URL support:
    image_url = models.URLField(blank=True, default="")
    image = models.ImageField(upload_to="restaurants/", blank=True, null=True)


    created_at    = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["latitude", "longitude"]),
        ]
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def eta_text(self) -> str:
        if self.eta_min == self.eta_max:
            return f"{self.eta_min} min"
        return f"{self.eta_min}-{self.eta_max} min"

    # Simple Haversine for distance in KM
    @staticmethod
    def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c



class Product(models.Model):
    """
    Menu item sold by a Restaurant.
    """
    restaurant   = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name="products")
    # Optional: categorize products (Burger, Sandwich, etc.) using your Category model
    categories   = models.ManyToManyField(Category, related_name="products", blank=True)

    # UI fields matching your RN page
    title        = models.CharField(max_length=140)          # "Burger Ferguson"
    subtitle     = models.CharField(max_length=140, blank=True, default="")  # "Spicy Restaurant" or short copy
    description  = models.TextField(blank=True, default="")

    # Price
    price        = models.DecimalField(max_digits=8, decimal_places=2, default=0)  # 999,999.99 max

    # Media (same pattern as Restaurant)
    image_url    = models.URLField(blank=True, default="")
    image        = models.ImageField(upload_to="products/", blank=True, null=True)

    # Flags
    is_available = models.BooleanField(default=True)
    is_veg       = models.BooleanField(default=False)
    is_spicy     = models.BooleanField(default=False)

    created_at   = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["restaurant__name", "title"]

    def __str__(self) -> str:
        return f"{self.title} ({self.restaurant.name})"

    @property
    def price_text(self) -> str:
        # Your RN page shows "$40" strings. Keep as $ by default; you can swap currency later.
        return f"${self.price:.0f}" if self.price == int(self.price) else f"${self.price}"

    def image_best(self) -> str:
        # returns relative URL or remote URL; serializer will absolutize
        try:
            if self.image:
                return self.image.url
        except Exception:
            pass
        return self.image_url or ""
