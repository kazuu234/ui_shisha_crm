from django.urls import path

from ui.owner.views.auth import OwnerLoginView, OwnerLogoutView
from ui.owner.views.customer import (
    CustomerDetailView,
    CustomerEditView,
    CustomerListView,
)
from ui.owner.views.staff_mgmt import (
    StaffCreateView,
    StaffDeactivateView,
    StaffDetailView,
    StaffListView,
    StaffQRIssueView,
)
from ui.owner.views.stub import StubDashboardView
from ui.owner.views.visit import (
    VisitDeleteView,
    VisitEditView,
    VisitListView,
)

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
    path("customers/", CustomerListView.as_view(), name="customer-list"),
    path(
        "customers/<uuid:pk>/",
        CustomerDetailView.as_view(),
        name="customer-detail",
    ),
    path(
        "customers/<uuid:pk>/edit/",
        CustomerEditView.as_view(),
        name="customer-edit",
    ),
    path("visits/", VisitListView.as_view(), name="visit-list"),
    path("visits/<uuid:pk>/edit/", VisitEditView.as_view(), name="visit-edit"),
    path(
        "visits/<uuid:pk>/delete/",
        VisitDeleteView.as_view(),
        name="visit-delete",
    ),
]
