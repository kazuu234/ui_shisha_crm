import base64
import re
from datetime import timedelta
from email.mime.image import MIMEImage

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.mail import EmailMultiAlternatives
from django.shortcuts import get_object_or_404, redirect, render
from django.template.defaultfilters import date as date_filter
from django.urls import reverse
from django.utils.html import escape
from django.utils import timezone
from django.views import View
from django.views.generic import ListView
from rest_framework import status

from accounts.models import QRToken, Staff
from accounts.qr_image import generate_qr_data_uri
from accounts.services import QRAuthService
from core.exceptions import BusinessError

from ui.mixins import OwnerRequiredMixin, StoreMixin
from ui.owner.forms.staff import StaffCreateForm, StaffEditForm

QR_EXPIRY_HOURS = {
    "temporary": 8,
    "regular": 720,
    "owner": 720,
}

_QR_DATA_URI_RE = re.compile(
    r"^data:image/png;base64,([A-Za-z0-9+/=]+)\s*$", re.DOTALL
)


def _png_bytes_from_qr_data_uri(data_uri: str) -> bytes:
    m = _QR_DATA_URI_RE.match((data_uri or "").strip())
    if not m:
        raise ValueError("invalid QR data URI")
    return base64.b64decode(m.group(1))


def _issue_qr_token(staff, *, expires_in_hours):
    """QR トークン発行（`QRAuthService.issue_token` があれば委譲、なければ C-02 相当のローカル実装）。"""
    issue = getattr(QRAuthService, "issue_token", None)
    if issue is not None:
        return issue(staff, expires_in_hours=expires_in_hours)

    if not staff.is_active:
        raise BusinessError(
            code="auth.staff_inactive",
            message="このスタッフアカウントは無効です。",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    max_hours = QR_EXPIRY_HOURS.get(staff.staff_type, 720)
    if expires_in_hours > max_hours:
        raise BusinessError(
            code="auth.expiry_exceeded",
            message=f"有効期限は最大 {max_hours} 時間です。",
            details={
                "max_hours": max_hours,
                "requested_hours": expires_in_hours,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return QRToken.objects.create(
        staff=staff,
        token=QRToken.generate_token(),
        expires_at=timezone.now() + timedelta(hours=expires_in_hours),
    )


def _other_active_owner_count(store, exclude_pk):
    return (
        Staff.objects.filter(store=store, role="owner", is_active=True)
        .exclude(pk=exclude_pk)
        .count()
    )


class StaffListView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, ListView):
    template_name = "ui/owner/staff_list.html"
    context_object_name = "staff_list"
    login_url = "/o/login/"

    def get_queryset(self):
        return Staff.objects.filter(store=self.store, is_active=True).order_by(
            "display_name"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_sidebar"] = "staff"
        return context


class StaffCreateView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    template_name = "ui/owner/staff_create.html"
    login_url = "/o/login/"

    def get(self, request):
        return render(
            request,
            self.template_name,
            {
                "form": StaffCreateForm(),
                "active_sidebar": "staff",
            },
        )

    def post(self, request):
        form = StaffCreateForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {
                    "form": form,
                    "active_sidebar": "staff",
                },
            )

        staff = Staff.objects.create_user(
            store=self.store,
            display_name=form.cleaned_data["display_name"],
            email=form.cleaned_data["email"],
            role=form.cleaned_data["role"],
            staff_type=form.cleaned_data["staff_type"],
        )

        expires_hours = QR_EXPIRY_HOURS[staff.staff_type]
        _issue_qr_token(staff, expires_in_hours=expires_hours)

        return redirect("owner:staff-detail", pk=staff.pk)


class StaffDetailView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    template_name = "ui/owner/staff_detail.html"
    login_url = "/o/login/"

    def get_staff(self):
        return get_object_or_404(
            Staff, pk=self.kwargs["pk"], store=self.store, is_active=True
        )

    def get(self, request, pk):
        staff = self.get_staff()
        latest_qr = (
            QRToken.objects.filter(staff=staff).order_by("-created_at").first()
        )
        qr_url = (
            StaffDetailView._build_qr_url(staff, latest_qr) if latest_qr else None
        )
        qr_image = (
            generate_qr_data_uri(request.build_absolute_uri(qr_url))
            if qr_url
            else None
        )

        return render(
            request,
            self.template_name,
            {
                "staff": staff,
                "latest_qr_token": latest_qr,
                "qr_url": qr_url,
                "qr_image": qr_image,
                "active_sidebar": "staff",
            },
        )

    @staticmethod
    def _build_qr_url(staff, qr_token):
        prefix = "/o/login/" if staff.role == "owner" else "/s/login/"
        return f"{prefix}#token={qr_token.token}"


class StaffEditView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    template_name = "ui/owner/staff_edit.html"
    login_url = "/o/login/"

    def _get_staff(self):
        return get_object_or_404(
            Staff, pk=self.kwargs["pk"], store=self.store, is_active=True
        )

    def _render(self, request, form, staff):
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "staff": staff,
                "active_sidebar": "staff",
            },
        )

    def get(self, request, pk):
        staff = self._get_staff()
        form = StaffEditForm(
            initial={
                "display_name": staff.display_name,
                "email": staff.email or "",
            }
        )
        return self._render(request, form, staff)

    def post(self, request, pk):
        staff = self._get_staff()
        form = StaffEditForm(request.POST)
        if not form.is_valid():
            return self._render(request, form, staff)

        staff.display_name = form.cleaned_data["display_name"]
        staff.email = form.cleaned_data["email"] or ""
        staff.save(update_fields=["display_name", "email"])
        return redirect(reverse("owner:staff-detail", kwargs={"pk": staff.pk}))


