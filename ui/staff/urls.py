from django.urls import path

from ui.staff.views.auth import LoginView, LogoutView
from ui.staff.views.customer import (
    CustomerCreateView,
    CustomerSearchView,
    CustomerSelectView,
)

app_name = "staff"

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("customers/", CustomerSelectView.as_view(), name="customers"),
    path("customers/search/", CustomerSearchView.as_view(), name="customer-search"),
    path("customers/new/", CustomerCreateView.as_view(), name="customer-create"),
]
