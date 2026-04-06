import json
import uuid
from datetime import date, timedelta
from unittest.mock import patch
from urllib.parse import urlencode

from django.test import TestCase
from django.utils import timezone

from accounts.models import Staff
from customers.models import Customer
from tasks.models import HearingTask
from tenants.models import Store, StoreGroup
from visits.models import Visit


class US03CustomerDetailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store_group = StoreGroup.objects.create(name="US03 Detail Group")
        cls.store = Store.objects.create(store_group=cls.store_group, name="US03 Store")
        cls.other_store = Store.objects.create(store_group=cls.store_group, name="US03 Other")
        cls.staff = Staff.objects.create_user(
            store=cls.store,
            display_name="US03 Staff",
            role="staff",
            staff_type="regular",
        )

    def setUp(self):
        self.client.force_login(self.staff)

    def _detail_url(self, customer):
        return f"/s/customers/{customer.pk}/"

    def test_customer_detail_get(self):
        c = Customer.objects.create(store=self.store, name="詳細太郎")
        response = self.client.get(self._detail_url(c))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/staff/customer_detail.html")

    def test_customer_detail_requires_auth(self):
        self.client.logout()
        c = Customer.objects.create(store=self.store, name="X")
        response = self.client.get(self._detail_url(c))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/s/login/"))

    def test_customer_detail_active_tab(self):
        c = Customer.objects.create(store=self.store, name="Tab")
        response = self.client.get(self._detail_url(c))
        self.assertEqual(response.context["active_tab"], "customers")

    def test_customer_detail_displays_all_attributes(self):
        c = Customer.objects.create(
            store=self.store,
            name="全属性",
            segment="repeat",
            visit_count=3,
            age=30,
            area="港区",
            shisha_experience="intermediate",
            line_id="@line",
            memo="顧客メモ本文",
        )
        response = self.client.get(self._detail_url(c))
        self.assertContains(response, "全属性")
        self.assertContains(response, "リピート")
        self.assertContains(response, "来店 3 回")
        self.assertContains(response, "30歳")
        self.assertContains(response, "港区")
        self.assertContains(response, "中級")
        self.assertContains(response, "@line")
        self.assertContains(response, "顧客メモ本文")

    def test_customer_detail_segment_badge(self):
        for seg, label in (("new", "新規"), ("repeat", "リピート"), ("regular", "常連")):
            c = Customer.objects.create(store=self.store, name=f"C-{seg}", segment=seg)
            response = self.client.get(self._detail_url(c))
            self.assertContains(response, f"badge-{seg}")
            self.assertContains(response, label)

    def test_customer_detail_null_fields_show_placeholder(self):
        c = Customer.objects.create(store=self.store, name="空欄", segment="new")
        response = self.client.get(self._detail_url(c))
        self.assertGreaterEqual(response.content.decode().count("未入力"), 4)

    def test_customer_detail_recent_visits_5(self):
        c = Customer.objects.create(store=self.store, name="来店多")
        today = timezone.localdate()
        for i in range(6):
            Visit.objects.create(
                store=self.store,
                customer=c,
                staff=self.staff,
                visited_at=today - timedelta(days=i),
                conversation_memo=f"memo{i}",
            )
        response = self.client.get(self._detail_url(c))
        for i in range(5):
            self.assertContains(response, f"memo{i}")
        self.assertNotContains(response, "memo5")

    def test_customer_detail_recent_visits_empty(self):
        c = Customer.objects.create(store=self.store, name="無来店")
        response = self.client.get(self._detail_url(c))
        self.assertContains(response, "来店記録はまだありません")

    def test_customer_detail_recent_visits_staff_name(self):
        c = Customer.objects.create(store=self.store, name="スタッフ表示")
        Visit.objects.create(
            store=self.store,
            customer=c,
            staff=self.staff,
            visited_at=timezone.localdate(),
        )
        response = self.client.get(self._detail_url(c))
        self.assertContains(response, "US03 Staff")

    def test_customer_detail_recent_visits_memo_truncated(self):
        c = Customer.objects.create(store=self.store, name="長メモ")
        long_memo = "あ" * 60
        Visit.objects.create(
            store=self.store,
            customer=c,
            staff=self.staff,
            visited_at=timezone.localdate(),
            conversation_memo=long_memo,
        )
        response = self.client.get(self._detail_url(c))
        self.assertNotContains(response, long_memo)
        self.assertContains(response, "…")

    def test_customer_detail_edit_link(self):
        c = Customer.objects.create(store=self.store, name="編集リンク")
        response = self.client.get(self._detail_url(c))
        self.assertContains(response, f"/s/customers/{c.pk}/edit/")

    def test_customer_detail_visit_list_link(self):
        c = Customer.objects.create(store=self.store, name="一覧リンク")
        Visit.objects.create(
            store=self.store,
            customer=c,
            staff=self.staff,
            visited_at=timezone.localdate(),
        )
        response = self.client.get(self._detail_url(c))
        self.assertContains(response, f"/s/customers/{c.pk}/visits/")
        self.assertContains(response, "すべて見る")

    def test_customer_detail_store_scope(self):
        c = Customer.objects.create(store=self.other_store, name="他店")
        response = self.client.get(self._detail_url(c))
        self.assertEqual(response.status_code, 404)

    def test_customer_detail_nonexistent(self):
        response = self.client.get(f"/s/customers/{uuid.uuid4()}/")
        self.assertEqual(response.status_code, 404)

    def test_customer_detail_age_display_label(self):
        c = Customer.objects.create(store=self.store, name="年齢25", age=25)
        response = self.client.get(self._detail_url(c))
        self.assertContains(response, "25歳")

    def test_customer_detail_experience_display_label(self):
        c = Customer.objects.create(
            store=self.store,
            name="初心者表示",
            shisha_experience="beginner",
        )
        response = self.client.get(self._detail_url(c))
        self.assertContains(response, "初心者")

    def test_customer_detail_session_url(self):
        c = Customer.objects.create(store=self.store, name="Sess")
        response = self.client.get(self._detail_url(c))
        self.assertEqual(response.context["session_url"], f"/s/customers/{c.pk}/session/")

    def test_customer_detail_same_day_visits_order_stable(self):
        c = Customer.objects.create(store=self.store, name="同日")
        d = timezone.localdate()
        v_first = Visit.objects.create(
            store=self.store,
            customer=c,
            staff=self.staff,
            visited_at=d,
            conversation_memo="older",
        )
        v_second = Visit.objects.create(
            store=self.store,
            customer=c,
            staff=self.staff,
            visited_at=d,
            conversation_memo="newer",
        )
        Visit.objects.filter(pk=v_first.pk).update(created_at=timezone.now() - timedelta(hours=2))
        Visit.objects.filter(pk=v_second.pk).update(created_at=timezone.now() - timedelta(hours=1))
        response = self.client.get(self._detail_url(c))
        content = response.content.decode()
        pos_newer = content.find("newer")
        pos_older = content.find("older")
        self.assertGreater(pos_older, 0)
        self.assertGreater(pos_newer, 0)
        self.assertLess(pos_newer, pos_older)


