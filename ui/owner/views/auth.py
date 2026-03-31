from django.contrib.auth import logout
from django.shortcuts import redirect, render
from django.views import View

from accounts.models import QRToken
from accounts.services import QRAuthService
from core.exceptions import BusinessError

from ui.owner.forms.auth import QROwnerLoginForm

ERROR_MESSAGES = {
    "auth.token_not_found": "QR コードが無効です",
    "auth.token_expired": "QR コードの有効期限が切れています",
    "auth.token_used": "この QR コードは既に使用されています",
    "auth.staff_inactive": "このアカウントは無効化されています",
}


class OwnerLoginView(View):
    template_name = "ui/owner/login.html"

    def get(self, request):
        if request.user.is_authenticated and request.user.role == "owner":
            return redirect("/o/dashboard/")
        return render(request, self.template_name, {"form": QROwnerLoginForm()})

    def post(self, request):
        form = QROwnerLoginForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        token = form.cleaned_data["token"]

        try:
            qr_token = QRToken.objects.select_related("staff").get(token=token)
        except QRToken.DoesNotExist:
            form.add_error(None, ERROR_MESSAGES["auth.token_not_found"])
            return render(request, self.template_name, {"form": form})

        if qr_token.staff.role != "owner":
            form.add_error(
                None,
                "オーナー専用です。スタッフ用 QR コードではログインできません",
            )
            return render(request, self.template_name, {"form": form})

        try:
            QRAuthService.authenticate(request, token)
        except BusinessError as e:
            form.add_error(
                None,
                ERROR_MESSAGES.get(e.business_code, "認証に失敗しました"),
            )
            return render(request, self.template_name, {"form": form})

        return redirect("/o/dashboard/")


class OwnerLogoutView(View):
    def post(self, request):
        logout(request)
        return redirect("/o/login/")
