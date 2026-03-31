from django.urls import path

from ui.owner.views.auth import OwnerLoginView, OwnerLogoutView
from ui.owner.views.stub import StubDashboardView

app_name = "owner"

urlpatterns = [
    path("login/", OwnerLoginView.as_view(), name="login"),
    path("logout/", OwnerLogoutView.as_view(), name="logout"),
    path("dashboard/", StubDashboardView.as_view(), name="dashboard"),
]