class US03CustomerEditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store_group = StoreGroup.objects.create(name="US03 Edit Group")
        cls.store = Store.objects.create(store_group=cls.store_group, name="US03 Edit Store")
        cls.other_store = Store.objects.create(store_group=cls.store_group, name="US03 Edit Other")
        cls.staff = Staff.objects.create_user(
            store=cls.store,
            display_name="Edit Staff",
            role="staff",
            staff_type="regular",
        )

    def setUp(self):
        self.client.force_login(self.staff)

    def _edit_url(self, customer):
        return f"/s/customers/{customer.pk}/edit/"

    def test_customer_edit_get(self):
        c = Customer.objects.create(store=self.store, name="編集画面")
        response = self.client.get(self._edit_url(c))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/staff/customer_edit.html")

    def test_customer_edit_requires_auth(self):
        self.client.logout()
        c = Customer.objects.create(store=self.store, name="A")
        response = self.client.get(self._edit_url(c))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/s/login/"))

    def test_customer_edit_active_tab(self):
        c = Customer.objects.create(store=self.store, name="B")
        response = self.client.get(self._edit_url(c))
        self.assertEqual(response.context["active_tab"], "customers")

    def test_customer_edit_has_all_zones(self):
        c = Customer.objects.create(store=self.store, name="Zones")
        response = self.client.get(self._edit_url(c))
        for zone_id in (
            "zone-name",
            "zone-age",
            "zone-area",
            "zone-shisha_experience",
            "zone-line_id",
            "zone-memo",
        ):
            self.assertContains(response, f'id="{zone_id}"')

    def test_customer_edit_back_link(self):
        c = Customer.objects.create(store=self.store, name="戻る")
        response = self.client.get(self._edit_url(c))
        self.assertContains(response, f"/s/customers/{c.pk}/")

    def test_customer_edit_store_scope(self):
        c = Customer.objects.create(store=self.other_store, name="他店")
        response = self.client.get(self._edit_url(c))
        self.assertEqual(response.status_code, 404)

    def test_customer_edit_displays_current_values(self):
        c = Customer.objects.create(
            store=self.store,
            name="現在値",
            age=40,
            area="渋谷",
            shisha_experience="advanced",
            line_id="@x",
            memo="メモあり",
        )
        response = self.client.get(self._edit_url(c))
        self.assertContains(response, "40歳")
        self.assertContains(response, "渋谷")
        self.assertContains(response, "上級")
        self.assertContains(response, "@x")
        self.assertContains(response, "メモあり")

    def test_customer_edit_session_url(self):
        c = Customer.objects.create(store=self.store, name="Ctx")
        response = self.client.get(self._edit_url(c))
        self.assertEqual(response.context["session_url"], f"/s/customers/{c.pk}/session/")


