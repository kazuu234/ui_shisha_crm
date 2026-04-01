from datetime import date, timedelta
from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Staff
from core.exceptions import BusinessError
from customers.models import Customer
from tasks.models import HearingTask
from tenants.models import Store, StoreGroup
from visits.models import Visit


class OwnerCustomerViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store_group = StoreGroup.objects.create(name="Owner Customer Group")
        cls.store = Store.objects.create(
            store_group=cls.store_group, name="Owner Customer Store"
        )
        cls.other_store = Store.objects.create(
            store_group=cls.store_group, name="Owner Customer Other"
        )
        cls.staff = Staff.objects.create_user(
            store=cls.store,
            display_name="OC Staff",
            role="staff",
            staff_type="regular",
        )
        cls.owner = Staff.objects.create_user(
            store=cls.store,
            display_name="OC Owner",
            role="owner",
            staff_type="owner",
        )

    def setUp(self):
        self.client.force_login(self.owner)

    # --- List #1–3 ---

    def test_customer_list_owner(self):
        Customer.objects.create(store=self.store, name="一覧太郎")
        response = self.client.get(reverse("owner:customer-list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/owner/customer_list.html")
        self.assertContains(response, "一覧太郎")
        self.assertContains(response, "顧客管理")

    def test_customer_list_unauthenticated(self):
        self.client.logout()
        response = self.client.get(reverse("owner:customer-list"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/o/login/"))

    def test_customer_list_staff_redirect(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("owner:customer-list"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/customers/")

    # --- List #4–5 ---

    def test_customer_list_search(self):
        Customer.objects.create(store=self.store, name="山田太郎")
        Customer.objects.create(store=self.store, name="田中花子")
        response = self.client.get(
            reverse("owner:customer-list"), {"search": "山田"}
        )
        self.assertContains(response, "山田太郎")
        self.assertNotContains(response, "田中花子")

    def test_customer_list_segment_filter(self):
        Customer.objects.create(store=self.store, name="新規君", segment="new")
        Customer.objects.create(store=self.store, name="常連君", segment="regular")
        response = self.client.get(reverse("owner:customer-list"), {"segment": "new"})
        self.assertContains(response, "新規君")
        self.assertNotContains(response, "常連君")

    # --- List #6–9 ---

    def test_customer_list_sort_name(self):
        Customer.objects.create(store=self.store, name="ZZZ")
        Customer.objects.create(store=self.store, name="AAA")
        response = self.client.get(reverse("owner:customer-list"), {"sort": "name"})
        content = response.content
        self.assertLess(content.find(b"AAA"), content.find(b"ZZZ"))

    def test_customer_list_sort_visit_count(self):
        Customer.objects.create(store=self.store, name="Low", visit_count=1)
        Customer.objects.create(store=self.store, name="High", visit_count=10)
        response = self.client.get(
            reverse("owner:customer-list"), {"sort": "-visit_count"}
        )
        content = response.content
        self.assertLess(content.find(b"High"), content.find(b"Low"))

    def test_customer_list_sort_last_visited(self):
        c_visit = Customer.objects.create(store=self.store, name="HasVisit")
        c_none = Customer.objects.create(store=self.store, name="NoVisit")
        today = timezone.localdate()
        Visit.objects.create(
            store=self.store,
            customer=c_visit,
            staff=self.staff,
            visited_at=today,
        )
        response = self.client.get(reverse("owner:customer-list"))
        self.assertEqual(response.status_code, 200)
        content = response.content
        self.assertLess(content.find(b"HasVisit"), content.find(b"NoVisit"))

    def test_customer_list_sort_invalid(self):
        Customer.objects.create(store=self.store, name="A", visit_count=0)
        Customer.objects.create(store=self.store, name="B", visit_count=0)
        r_bad = self.client.get(
            reverse("owner:customer-list"), {"sort": "invalid_field"}
        )
        r_default = self.client.get(reverse("owner:customer-list"))
        self.assertEqual(
            [c.pk for c in r_bad.context["customers"]],
            [c.pk for c in r_default.context["customers"]],
        )

    # --- List #10–12 ---

    def test_customer_list_pagination(self):
        for i in range(26):
            Customer.objects.create(store=self.store, name=f"C{i:02d}")
        r1 = self.client.get(reverse("owner:customer-list"))
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(len(r1.context["customers"]), 25)
        r2 = self.client.get(reverse("owner:customer-list"), {"page": 2})
        self.assertEqual(len(r2.context["customers"]), 1)

    def test_customer_list_htmx_fragment(self):
        Customer.objects.create(store=self.store, name="HX")
        response = self.client.get(
            reverse("owner:customer-list"),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/owner/_customer_table.html")
        self.assertTemplateNotUsed(response, "ui/owner/customer_list.html")

    def test_customer_list_store_scope(self):
        Customer.objects.create(store=self.store, name="自店")
        Customer.objects.create(store=self.other_store, name="他店")
        response = self.client.get(reverse("owner:customer-list"))
        self.assertContains(response, "自店")
        self.assertNotContains(response, "他店")

    # --- List #13–15 ---

    def test_customer_list_last_visited_annotation(self):
        c = Customer.objects.create(store=self.store, name="Annot")
        d = timezone.localdate()
        Visit.objects.create(
            store=self.store,
            customer=c,
            staff=self.staff,
            visited_at=d,
        )
        response = self.client.get(reverse("owner:customer-list"))
        self.assertContains(response, d.strftime("%Y/%m/%d"))

        c2 = Customer.objects.create(store=self.store, name="Never")
        r2 = self.client.get(reverse("owner:customer-list"))
        self.assertContains(r2, "未来店")

    def test_customer_list_open_task_count(self):
        c = Customer.objects.create(store=self.store, name="Tasks")
        HearingTask.objects.create(
            store=self.store,
            customer=c,
            field_name="age",
            status=HearingTask.STATUS_OPEN,
        )
        HearingTask.objects.create(
            store=self.store,
            customer=c,
            field_name="area",
            status=HearingTask.STATUS_CLOSED,
        )
        response = self.client.get(reverse("owner:customer-list"))
        listed = {x.name: x.open_task_count for x in response.context["customers"]}
        self.assertEqual(listed.get("Tasks"), 1)

    def test_customer_list_deleted_visit_excluded(self):
        c = Customer.objects.create(store=self.store, name="DelVisit")
        Visit.objects.create(
            store=self.store,
            customer=c,
            staff=self.staff,
            visited_at=date(2024, 1, 1),
        )
        Visit.objects.all_with_deleted().create(
            store=self.store,
            customer=c,
            staff=self.staff,
            visited_at=date(2025, 6, 1),
            is_deleted=True,
        )
        response = self.client.get(reverse("owner:customer-list"))
        self.assertContains(response, "2024/01/01")
        self.assertNotContains(response, "2025/06/01")

    # --- List #36, #37 ---

    def test_customer_list_nulls_last(self):
        c_old = Customer.objects.create(store=self.store, name="OldVisit")
        c_new = Customer.objects.create(store=self.store, name="NewVisit")
        c_never = Customer.objects.create(store=self.store, name="NeverVisit")
        today = timezone.localdate()
        Visit.objects.create(
            store=self.store,
            customer=c_new,
            staff=self.staff,
            visited_at=today,
        )
        Visit.objects.create(
            store=self.store,
            customer=c_old,
            staff=self.staff,
            visited_at=today - timedelta(days=10),
        )
        response = self.client.get(
            reverse("owner:customer-list"), {"sort": "-last_visited_at"}
        )
        content = response.content
        self.assertLess(content.find(b"NewVisit"), content.find(b"OldVisit"))
        self.assertLess(content.find(b"OldVisit"), content.find(b"NeverVisit"))

    def test_sidebar_active_customers(self):
        response = self.client.get(reverse("owner:customer-list"))
        self.assertEqual(response.context["active_sidebar"], "customers")

    # --- Detail #16–24 ---

    def test_customer_detail_owner(self):
        c = Customer.objects.create(
            store=self.store,
            name="詳細花子",
            segment="repeat",
            visit_count=2,
            age=28,
            area="港区",
            shisha_experience="beginner",
            line_id="@x",
            memo="メモ",
        )
        response = self.client.get(reverse("owner:customer-detail", args=[c.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/owner/customer_detail.html")
        self.assertContains(response, "詳細花子")
        self.assertContains(response, "28歳")

    def test_customer_detail_visits(self):
        c = Customer.objects.create(store=self.store, name="履歴")
        d = timezone.localdate()
        Visit.objects.create(
            store=self.store,
            customer=c,
            staff=self.staff,
            visited_at=d,
            conversation_memo="会話メモ",
        )
        response = self.client.get(reverse("owner:customer-detail", args=[c.pk]))
        self.assertContains(response, d.strftime("%Y/%m/%d"))
        self.assertContains(response, "会話メモ")

    def test_customer_detail_visits_staff_name(self):
        c = Customer.objects.create(store=self.store, name="StaffDisp")
        Visit.objects.create(
            store=self.store,
            customer=c,
            staff=self.staff,
            visited_at=timezone.localdate(),
        )
        response = self.client.get(reverse("owner:customer-detail", args=[c.pk]))
        self.assertContains(response, "OC Staff")

    def test_customer_detail_open_tasks(self):
        c = Customer.objects.create(store=self.store, name="OpenT")
        HearingTask.objects.create(
            store=self.store,
            customer=c,
            field_name="age",
            status=HearingTask.STATUS_OPEN,
        )
        HearingTask.objects.create(
            store=self.store,
            customer=c,
            field_name="area",
            status=HearingTask.STATUS_CLOSED,
        )
        response = self.client.get(reverse("owner:customer-detail", args=[c.pk]))
        open_tasks = response.context["open_tasks"]
        self.assertEqual(len(open_tasks), 1)
        self.assertEqual(open_tasks[0]["field_name"], "age")
        self.assertEqual(open_tasks[0]["field_label"], "年齢")

    def test_customer_detail_all_tasks_done(self):
        c = Customer.objects.create(store=self.store, name="Done")
        HearingTask.objects.create(
            store=self.store,
            customer=c,
            field_name="age",
            status=HearingTask.STATUS_CLOSED,
        )
        response = self.client.get(reverse("owner:customer-detail", args=[c.pk]))
        self.assertContains(response, "全てのヒアリングが完了しています")

    def test_customer_detail_not_found(self):
        response = self.client.get(
            reverse("owner:customer-detail", args=[uuid4()])
        )
        self.assertEqual(response.status_code, 404)

    def test_customer_detail_other_store(self):
        c = Customer.objects.create(store=self.other_store, name="他人")
        response = self.client.get(reverse("owner:customer-detail", args=[c.pk]))
        self.assertEqual(response.status_code, 404)

    def test_customer_detail_edit_link(self):
        c = Customer.objects.create(store=self.store, name="EditL")
        response = self.client.get(reverse("owner:customer-detail", args=[c.pk]))
        self.assertContains(response, reverse("owner:customer-edit", args=[c.pk]))

    def test_customer_detail_toast(self):
        c = Customer.objects.create(store=self.store, name="ToastD")
        session = self.client.session
        session["toast"] = {"message": "テストトースト", "type": "success"}
        session.save()
        response = self.client.get(reverse("owner:customer-detail", args=[c.pk]))
        self.assertContains(response, "テストトースト")
        self.client.get(reverse("owner:customer-detail", args=[c.pk]))
        self.assertNotIn("toast", self.client.session)

    # --- Edit #25–35 ---

    def test_customer_edit_get(self):
        c = Customer.objects.create(
            store=self.store,
            name="編集前",
            age=20,
            area="渋谷",
        )
        response = self.client.get(reverse("owner:customer-edit", args=[c.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/owner/customer_edit.html")
        self.assertContains(response, "編集前")
        self.assertContains(response, "20")

    @patch("ui.owner.views.customer.HearingTaskService.sync_tasks")
    def test_customer_edit_post_valid(self, mock_sync):
        c = Customer.objects.create(store=self.store, name="保存前", age=None)
        response = self.client.post(
            reverse("owner:customer-edit", args=[c.pk]),
            {
                "name": "保存後",
                "age": "30",
                "area": "",
                "shisha_experience": "",
                "line_id": "",
                "memo": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url, reverse("owner:customer-detail", args=[c.pk])
        )
        c.refresh_from_db()
        self.assertEqual(c.name, "保存後")
        self.assertEqual(c.age, 30)
        mock_sync.assert_called_once()
        detail = self.client.get(response.url)
        self.assertContains(detail, "顧客情報を更新しました")

    def test_customer_edit_post_invalid_name_empty(self):
        c = Customer.objects.create(store=self.store, name="必須")
        response = self.client.post(
            reverse("owner:customer-edit", args=[c.pk]),
            {
                "name": "",
                "age": "",
                "area": "",
                "shisha_experience": "",
                "line_id": "",
                "memo": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "名前を入力してください")

    @patch("ui.owner.views.customer.HearingTaskService.sync_tasks")
    def test_customer_edit_sync_tasks_called(self, mock_sync):
        c = Customer.objects.create(store=self.store, name="Sync", age=None)
        self.client.post(
            reverse("owner:customer-edit", args=[c.pk]),
            {
                "name": "Sync",
                "age": "22",
                "area": "",
                "shisha_experience": "",
                "line_id": "",
                "memo": "",
            },
        )
        mock_sync.assert_called_once()

    @patch("ui.owner.views.customer.HearingTaskService.sync_tasks")
    def test_customer_edit_sync_tasks_not_called(self, mock_sync):
        c = Customer.objects.create(store=self.store, name="NoSync", memo="")
        self.client.post(
            reverse("owner:customer-edit", args=[c.pk]),
            {
                "name": "NoSync",
                "age": "",
                "area": "",
                "shisha_experience": "",
                "line_id": "",
                "memo": "だけ変える",
            },
        )
        mock_sync.assert_not_called()

    def test_customer_edit_empty_to_none(self):
        c = Customer.objects.create(
            store=self.store,
            name="Norm",
            age=10,
            area="旧",
            shisha_experience="none",
            line_id="@old",
            memo="old",
        )
        self.client.post(
            reverse("owner:customer-edit", args=[c.pk]),
            {
                "name": "Norm",
                "age": "",
                "area": "",
                "shisha_experience": "",
                "line_id": "",
                "memo": "",
            },
        )
        c.refresh_from_db()
        self.assertIsNone(c.age)
        self.assertIsNone(c.area)
        self.assertIsNone(c.shisha_experience)
        self.assertIsNone(c.line_id)
        self.assertEqual(c.memo, "")

    def test_customer_edit_unauthenticated(self):
        self.client.logout()
        c = Customer.objects.create(store=self.store, name="Auth")
        response = self.client.get(reverse("owner:customer-edit", args=[c.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/o/login/"))

    def test_customer_edit_staff_redirect(self):
        self.client.force_login(self.staff)
        c = Customer.objects.create(store=self.store, name="StaffEd")
        response = self.client.get(reverse("owner:customer-edit", args=[c.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/customers/")

    def test_customer_edit_not_found(self):
        response = self.client.get(
            reverse("owner:customer-edit", args=[uuid4()])
        )
        self.assertEqual(response.status_code, 404)

    def test_customer_edit_other_store(self):
        c = Customer.objects.create(store=self.other_store, name="OS")
        response = self.client.get(reverse("owner:customer-edit", args=[c.pk]))
        self.assertEqual(response.status_code, 404)

    @patch("ui.owner.views.customer.HearingTaskService.sync_tasks")
    def test_customer_edit_business_error(self, mock_sync):
        mock_sync.side_effect = BusinessError(
            code="test.error", message="業務エラーです"
        )
        c = Customer.objects.create(store=self.store, name="BE", age=None)
        response = self.client.post(
            reverse("owner:customer-edit", args=[c.pk]),
            {
                "name": "BE",
                "age": "40",
                "area": "",
                "shisha_experience": "",
                "line_id": "",
                "memo": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "業務エラーです")
        c.refresh_from_db()
        self.assertIsNone(c.age)
