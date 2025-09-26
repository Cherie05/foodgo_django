# accounts/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html

from .models import (
    CustomerUser,
    OTPCode,
    UserLocation,
    UserAddress,
    Category,
    Restaurant,
    Product,
)


# ---------- Users ----------
@admin.register(CustomerUser)
class CustomerUserAdmin(BaseUserAdmin):
    model = CustomerUser
    ordering = ("-date_joined",)
    list_display = ("email", "full_name", "is_active", "is_staff", "date_joined")
    list_filter = ("is_active", "is_staff", "is_superuser")
    search_fields = ("email", "full_name")
    readonly_fields = ("date_joined",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("full_name",)}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "password1", "password2", "is_staff", "is_superuser"),
            },
        ),
    )
    filter_horizontal = ("groups", "user_permissions")


# ---------- OTP ----------
@admin.register(OTPCode)
class OTPCodeAdmin(admin.ModelAdmin):
    list_display = ("user", "purpose", "code", "is_used", "attempts", "expires_at", "created_at")
    list_filter = ("purpose", "is_used", "created_at")
    search_fields = ("user__email", "code")
    readonly_fields = ("created_at",)


# ---------- Location (single current location) ----------
@admin.register(UserLocation)
class UserLocationAdmin(admin.ModelAdmin):
    list_display = ("user", "latitude", "longitude", "updated_at")
    search_fields = ("user__email",)
    readonly_fields = ("updated_at",)


# ---------- Addresses ----------
@admin.register(UserAddress)
class UserAddressAdmin(admin.ModelAdmin):
    list_display = ("user", "label", "short_address", "is_primary", "latitude", "longitude", "created_at")
    list_filter = ("label", "is_primary", "created_at")
    search_fields = ("user__email", "address")
    list_editable = ("is_primary",)

    def short_address(self, obj):
        return (obj.address or "")[:60]
    short_address.short_description = "Address"


# ---------- Menu ----------
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "icon")
    search_fields = ("name",)


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "rating",
        "is_open",
        "delivery_free",
        "eta_min",
        "eta_max",
        "latitude",
        "longitude",
        "image_preview",
    )
    list_filter = ("is_open", "delivery_free", "categories")
    search_fields = ("name", "tags")
    filter_horizontal = ("categories",)
    autocomplete_fields = ()
    readonly_fields = ("created_at", "image_preview")
    fieldsets = (
        (None, {"fields": ("name", "tags", "rating", "is_open", "delivery_free")}),
        ("ETA", {"fields": ("eta_min", "eta_max")}),
        ("Geo", {"fields": ("latitude", "longitude")}),
        ("Relations", {"fields": ("categories",)}),
        ("Media", {"fields": ("image", "image_url", "image_preview")}), 
        ("Meta", {"fields": ("created_at",)}),
    )

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:60px;border-radius:6px;" />', obj.image.url
            )
        if obj.image_url:
            return format_html(
                '<img src="{}" style="height:60px;border-radius:6px;" />', obj.image_url
            )
        return "—"
    image_preview.short_description = "Preview"



@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "restaurant",
        "price",
        "is_available",
        "is_veg",
        "is_spicy",
        "preview",
    )
    list_filter = ("is_available", "is_veg", "is_spicy", "restaurant", "categories")
    search_fields = ("title", "subtitle", "restaurant__name")
    filter_horizontal = ("categories",)
    readonly_fields = ("created_at", "preview")
    fieldsets = (
        (None, {"fields": ("restaurant", "categories")}),
        ("Texts", {"fields": ("title", "subtitle", "description")}),
        ("Price", {"fields": ("price",)}),
        ("Media", {"fields": ("image", "image_url", "preview")}),
        ("Flags", {"fields": ("is_available", "is_veg", "is_spicy")}),
        ("Meta", {"fields": ("created_at",)}),
    )

    def preview(self, obj):
        try:
            if obj.image:
                return format_html('<img src="{}" style="height:60px;border-radius:6px;" />', obj.image.url)
        except Exception:
            pass
        if obj.image_url:
            return format_html('<img src="{}" style="height:60px;border-radius:6px;" />', obj.image_url)
        return "—"
    preview.short_description = "Preview"