class StaffQRIssueView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    """HTMX POST: QR 再発行 → QR セクション HTML フラグメントを返す。"""

    login_url = "/o/login/"

    def post(self, request, pk):
        staff = get_object_or_404(
            Staff, pk=pk, store=self.store, is_active=True
        )
        expires_hours = QR_EXPIRY_HOURS[staff.staff_type]
        qr_token = _issue_qr_token(staff, expires_in_hours=expires_hours)
        qr_url = StaffDetailView._build_qr_url(staff, qr_token)
        qr_image = generate_qr_data_uri(request.build_absolute_uri(qr_url))

        return render(
            request,
            "ui/owner/_qr_section.html",
            {
                "latest_qr_token": qr_token,
                "qr_url": qr_url,
                "qr_image": qr_image,
                "staff": staff,
            },
        )


class StaffQREmailView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    """HTMX POST: QR をメール送信 → ステータスフラグメントを返す。"""

    login_url = "/o/login/"

    def post(self, request, pk):
        staff = get_object_or_404(
            Staff, pk=pk, store=self.store, is_active=True
        )
        if not (staff.email or "").strip():
            return render(
                request,
                "ui/owner/_qr_email_status.html",
                {
                    "success": False,
                    "message": "メールアドレスが未設定です",
                },
                status=400,
            )

        qr_token = (
            QRToken.objects.filter(
                staff=staff,
                is_used=False,
                expires_at__gt=timezone.now(),
            )
            .order_by("-created_at")
            .first()
        )
        if qr_token is None:
            expires_hours = QR_EXPIRY_HOURS[staff.staff_type]
            qr_token = _issue_qr_token(staff, expires_in_hours=expires_hours)

        qr_url = StaffDetailView._build_qr_url(staff, qr_token)
        absolute_url = request.build_absolute_uri(qr_url)
        expires_str = date_filter(qr_token.expires_at, "Y/m/d H:i")

        try:
            data_uri = generate_qr_data_uri(absolute_url)
            png_bytes = _png_bytes_from_qr_data_uri(data_uri)
        except Exception:
            return render(
                request,
                "ui/owner/_qr_email_status.html",
                {
                    "success": False,
                    "message": "メール送信に失敗しました",
                },
            )

        text_body = (
            "QR ログインコード\n\n"
            "以下の URL からログインできます:\n"
            f"{absolute_url}\n\n"
            f"有効期限: {expires_str}\n"
        )
        safe_url = escape(absolute_url)
        html_body = (
            "<h2>QR ログインコード</h2>"
            "<p>以下の QR コードをスキャンしてログインしてください:</p>"
            '<img src="cid:qr-code" alt="QR コード" width="200" height="200">'
            f'<p>URL: <a href="{safe_url}">{safe_url}</a></p>'
            f"<p>有効期限: {escape(expires_str)}</p>"
        )

        msg = EmailMultiAlternatives(
            subject="【シーシャ CRM】QR ログインコード",
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[staff.email.strip()],
        )
        msg.attach_alternative(html_body, "text/html")
        image = MIMEImage(png_bytes)
        image.add_header("Content-ID", "<qr-code>")
        image.add_header("Content-Disposition", "inline", filename="qr-code.png")
        msg.attach(image)

        try:
            msg.send()
        except Exception:
            return render(
                request,
                "ui/owner/_qr_email_status.html",
                {
                    "success": False,
                    "message": "メール送信に失敗しました",
                },
            )

        return render(
            request,
            "ui/owner/_qr_email_status.html",
            {
                "success": True,
                "message": "メールを送信しました",
            },
        )


class StaffDeactivateView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    login_url = "/o/login/"

    def post(self, request, pk):
        staff = get_object_or_404(
            Staff, pk=pk, store=self.store, is_active=True
        )

        def _render_detail_with_error(error_msg):
            latest_qr = (
                QRToken.objects.filter(staff=staff).order_by("-created_at").first()
            )
            qr_url = (
                StaffDetailView._build_qr_url(staff, latest_qr)
                if latest_qr
                else None
            )
            qr_image = (
                generate_qr_data_uri(request.build_absolute_uri(qr_url))
                if qr_url
                else None
            )
            return render(
                request,
                "ui/owner/staff_detail.html",
                {
                    "staff": staff,
                    "latest_qr_token": latest_qr,
                    "qr_url": qr_url,
                    "qr_image": qr_image,
                    "error": error_msg,
                    "active_sidebar": "staff",
                },
            )

        if staff.pk == request.user.pk:
            return _render_detail_with_error("自分自身を無効化することはできません")

        if staff.role == "owner" and _other_active_owner_count(
            self.store, staff.pk
        ) == 0:
            return _render_detail_with_error("最後のオーナーは無効化できません")

        staff.is_active = False
        staff.save(update_fields=["is_active"])
        return redirect("owner:staff-list")
