from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    # authentication
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="squiggle_automation/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(next_page="/"), name="logout"),
    # include apps
    path("", include("core.urls", namespace="core")),
    path("management/", include("management.urls", namespace="management")),
    path("api/", include("api.urls", namespace="api")),
    # django admin
    path("admin/", admin.site.urls),
]
