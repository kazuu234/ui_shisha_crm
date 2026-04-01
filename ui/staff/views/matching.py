import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseBadRequest, QueryDict
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from core.exceptions import BusinessError
from imports.models import CsvImportRow
from imports.services import MatchingService

from ui.mixins import StaffRequiredMixin, StoreMixin
from ui.staff.forms.matching import MatchingConfirmForm

ERROR_MESSAGES = {
    "import.row_not_pending": "この明細は既に処理されています",
    "import.row_already_processed": "この明細は既に処理されています",
    "import.direct_confirm_reject": "この明細はまだマッチング未実行です",
    "import.visit_not_in_candidates": "選択した候補は無効です。再読み込みしてください",
    "import.row_conflict": "他のスタッフが先に処理しました",
}


class MatchingView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, TemplateView):
    """会計後マッチング一覧画面。当日の pending_review CsvImportRow を表示する。"""

    template_name = "ui/staff/matching.html"
    login_url = "/s/login/"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()

        rows = (
            CsvImportRow.objects.for_store(self.store)
            .filter(
                status=CsvImportRow.STATUS_PENDING_REVIEW,
                business_date=today,
            )
            .select_related("csv_import")
            .order_by("receipt_no")
        )

        for row in rows:
            row.csv_customer_name = (row.normalized_data or {}).get("customer_name")

        context["rows"] = rows
        context["active_tab"] = "matching"
        return context


class MatchingCandidatesView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, View):
    """HTMX GET: 候補一覧を遅延ロードする。"""

    login_url = "/s/login/"

    def get(self, request, row_id):
        row = get_object_or_404(
            CsvImportRow.objects.for_store(self.store),
            pk=row_id,
        )

        if row.status != CsvImportRow.STATUS_PENDING_REVIEW:
            return HttpResponseBadRequest("候補を取得できません")

        try:
            raw_candidates = MatchingService.get_candidates(row, self.store)
        except BusinessError:
            return HttpResponseBadRequest("候補を取得できません")

        candidates = []
        for c in raw_candidates:
            candidates.append(
                {
                    "visit_id": c["visit_id"],
                    "customer_name": c["customer"]["name"],
                    "customer_id": c["customer"]["id"],
                    "visited_at": c["visited_at"],
                    "name_match_score": c["name_match_score"],
                }
            )

        return render(
            request,
            "ui/staff/_matching_candidates.html",
            {
                "candidates": candidates,
                "row_id": str(row.pk),
            },
        )


class MatchingConfirmView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, View):
    """HTMX PATCH: 候補を確定する。"""

    login_url = "/s/login/"

    def patch(self, request, row_id):
        row = get_object_or_404(
            CsvImportRow.objects.for_store(self.store),
            pk=row_id,
        )

        data = QueryDict(request.body)
        form = MatchingConfirmForm(data)

        if not form.is_valid():
            return HttpResponseBadRequest("無効なリクエストです")

        visit_id = form.cleaned_data["visit_id"]

        try:
            MatchingService.confirm_row(row, visit_id, self.store, request=request)
        except BusinessError as e:
            message = ERROR_MESSAGES.get(
                e.business_code,
                "確定に失敗しました",
            )
            response = HttpResponse(status=422)
            response["HX-Trigger"] = json.dumps(
                {"showToast": {"message": message, "type": "error"}}
            )
            response["HX-Reswap"] = "none"
            return response

        response = HttpResponse("")
        response["HX-Trigger"] = json.dumps(
            {"showToast": {"message": "確定しました", "type": "success"}}
        )
        return response


class MatchingRejectView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, View):
    """HTMX PATCH: 明細を却下する。"""

    login_url = "/s/login/"

    def patch(self, request, row_id):
        row = get_object_or_404(
            CsvImportRow.objects.for_store(self.store),
            pk=row_id,
        )

        try:
            MatchingService.reject_row(row, self.store, request=request)
        except BusinessError as e:
            message = ERROR_MESSAGES.get(
                e.business_code,
                "却下に失敗しました",
            )
            response = HttpResponse(status=422)
            response["HX-Trigger"] = json.dumps(
                {"showToast": {"message": message, "type": "error"}}
            )
            response["HX-Reswap"] = "none"
            return response

        response = HttpResponse("")
        response["HX-Trigger"] = json.dumps(
            {"showToast": {"message": "却下しました", "type": "success"}}
        )
        return response