class US03CustomerEditFieldTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store_group = StoreGroup.objects.create(name="US03 Field Group")
        cls.store = Store.objects.create(store_group=cls.store_group, name="US03 Field Store")
        cls.other_store = Store.objects.create(store_group=cls.store_group, name="US03 Field Other")
        cls.staff = Staff.objects.create_user(
            store=cls.store,
            display_name="Field Staff",
            role="staff",
            staff_type="regular",
        )

    def setUp(self):
        self.client.force_login(self.staff)

    def _patch_url(self, customer):
        return f"/s/customers/{customer.pk}/edit/field/"

    def _patch(self, customer, field, value):
        body = urlencode({"field": field, "value": value})
        return self.client.generic(
            "PATCH",
            self._patch_url(customer),
            data=body,
            content_type="application/x-www-form-urlencoded",
        )

    def test_edit_field_name_patch(self):
        c = Customer.objects.create(store=self.store, name="旧名")
        response = self._patch(c, "name", "新しい名前")
        self.assertEqual(response.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.name, "新しい名前")

    def test_edit_field_name_empty_rejected(self):
        c = Customer.objects.create(store=self.store, name="保持")
        response = self._patch(c, "name", "")
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "名前を入力してください", status_code=422)

    def test_edit_field_name_whitespace_rejected(self):
        c = Customer.objects.create(store=self.store, name="保持2")
        response = self._patch(c, "name", "   ")
        self.assertEqual(response.status_code, 422)

    def test_edit_field_name_trimmed(self):
        c = Customer.objects.create(store=self.store, name="x")
        response = self._patch(c, "name", "  太郎  ")
        self.assertEqual(response.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.name, "太郎")

    def test_edit_field_age_patch(self):
        c = Customer.objects.create(store=self.store, name="Age")
        response = self._patch(c, "age", "25")
        self.assertEqual(response.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.age, 25)

    def test_edit_field_age_invalid_value(self):
        c = Customer.objects.create(store=self.store, name="BadAge")
        response = self._patch(c, "age", "invalid")
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "年齢は整数で入力してください", status_code=422)

    def test_edit_field_age_clear(self):
        c = Customer.objects.create(store=self.store, name="ClearAge", age=10)
        response = self._patch(c, "age", "")
        self.assertEqual(response.status_code, 200)
        c.refresh_from_db()
        self.assertIsNone(c.age)

    def test_edit_field_age_out_of_range(self):
        c = Customer.objects.create(store=self.store, name="Range")
        response = self._patch(c, "age", "200")
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "年齢は 0〜150 の範囲で入力してください", status_code=422)

    def test_edit_field_area_patch(self):
        c = Customer.objects.create(store=self.store, name="Area")
        response = self._patch(c, "area", "渋谷")
        self.assertEqual(response.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.area, "渋谷")

    def test_edit_field_area_empty_to_null(self):
        c = Customer.objects.create(store=self.store, name="A2", area="旧")
        response = self._patch(c, "area", "")
        self.assertEqual(response.status_code, 200)
        c.refresh_from_db()
        self.assertIsNone(c.area)

    def test_edit_field_shisha_experience_patch(self):
        c = Customer.objects.create(store=self.store, name="Exp")
        response = self._patch(c, "shisha_experience", "beginner")
        self.assertEqual(response.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.shisha_experience, "beginner")

    def test_edit_field_line_id_patch(self):
        c = Customer.objects.create(store=self.store, name="L")
        response = self._patch(c, "line_id", "@example")
        self.assertEqual(response.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.line_id, "@example")

    def test_edit_field_line_id_empty_to_null(self):
        c = Customer.objects.create(store=self.store, name="L2", line_id="@old")
        response = self._patch(c, "line_id", "")
        self.assertEqual(response.status_code, 200)
        c.refresh_from_db()
        self.assertIsNone(c.line_id)

    def test_edit_field_memo_patch(self):
        c = Customer.objects.create(store=self.store, name="M")
        text = "長いメモテキスト" * 5
        response = self._patch(c, "memo", text)
        self.assertEqual(response.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.memo, text)

    def test_edit_field_memo_empty_to_null(self):
        c = Customer.objects.create(store=self.store, name="M2", memo="x")
        response = self._patch(c, "memo", "")
        self.assertEqual(response.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.memo, "")

    def test_edit_field_invalid_field(self):
        c = Customer.objects.create(store=self.store, name="BadF")
        response = self._patch(c, "unknown_field", "x")
        self.assertEqual(response.status_code, 400)

    @patch("ui.staff.views.customer.HearingTaskService.sync_tasks")
    def test_edit_field_hearing_triggers_sync_tasks(self, mock_sync):
        c = Customer.objects.create(store=self.store, name="Hear")
        response = self._patch(c, "age", "25")
        self.assertEqual(response.status_code, 200)
        mock_sync.assert_called_once()
        args, _kwargs = mock_sync.call_args
        self.assertEqual(args[0].pk, c.pk)

    @patch("ui.staff.views.customer.HearingTaskService.sync_tasks")
    def test_edit_field_non_hearing_no_sync_tasks(self, mock_sync):
        c = Customer.objects.create(store=self.store, name="NH")
        response = self._patch(c, "name", "改名")
        self.assertEqual(response.status_code, 200)
        mock_sync.assert_not_called()

    @patch("ui.staff.views.customer.HearingTaskService.sync_tasks")
    def test_edit_field_non_hearing_line_id_no_sync_tasks(self, mock_sync):
        c = Customer.objects.create(store=self.store, name="L3")
        response = self._patch(c, "line_id", "@z")
        self.assertEqual(response.status_code, 200)
        mock_sync.assert_not_called()

    @patch("ui.staff.views.customer.HearingTaskService.sync_tasks")
    def test_edit_field_non_hearing_memo_no_sync_tasks(self, mock_sync):
        c = Customer.objects.create(store=self.store, name="M3")
        response = self._patch(c, "memo", "note")
        self.assertEqual(response.status_code, 200)
        mock_sync.assert_not_called()

    def test_edit_field_success_toast(self):
        c = Customer.objects.create(store=self.store, name="Toast")
        response = self._patch(c, "name", "Toast2")
        self.assertEqual(response.status_code, 200)
        trigger_raw = response.headers.get("HX-Trigger", "")
        payload = json.loads(trigger_raw)
        self.assertEqual(payload["showToast"]["message"], "保存しました")
        self.assertEqual(payload["showToast"]["type"], "success")

    def test_edit_field_returns_zone_fragment(self):
        c = Customer.objects.create(store=self.store, name="Frag")
        response = self._patch(c, "age", "33")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="zone-age"')

    def test_edit_field_store_scope(self):
        c = Customer.objects.create(store=self.other_store, name="OS")
        response = self._patch(c, "name", "hack")
        self.assertEqual(response.status_code, 404)

    def test_edit_field_requires_auth(self):
        self.client.logout()
        c = Customer.objects.create(store=self.store, name="Auth")
        response = self._patch(c, "name", "y")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/s/login/"))

    def test_edit_field_patch_body_parsing(self):
        c = Customer.objects.create(store=self.store, name="旧")
        body = urlencode({"field": "name", "value": "太郎"})
        response = self.client.generic(
            "PATCH",
            self._patch_url(c),
            data=body,
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.name, "太郎")

    def test_edit_field_area_whitespace_only_to_null(self):
        c = Customer.objects.create(store=self.store, name="WS", area="old")
        response = self._patch(c, "area", "   ")
        self.assertEqual(response.status_code, 200)
        c.refresh_from_db()
        self.assertIsNone(c.area)

    def test_edit_field_line_id_whitespace_only_to_null(self):
        c = Customer.objects.create(store=self.store, name="WS2", line_id="@old")
        response = self._patch(c, "line_id", "  \t  ")
        self.assertEqual(response.status_code, 200)
        c.refresh_from_db()
        self.assertIsNone(c.line_id)

    def test_edit_field_memo_whitespace_only_to_null(self):
        c = Customer.objects.create(store=self.store, name="WS3", memo="old")
        response = self._patch(c, "memo", "   ")
        self.assertEqual(response.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.memo, "")

    def test_edit_field_validation_error_returns_zone_fragment(self):
        """BusinessError は使わない前提の代替: バリデーション失敗時もゾーンフラグメントを返す。"""
        c = Customer.objects.create(store=self.store, name="Val")
        response = self._patch(c, "age", "not-int")
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, 'id="zone-age"', status_code=422)
        self.assertContains(response, "年齢は整数で入力してください", status_code=422)


