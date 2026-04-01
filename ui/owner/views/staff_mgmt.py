from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import ListView
from rest_framework import status

from accounts.models import QRToken, Staff
from accounts.services import QRAuthService
from core.exceptions import BusinessError

from ui.mixins import OwnerRequiredMixin, StoreMixin
from ui.owner.forms.staff import StaffCreateForm

QR_EXPIRY_HOURS = {
    "temporary": 8,
    "regular": 720,
    "owner": 720,
}


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

        return render(
            request,
            self.template_name,
            {
                "staff": staff,
                "latest_qr_token": latest_qr,
                "qr_url": qr_url,
                "active_sidebar": "staff",
            },
        )

    @staticmethod
    def _build_qr_url(staff, qr_token):
        prefix = "/o/login/" if staff.role == "owner" else "/s/login/"
        return f"{prefix}#token={qr_token.token}"


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

        return render(
            request,
            "ui/owner/_qr_section.html",
            {
                "latest_qr_token": qr_token,
                "qr_url": qr_url,
                "staff": staff,
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
            return render(
                request,
                "ui/owner/staff_detail.html",
                {
                    "staff": staff,
                    "latest_qr_token": latest_qr,
                    "qr_url": qr_url,
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
