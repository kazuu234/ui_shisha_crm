from django.urls import path

from ui.owner.views.auth import OwnerLoginView, OwnerLogoutView
from ui.owner.views.staff_mgmt import (
    StaffCreateView,
    StaffDeactivateView,
    StaffDetailView,
    StaffListView,
    StaffQRIssueView,
)
from ui.owner.views.stub import StubDashboardView

app_name = "owner"

urlpatterns = [
    path("login/", OwnerLoginView.as_view(), name="login"),
    path("logout/", OwnerLogoutView.as_view(), name="logout"),
    path("dashboard/", StubDashboardView.as_view(), name="dashboard"),
    path("staff/", StaffListView.as_view(), name="staff-list"),
    path("staff/new/", StaffCreateView.as_view(), name="staff-create"),
    path("staff/<uuid:pk>/", StaffDetailView.as_view(), name="staff-detail"),
    path(
        "staff/<uuid:pk>/qr-issue/",
        StaffQRIssueView.as_view(),
        name="staff-qr-issue",
    ),
    path(
        "staff/<uuid:pk>/deactivate/",
        StaffDeactivateView.as_view(),
        name="staff-deactivate",
    ),
]
