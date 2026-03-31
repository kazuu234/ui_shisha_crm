from django.urls import path

from ui.staff.views.auth import LoginView, LogoutView
from ui.staff.views.stub import StubCustomerView

app_name = "staff"

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("customers/", StubCustomerView.as_view(), name="customers"),
]