class US03VisitListTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store_group = StoreGroup.objects.create(name="US03 Visit Group")
        cls.store = Store.objects.create(store_group=cls.store_group, name="US03 Visit Store")
        cls.other_store = Store.objects.create(store_group=cls.store_group, name="US03 Visit Other")
        cls.staff = Staff.objects.create_user(
            store=cls.store,
            display_name="Visit Staff",
            role="staff",
            staff_type="regular",
        )

    def setUp(self):
        self.client.force_login(self.staff)

    def _list_url(self, customer):
        return f"/s/customers/{customer.pk}/visits/"

    def test_visit_list_get(self):
        c = Customer.objects.create(store=self.store, name="VL")
        response = self.client.get(self._list_url(c))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/staff/visit_list.html")

    def test_visit_list_requires_auth(self):
        self.client.logout()
        c = Customer.objects.create(store=self.store, name="V")
        response = self.client.get(self._list_url(c))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/s/login/"))

    def test_visit_list_active_tab(self):
        c = Customer.objects.create(store=self.store, name="T")
        response = self.client.get(self._list_url(c))
        self.assertEqual(response.context["active_tab"], "customers")

    def test_visit_list_displays_visits(self):
        c = Customer.objects.create(store=self.store, name="表示")
        Visit.objects.create(
            store=self.store,
            customer=c,
            staff=self.staff,
            visited_at=date(2026, 3, 15),
            conversation_memo="会話メモ",
        )
        response = self.client.get(self._list_url(c))
        self.assertContains(response, "2026/3/15")
        self.assertContains(response, "Visit Staff")
        self.assertContains(response, "会話メモ")

    def test_visit_list_limit_20(self):
        c = Customer.objects.create(store=self.store, name="25件")
        today = timezone.localdate()
        for i in range(25):
            Visit.objects.create(
                store=self.store,
                customer=c,
                staff=self.staff,
                visited_at=today - timedelta(days=i),
            )
        response = self.client.get(self._list_url(c))
        self.assertEqual(len(response.context["visits"]), 20)

    def test_visit_list_order_desc(self):
        c = Customer.objects.create(store=self.store, name="順序")
        d_old = date(2025, 1, 1)
        d_new = date(2026, 1, 1)
        Visit.objects.create(
            store=self.store,
            customer=c,
            staff=self.staff,
            visited_at=d_old,
            conversation_memo="古い",
        )
        Visit.objects.create(
            store=self.store,
            customer=c,
            staff=self.staff,
            visited_at=d_new,
            conversation_memo="新しい",
        )
        response = self.client.get(self._list_url(c))
        content = response.content.decode()
        self.assertLess(content.find("新しい"), content.find("古い"))

    def test_visit_list_same_day_order_stable(self):
        c = Customer.objects.create(store=self.store, name="同日V")
        d = timezone.localdate()
        v1 = Visit.objects.create(
            store=self.store,
            customer=c,
            staff=self.staff,
            visited_at=d,
            conversation_memo="first",
        )
        v2 = Visit.objects.create(
            store=self.store,
            customer=c,
            staff=self.staff,
            visited_at=d,
            conversation_memo="second",
        )
        Visit.objects.filter(pk=v1.pk).update(created_at=timezone.now() - timedelta(hours=3))
        Visit.objects.filter(pk=v2.pk).update(created_at=timezone.now() - timedelta(hours=1))
        response = self.client.get(self._list_url(c))
        content = response.content.decode()
        self.assertLess(content.find("second"), content.find("first"))

    def test_visit_list_memo_truncated(self):
        c = Customer.objects.create(store=self.store, name="切詰")
        long_memo = "い" * 60
        Visit.objects.create(
            store=self.store,
            customer=c,
            staff=self.staff,
            visited_at=timezone.localdate(),
            conversation_memo=long_memo,
        )
        response = self.client.get(self._list_url(c))
        self.assertNotContains(response, long_memo)
        self.assertContains(response, "…")

    def test_visit_list_empty(self):
        c = Customer.objects.create(store=self.store, name="空")
        response = self.client.get(self._list_url(c))
        self.assertContains(response, "来店記録はまだありません")

    def test_visit_list_store_scope(self):
        c = Customer.objects.create(store=self.other_store, name="他店")
        response = self.client.get(self._list_url(c))
        self.assertEqual(response.status_code, 404)

    def test_visit_list_nonexistent_customer(self):
        response = self.client.get(f"/s/customers/{uuid.uuid4()}/visits/")
        self.assertEqual(response.status_code, 404)

    def test_visit_list_back_link(self):
        c = Customer.objects.create(store=self.store, name="戻る名")
        response = self.client.get(self._list_url(c))
        self.assertContains(response, f"/s/customers/{c.pk}/")
        self.assertContains(response, "戻る名")

    def test_visit_list_read_only(self):
        c = Customer.objects.create(store=self.store, name="RO")
        response = self.client.post(self._list_url(c), {})
        self.assertEqual(response.status_code, 405)

    def test_visit_list_session_url(self):
        c = Customer.objects.create(store=self.store, name="SU")
        response = self.client.get(self._list_url(c))
        self.assertEqual(response.context["session_url"], f"/s/customers/{c.pk}/session/")


