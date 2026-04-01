import json
import uuid
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import urlencode

from django.test import TestCase
from django.utils import timezone

from accounts.models import Staff
from core.exceptions import BusinessError
from customers.models import Customer
from imports.models import CsvImport, CsvImportRow
from tenants.models import Store, StoreGroup
from visits.models import Visit


class MatchingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store_group = StoreGroup.objects.create(name="Matching Group")
        cls.store = Store.objects.create(store_group=cls.store_group, name="Matching Store")
        cls.other_store = Store.objects.create(store_group=cls.store_group, name="Matching Other")
        cls.staff = Staff.objects.create_user(
            store=cls.store,
            display_name="Matching Staff",
            role="staff",
            staff_type="regular",
        )

    def setUp(self):
        self.client.force_login(self.staff)

    def _csv_import(self, store=None):
        store = store or self.store
        return CsvImport.objects.create(
            store=store,
            file_name="m.csv",
            row_count=1,
            status=CsvImport.STATUS_COMPLETED,
            error_message=[],
        )

    def _row(
        self,
        *,
        store=None,
        business_date,
        status,
        receipt_no="001",
        normalized_data=None,
        csv_import=None,
        row_number=1,
    ):
        store = store or self.store
        csv_import = csv_import or self._csv_import(store)
        key = f"{store.id}_{business_date.isoformat()}_{receipt_no}"
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

    def _matching_link_html(self, response):
        html = response.content.decode()
        idx = html.find('href="/s/matching/"')
        self.assertNotEqual(idx, -1)
        start = html.rfind("<a", 0, idx)
        end = html.find("</a>", idx)
        self.assertNotEqual(start, -1)
        return html[start:end]

    def _patch_confirm(self, row_id, visit_id):
        body = urlencode({"visit_id": str(visit_id)})
        return self.client.generic(
            "PATCH",
            f"/s/matching/{row_id}/confirm/",
            data=body,
            content_type="application/x-www-form-urlencoded",
        )

    def _patch_reject(self, row_id):
        return self.client.generic(
            "PATCH",
            f"/s/matching/{row_id}/reject/",
            data="",
            content_type="application/x-www-form-urlencoded",
        )

    # --- 一覧 ---

    def test_matching_list_get(self):
        response = self.client.get("/s/matching/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/staff/matching.html")

    def test_matching_list_requires_auth(self):
        self.client.logout()
        response = self.client.get("/s/matching/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/s/login/"))

    def test_matching_list_active_tab(self):
        response = self.client.get("/s/matching/")
        self.assertEqual(response.context["active_tab"], "matching")

    def test_matching_list_shows_pending_review_only(self):
        today = timezone.localdate()
        self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW, receipt_no="p1")
        self._row(business_date=today, status=CsvImportRow.STATUS_VALIDATED, receipt_no="v1")
        self._row(business_date=today, status=CsvImportRow.STATUS_CONFIRMED, receipt_no="c1")
        self._row(business_date=today, status=CsvImportRow.STATUS_REJECTED, receipt_no="r1")
        response = self.client.get("/s/matching/")
        self.assertContains(response, "No.p1")
        self.assertNotContains(response, "No.v1")
        self.assertNotContains(response, "No.c1")
        self.assertNotContains(response, "No.r1")

    def test_matching_list_today_only(self):
        today = timezone.localdate()
        self._row(business_date=today - timedelta(days=1), status=CsvImportRow.STATUS_PENDING_REVIEW, receipt_no="old")
        response = self.client.get("/s/matching/")
        self.assertNotContains(response, "No.old")
        self.assertContains(response, "マッチ待ちの明細はありません")

    def test_matching_list_uses_timezone_localdate(self):
        fixed = timezone.localdate()

        with patch("ui.staff.views.matching.timezone.localdate") as m_local:
            m_local.return_value = fixed
            self.client.get("/s/matching/")
            m_local.assert_called()

        self._row(business_date=fixed, status=CsvImportRow.STATUS_PENDING_REVIEW, receipt_no="d1")
        with patch("ui.staff.views.matching.timezone.localdate") as m_local:
            m_local.return_value = fixed
            r_ok = self.client.get("/s/matching/")
        self.assertContains(r_ok, "No.d1")

        with patch("ui.staff.views.matching.timezone.localdate") as m_local:
            m_local.return_value = fixed - timedelta(days=1)
            r_hide = self.client.get("/s/matching/")
        self.assertNotContains(r_hide, "No.d1")

    def test_matching_list_empty_message(self):
        response = self.client.get("/s/matching/")
        self.assertContains(response, "マッチ待ちの明細はありません")

    def test_matching_list_displays_receipt_no(self):
        today = timezone.localdate()
        self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW, receipt_no="R-99")
        response = self.client.get("/s/matching/")
        self.assertContains(response, "No.R-99")

    def test_matching_list_displays_csv_customer_name(self):
        today = timezone.localdate()
        self._row(
            business_date=today,
            status=CsvImportRow.STATUS_PENDING_REVIEW,
            receipt_no="n1",
            normalized_data={"customer_name": "CSV名前"},
        )
        response = self.client.get("/s/matching/")
        self.assertContains(response, "CSV 顧客名: CSV名前")

    def test_matching_list_no_csv_customer_name(self):
        today = timezone.localdate()
        self._row(
            business_date=today,
            status=CsvImportRow.STATUS_PENDING_REVIEW,
            receipt_no="n2",
            normalized_data={},
        )
        response = self.client.get("/s/matching/")
        self.assertContains(response, "No.n2")
        self.assertNotContains(response, "CSV 顧客名:")

    def test_matching_list_store_scope(self):
        today = timezone.localdate()
        self._row(store=self.other_store, business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW, receipt_no="os")
        response = self.client.get("/s/matching/")
        self.assertNotContains(response, "No.os")

    def test_matching_list_order_by_receipt_no(self):
        today = timezone.localdate()
        imp = self._csv_import()
        self._row(
            csv_import=imp,
            business_date=today,
            status=CsvImportRow.STATUS_PENDING_REVIEW,
            receipt_no="003",
        )
        self._row(
            csv_import=imp,
            business_date=today,
            status=CsvImportRow.STATUS_PENDING_REVIEW,
            receipt_no="001",
            row_number=2,
        )
        self._row(
            csv_import=imp,
            business_date=today,
            status=CsvImportRow.STATUS_PENDING_REVIEW,
            receipt_no="002",
            row_number=3,
        )
        response = self.client.get("/s/matching/")
        html = response.content.decode()
        self.assertLess(html.find("No.001"), html.find("No.002"))
        self.assertLess(html.find("No.002"), html.find("No.003"))

    # --- 候補 ---

    def test_candidates_get(self):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW)
        response = self.client.get(f"/s/matching/{row.pk}/candidates/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/staff/_matching_candidates.html")

    def test_candidates_requires_auth(self):
        self.client.logout()
        row_id = uuid.uuid4()
        response = self.client.get(f"/s/matching/{row_id}/candidates/")
        self.assertEqual(response.status_code, 302)

    def test_candidates_store_scope(self):
        today = timezone.localdate()
        row = self._row(
            store=self.other_store,
            business_date=today,
            status=CsvImportRow.STATUS_PENDING_REVIEW,
        )
        response = self.client.get(f"/s/matching/{row.pk}/candidates/")
        self.assertEqual(response.status_code, 404)

    def test_candidates_nonexistent_row(self):
        response = self.client.get(f"/s/matching/{uuid.uuid4()}/candidates/")
        self.assertEqual(response.status_code, 404)

    @patch("imports.services.MatchingService.get_candidates")
    def test_candidates_displays_customer_name(self, mock_gc):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW)
        vid = uuid.uuid4()
        mock_gc.return_value = [
            {
                "visit_id": vid,
                "customer": {"id": uuid.uuid4(), "name": "候補太郎"},
                "visited_at": today,
                "name_match_score": None,
            },
        ]
        response = self.client.get(f"/s/matching/{row.pk}/candidates/")
        self.assertContains(response, "候補太郎")

    @patch("imports.services.MatchingService.get_candidates")
    def test_candidates_displays_visited_at(self, mock_gc):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW)
        mock_gc.return_value = [
            {
                "visit_id": uuid.uuid4(),
                "customer": {"id": uuid.uuid4(), "name": "X"},
                "visited_at": today,
                "name_match_score": None,
            },
        ]
        response = self.client.get(f"/s/matching/{row.pk}/candidates/")
        self.assertContains(response, f"{today.month}/{today.day}")

    @patch("imports.services.MatchingService.get_candidates")
    def test_candidates_displays_match_score(self, mock_gc):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW)
        mock_gc.return_value = [
            {
                "visit_id": uuid.uuid4(),
                "customer": {"id": uuid.uuid4(), "name": "Full"},
                "visited_at": today,
                "name_match_score": 1.0,
            },
            {
                "visit_id": uuid.uuid4(),
                "customer": {"id": uuid.uuid4(), "name": "Part"},
                "visited_at": today,
                "name_match_score": 0.5,
            },
        ]
        response = self.client.get(f"/s/matching/{row.pk}/candidates/")
        self.assertContains(response, "完全一致")
        self.assertContains(response, "部分一致")

    def test_candidates_not_pending_review_validated(self):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_VALIDATED)
        response = self.client.get(f"/s/matching/{row.pk}/candidates/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("候補を取得できません", response.content.decode())
        self.assertIsNone(response.headers.get("HX-Trigger"))

    def test_candidates_not_pending_review_confirmed(self):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_CONFIRMED)
        response = self.client.get(f"/s/matching/{row.pk}/candidates/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("候補を取得できません", response.content.decode())
        self.assertIsNone(response.headers.get("HX-Trigger"))

    def test_candidates_not_pending_review_rejected(self):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_REJECTED)
        response = self.client.get(f"/s/matching/{row.pk}/candidates/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("候補を取得できません", response.content.decode())
        self.assertIsNone(response.headers.get("HX-Trigger"))

    @patch("imports.services.MatchingService.get_candidates")
    def test_candidates_has_confirm_button(self, mock_gc):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW)
        vid = uuid.uuid4()
        mock_gc.return_value = [
            {
                "visit_id": vid,
                "customer": {"id": uuid.uuid4(), "name": "B"},
                "visited_at": today,
                "name_match_score": None,
            },
        ]
        response = self.client.get(f"/s/matching/{row.pk}/candidates/")
        self.assertContains(response, "hx-patch")
        self.assertContains(response, f"/s/matching/{row.pk}/confirm/")

    @patch("imports.services.MatchingService.get_candidates")
    def test_candidates_has_reject_button(self, mock_gc):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW)
        mock_gc.return_value = []
        response = self.client.get(f"/s/matching/{row.pk}/candidates/")
        self.assertContains(response, "この明細を却下")
        self.assertContains(response, f"/s/matching/{row.pk}/reject/")

    @patch("imports.services.MatchingService.get_candidates")
    def test_candidates_empty(self, mock_gc):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW)
        mock_gc.return_value = []
        response = self.client.get(f"/s/matching/{row.pk}/candidates/")
        self.assertContains(response, "候補が見つかりませんでした")
        self.assertContains(response, "この明細を却下")

    @patch("imports.services.MatchingService.get_candidates")
    def test_candidates_row_id_in_context(self, mock_gc):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW)
        mock_gc.return_value = []
        response = self.client.get(f"/s/matching/{row.pk}/candidates/")
        self.assertContains(response, f"matching-row-{row.pk}")

    @patch("imports.services.MatchingService.get_candidates")
    def test_candidates_sort_order(self, mock_gc):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW)
        v_high = uuid.uuid4()
        v_mid = uuid.uuid4()
        v_low = uuid.uuid4()
        mock_gc.return_value = [
            {
                "visit_id": v_high,
                "customer": {"id": uuid.uuid4(), "name": "AAA高スコア"},
                "visited_at": today,
                "name_match_score": 1.0,
            },
            {
                "visit_id": v_mid,
                "customer": {"id": uuid.uuid4(), "name": "BBB中スコア"},
                "visited_at": today,
                "name_match_score": 0.5,
            },
            {
                "visit_id": v_low,
                "customer": {"id": uuid.uuid4(), "name": "CCC低スコア"},
                "visited_at": today,
                "name_match_score": 0.0,
            },
        ]
        response = self.client.get(f"/s/matching/{row.pk}/candidates/")
        html = response.content.decode()
        self.assertLess(html.find("AAA高スコア"), html.find("BBB中スコア"))
        self.assertLess(html.find("BBB中スコア"), html.find("CCC低スコア"))

    @patch("imports.services.MatchingService.get_candidates")
    def test_candidates_flat_mapping(self, mock_gc):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW)
        cid = uuid.uuid4()
        mock_gc.return_value = [
            {
                "visit_id": uuid.uuid4(),
                "customer": {"id": cid, "name": "ネスト名"},
                "visited_at": today,
                "name_match_score": None,
            },
        ]
        response = self.client.get(f"/s/matching/{row.pk}/candidates/")
        self.assertContains(response, "ネスト名")

    # --- confirm ---

    def test_confirm_patch(self):
        today = timezone.localdate()
        cust = Customer.objects.create(store=self.store, name="確定顧客")
        visit = Visit.objects.create(
            store=self.store,
            customer=cust,
            staff=self.staff,
            visited_at=today,
        )
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW, receipt_no="cf")
        response = self._patch_confirm(row.pk, visit.pk)
        self.assertEqual(response.status_code, 200)
        row.refresh_from_db()
        self.assertEqual(row.status, CsvImportRow.STATUS_CONFIRMED)

    def test_confirm_requires_auth(self):
        self.client.logout()
        response = self._patch_confirm(uuid.uuid4(), uuid.uuid4())
        self.assertEqual(response.status_code, 302)

    def test_confirm_store_scope(self):
        today = timezone.localdate()
        row = self._row(
            store=self.other_store,
            business_date=today,
            status=CsvImportRow.STATUS_PENDING_REVIEW,
        )
        response = self._patch_confirm(row.pk, uuid.uuid4())
        self.assertEqual(response.status_code, 404)

    def test_confirm_nonexistent_row(self):
        response = self._patch_confirm(uuid.uuid4(), uuid.uuid4())
        self.assertEqual(response.status_code, 404)

    def test_confirm_invalid_visit_id(self):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW)
        response = self.client.generic(
            "PATCH",
            f"/s/matching/{row.pk}/confirm/",
            data=urlencode({"visit_id": "not-a-uuid"}),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("無効なリクエストです", response.content.decode())

    def test_confirm_missing_visit_id(self):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW)
        response = self.client.generic(
            "PATCH",
            f"/s/matching/{row.pk}/confirm/",
            data="",
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 400)

    def test_confirm_visit_not_in_candidates(self):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW)
        orphan = uuid.uuid4()
        response = self._patch_confirm(row.pk, orphan)
        self.assertEqual(response.status_code, 422)
        payload = json.loads(response.headers.get("HX-Trigger", "{}"))
        self.assertEqual(
            payload["showToast"]["message"],
            "選択した候補は無効です。再読み込みしてください",
        )

    @patch("imports.services.MatchingService.confirm_row")
    def test_confirm_row_not_pending(self, mock_confirm):
        """コアは import.row_not_pending を出さないが、既に処理済みと同じ文言で通知する。"""
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW)
        mock_confirm.side_effect = BusinessError(
            code="import.row_already_processed",
            message="x",
            status_code=400,
        )
        response = self._patch_confirm(row.pk, uuid.uuid4())
        self.assertEqual(response.status_code, 422)
        payload = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(payload["showToast"]["message"], "この明細は既に処理されています")

    @patch("imports.services.MatchingService.confirm_row")
    def test_confirm_row_conflict(self, mock_confirm):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW)
        mock_confirm.side_effect = BusinessError(
            code="import.row_conflict",
            message="x",
            status_code=409,
        )
        response = self._patch_confirm(row.pk, uuid.uuid4())
        self.assertEqual(response.status_code, 422)
        payload = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(payload["showToast"]["message"], "他のスタッフが先に処理しました")

    @patch("imports.services.MatchingService.confirm_row")
    def test_confirm_row_already_processed(self, mock_confirm):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW)
        mock_confirm.side_effect = BusinessError(
            code="import.row_already_processed",
            message="x",
            status_code=400,
        )
        response = self._patch_confirm(row.pk, uuid.uuid4())
        payload = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(payload["showToast"]["message"], "この明細は既に処理されています")

    @patch("imports.services.MatchingService.confirm_row")
    def test_confirm_direct_confirm_reject(self, mock_confirm):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW)
        mock_confirm.side_effect = BusinessError(
            code="import.direct_confirm_reject",
            message="x",
            status_code=400,
        )
        response = self._patch_confirm(row.pk, uuid.uuid4())
        payload = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(payload["showToast"]["message"], "この明細はまだマッチング未実行です")

    def test_confirm_success_removes_row(self):
        today = timezone.localdate()
        cust = Customer.objects.create(store=self.store, name="R1")
        visit = Visit.objects.create(
            store=self.store,
            customer=cust,
            staff=self.staff,
            visited_at=today,
        )
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW, receipt_no="sr")
        response = self._patch_confirm(row.pk, visit.pk)
        self.assertEqual(response.content, b"")

    def test_confirm_success_toast(self):
        today = timezone.localdate()
        cust = Customer.objects.create(store=self.store, name="R2")
        visit = Visit.objects.create(
            store=self.store,
            customer=cust,
            staff=self.staff,
            visited_at=today,
        )
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW, receipt_no="st")
        response = self._patch_confirm(row.pk, visit.pk)
        payload = json.loads(response.headers.get("HX-Trigger", "{}"))
        self.assertEqual(payload["showToast"]["message"], "確定しました")
        self.assertEqual(payload["showToast"]["type"], "success")

    @patch("imports.services.MatchingService.confirm_row")
    def test_confirm_error_no_dom_change(self, mock_confirm):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW)
        mock_confirm.side_effect = BusinessError(
            code="import.row_conflict",
            message="x",
            status_code=409,
        )
        response = self._patch_confirm(row.pk, uuid.uuid4())
        self.assertEqual(response.headers.get("HX-Reswap"), "none")

    def test_confirm_patch_body_parsing(self):
        today = timezone.localdate()
        cust = Customer.objects.create(store=self.store, name="Parse")
        visit = Visit.objects.create(
            store=self.store,
            customer=cust,
            staff=self.staff,
            visited_at=today,
        )
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW, receipt_no="pb")
        body = urlencode({"visit_id": str(visit.pk)})
        response = self.client.generic(
            "PATCH",
            f"/s/matching/{row.pk}/confirm/",
            data=body,
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 200)
        row.refresh_from_db()
        self.assertEqual(row.status, CsvImportRow.STATUS_CONFIRMED)

    # --- reject ---

    def test_reject_patch(self):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW, receipt_no="rj")
        response = self._patch_reject(row.pk)
        self.assertEqual(response.status_code, 200)
        row.refresh_from_db()
        self.assertEqual(row.status, CsvImportRow.STATUS_REJECTED)

    def test_reject_requires_auth(self):
        self.client.logout()
        response = self._patch_reject(uuid.uuid4())
        self.assertEqual(response.status_code, 302)

    def test_reject_store_scope(self):
        today = timezone.localdate()
        row = self._row(
            store=self.other_store,
            business_date=today,
            status=CsvImportRow.STATUS_PENDING_REVIEW,
        )
        response = self._patch_reject(row.pk)
        self.assertEqual(response.status_code, 404)

    def test_reject_nonexistent_row(self):
        response = self._patch_reject(uuid.uuid4())
        self.assertEqual(response.status_code, 404)

    @patch("imports.services.MatchingService.reject_row")
    def test_reject_row_not_pending(self, mock_reject):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW)
        mock_reject.side_effect = BusinessError(
            code="import.row_already_processed",
            message="x",
            status_code=400,
        )
        response = self._patch_reject(row.pk)
        self.assertEqual(response.status_code, 422)
        payload = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(payload["showToast"]["message"], "この明細は既に処理されています")

    @patch("imports.services.MatchingService.reject_row")
    def test_reject_row_conflict(self, mock_reject):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW)
        mock_reject.side_effect = BusinessError(
            code="import.row_conflict",
            message="x",
            status_code=409,
        )
        response = self._patch_reject(row.pk)
        payload = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(payload["showToast"]["message"], "他のスタッフが先に処理しました")

    @patch("imports.services.MatchingService.reject_row")
    def test_reject_row_already_processed(self, mock_reject):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW)
        mock_reject.side_effect = BusinessError(
            code="import.row_already_processed",
            message="x",
            status_code=400,
        )
        response = self._patch_reject(row.pk)
        payload = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(payload["showToast"]["message"], "この明細は既に処理されています")

    @patch("imports.services.MatchingService.reject_row")
    def test_reject_direct_confirm_reject(self, mock_reject):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW)
        mock_reject.side_effect = BusinessError(
            code="import.direct_confirm_reject",
            message="x",
            status_code=400,
        )
        response = self._patch_reject(row.pk)
        payload = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(payload["showToast"]["message"], "この明細はまだマッチング未実行です")

    def test_reject_success_removes_row(self):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW, receipt_no="rr")
        response = self._patch_reject(row.pk)
        self.assertEqual(response.content, b"")

    def test_reject_success_toast(self):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW, receipt_no="rt")
        response = self._patch_reject(row.pk)
        payload = json.loads(response.headers.get("HX-Trigger", "{}"))
        self.assertEqual(payload["showToast"]["message"], "却下しました")

    @patch("imports.services.MatchingService.reject_row")
    def test_reject_error_no_dom_change(self, mock_reject):
        today = timezone.localdate()
        row = self._row(business_date=today, status=CsvImportRow.STATUS_PENDING_REVIEW)
        mock_reject.side_effect = BusinessError(
            code="import.row_conflict",
            message="x",
            status_code=409,
        )
        response = self._patch_reject(row.pk)
        self.assertEqual(response.headers.get("HX-Reswap"), "none")

    # --- BottomTab ---

    def test_matching_tab_is_link(self):
        response = self.client.get("/s/matching/")
        html = self._matching_link_html(response)
        self.assertIn('href="/s/matching/"', html)
        self.assertNotIn("disabled", html.lower())

    def test_matching_tab_active_on_matching_page(self):
        response = self.client.get("/s/matching/")
        html = self._matching_link_html(response)
        self.assertIn("text-accent", html)
        self.assertIn("font-medium", html)

    def test_matching_tab_inactive_on_other_pages(self):
        response = self.client.get("/s/customers/")
        html = self._matching_link_html(response)
        self.assertIn("text-text-secondary", html)
        self.assertNotIn("text-accent font-medium", html)
