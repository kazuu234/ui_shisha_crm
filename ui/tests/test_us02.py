from datetime import timedelta
from urllib.parse import urlencode

from django.test import TestCase
from django.utils import timezone

from accounts.models import Staff
from customers.models import Customer
from tasks.models import HearingTask
from tenants.models import Store, StoreGroup


class US02RecentAreasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store_group = StoreGroup.objects.create(name="US02 Recent Areas Group")
        cls.store = Store.objects.create(store_group=cls.store_group, name="US02 Store")
        cls.other_store = Store.objects.create(store_group=cls.store_group, name="US02 Other Store")
        cls.staff = Staff.objects.create_user(
            store=cls.store,
            display_name="US02 Staff",
            role="staff",
            staff_type="regular",
        )

    def setUp(self):
        self.client.force_login(self.staff)

    def _session_url(self, customer):
        return f"/s/customers/{customer.pk}/session/"

    def test_session_recent_areas_in_context(self):
        Customer.objects.create(store=self.store, name="履歴1", area="渋谷周辺")
        Customer.objects.create(store=self.store, name="履歴2", area="港区")
        Customer.objects.create(store=self.store, name="履歴3", area="渋谷周辺")
        c = Customer.objects.create(store=self.store, name="対象", area=None)
        HearingTask.objects.create(
            store=self.store,
            customer=c,
            field_name="area",
            status=HearingTask.STATUS_OPEN,
        )
        response = self.client.get(self._session_url(c))
        self.assertEqual(response.status_code, 200)
        areas = response.context["recent_areas"]
        self.assertIn("渋谷周辺", areas)
        self.assertIn("港区", areas)
        self.assertEqual(areas.count("渋谷周辺"), 1)

    def test_session_recent_areas_empty_when_no_data(self):
        c = Customer.objects.create(store=self.store, name="エリアなし", area=None)
        HearingTask.objects.create(
            store=self.store,
            customer=c,
            field_name="area",
            status=HearingTask.STATUS_OPEN,
        )
        response = self.client.get(self._session_url(c))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["recent_areas"], [])

    def test_session_recent_areas_store_scope(self):
        Customer.objects.create(store=self.other_store, name="他店", area="他店エリア")
        Customer.objects.create(store=self.store, name="自店", area="自店エリア")
        c = Customer.objects.create(store=self.store, name="対象2", area=None)
        HearingTask.objects.create(
            store=self.store,
            customer=c,
            field_name="area",
            status=HearingTask.STATUS_OPEN,
        )
        response = self.client.get(self._session_url(c))
        self.assertEqual(response.status_code, 200)
        areas = response.context["recent_areas"]
        self.assertIn("自店エリア", areas)
        self.assertNotIn("他店エリア", areas)

    def test_session_recent_areas_limit_10(self):
        base = timezone.now()
        for i in range(11):
            cust = Customer.objects.create(
                store=self.store,
                name=f"Limit{i}",
                area=f"エリア{i:02d}",
            )
            Customer.objects.filter(pk=cust.pk).update(
                updated_at=base - timedelta(minutes=i),
            )
        c = Customer.objects.create(store=self.store, name="LimitTarget", area=None)
        HearingTask.objects.create(
            store=self.store,
            customer=c,
            field_name="area",
            status=HearingTask.STATUS_OPEN,
        )
        response = self.client.get(self._session_url(c))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["recent_areas"]), 10)

    def test_session_recent_areas_empty_when_area_task_closed(self):
        Customer.objects.create(store=self.store, name="過去", area="渋谷周辺")
        c = Customer.objects.create(store=self.store, name="年齢のみ", area=None)
        HearingTask.objects.create(
            store=self.store,
            customer=c,
            field_name="age",
            status=HearingTask.STATUS_OPEN,
        )
        response = self.client.get(self._session_url(c))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["recent_areas"], [])

    def test_field_update_error_includes_recent_areas(self):
        Customer.objects.create(store=self.store, name="履歴顧客", area="履歴エリア表示用")
        c = Customer.objects.create(store=self.store, name="PATCH対象", area=None)
        HearingTask.objects.create(
            store=self.store,
            customer=c,
            field_name="area",
            status=HearingTask.STATUS_OPEN,
        )
        url = f"/s/customers/{c.pk}/field/"
        long_value = "x" * 256
        body = urlencode({"field": "area", "value": long_value})
        response = self.client.generic(
            "PATCH",
            url,
            data=body,
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "履歴エリア表示用", status_code=422)

    def test_field_update_empty_area_keeps_recent_areas(self):
        """area を空文字で PATCH 成功した場合も recent_areas が返ること"""
        Customer.objects.create(store=self.store, name="履歴あり", area="渋谷周辺")
        c = Customer.objects.create(store=self.store, name="空入力対象", area=None)
        HearingTask.objects.create(
            store=self.store,
            customer=c,
            field_name="area",
            status=HearingTask.STATUS_OPEN,
        )
        url = f"/s/customers/{c.pk}/field/"
        body = urlencode({"field": "area", "value": ""})
        response = self.client.generic(
            "PATCH",
            url,
            data=body,
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "渋谷周辺")

    def test_session_recent_areas_special_chars_escaped(self):
        """area に特殊文字が含まれても hx-vals が壊れないこと"""
        Customer.objects.create(store=self.store, name="特殊", area='渋谷"周辺')
        c = Customer.objects.create(store=self.store, name="対象特殊", area=None)
        HearingTask.objects.create(
            store=self.store,
            customer=c,
            field_name="area",
            status=HearingTask.STATUS_OPEN,
        )
        response = self.client.get(self._session_url(c))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # escapejs により " が \u0022 にエスケープされること
        self.assertIn("\\u0022", content)
        self.assertNotIn('value": "渋谷"周辺"', content)
