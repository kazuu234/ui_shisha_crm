import json
import uuid
from datetime import date
from unittest.mock import patch
from urllib.parse import urlencode

from django.test import TestCase
from django.urls import reverse

from accounts.models import Staff
from core.exceptions import BusinessError
from customers.models import Customer
from imports.models import CsvImport, CsvImportRow
from tenants.models import Store, StoreGroup
from visits.models import Visit


class OwnerMatchingViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store_group = StoreGroup.objects.create(name="Owner Matching Group")
        cls.store = Store.objects.create(
            store_group=cls.store_group, name="Matching Store"
        )
        cls.other_store = Store.objects.create(
            store_group=cls.store_group, name="Matching Other"
        )

    def setUp(self):
        self.owner = Staff.objects.create_user(
            store=self.store,
            display_name="Matching Owner",
            role="owner",
            staff_type="owner",
        )
        self.staff = Staff.objects.create_user(
            store=self.store,
            display_name="Matching Staff User",
            role="staff",
            staff_type="regular",
        )
        self.client.force_login(self.owner)

    def _csv_import(self, *, store=None, status=CsvImport.STATUS_COMPLETED):
        store = store or self.store
        return CsvImport.objects.create(
            store=store,
            file_name="m.csv",
            row_count=1,
            status=status,
            error_message=[],
        )

    def _row(
        self,
        csv_import,
        *,
        row_number=1,
        receipt_no="001",
        business_date=None,
        status=CsvImportRow.STATUS_PENDING_REVIEW,
        normalized_data=None,
        store=None,
    ):
        store = store or self.store
        business_date = business_date or date(2026, 1, 15)
        key = f"{store.id}_{csv_import.id}_{row_number}_{receipt_no}"
        return CsvImportRow.objects.create(
            store=store,
            csv_import=csv_import,
            row_number=row_number,
            receipt_no=receipt_no,
            business_date=business_date,
            idempotency_key=key,
            raw_data={},
            normalized_data=normalized_data if normalized_data is not None else {},
            status=status,
        )

    def _patch_confirm(self, imp_pk, row_pk, visit_id):
        body = urlencode({"visit_id": str(visit_id)})
        return self.client.generic(
            "PATCH",
            reverse(
                "owner:matching-confirm",
                kwargs={"pk": imp_pk, "row_id": row_pk},
            ),
            data=body,
            content_type="application/x-www-form-urlencoded",
        )

    def _patch_reject(self, imp_pk, row_pk, data=None):
        return self.client.generic(
            "PATCH",
            reverse(
                "owner:matching-reject",
                kwargs={"pk": imp_pk, "row_id": row_pk},
            ),
            data=data if data is not None else "",
            content_type="application/x-www-form-urlencoded",
        )

    # --- #32–#40a マッチング実行 ---

    @patch("ui.owner.views.csv_import.MatchingService.run_matching")
    def test_matching_execute_post(self, mock_run):
        imp = self._csv_import()
        mock_run.return_value = {
            "auto_confirmed_count": 0,
            "pending_review_count": 0,
            "no_candidate_count": 0,
            "already_processed_count": 0,
        }
        response = self.client.post(
            reverse("owner:matching-execute", kwargs={"pk": imp.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("owner:matching-manage", kwargs={"pk": imp.pk}),
        )
        self.assertEqual(
            self.client.session.get("toast"),
            {"message": "マッチング完了: 処理対象なし", "type": "success"},
        )
        mock_run.assert_called_once()

    def test_matching_execute_requires_auth(self):
        imp = self._csv_import()
        self.client.logout()
        response = self.client.post(
            reverse("owner:matching-execute", kwargs={"pk": imp.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/o/login/"))

    def test_matching_execute_requires_owner(self):
        imp = self._csv_import()
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("owner:matching-execute", kwargs={"pk": imp.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/customers/")

    def test_matching_execute_store_scope(self):
        imp = self._csv_import(store=self.other_store)
        response = self.client.post(
            reverse("owner:matching-execute", kwargs={"pk": imp.pk})
        )
        self.assertEqual(response.status_code, 404)

    def test_matching_execute_nonexistent(self):
        response = self.client.post(
            reverse("owner:matching-execute", kwargs={"pk": uuid.uuid4()})
        )
        self.assertEqual(response.status_code, 404)

    def test_matching_execute_get_not_allowed(self):
        imp = self._csv_import()
        response = self.client.get(
            reverse("owner:matching-execute", kwargs={"pk": imp.pk})
        )
        self.assertEqual(response.status_code, 405)

    def test_matching_execute_not_completed(self):
        imp = self._csv_import(status=CsvImport.STATUS_FAILED)
        response = self.client.post(
            reverse("owner:matching-execute", kwargs={"pk": imp.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("owner:csv-import-rows", kwargs={"pk": imp.pk}),
        )
        self.assertEqual(
            self.client.session.get("toast"),
            {"message": "マッチングを実行できません", "type": "error"},
        )

    @patch("ui.owner.views.csv_import.MatchingService.run_matching")
    def test_matching_execute_toast_summary(self, mock_run):
        imp = self._csv_import()
        mock_run.return_value = {
            "auto_confirmed_count": 2,
            "pending_review_count": 3,
            "no_candidate_count": 1,
            "already_processed_count": 0,
        }
        self.client.post(reverse("owner:matching-execute", kwargs={"pk": imp.pk}))
        msg = self.client.session.get("toast", {}).get("message", "")
        self.assertIn("自動確定 2 件", msg)
        self.assertIn("レビュー待ち 3 件", msg)
        self.assertIn("候補なし 1 件", msg)

    @patch("ui.owner.views.csv_import.MatchingService.run_matching")
    def test_matching_execute_idempotent(self, mock_run):
        imp = self._csv_import()
        mock_run.return_value = {
            "auto_confirmed_count": 0,
            "pending_review_count": 0,
            "no_candidate_count": 0,
            "already_processed_count": 4,
        }
        self.client.post(reverse("owner:matching-execute", kwargs={"pk": imp.pk}))
        msg = self.client.session.get("toast", {}).get("message", "")
        self.assertIn("処理済みスキップ 4 件", msg)

    def test_csv_import_rows_matching_button_visible_slice2(self):
        imp = self._csv_import()
        response = self.client.get(
            reverse("owner:csv-import-rows", kwargs={"pk": imp.pk})
        )
        self.assertContains(response, "マッチング実行")

    # --- #41–#52 マッチング管理画面 ---

    def test_matching_manage_get(self):
        imp = self._csv_import()
        response = self.client.get(
            reverse("owner:matching-manage", kwargs={"pk": imp.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/owner/csv_import_matching.html")

    def test_matching_manage_requires_auth(self):
        imp = self._csv_import()
        self.client.logout()
        response = self.client.get(
            reverse("owner:matching-manage", kwargs={"pk": imp.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/o/login/"))

    def test_matching_manage_requires_owner(self):
        imp = self._csv_import()
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("owner:matching-manage", kwargs={"pk": imp.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/customers/")

    def test_matching_manage_store_scope(self):
        imp = self._csv_import(store=self.other_store)
        response = self.client.get(
            reverse("owner:matching-manage", kwargs={"pk": imp.pk})
        )
        self.assertEqual(response.status_code, 404)

    def test_matching_manage_active_sidebar(self):
        imp = self._csv_import()
        response = self.client.get(
            reverse("owner:matching-manage", kwargs={"pk": imp.pk})
        )
        self.assertEqual(response.context["active_sidebar"], "imports")

    def test_matching_manage_shows_pending_review_only(self):
        imp = self._csv_import()
        d = date(2026, 2, 1)
        self._row(imp, receipt_no="pr", status=CsvImportRow.STATUS_PENDING_REVIEW, business_date=d)
        self._row(
            imp,
            row_number=2,
            receipt_no="v",
            status=CsvImportRow.STATUS_VALIDATED,
            business_date=d,
        )
        self._row(
            imp,
            row_number=3,
            receipt_no="c",
            status=CsvImportRow.STATUS_CONFIRMED,
            business_date=d,
        )
        self._row(
            imp,
            row_number=4,
            receipt_no="r",
            status=CsvImportRow.STATUS_REJECTED,
            business_date=d,
        )
        response = self.client.get(
            reverse("owner:matching-manage", kwargs={"pk": imp.pk})
        )
        self.assertContains(response, "No.pr")
        self.assertNotContains(response, "No.v")
        self.assertNotContains(response, "No.c")
        self.assertNotContains(response, "No.r")

    def test_matching_manage_empty_message(self):
        imp = self._csv_import()
        response = self.client.get(
            reverse("owner:matching-manage", kwargs={"pk": imp.pk})
        )
        self.assertContains(response, "マッチ待ちの明細はありません")

    def test_matching_manage_displays_receipt_no(self):
        imp = self._csv_import()
        self._row(imp, receipt_no="R-88", business_date=date(2026, 3, 1))
        response = self.client.get(
            reverse("owner:matching-manage", kwargs={"pk": imp.pk})
        )
        self.assertContains(response, "No.R-88")

    def test_matching_manage_displays_csv_customer_name(self):
        imp = self._csv_import()
        self._row(
            imp,
            receipt_no="n1",
            normalized_data={"customer_name": "CSV名前"},
            business_date=date(2026, 3, 2),
        )
        response = self.client.get(
            reverse("owner:matching-manage", kwargs={"pk": imp.pk})
        )
        self.assertContains(response, "CSV 顧客名: CSV名前")

    def test_matching_manage_no_csv_customer_name(self):
        imp = self._csv_import()
        self._row(
            imp,
            receipt_no="n2",
            normalized_data={},
            business_date=date(2026, 3, 3),
        )
        response = self.client.get(
            reverse("owner:matching-manage", kwargs={"pk": imp.pk})
        )
        self.assertContains(response, "No.n2")
        self.assertNotContains(response, "CSV 顧客名:")

    def test_matching_manage_displays_csv_customer_number(self):
        imp = self._csv_import()
        self._row(
            imp,
            receipt_no="n3",
            normalized_data={"customer_number": "C-001"},
            business_date=date(2026, 3, 4),
        )
        response = self.client.get(
            reverse("owner:matching-manage", kwargs={"pk": imp.pk})
        )
        self.assertContains(response, "顧客番号: C-001")

    def test_matching_manage_no_csv_customer_number(self):
        imp = self._csv_import()
        self._row(
            imp,
            receipt_no="n4",
            normalized_data={},
            business_date=date(2026, 3, 5),
        )
        response = self.client.get(
            reverse("owner:matching-manage", kwargs={"pk": imp.pk})
        )
        self.assertNotContains(response, "顧客番号:")

    def test_matching_manage_order_by_row_number(self):
        imp = self._csv_import()
        d = date(2026, 4, 1)
        self._row(imp, row_number=3, receipt_no="03", business_date=d)
        self._row(imp, row_number=1, receipt_no="01", business_date=d)
        self._row(imp, row_number=2, receipt_no="02", business_date=d)
        response = self.client.get(
            reverse("owner:matching-manage", kwargs={"pk": imp.pk})
        )
        html = response.content.decode()
        self.assertLess(html.find("No.01"), html.find("No.02"))
        self.assertLess(html.find("No.02"), html.find("No.03"))

    def test_matching_manage_toast_display(self):
        imp = self._csv_import()
        session = self.client.session
        session["toast"] = {"message": "オーナートースト", "type": "success"}
        session.save()
        response = self.client.get(
            reverse("owner:matching-manage", kwargs={"pk": imp.pk})
        )
        self.assertContains(response, "オーナートースト")

    # --- #53–#67 候補 ---

    def test_candidates_get(self):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 5, 1))
        response = self.client.get(
            reverse(
                "owner:matching-candidates",
                kwargs={"pk": imp.pk, "row_id": row.pk},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/owner/_matching_candidates.html")

    def test_candidates_requires_auth(self):
        self.client.logout()
        response = self.client.get(
            reverse(
                "owner:matching-candidates",
                kwargs={"pk": uuid.uuid4(), "row_id": uuid.uuid4()},
            )
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/o/login/"))

    def test_candidates_requires_owner(self):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 5, 2))
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse(
                "owner:matching-candidates",
                kwargs={"pk": imp.pk, "row_id": row.pk},
            )
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/customers/")

    def test_candidates_store_scope(self):
        imp = self._csv_import(store=self.other_store)
        row = self._row(
            imp,
            store=self.other_store,
            business_date=date(2026, 5, 3),
        )
        response = self.client.get(
            reverse(
                "owner:matching-candidates",
                kwargs={"pk": imp.pk, "row_id": row.pk},
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_candidates_nonexistent_row(self):
        imp = self._csv_import()
        response = self.client.get(
            reverse(
                "owner:matching-candidates",
                kwargs={"pk": imp.pk, "row_id": uuid.uuid4()},
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_candidates_wrong_import(self):
        imp_a = self._csv_import()
        imp_b = self._csv_import()
        row = self._row(imp_b, business_date=date(2026, 5, 4))
        response = self.client.get(
            reverse(
                "owner:matching-candidates",
                kwargs={"pk": imp_a.pk, "row_id": row.pk},
            )
        )
        self.assertEqual(response.status_code, 404)

    @patch("imports.services.MatchingService.get_candidates")
    def test_candidates_displays_customer_name(self, mock_gc):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 5, 5))
        vid = uuid.uuid4()
        mock_gc.return_value = [
            {
                "visit_id": vid,
                "customer": {"id": uuid.uuid4(), "name": "候補太郎"},
                "visited_at": date(2026, 5, 5),
                "name_match_score": None,
            },
        ]
        response = self.client.get(
            reverse(
                "owner:matching-candidates",
                kwargs={"pk": imp.pk, "row_id": row.pk},
            )
        )
        self.assertContains(response, "候補太郎")

    @patch("imports.services.MatchingService.get_candidates")
    def test_candidates_displays_visited_at(self, mock_gc):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 6, 10))
        mock_gc.return_value = [
            {
                "visit_id": uuid.uuid4(),
                "customer": {"id": uuid.uuid4(), "name": "X"},
                "visited_at": date(2026, 6, 10),
                "name_match_score": None,
            },
        ]
        response = self.client.get(
            reverse(
                "owner:matching-candidates",
                kwargs={"pk": imp.pk, "row_id": row.pk},
            )
        )
        self.assertContains(response, "6/10")

    @patch("imports.services.MatchingService.get_candidates")
    def test_candidates_displays_match_score(self, mock_gc):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 6, 11))
        mock_gc.return_value = [
            {
                "visit_id": uuid.uuid4(),
                "customer": {"id": uuid.uuid4(), "name": "Full"},
                "visited_at": date(2026, 6, 11),
                "name_match_score": 1.0,
            },
            {
                "visit_id": uuid.uuid4(),
                "customer": {"id": uuid.uuid4(), "name": "Part"},
                "visited_at": date(2026, 6, 11),
                "name_match_score": 0.5,
            },
        ]
        response = self.client.get(
            reverse(
                "owner:matching-candidates",
                kwargs={"pk": imp.pk, "row_id": row.pk},
            )
        )
        self.assertContains(response, "完全一致")
        self.assertContains(response, "部分一致")

    def test_candidates_not_pending_review_validated(self):
        imp = self._csv_import()
        row = self._row(
            imp,
            status=CsvImportRow.STATUS_VALIDATED,
            business_date=date(2026, 6, 12),
        )
        response = self.client.get(
            reverse(
                "owner:matching-candidates",
                kwargs={"pk": imp.pk, "row_id": row.pk},
            )
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("候補を取得できません", response.content.decode())
        self.assertIsNone(response.headers.get("HX-Trigger"))

    def test_candidates_not_pending_review_confirmed(self):
        imp = self._csv_import()
        row = self._row(
            imp,
            status=CsvImportRow.STATUS_CONFIRMED,
            business_date=date(2026, 6, 13),
        )
        response = self.client.get(
            reverse(
                "owner:matching-candidates",
                kwargs={"pk": imp.pk, "row_id": row.pk},
            )
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("候補を取得できません", response.content.decode())
        self.assertIsNone(response.headers.get("HX-Trigger"))

    def test_candidates_not_pending_review_rejected(self):
        imp = self._csv_import()
        row = self._row(
            imp,
            status=CsvImportRow.STATUS_REJECTED,
            business_date=date(2026, 6, 14),
        )
        response = self.client.get(
            reverse(
                "owner:matching-candidates",
                kwargs={"pk": imp.pk, "row_id": row.pk},
            )
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("候補を取得できません", response.content.decode())
        self.assertIsNone(response.headers.get("HX-Trigger"))

    @patch("imports.services.MatchingService.get_candidates")
    def test_candidates_has_confirm_button(self, mock_gc):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 6, 15))
        vid = uuid.uuid4()
        mock_gc.return_value = [
            {
                "visit_id": vid,
                "customer": {"id": uuid.uuid4(), "name": "B"},
                "visited_at": date(2026, 6, 15),
                "name_match_score": None,
            },
        ]
        response = self.client.get(
            reverse(
                "owner:matching-candidates",
                kwargs={"pk": imp.pk, "row_id": row.pk},
            )
        )
        self.assertContains(response, "hx-patch")
        self.assertContains(
            response,
            f"/o/imports/{imp.pk}/rows/{row.pk}/confirm/",
        )

    @patch("imports.services.MatchingService.get_candidates")
    def test_candidates_has_reject_button(self, mock_gc):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 6, 16))
        mock_gc.return_value = []
        response = self.client.get(
            reverse(
                "owner:matching-candidates",
                kwargs={"pk": imp.pk, "row_id": row.pk},
            )
        )
        self.assertContains(response, "この明細を却下")
        self.assertContains(
            response,
            f"/o/imports/{imp.pk}/rows/{row.pk}/reject/",
        )

    @patch("imports.services.MatchingService.get_candidates")
    def test_candidates_empty(self, mock_gc):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 6, 17))
        mock_gc.return_value = []
        response = self.client.get(
            reverse(
                "owner:matching-candidates",
                kwargs={"pk": imp.pk, "row_id": row.pk},
            )
        )
        self.assertContains(response, "候補が見つかりませんでした")
        self.assertContains(response, "この明細を却下")

    @patch("imports.services.MatchingService.get_candidates")
    def test_candidates_sort_order(self, mock_gc):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 6, 18))
        mock_gc.return_value = [
            {
                "visit_id": uuid.uuid4(),
                "customer": {"id": uuid.uuid4(), "name": "AAA高スコア"},
                "visited_at": date(2026, 6, 18),
                "name_match_score": 1.0,
            },
            {
                "visit_id": uuid.uuid4(),
                "customer": {"id": uuid.uuid4(), "name": "BBB中スコア"},
                "visited_at": date(2026, 6, 18),
                "name_match_score": 0.5,
            },
            {
                "visit_id": uuid.uuid4(),
                "customer": {"id": uuid.uuid4(), "name": "CCC低スコア"},
                "visited_at": date(2026, 6, 18),
                "name_match_score": 0.0,
            },
        ]
        response = self.client.get(
            reverse(
                "owner:matching-candidates",
                kwargs={"pk": imp.pk, "row_id": row.pk},
            )
        )
        html = response.content.decode()
        self.assertLess(html.find("AAA高スコア"), html.find("BBB中スコア"))
        self.assertLess(html.find("BBB中スコア"), html.find("CCC低スコア"))

    @patch("imports.services.MatchingService.get_candidates")
    def test_candidates_flat_mapping(self, mock_gc):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 6, 19))
        cid = uuid.uuid4()
        mock_gc.return_value = [
            {
                "visit_id": uuid.uuid4(),
                "customer": {"id": cid, "name": "ネスト名"},
                "visited_at": date(2026, 6, 19),
                "name_match_score": None,
            },
        ]
        response = self.client.get(
            reverse(
                "owner:matching-candidates",
                kwargs={"pk": imp.pk, "row_id": row.pk},
            )
        )
        self.assertContains(response, "ネスト名")

    # --- #68–#82 confirm ---

    def test_confirm_patch(self):
        imp = self._csv_import()
        bd = date(2026, 7, 1)
        row = self._row(imp, business_date=bd)
        cust = Customer.objects.create(store=self.store, name="確定顧客")
        visit = Visit.objects.create(
            store=self.store,
            customer=cust,
            staff=self.owner,
            visited_at=bd,
        )
        response = self._patch_confirm(imp.pk, row.pk, visit.pk)
        self.assertEqual(response.status_code, 200)
        row.refresh_from_db()
        self.assertEqual(row.status, CsvImportRow.STATUS_CONFIRMED)

    def test_confirm_requires_auth(self):
        self.client.logout()
        response = self._patch_confirm(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/o/login/"))

    def test_confirm_requires_owner(self):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 7, 2))
        self.client.force_login(self.staff)
        response = self._patch_confirm(imp.pk, row.pk, uuid.uuid4())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/customers/")

    def test_confirm_store_scope(self):
        imp = self._csv_import(store=self.other_store)
        row = self._row(
            imp,
            store=self.other_store,
            business_date=date(2026, 7, 3),
        )
        response = self._patch_confirm(imp.pk, row.pk, uuid.uuid4())
        self.assertEqual(response.status_code, 404)

    def test_confirm_nonexistent_row(self):
        imp = self._csv_import()
        response = self._patch_confirm(imp.pk, uuid.uuid4(), uuid.uuid4())
        self.assertEqual(response.status_code, 404)

    def test_confirm_wrong_import(self):
        imp_a = self._csv_import()
        imp_b = self._csv_import()
        row = self._row(imp_b, business_date=date(2026, 7, 4))
        response = self._patch_confirm(imp_a.pk, row.pk, uuid.uuid4())
        self.assertEqual(response.status_code, 404)

    def test_confirm_invalid_visit_id(self):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 7, 5))
        response = self.client.generic(
            "PATCH",
            reverse(
                "owner:matching-confirm",
                kwargs={"pk": imp.pk, "row_id": row.pk},
            ),
            data=urlencode({"visit_id": "not-a-uuid"}),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("無効なリクエストです", response.content.decode())

    def test_confirm_missing_visit_id(self):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 7, 6))
        response = self.client.generic(
            "PATCH",
            reverse(
                "owner:matching-confirm",
                kwargs={"pk": imp.pk, "row_id": row.pk},
            ),
            data="",
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("無効なリクエストです", response.content.decode())

    @patch("imports.services.MatchingService.confirm_row")
    def test_confirm_visit_not_in_candidates(self, mock_confirm):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 7, 7))
        mock_confirm.side_effect = BusinessError(
            code="import.visit_not_in_candidates",
            message="x",
            status_code=400,
        )
        response = self._patch_confirm(imp.pk, row.pk, uuid.uuid4())
        self.assertEqual(response.status_code, 422)
        payload = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(
            payload["showToast"]["message"],
            "選択した候補は無効です。再読み込みしてください",
        )
        self.assertEqual(response.headers.get("HX-Reswap"), "none")

    @patch("imports.services.MatchingService.confirm_row")
    def test_confirm_row_not_pending(self, mock_confirm):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 7, 8))
        mock_confirm.side_effect = BusinessError(
            code="import.row_not_pending",
            message="x",
            status_code=400,
        )
        response = self._patch_confirm(imp.pk, row.pk, uuid.uuid4())
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.headers.get("HX-Reswap"), "none")
        payload = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(
            payload["showToast"]["message"],
            "この明細は既に処理されています",
        )

    @patch("imports.services.MatchingService.confirm_row")
    def test_confirm_row_already_processed(self, mock_confirm):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 7, 9))
        mock_confirm.side_effect = BusinessError(
            code="import.row_already_processed",
            message="x",
            status_code=400,
        )
        response = self._patch_confirm(imp.pk, row.pk, uuid.uuid4())
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.headers.get("HX-Reswap"), "none")
        payload = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(
            payload["showToast"]["message"],
            "この明細は既に処理されています",
        )

    @patch("imports.services.MatchingService.confirm_row")
    def test_confirm_row_conflict(self, mock_confirm):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 7, 10))
        mock_confirm.side_effect = BusinessError(
            code="import.row_conflict",
            message="x",
            status_code=409,
        )
        response = self._patch_confirm(imp.pk, row.pk, uuid.uuid4())
        self.assertEqual(response.status_code, 422)
        payload = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(
            payload["showToast"]["message"],
            "他のユーザーが先に処理しました",
        )

    @patch("imports.services.MatchingService.confirm_row")
    def test_confirm_direct_confirm_reject(self, mock_confirm):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 7, 11))
        mock_confirm.side_effect = BusinessError(
            code="import.direct_confirm_reject",
            message="x",
            status_code=400,
        )
        response = self._patch_confirm(imp.pk, row.pk, uuid.uuid4())
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.headers.get("HX-Reswap"), "none")
        payload = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(
            payload["showToast"]["message"],
            "この明細はまだマッチング未実行です",
        )

    def test_confirm_success_empty_response(self):
        imp = self._csv_import()
        bd = date(2026, 7, 12)
        row = self._row(imp, business_date=bd)
        cust = Customer.objects.create(store=self.store, name="E1")
        visit = Visit.objects.create(
            store=self.store,
            customer=cust,
            staff=self.owner,
            visited_at=bd,
        )
        response = self._patch_confirm(imp.pk, row.pk, visit.pk)
        self.assertEqual(response.content, b"")

    def test_confirm_success_toast(self):
        imp = self._csv_import()
        bd = date(2026, 7, 13)
        row = self._row(imp, business_date=bd)
        cust = Customer.objects.create(store=self.store, name="E2")
        visit = Visit.objects.create(
            store=self.store,
            customer=cust,
            staff=self.owner,
            visited_at=bd,
        )
        response = self._patch_confirm(imp.pk, row.pk, visit.pk)
        payload = json.loads(response.headers.get("HX-Trigger", "{}"))
        self.assertEqual(payload["showToast"]["message"], "確定しました")
        self.assertEqual(payload["showToast"]["type"], "success")

    @patch("imports.services.MatchingService.confirm_row")
    def test_confirm_error_reswap_none(self, mock_confirm):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 7, 14))
        mock_confirm.side_effect = BusinessError(
            code="import.row_conflict",
            message="x",
            status_code=409,
        )
        response = self._patch_confirm(imp.pk, row.pk, uuid.uuid4())
        self.assertEqual(response.headers.get("HX-Reswap"), "none")

    # --- #83–#94 reject ---

    def test_reject_patch(self):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 8, 1))
        response = self._patch_reject(imp.pk, row.pk)
        self.assertEqual(response.status_code, 200)
        row.refresh_from_db()
        self.assertEqual(row.status, CsvImportRow.STATUS_REJECTED)

    def test_reject_requires_auth(self):
        self.client.logout()
        response = self._patch_reject(uuid.uuid4(), uuid.uuid4())
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/o/login/"))

    def test_reject_requires_owner(self):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 8, 2))
        self.client.force_login(self.staff)
        response = self._patch_reject(imp.pk, row.pk)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/customers/")

    def test_reject_store_scope(self):
        imp = self._csv_import(store=self.other_store)
        row = self._row(
            imp,
            store=self.other_store,
            business_date=date(2026, 8, 3),
        )
        response = self._patch_reject(imp.pk, row.pk)
        self.assertEqual(response.status_code, 404)

    def test_reject_nonexistent_row(self):
        imp = self._csv_import()
        response = self._patch_reject(imp.pk, uuid.uuid4())
        self.assertEqual(response.status_code, 404)

    def test_reject_wrong_import(self):
        imp_a = self._csv_import()
        imp_b = self._csv_import()
        row = self._row(imp_b, business_date=date(2026, 8, 4))
        response = self._patch_reject(imp_a.pk, row.pk)
        self.assertEqual(response.status_code, 404)

    @patch("imports.services.MatchingService.reject_row")
    def test_reject_row_not_pending(self, mock_reject):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 8, 5))
        mock_reject.side_effect = BusinessError(
            code="import.row_not_pending",
            message="x",
            status_code=400,
        )
        response = self._patch_reject(imp.pk, row.pk)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.headers.get("HX-Reswap"), "none")
        payload = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(
            payload["showToast"]["message"],
            "この明細は既に処理されています",
        )

    @patch("imports.services.MatchingService.reject_row")
    def test_reject_row_conflict(self, mock_reject):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 8, 6))
        mock_reject.side_effect = BusinessError(
            code="import.row_conflict",
            message="x",
            status_code=409,
        )
        response = self._patch_reject(imp.pk, row.pk)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.headers.get("HX-Reswap"), "none")
        payload = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(
            payload["showToast"]["message"],
            "他のユーザーが先に処理しました",
        )

    @patch("imports.services.MatchingService.reject_row")
    def test_reject_row_already_processed(self, mock_reject):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 8, 7))
        mock_reject.side_effect = BusinessError(
            code="import.row_already_processed",
            message="x",
            status_code=400,
        )
        response = self._patch_reject(imp.pk, row.pk)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.headers.get("HX-Reswap"), "none")
        payload = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(
            payload["showToast"]["message"],
            "この明細は既に処理されています",
        )

    @patch("imports.services.MatchingService.reject_row")
    def test_reject_direct_confirm_reject(self, mock_reject):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 8, 8))
        mock_reject.side_effect = BusinessError(
            code="import.direct_confirm_reject",
            message="x",
            status_code=400,
        )
        response = self._patch_reject(imp.pk, row.pk)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.headers.get("HX-Reswap"), "none")
        payload = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(
            payload["showToast"]["message"],
            "この明細はまだマッチング未実行です",
        )

    def test_reject_success_empty_response(self):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 8, 9))
        response = self._patch_reject(imp.pk, row.pk)
        self.assertEqual(response.content, b"")

    def test_reject_success_toast(self):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 8, 10))
        response = self._patch_reject(imp.pk, row.pk)
        payload = json.loads(response.headers.get("HX-Trigger", "{}"))
        self.assertEqual(payload["showToast"]["message"], "却下しました")

    @patch("imports.services.MatchingService.reject_row")
    def test_reject_error_reswap_none(self, mock_reject):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 8, 11))
        mock_reject.side_effect = BusinessError(
            code="import.row_conflict",
            message="x",
            status_code=409,
        )
        response = self._patch_reject(imp.pk, row.pk)
        self.assertEqual(response.headers.get("HX-Reswap"), "none")

    def test_reject_no_body_required(self):
        imp = self._csv_import()
        row = self._row(imp, business_date=date(2026, 8, 12))
        response = self.client.generic(
            "PATCH",
            reverse(
                "owner:matching-reject",
                kwargs={"pk": imp.pk, "row_id": row.pk},
            ),
            data="",
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 200)
        row.refresh_from_db()
        self.assertEqual(row.status, CsvImportRow.STATUS_REJECTED)
