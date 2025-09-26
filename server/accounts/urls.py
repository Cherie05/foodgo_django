from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework.routers import DefaultRouter

from .views import (
    # Signup + login
    RegisterView, LoginView,
    SendOTPView, VerifyOTPView,

    # Location
    LocationUpsertView, LocationGetView,

    # Logout
    LogoutSessionView, LogoutJWTView, LogoutAllJWTView,

    # Forgot password
    SendPasswordResetOTPView, VerifyPasswordResetOTPView, ForgotPasswordResetView,

    # Addresses
    AddressListCreate, AddressDetail,

    # Home feed
    HomeFeedView,

    # Feed (Categories + Restaurants)
    CategoryViewSet, RestaurantViewSet,
    ProductViewSet,
)

router = DefaultRouter()
router.register(r"restaurants", RestaurantViewSet, basename="restaurant")
router.register(r"categories", CategoryViewSet, basename="category")
router.register(r"products", ProductViewSet, basename="product")

urlpatterns = [
    # Auth (email+password & OTP signup)
    path("auth/register/",        RegisterView.as_view(),        name="register"),
    path("auth/login/",           LoginView.as_view(),           name="login"),
    path("auth/send-otp/",        SendOTPView.as_view(),         name="send-otp"),
    path("auth/verify-otp/",      VerifyOTPView.as_view(),       name="verify-otp"),

    # Forgot-password OTP flow
    path("auth/password/forgot/send-otp/", SendPasswordResetOTPView.as_view(), name="password-forgot-send-otp"),
    path("auth/password/forgot/verify/",   VerifyPasswordResetOTPView.as_view(), name="password-forgot-verify"),
    path("auth/password/forgot/reset/",    ForgotPasswordResetView.as_view(),    name="password-forgot-reset"),

    # JWT helpers
    path("auth/token/",           TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/token/refresh/",   TokenRefreshView.as_view(),    name="token_refresh"),

    # Logout (JWT + session)
    path("auth/logout/session/",  LogoutSessionView.as_view(),   name="logout-session"),
    path("auth/logout/jwt/",      LogoutJWTView.as_view(),       name="logout-jwt"),
    path("auth/logout-all/jwt/",  LogoutAllJWTView.as_view(),    name="logout-all-jwt"),

    # Location
    path("me/location/",          LocationUpsertView.as_view(),  name="me-location-upsert"),  # POST
    path("me/location/get/",      LocationGetView.as_view(),     name="me-location-get"),     # GET

    # Addresses
    path("addresses/",            AddressListCreate.as_view(),   name="address-list-create"),
    path("addresses/<int:pk>/",   AddressDetail.as_view(),       name="address-detail"),

    # Home feed
    path("home/feed/",            HomeFeedView.as_view(),        name="home-feed"),
]


urlpatterns += router.urls