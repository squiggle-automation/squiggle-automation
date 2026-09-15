from django.urls import path

from .views import (
    ApiTokenCreateView,
    ApiTokenDeleteView,
    ApiTokenView,
    PasswordChangeView,
    SettingsView,
    UserCreateView,
    UserDeleteView,
    UserListView,
    UserPasswordResetView,
    UserUpdateView,
)

app_name = "management"

urlpatterns = [
    path("", SettingsView.as_view(), name="settings"),
    path("password/", PasswordChangeView.as_view(), name="password-change"),
    path("apitoken/", ApiTokenView.as_view(), name="apitoken"),
    path("apitoken/create/", ApiTokenCreateView.as_view(), name="apitoken-create"),
    path("apitoken/delete/", ApiTokenDeleteView.as_view(), name="apitoken-delete"),
    path("users/", UserListView.as_view(), name="users"),
    path("users/create/", UserCreateView.as_view(), name="user-create"),
    path("users/<int:pk>/", UserUpdateView.as_view(), name="user-update"),
    path("users/<int:pk>/password/", UserPasswordResetView.as_view(), name="user-password-reset"),
    path("users/<int:pk>/delete/", UserDeleteView.as_view(), name="user-delete"),
]
