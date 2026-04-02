from datetime import date, timedelta
from unittest.mock import patch
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Staff
from core.exceptions import BusinessError
from customers.models import Customer
from imports.models import CsvImport, CsvImportRow
from tenants.models import Store, StoreGroup
from visits.models import Visit


class OwnerCsvImportViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store_group = StoreGroup.objects.create(name="Owner CSV Import Group")
        cls.store = Store.objects.create(
            store_group=cls.store_group, name="CSV Import Store"
        )
        cls.other_store = Store.objects.create(
            store_group=cls.store_group, name="CSV Import Other"
        )

    def setUp(self):
        self.owner = Staff.objects.create_user(
            store=self.store,
            display_name="CSV Owner",
            role="owner",
            staff_type="owner",
        )
        self.staff = Staff.objects.create_user(
            store=self.store,
            display_name="CSV Staff",
            role="staff",
            staff_type="regular",
        )
        self.client.force_login(self.owner)

    # --- CSV upload GET / auth / sidebar (#1–#9) ---

    def test_csv_upload_get(self):
        response = self.client.get(reverse("owner:csv-upload"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/owner/csv_upload.html")

    def test_csv_upload_requires_auth(self):
        self.client.logout()
        response = self.client.get(reverse("owner:csv-upload"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/o/login/"))

    def test_csv_upload_requires_owner(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("owner:csv-upload"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/customers/")

    def test_csv_upload_active_sidebar(self):
        response = self.client.get(reverse("owner:csv-upload"))
        self.assertEqual(response.context["active_sidebar"], "imports")

    def test_csv_upload_shows_form(self):
        response = self.client.get(reverse("owner:csv-upload"))
        self.assertContains(response, 'type="file"')
        self.assertContains(response, "アップロード")

    def test_csv_upload_shows_recent_imports(self):
        CsvImport.objects.create(
            store=self.store,
            file_name="a.csv",
            status=CsvImport.STATUS_COMPLETED,
            row_count=1,
        )
        response = self.client.get(reverse("owner:csv-upload"))
        self.assertContains(response, "a.csv")

    def test_csv_upload_recent_imports_limit_10(self):
        for i in range(11):
            CsvImport.objects.create(
                store=self.store,
                file_name=f"f{i}.csv",
                status=CsvImport.STATUS_COMPLETED,
                row_count=1,
            )
        response = self.client.get(reverse("owner:csv-upload"))
        self.assertContains(response, "f10.csv")
        self.assertNotContains(response, "f0.csv")

    def test_csv_upload_recent_imports_order(self):
        older = CsvImport.objects.create(
            store=self.store,
            file_name="older.csv",
            status=CsvImport.STATUS_COMPLETED,
            row_count=1,
        )
        newer = CsvImport.objects.create(
            store=self.store,
            file_name="newer.csv",
            status=CsvImport.STATUS_COMPLETED,
            row_count=1,
        )
        t_old = timezone.now() - timedelta(days=2)
        t_new = timezone.now() - timedelta(days=1)
        CsvImport.objects.filter(pk=older.pk).update(created_at=t_old)
        CsvImport.objects.filter(pk=newer.pk).update(created_at=t_new)
        response = self.client.get(reverse("owner:csv-upload"))
        content = response.content.decode()
        self.assertLess(content.find("newer.csv"), content.find("older.csv"))

    def test_csv_upload_recent_imports_store_scope(self):
        CsvImport.objects.create(
            store=self.other_store,
            file_name="other.csv",
            status=CsvImport.STATUS_COMPLETED,
            row_count=1,
        )
        response = self.client.get(reverse("owner:csv-upload"))
        self.assertNotContains(response, "other.csv")

    # --- CSV upload POST (#10–#16c) ---

    @patch("ui.owner.views.csv_import.ImportService.upload_csv")
    def test_csv_upload_post_success(self, mock_upload):
        imp = CsvImport.objects.create(
            store=self.store,
            file_name="ok.csv",
            status=CsvImport.STATUS_COMPLETED,
            row_count=3,
        )
        mock_upload.return_value = imp
        f = SimpleUploadedFile("ok.csv", b"a,b\n", content_type="text/csv")
        response = self.client.post(reverse("owner:csv-upload"), {"file": f})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("owner:csv-import-rows", kwargs={"pk": imp.pk}),
        )
        self.assertEqual(
            self.client.session.get("toast"),
            {"message": "CSV をインポートしました（3 件）", "type": "success"},
        )
        mock_upload.assert_called_once()

    @patch("ui.owner.views.csv_import.ImportService.upload_csv")
    def test_csv_upload_post_invalid_header(self, mock_upload):
        mock_upload.side_effect = BusinessError(
            code="import.invalid_header",
            message="bad",
            status_code=400,
        )
        f = SimpleUploadedFile("x.csv", b"a,b\n", content_type="text/csv")
        response = self.client.post(reverse("owner:csv-upload"), {"file": f})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ヘッダーが不正")

    @patch("ui.owner.views.csv_import.ImportService.upload_csv")
    def test_csv_upload_post_all_groups_invalid(self, mock_upload):
        mock_upload.side_effect = BusinessError(
            code="import.all_groups_invalid",
            message="bad",
            status_code=400,
        )
        f = SimpleUploadedFile("x.csv", b"a,b\n", content_type="text/csv")
        response = self.client.post(reverse("owner:csv-upload"), {"file": f})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "全データが不正")

    def test_csv_upload_post_no_file(self):
        response = self.client.post(reverse("owner:csv-upload"), {})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("file"))

    def test_csv_upload_post_non_csv(self):
        f = SimpleUploadedFile("x.txt", b"hello", content_type="text/plain")
        response = self.client.post(reverse("owner:csv-upload"), {"file": f})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("file"))

    def test_csv_upload_post_oversized(self):
        f = SimpleUploadedFile("big.csv", b"name\na", content_type="text/csv")
        f.size = 10 * 1024 * 1024 + 1  # 実際にはメモリを使わない
        response = self.client.post(reverse("owner:csv-upload"), {"file": f})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("file"))

    @patch("ui.owner.views.csv_import.ImportService.upload_csv")
    def test_csv_upload_toast_message(self, mock_upload):
        imp = CsvImport.objects.create(
            store=self.store,
            file_name="t.csv",
            status=CsvImport.STATUS_COMPLETED,
            row_count=5,
        )
        mock_upload.return_value = imp
        f = SimpleUploadedFile("t.csv", b"x", content_type="text/csv")
        self.client.post(reverse("owner:csv-upload"), {"file": f})
        self.assertEqual(
            self.client.session.get("toast", {}).get("message"),
            "CSV をインポートしました（5 件）",
        )

    @patch("ui.owner.views.csv_import.ImportService.upload_csv")
    def test_csv_upload_post_all_duplicates(self, mock_upload):
        imp = CsvImport.objects.create(
            store=self.store,
            file_name="d.csv",
            status=CsvImport.STATUS_COMPLETED,
            row_count=0,
        )
        mock_upload.return_value = imp
        f = SimpleUploadedFile("d.csv", b"x", content_type="text/csv")
        response = self.client.post(reverse("owner:csv-upload"), {"file": f})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.client.session.get("toast"),
            {
                "message": "アップロード完了（0件: 全て重複スキップ）",
                "type": "success",
            },
        )

    @patch("ui.owner.views.csv_import.ImportService.upload_csv")
    def test_csv_upload_all_duplicates_redirect_to_rows(self, mock_upload):
        imp = CsvImport.objects.create(
            store=self.store,
            file_name="empty.csv",
            status=CsvImport.STATUS_COMPLETED,
            row_count=0,
        )
        mock_upload.return_value = imp
        f = SimpleUploadedFile("empty.csv", b"x", content_type="text/csv")
        response = self.client.post(
            reverse("owner:csv-upload"), {"file": f}, follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "インポートデータがありません")

    def test_csv_upload_failed_import_in_history(self):
        CsvImport.objects.create(
            store=self.store,
            file_name="bad.csv",
            status=CsvImport.STATUS_FAILED,
            row_count=0,
        )
        response = self.client.get(reverse("owner:csv-upload"))
        self.assertContains(response, "bad.csv")
        self.assertContains(response, "badge-rejected")

    # --- Row list (#17–#31b) ---

    def test_csv_import_rows_get(self):
        imp = CsvImport.objects.create(
            store=self.store,
            file_name="r.csv",
            status=CsvImport.STATUS_COMPLETED,
            row_count=0,
        )
        response = self.client.get(
            reverse("owner:csv-import-rows", kwargs={"pk": imp.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/owner/csv_import_rows.html")

    def test_csv_import_rows_requires_auth(self):
        imp = CsvImport.objects.create(
            store=self.store,
            file_name="r.csv",
            status=CsvImport.STATUS_COMPLETED,
            row_count=0,
        )
        self.client.logout()
        response = self.client.get(
            reverse("owner:csv-import-rows", kwargs={"pk": imp.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/o/login/"))

    def test_csv_import_rows_requires_owner(self):
        imp = CsvImport.objects.create(
            store=self.store,
            file_name="r.csv",
            status=CsvImport.STATUS_COMPLETED,
            row_count=0,
        )
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("owner:csv-import-rows", kwargs={"pk": imp.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/customers/")

    def test_csv_import_rows_store_scope(self):
        imp = CsvImport.objects.create(
            store=self.other_store,
            file_name="other.csv",
            status=CsvImport.STATUS_COMPLETED,
            row_count=0,
        )
        response = self.client.get(
            reverse("owner:csv-import-rows", kwargs={"pk": imp.pk})
        )
        self.assertEqual(response.status_code, 404)

    def test_csv_import_rows_nonexistent(self):
        response = self.client.get(
            reverse("owner:csv-import-rows", kwargs={"pk": uuid4()})
        )
        self.assertEqual(response.status_code, 404)

    def test_csv_import_rows_active_sidebar(self):
        imp = CsvImport.objects.create(
            store=self.store,
            file_name="r.csv",
            status=CsvImport.STATUS_COMPLETED,
            row_count=0,
        )
        response = self.client.get(
            reverse("owner:csv-import-rows", kwargs={"pk": imp.pk})
        )
        self.assertEqual(response.context["active_sidebar"], "imports")

    def test_csv_import_rows_displays_columns(self):
        imp = CsvImport.objects.create(
            store=self.store,
            file_name="r.csv",
            status=CsvImport.STATUS_COMPLETED,
            row_count=1,
        )
        CsvImportRow.objects.create(
            store=self.store,
            csv_import=imp,
            row_number=1,
            receipt_no="001",
            business_date=date(2026, 1, 1),
            idempotency_key="key-col-1",
            raw_data={},
            normalized_data={},
            status=CsvImportRow.STATUS_VALIDATED,
        )
        response = self.client.get(
            reverse("owner:csv-import-rows", kwargs={"pk": imp.pk})
        )
        for label in ("行番号", "営業日", "レシート番号", "ステータス", "マッチ先"):
            self.assertContains(response, label)

    def test_csv_import_rows_order_by_row_number(self):
        imp = CsvImport.objects.create(
            store=self.store,
            file_name="r.csv",
            status=CsvImport.STATUS_COMPLETED,
            row_count=3,
        )
        for n, key in ((3, "k3"), (1, "k1"), (2, "k2")):
            CsvImportRow.objects.create(
                store=self.store,
                csv_import=imp,
                row_number=n,
                receipt_no=f"0{n}",
                business_date=date(2026, 1, n),
                idempotency_key=key,
                raw_data={},
                normalized_data={},
                status=CsvImportRow.STATUS_VALIDATED,
            )
        response = self.client.get(
            reverse("owner:csv-import-rows", kwargs={"pk": imp.pk})
        )
        content = response.content.decode()
        # row_number 昇順 → receipt_no 01, 02, 03
        p01 = content.find(">01<")
        p02 = content.find(">02<")
        p03 = content.find(">03<")
        self.assertLess(p01, p02)
        self.assertLess(p02, p03)

    def test_csv_import_rows_status_badge(self):
        imp = CsvImport.objects.create(
            store=self.store,
            file_name="r.csv",
            status=CsvImport.STATUS_COMPLETED,
            row_count=4,
        )
        specs = [
            (1, "k1", CsvImportRow.STATUS_VALIDATED),
            (2, "k2", CsvImportRow.STATUS_PENDING_REVIEW),
            (3, "k3", CsvImportRow.STATUS_CONFIRMED),
            (4, "k4", CsvImportRow.STATUS_REJECTED),
        ]
        for n, key, st in specs:
            CsvImportRow.objects.create(
                store=self.store,
                csv_import=imp,
                row_number=n,
                receipt_no=str(n),
                business_date=date(2026, 1, 1),
                idempotency_key=key,
                raw_data={},
                normalized_data={},
                status=st,
            )
        response = self.client.get(
            reverse("owner:csv-import-rows", kwargs={"pk": imp.pk})
        )
        self.assertContains(response, "bg-accent-subtle text-accent")
        self.assertContains(response, "bg-warning-subtle text-warning-dark")
        self.assertContains(response, "bg-success-subtle text-success")
        self.assertContains(response, "bg-error-subtle text-error")

    def test_csv_import_rows_matched_visit_customer_name(self):
        imp = CsvImport.objects.create(
            store=self.store,
            file_name="r.csv",
            status=CsvImport.STATUS_COMPLETED,
            row_count=1,
        )
        cust = Customer.objects.create(store=self.store, name="マッチ太郎")
        visit = Visit.objects.create(
            store=self.store,
            customer=cust,
            staff=self.owner,
            visited_at=date(2026, 1, 1),
        )
        CsvImportRow.objects.create(
            store=self.store,
            csv_import=imp,
            row_number=1,
            receipt_no="001",
            business_date=date(2026, 1, 1),
            idempotency_key="km",
            raw_data={},
            normalized_data={},
            status=CsvImportRow.STATUS_CONFIRMED,
            matched_visit=visit,
        )
        response = self.client.get(
            reverse("owner:csv-import-rows", kwargs={"pk": imp.pk})
        )
        self.assertContains(response, "マッチ太郎")

    def test_csv_import_rows_no_match_dash(self):
        imp = CsvImport.objects.create(
            store=self.store,
            file_name="r.csv",
            status=CsvImport.STATUS_COMPLETED,
            row_count=1,
        )
        CsvImportRow.objects.create(
            store=self.store,
            csv_import=imp,
            row_number=1,
            receipt_no="001",
            business_date=date(2026, 1, 1),
            idempotency_key="knm",
            raw_data={},
            normalized_data={},
            status=CsvImportRow.STATUS_VALIDATED,
        )
        response = self.client.get(
            reverse("owner:csv-import-rows", kwargs={"pk": imp.pk})
        )
        self.assertContains(response, 'text-text-muted">-</span>')

    def test_csv_import_rows_toast_display(self):
        imp = CsvImport.objects.create(
            store=self.store,
            file_name="r.csv",
            status=CsvImport.STATUS_COMPLETED,
            row_count=0,
        )
        session = self.client.session
        session["toast"] = {"message": "トーストテスト", "type": "success"}
        session.save()
        response = self.client.get(
            reverse("owner:csv-import-rows", kwargs={"pk": imp.pk})
        )
        self.assertContains(response, "トーストテスト")

    def test_csv_import_rows_error_message_display(self):
        imp = CsvImport.objects.create(
            store=self.store,
            file_name="r.csv",
            status=CsvImport.STATUS_COMPLETED,
            row_count=1,
            error_message=[
                {
                    "group_id": 1,
                    "receipt_no": "001",
                    "lines": [3, 4],
                    "error": "エラー内容",
                }
            ],
        )
        response = self.client.get(
            reverse("owner:csv-import-rows", kwargs={"pk": imp.pk})
        )
        self.assertContains(response, "取引No 001")
        self.assertContains(response, "3, 4")
        self.assertContains(response, "エラー内容")

    def test_csv_import_rows_empty(self):
        imp = CsvImport.objects.create(
            store=self.store,
            file_name="r.csv",
            status=CsvImport.STATUS_COMPLETED,
            row_count=0,
        )
        response = self.client.get(
            reverse("owner:csv-import-rows", kwargs={"pk": imp.pk})
        )
        self.assertContains(response, "インポートデータがありません")

    def test_csv_import_rows_header_status_badge(self):
        imp_ok = CsvImport.objects.create(
            store=self.store,
            file_name="ok.csv",
            status=CsvImport.STATUS_COMPLETED,
            row_count=0,
        )
        r1 = self.client.get(
            reverse("owner:csv-import-rows", kwargs={"pk": imp_ok.pk})
        )
        self.assertContains(r1, "badge-confirmed")

        imp_bad = CsvImport.objects.create(
            store=self.store,
            file_name="ng.csv",
            status=CsvImport.STATUS_FAILED,
            row_count=0,
        )
        r2 = self.client.get(
            reverse("owner:csv-import-rows", kwargs={"pk": imp_bad.pk})
        )
        self.assertContains(r2, "badge-rejected")

    def test_csv_import_rows_header_filename(self):
        imp = CsvImport.objects.create(
            store=self.store,
            file_name="unique_name.csv",
            status=CsvImport.STATUS_COMPLETED,
            row_count=0,
        )
        response = self.client.get(
            reverse("owner:csv-import-rows", kwargs={"pk": imp.pk})
        )
        self.assertContains(response, "unique_name.csv")
