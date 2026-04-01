from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView

from core.exceptions import BusinessError
from imports.models import CsvImport, CsvImportRow
from imports.services import ImportService

from ui.mixins import OwnerRequiredMixin, StoreMixin
from ui.owner.forms.csv_import import CsvUploadForm


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
        context["matching_enabled"] = False

        toast = self.request.session.pop("toast", None)
        if toast:
            context["toast"] = toast

        return context
