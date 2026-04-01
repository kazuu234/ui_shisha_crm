from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.models import Staff
from customers.models import Customer
from tenants.models import Store, StoreGroup
from visits.models import SegmentThreshold
from visits.services import SegmentService


def _seed_segment_thresholds(store):
    SegmentThreshold.objects.get_or_create(
        store=store,
        segment_name="new",
        defaults={
            "min_visits": 0,
            "max_visits": 1,
            "display_order": 1,
        },
    )
    SegmentThreshold.objects.get_or_create(
        store=store,
        segment_name="repeat",
        defaults={
            "min_visits": 2,
            "max_visits": 4,
            "display_order": 2,
        },
    )
    SegmentThreshold.objects.get_or_create(
        store=store,
        segment_name="regular",
        defaults={
            "min_visits": 5,
            "max_visits": None,
            "display_order": 3,
        },
    )


def _default_thresholds_list():
    return [
        {"segment_name": "new", "min_visits": 0, "max_visits": 1, "display_order": 1},
        {"segment_name": "repeat", "min_visits": 2, "max_visits": 4, "display_order": 2},
        {"segment_name": "regular", "min_visits": 5, "max_visits": None, "display_order": 3},
    ]


def _alt_thresholds_list():
    """new 0–2, repeat 3–5, regular 6+（連続）"""
    return [
        {"segment_name": "new", "min_visits": 0, "max_visits": 2, "display_order": 1},
        {"segment_name": "repeat", "min_visits": 3, "max_visits": 5, "display_order": 2},
        {"segment_name": "regular", "min_visits": 6, "max_visits": None, "display_order": 3},
    ]


class OwnerSegmentViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store_group = StoreGroup.objects.create(name="Segment Test Group")
        cls.store = Store.objects.create(
            store_group=cls.store_group,
            name="Segment Store",
        )
        cls.other_store = Store.objects.create(
            store_group=cls.store_group,
            name="Other Segment Store",
        )

    def setUp(self):
        _seed_segment_thresholds(self.store)
        _seed_segment_thresholds(self.other_store)
        self.owner = Staff.objects.create_user(
            store=self.store,
            display_name="Owner Seg",
            role="owner",
            staff_type="owner",
        )
        self.staff_user = Staff.objects.create_user(
            store=self.store,
            display_name="Staff Seg",
            role="staff",
            staff_type="regular",
        )
        self.staff_other = Staff.objects.create_user(
            store=self.other_store,
            display_name="Other Owner",
            role="owner",
            staff_type="owner",
        )

        self.c_new = Customer.objects.create(
            store=self.store,
            name="C0",
            visit_count=0,
            segment="new",
        )
        self.c_repeat = Customer.objects.create(
            store=self.store,
            name="C2",
            visit_count=2,
            segment="repeat",
        )
        self.c_regular = Customer.objects.create(
            store=self.store,
            name="C5",
            visit_count=5,
            segment="regular",
        )
        self.client.force_login(self.owner)

    def _build_formset_data(self, thresholds_list):
        data = {
            "form-TOTAL_FORMS": str(len(thresholds_list)),
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "3",
            "form-MAX_NUM_FORMS": "3",
        }
        for i, t in enumerate(thresholds_list):
            data[f"form-{i}-segment_name"] = t["segment_name"]
            data[f"form-{i}-min_visits"] = str(t["min_visits"])
            data[f"form-{i}-max_visits"] = (
                str(t["max_visits"]) if t["max_visits"] is not None else ""
            )
            data[f"form-{i}-display_order"] = str(t["display_order"])
        return data

    def test_segment_settings_get(self):
        response = self.client.get(reverse("owner:segment-settings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/owner/segment_settings.html")
        self.assertContains(response, "現在の閾値")
        self.assertContains(response, "閾値変更")

    def test_segment_settings_unauthenticated(self):
        self.client.logout()
        response = self.client.get(reverse("owner:segment-settings"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/o/login/"))

    def test_segment_settings_staff_redirect(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("owner:segment-settings"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/customers/")

    def test_segment_preview_valid(self):
        data = self._build_formset_data(_default_thresholds_list())
        response = self.client.post(reverse("owner:segment-preview"), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "プレビュー結果")
        self.assertContains(response, "件の顧客のセグメントが変わります")

    def test_segment_preview_invalid_formset(self):
        bad = _default_thresholds_list()
        bad[1]["min_visits"] = 99
        data = self._build_formset_data(bad)
        response = self.client.post(reverse("owner:segment-preview"), data)
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "入力内容にエラー")

    def test_segment_preview_affected_count(self):
        """閾値を変えたとき、セグメントが変わる顧客数が一致する"""
        data = self._build_formset_data(_alt_thresholds_list())
        response = self.client.post(reverse("owner:segment-preview"), data)
        self.assertEqual(response.status_code, 200)
        # vc=2 は repeat→new、vc=5 は regular→repeat の 2 件が変化
        self.assertContains(response, "2 件の顧客のセグメントが変わります")

    def test_segment_preview_segment_counts(self):
        data = self._build_formset_data(_default_thresholds_list())
        response = self.client.post(reverse("owner:segment-preview"), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1 件", count=3)

    def test_segment_apply_valid(self):
        data = self._build_formset_data(_alt_thresholds_list())
        response = self.client.post(reverse("owner:segment-apply"), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("HX-Redirect"),
            reverse("owner:segment-settings"),
        )
        n = SegmentThreshold.objects.get(store=self.store, segment_name="new")
        self.assertEqual(n.max_visits, 2)
        r = SegmentThreshold.objects.get(store=self.store, segment_name="regular")
        self.assertEqual(r.min_visits, 6)

    def test_segment_apply_invalid_formset(self):
        bad = _default_thresholds_list()
        bad[1]["min_visits"] = 50
        data = self._build_formset_data(bad)
        response = self.client.post(reverse("owner:segment-apply"), data)
        self.assertEqual(response.status_code, 422)

    def test_segment_apply_validation_error(self):
        """FormSet で非連続（new.max+1 != repeat.min）→ 422"""
        rows = [
            {"segment_name": "new", "min_visits": 0, "max_visits": 0, "display_order": 1},
            {"segment_name": "repeat", "min_visits": 2, "max_visits": 4, "display_order": 2},
            {"segment_name": "regular", "min_visits": 5, "max_visits": None, "display_order": 3},
        ]
        data = self._build_formset_data(rows)
        response = self.client.post(reverse("owner:segment-apply"), data)
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "連続")

    def test_segment_apply_toast(self):
        data = self._build_formset_data(_default_thresholds_list())
        response = self.client.post(reverse("owner:segment-apply"), data)
        self.assertEqual(response.status_code, 200)
        r2 = self.client.get(reverse("owner:segment-settings"))
        self.assertContains(r2, "セグメント閾値を更新しました")

    def test_segment_apply_recalculate_called(self):
        data = self._build_formset_data(_default_thresholds_list())
        with patch.object(
            SegmentService,
            "bulk_recalculate_segments",
            wraps=SegmentService.bulk_recalculate_segments,
        ) as mocked:
            response = self.client.post(reverse("owner:segment-apply"), data)
        self.assertEqual(response.status_code, 200)
        mocked.assert_called_once()
        self.assertEqual(mocked.call_args[0][0], self.store)

    def test_segment_apply_transaction_rollback(self):
        data = self._build_formset_data(_alt_thresholds_list())
        with patch(
            "ui.owner.views.segment.SegmentThreshold.validate_store_thresholds",
            side_effect=ValidationError("rollback test"),
        ):
            response = self.client.post(reverse("owner:segment-apply"), data)
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "rollback test")
        n = SegmentThreshold.objects.get(store=self.store, segment_name="new")
        self.assertEqual(n.max_visits, 1)

    def test_segment_settings_store_scope(self):
        SegmentThreshold.objects.filter(store=self.other_store).update(max_visits=99)
        response = self.client.get(reverse("owner:segment-settings"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "99")

    def test_sidebar_active_segments(self):
        response = self.client.get(reverse("owner:segment-settings"))
        self.assertEqual(response.context["active_sidebar"], "segments")

    def test_segment_settings_toast_display(self):
        session = self.client.session
        session["toast"] = {"message": "トーストテスト", "type": "success"}
        session.save()
        response = self.client.get(reverse("owner:segment-settings"))
        self.assertContains(response, "トーストテスト")
        self.assertIsNone(self.client.session.get("toast"))

    def test_segment_preview_unauthenticated(self):
        self.client.logout()
        data = self._build_formset_data(_default_thresholds_list())
        response = self.client.post(reverse("owner:segment-preview"), data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/o/login/"))

    def test_segment_apply_unauthenticated(self):
        self.client.logout()
        data = self._build_formset_data(_default_thresholds_list())
        response = self.client.post(reverse("owner:segment-apply"), data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/o/login/"))

    def test_segment_preview_staff_access_denied(self):
        self.client.force_login(self.staff_user)
        data = self._build_formset_data(_default_thresholds_list())
        response = self.client.post(reverse("owner:segment-preview"), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/customers/")

    def test_segment_apply_staff_access_denied(self):
        self.client.force_login(self.staff_user)
        data = self._build_formset_data(_default_thresholds_list())
        response = self.client.post(reverse("owner:segment-apply"), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/customers/")

    def test_segment_apply_display_order_tamper_ignored(self):
        rows = _alt_thresholds_list()
        rows[0]["display_order"] = 99
        rows[1]["display_order"] = 98
        rows[2]["display_order"] = 97
        data = self._build_formset_data(rows)
        response = self.client.post(reverse("owner:segment-apply"), data)
        self.assertEqual(response.status_code, 200)
        by_name = {
            t.segment_name: t.display_order
            for t in SegmentThreshold.objects.filter(store=self.store)
        }
        self.assertEqual(by_name["new"], 1)
        self.assertEqual(by_name["repeat"], 2)
        self.assertEqual(by_name["regular"], 3)