class US03SessionHearingSummaryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store_group = StoreGroup.objects.create(name="US03 Hearing Summary Group")
        cls.store = Store.objects.create(store_group=cls.store_group, name="US03 Hearing Store")
        cls.staff = Staff.objects.create_user(
            store=cls.store,
            display_name="Hearing Staff",
            role="staff",
            staff_type="regular",
        )

    def setUp(self):
        self.client.force_login(self.staff)

    def _session_url(self, customer):
        return f"/s/customers/{customer.pk}/session/"

    def _reset_hearing_tasks_closed(self, customer, field_names):
        HearingTask.objects.filter(store=self.store, customer=customer).delete()
        for field_name in field_names:
            HearingTask.objects.create(
                store=self.store,
                customer=customer,
                field_name=field_name,
                status=HearingTask.STATUS_CLOSED,
            )

    def test_session_hearing_summary_all_done(self):
        c = Customer.objects.create(
            store=self.store,
            name="HearDone",
            age=20,
            area="渋谷",
            shisha_experience="beginner",
        )
        self._reset_hearing_tasks_closed(c, ("age", "area", "shisha_experience"))
        response = self.client.get(self._session_url(c))
        self.assertContains(response, "ヒアリング完了")
        self.assertContains(response, "20代")
        self.assertContains(response, "渋谷")
        self.assertContains(response, "初心者")

    def test_session_hearing_summary_partial(self):
        c = Customer.objects.create(
            store=self.store,
            name="HearPartial",
            age=20,
            area=None,
            shisha_experience=None,
        )
        self._reset_hearing_tasks_closed(c, ("age", "area", "shisha_experience"))
        response = self.client.get(self._session_url(c))
        self.assertContains(response, "20代")
        self.assertGreaterEqual(response.content.decode().count("未入力"), 2)

    def test_session_hearing_summary_edit_link(self):
        c = Customer.objects.create(
            store=self.store,
            name="HearEdit",
            age=30,
            area="港区",
            shisha_experience="intermediate",
        )
        self._reset_hearing_tasks_closed(c, ("age", "area", "shisha_experience"))
        response = self.client.get(self._session_url(c))
        self.assertContains(response, f'/s/customers/{c.pk}/edit/')
        self.assertContains(response, "顧客情報を編集")

    def test_session_hearing_summary_not_shown_when_tasks_open(self):
        c = Customer.objects.create(
            store=self.store,
            name="HearOpen",
            age=20,
            area="渋谷",
            shisha_experience="beginner",
        )
        HearingTask.objects.filter(store=self.store, customer=c).delete()
        HearingTask.objects.create(
            store=self.store,
            customer=c,
            field_name="age",
            status=HearingTask.STATUS_OPEN,
        )
        response = self.client.get(self._session_url(c))
        self.assertNotContains(response, "ヒアリング完了")

    def test_hearing_summary_fragment_returns_latest_data(self):
        c = Customer.objects.create(
            store=self.store,
            name="FragLatest",
            age=10,
            area="旧エリア",
            shisha_experience="beginner",
        )
        fragment_url = f"/s/customers/{c.pk}/session/hearing-summary/"
        response_before = self.client.get(fragment_url)
        self.assertEqual(response_before.status_code, 200)
        self.assertContains(response_before, "10代")

        Customer.objects.filter(pk=c.pk).update(age=20)
        response_after = self.client.get(fragment_url)
        self.assertEqual(response_after.status_code, 200)
        self.assertContains(response_after, "20代")
        self.assertNotContains(response_after, "10代")
