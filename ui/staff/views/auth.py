from django.contrib.auth import logout
from django.shortcuts import redirect, render
from django.views import View

from accounts.services import QRAuthService
from core.exceptions import BusinessError

from ui.staff.forms import QRLoginForm

ERROR_MESSAGES = {
    "auth.token_not_found": "QR コードが無効です",
    "auth.token_expired": "QR コードの有効期限が切れています",
    "auth.token_used": "この QR コードは既に使用されています",
    "auth.staff_inactive": "このアカウントは無効化されています",
}


class LoginView(View):
    template_name = "ui/staff/login.html"

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("/s/customers/")
        return render(request, self.template_name, {"form": QRLoginForm()})

    def post(self, request):
        form = QRLoginForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        token = form.cleaned_data["token"]
        try:
            QRAuthService.authenticate(request, token)
        except BusinessError as e:
            form.add_error(
                None,
                ERROR_MESSAGES.get(e.business_code, "認証に失敗しました"),
            )
            return render(request, self.template_name, {"form": form})

        return redirect("/s/customers/")


class LogoutView(View):
    def post(self, request):
        logout(request)
        return redirect("/s/login/")
