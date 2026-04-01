from django.urls import path

from ui.staff.views.auth import LoginView, LogoutView
from ui.staff.views.customer import (
    CustomerCreateView,
    CustomerDetailView,
    CustomerEditFieldView,
    CustomerEditView,
    CustomerSearchView,
    CustomerSelectView,
)
from ui.staff.views.session import (
    CustomerFieldUpdateView,
    SessionHeaderFragmentView,
    SessionRecentVisitsFragmentView,
    SessionView,
)
from ui.staff.views.matching import (
    MatchingCandidatesView,
    MatchingConfirmView,
    MatchingRejectView,
    MatchingView,
)
from ui.staff.views.visit import VisitCreateView, VisitListView

app_name = "staff"

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("customers/", CustomerSelectView.as_view(), name="customers"),
    path("customers/search/", CustomerSearchView.as_view(), name="customer-search"),
    path("customers/new/", CustomerCreateView.as_view(), name="customer-create"),
    path("customers/<uuid:pk>/", CustomerDetailView.as_view(), name="customer-detail"),
    path("customers/<uuid:pk>/edit/", CustomerEditView.as_view(), name="customer-edit"),
    path(
        "customers/<uuid:pk>/edit/field/",
        CustomerEditFieldView.as_view(),
        name="customer-edit-field",
    ),
    path("customers/<uuid:pk>/visits/", VisitListView.as_view(), name="visit-list"),
    path("customers/<uuid:pk>/session/", SessionView.as_view(), name="session"),
    path(
        "customers/<uuid:pk>/session/header/",
        SessionHeaderFragmentView.as_view(),
        name="session-header",
    ),
    path(
        "customers/<uuid:pk>/session/recent-visits/",
        SessionRecentVisitsFragmentView.as_view(),
        name="session-recent-visits",
    ),
    path(
        "customers/<uuid:pk>/field/",
        CustomerFieldUpdateView.as_view(),
        name="customer-field-update",
    ),
    path("visits/create/", VisitCreateView.as_view(), name="visit-create"),
    path("matching/", MatchingView.as_view(), name="matching"),
    path(
        "matching/<uuid:row_id>/candidates/",
        MatchingCandidatesView.as_view(),
        name="matching-candidates",
    ),
    path(
        "matching/<uuid:row_id>/confirm/",
        MatchingConfirmView.as_view(),
        name="matching-confirm",
    ),
    path(
        "matching/<uuid:row_id>/reject/",
        MatchingRejectView.as_view(),
        name="matching-reject",
    ),
]
