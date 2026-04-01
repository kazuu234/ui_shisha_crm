import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseBadRequest, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView

from core.exceptions import BusinessError
from imports.models import CsvImport, CsvImportRow
from imports.services import ImportService, MatchingService

from ui.mixins import OwnerRequiredMixin, StoreMixin
from ui.owner.forms.csv_import import CsvUploadForm, MatchingConfirmForm

ERROR_MESSAGES = {
    "import.row_not_pending": "この明細は既に処理されています",
    "import.row_already_processed": "この明細は既に処理されています",
    "import.direct_confirm_reject": "この明細はまだマッチング未実行です",
    "import.visit_not_in_candidates": "選択した候補は無効です。再読み込みしてください",
    "import.row_conflict": "他のユーザーが先に処理しました",
}


class CsvUploadView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    """CSV アップロード画面。アップロードフォーム + 過去インポート履歴を表示する。"""

    template_name = "ui/owner/csv_upload.html"
    login_url = "/o/login/"

    def _get_recent_imports(self):
        return CsvImport.objects.for_store(self.store).order_by("-created_at")[:10]

    def get(self, request):
        form = CsvUploadForm()
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "recent_imports": self._get_recent_imports(),
                "active_sidebar": "imports",
            },
        )

    def post(self, request):
        form = CsvUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {
                    "form": form,
                    "recent_imports": self._get_recent_imports(),
                    "active_sidebar": "imports",
                },
            )

        csv_file = form.cleaned_data["file"]

        try:
            csv_import = ImportService.upload_csv(csv_file, self.store, request=request)
        except BusinessError as e:
            form.add_error(None, self._error_message(e))
            return render(
                request,
                self.template_name,
                {
                    "form": form,
                    "recent_imports": self._get_recent_imports(),
                    "active_sidebar": "imports",
                },
            )

        if csv_import.row_count == 0:
            toast_message = "アップロード完了（0件: 全て重複スキップ）"
        else:
            toast_message = f"CSV をインポートしました（{csv_import.row_count} 件）"

        request.session["toast"] = {
            "message": toast_message,
            "type": "success",
        }
        return redirect(
            reverse("owner:csv-import-rows", kwargs={"pk": csv_import.pk})
        )

    @staticmethod
    def _error_message(error):
        messages = {
            "import.invalid_header": (
                "CSV のヘッダーが不正です。「取引No」と「来店日」列が必要です。"
            ),
            "import.all_groups_invalid": (
                "CSV の全データが不正です。日付フォーマットや取引No を確認してください。"
            ),
        }
        return messages.get(error.business_code, f"インポートに失敗しました: {error.detail}")


class CsvImportRowListView(
    LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, DetailView
):
    """インポート行一覧画面。CsvImport の詳細 + 配下の CsvImportRow 一覧を表示する。"""

    template_name = "ui/owner/csv_import_rows.html"
    context_object_name = "csv_import"
    login_url = "/o/login/"

    def get_object(self):
        return get_object_or_404(
            CsvImport.objects.for_store(self.store),
            pk=self.kwargs["pk"],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        csv_import = self.object

        rows = (
            CsvImportRow.objects.for_store(self.store)
            .filter(csv_import=csv_import)
            .select_related("matched_visit__customer")
            .order_by("row_number")
        )

        context["rows"] = rows
        context["active_sidebar"] = "imports"
        context["matching_enabled"] = True

        toast = self.request.session.pop("toast", None)
        if toast:
            context["toast"] = toast

        return context


class MatchingExecuteView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    """マッチング実行トリガー。POST でマッチングを実行し、マッチング管理画面にリダイレクトする。"""

    login_url = "/o/login/"

    def post(self, request, pk):
        csv_import = get_object_or_404(
            CsvImport.objects.for_store(self.store),
            pk=pk,
        )
        if csv_import.status != CsvImport.STATUS_COMPLETED:
            request.session["toast"] = {
                "message": "マッチングを実行できません",
                "type": "error",
            }
            return redirect(
                reverse("owner:csv-import-rows", kwargs={"pk": csv_import.pk})
            )
        try:
            result = MatchingService.run_matching(
                csv_import, self.store, request=request
            )
        except BusinessError:
            request.session["toast"] = {
                "message": "マッチングを実行できません",
                "type": "error",
            }
            return redirect(
                reverse("owner:csv-import-rows", kwargs={"pk": csv_import.pk})
            )

        summary_parts = []
        if result["auto_confirmed_count"] > 0:
            summary_parts.append(f"自動確定 {result['auto_confirmed_count']} 件")
        if result["pending_review_count"] > 0:
            summary_parts.append(f"レビュー待ち {result['pending_review_count']} 件")
        if result["no_candidate_count"] > 0:
            summary_parts.append(f"候補なし {result['no_candidate_count']} 件")
        if result["already_processed_count"] > 0:
            summary_parts.append(
                f"処理済みスキップ {result['already_processed_count']} 件"
            )

        request.session["toast"] = {
            "message": (
                f"マッチング完了: {', '.join(summary_parts)}"
                if summary_parts
                else "マッチング完了: 処理対象なし"
            ),
            "type": "success",
        }
        return redirect(
            reverse("owner:matching-manage", kwargs={"pk": csv_import.pk})
        )


class MatchingManageView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, DetailView):
    """マッチング管理画面。pending_review の行一覧を表示する。"""

    template_name = "ui/owner/csv_import_matching.html"
    context_object_name = "csv_import"
    login_url = "/o/login/"

    def get_object(self):
        return get_object_or_404(
            CsvImport.objects.for_store(self.store),
            pk=self.kwargs["pk"],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        csv_import = self.object
        rows = list(
            CsvImportRow.objects.for_store(self.store)
            .filter(
                csv_import=csv_import,
                status=CsvImportRow.STATUS_PENDING_REVIEW,
            )
            .order_by("row_number")
        )
        for row in rows:
            nd = row.normalized_data or {}
            row.csv_customer_name = nd.get("customer_name")
            row.csv_customer_number = nd.get("customer_number")
        context["rows"] = rows
        context["active_sidebar"] = "imports"
        toast = self.request.session.pop("toast", None)
        if toast:
            context["toast"] = toast
        return context


class MatchingCandidatesView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    """HTMX GET: 候補一覧を遅延ロードする。"""

    login_url = "/o/login/"

    def get(self, request, pk, row_id):
        row = get_object_or_404(
            CsvImportRow.objects.for_store(self.store).filter(csv_import_id=pk),
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
            "ui/owner/_matching_candidates.html",
            {
                "candidates": candidates,
                "csv_import_id": str(pk),
                "row_id": str(row.pk),
            },
        )


class MatchingConfirmView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    """HTMX PATCH: 候補を確定する。"""

    login_url = "/o/login/"

    def patch(self, request, pk, row_id):
        row = get_object_or_404(
            CsvImportRow.objects.for_store(self.store).filter(csv_import_id=pk),
            pk=row_id,
        )
        data = QueryDict(request.body)
        form = MatchingConfirmForm(data)
        if not form.is_valid():
            return HttpResponseBadRequest("無効なリクエストです")
        visit_id = form.cleaned_data["visit_id"]
        try:
            MatchingService.confirm_row(
                row, visit_id, self.store, request=request
            )
        except BusinessError as e:
            message = ERROR_MESSAGES.get(e.business_code, "確定に失敗しました")
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


class MatchingRejectView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    """HTMX PATCH: 明細を却下する。"""

    login_url = "/o/login/"

    def patch(self, request, pk, row_id):
        row = get_object_or_404(
            CsvImportRow.objects.for_store(self.store).filter(csv_import_id=pk),
            pk=row_id,
        )
        try:
            MatchingService.reject_row(row, self.store, request=request)
        except BusinessError as e:
            message = ERROR_MESSAGES.get(e.business_code, "却下に失敗しました")
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
