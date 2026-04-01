import re
import uuid
from datetime import date, timedelta
from urllib.parse import urlencode

from django.test import TestCase
from django.utils import timezone

from accounts.models import Staff
from customers.models import Customer
from tasks.models import HearingTask
from tasks.services import HearingTaskService
from tenants.models import Store, StoreGroup
from visits.models import Visit


class SessionFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store_group = StoreGroup.objects.create(name="Session Test Group")
        cls.store = Store.objects.create(store_group=cls.store_group, name="Session Store")
        cls.other_store = Store.objects.create(store_group=cls.store_group, name="Other Session Store")
        cls.staff = Staff.objects.create_user(
            store=cls.store,
            display_name="Session Staff",
            role="staff",
            staff_type="regular",
        )

    def setUp(self):
        self.client.force_login(self.staff)

    def _session_url(self, customer):
        return f"/s/customers/{customer.pk}/session/"

    def test_session_get(self):
        c = Customer.objects.create(store=self.store, name="S1")
        response = self.client.get(self._session_url(c))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/staff/session.html")

    def test_session_requires_auth(self):
        self.client.logout()
        c = Customer.objects.create(store=self.store, name="S2")
        response = self.client.get(self._session_url(c))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/s/login/"))

    def test_session_active_tab(self):
        c = Customer.objects.create(store=self.store, name="S3")
        response = self.client.get(self._session_url(c))
        self.assertEqual(response.context["active_tab"], "session")

    def test_session_customer_header(self):
        c = Customer.objects.create(store=self.store, name="ヘッダー太郎", segment="new")
        response = self.client.get(self._session_url(c))
        self.assertContains(response, "ヘッダー太郎")
        self.assertContains(response, "badge-new")
        self.assertContains(response, "来店")

    def test_session_open_tasks(self):
        c = Customer.objects.create(store=self.store, name="TaskOpen")
        HearingTask.objects.create(
            store=self.store,
            customer=c,
            field_name="age",
            status=HearingTask.STATUS_OPEN,
        )
        response = self.client.get(self._session_url(c))
        self.assertContains(response, "zone-age")
        self.assertContains(response, "タップして入力")

    def test_session_no_tasks(self):
        c = Customer.objects.create(store=self.store, name="NoTask")
        response = self.client.get(self._session_url(c))
        self.assertContains(response, "全てのヒアリングが完了しています")

    def test_session_recent_visits(self):
        c = Customer.objects.create(store=self.store, name="VisitHist")
        today = timezone.localdate()
        for i in range(6):
            Visit.objects.create(
                store=self.store,
                customer=c,
                staff=self.staff,
                visited_at=today - timedelta(days=i),
                conversation_memo=f"memo{i}",
            )
        response = self.client.get(self._session_url(c))
        self.assertContains(response, "memo0")
        self.assertContains(response, "memo4")
        self.assertNotContains(response, "memo5")

    def test_session_store_scope(self):
        c = Customer.objects.create(store=self.other_store, name="Other")
        response = self.client.get(self._session_url(c))
        self.assertEqual(response.status_code, 404)

    def test_session_nonexistent_customer(self):
        response = self.client.get(f"/s/customers/{uuid.uuid4()}/session/")
        self.assertEqual(response.status_code, 404)

    def test_session_session_url(self):
        c = Customer.objects.create(store=self.store, name="URLCtx")
        response = self.client.get(self._session_url(c))
        self.assertEqual(response.context["session_url"], f"/s/customers/{c.pk}/session/")

    def test_session_visit_button_always_active(self):
        c = Customer.objects.create(store=self.store, name="VisitBtn")
        Visit.objects.create(
            store=self.store,
            customer=c,
            staff=self.staff,
            visited_at=timezone.localdate(),
        )
        response = self.client.get(self._session_url(c))
        self.assertContains(response, "来店記録を作成する")

    def test_field_update_patch(self):
        c = Customer.objects.create(store=self.store, name="PatchAge")
        HearingTask.objects.create(
            store=self.store,
            customer=c,
            field_name="age",
            status=HearingTask.STATUS_OPEN,
        )
        url = f"/s/customers/{c.pk}/field/"
        body = urlencode({"field": "age", "value": "20"})
        response = self.client.generic(
            "PATCH",
            url,
            data=body,
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.age, 20)
        t = HearingTask.objects.filter(customer=c, field_name="age").order_by("-pk").first()
        self.assertIsNotNone(t)
        closed = getattr(HearingTask, "STATUS_CLOSED", "closed")
        self.assertEqual(t.status, closed)

    def test_field_update_invalid_field(self):
        c = Customer.objects.create(store=self.store, name="BadField")
        url = f"/s/customers/{c.pk}/field/"
        body = urlencode({"field": "invalid", "value": "x"})
        response = self.client.generic(
            "PATCH",
            url,
            data=body,
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 422)

    def test_field_update_invalid_value(self):
        c = Customer.objects.create(store=self.store, name="BadVal")
        HearingTask.objects.create(
            store=self.store,
            customer=c,
            field_name="age",
            status=HearingTask.STATUS_OPEN,
        )
        url = f"/s/customers/{c.pk}/field/"
        body = urlencode({"field": "age", "value": "not-a-number"})
        response = self.client.generic(
            "PATCH",
            url,
            data=body,
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 422)

    def test_field_update_text_field(self):
        c = Customer.objects.create(store=self.store, name="AreaPatch")
        HearingTask.objects.create(
            store=self.store,
            customer=c,
            field_name="area",
            status=HearingTask.STATUS_OPEN,
        )
        url = f"/s/customers/{c.pk}/field/"
        body = urlencode({"field": "area", "value": "渋谷"})
        response = self.client.generic(
            "PATCH",
            url,
            data=body,
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.area, "渋谷")

    def test_field_update_all_tasks_done(self):
        c = Customer.objects.create(store=self.store, name="AllDone")
        HearingTaskService.generate_tasks(c)
        url = f"/s/customers/{c.pk}/field/"
        for payload in (
            {"field": "age", "value": "30"},
            {"field": "area", "value": "港区"},
            {"field": "shisha_experience", "value": "beginner"},
        ):
            body = urlencode(payload)
            response = self.client.generic(
                "PATCH",
                url,
                data=body,
                content_type="application/x-www-form-urlencoded",
            )
            self.assertEqual(response.status_code, 200, msg=payload)
        last_trigger = response.headers.get("HX-Trigger", "")
        self.assertIn("all-tasks-done", last_trigger)

    def test_field_update_store_scope(self):
        c = Customer.objects.create(store=self.other_store, name="Scope")
        url = f"/s/customers/{c.pk}/field/"
        body = urlencode({"field": "age", "value": "20"})
        response = self.client.generic(
            "PATCH",
            url,
            data=body,
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 404)

    def test_field_update_requires_auth(self):
        self.client.logout()
        c = Customer.objects.create(store=self.store, name="Auth")
        url = f"/s/customers/{c.pk}/field/"
        body = urlencode({"field": "age", "value": "20"})
        response = self.client.generic(
            "PATCH",
            url,
            data=body,
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/s/login/"))

    def test_field_update_area_empty_normalized_to_null(self):
        c = Customer.objects.create(store=self.store, name="AreaNull", area="渋谷")
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
        c.refresh_from_db()
        self.assertIsNone(c.area)

    def test_patch_body_parsing(self):
        c = Customer.objects.create(store=self.store, name="ParseBody")
        HearingTask.objects.create(
            store=self.store,
            customer=c,
            field_name="age",
            status=HearingTask.STATUS_OPEN,
        )
        url = f"/s/customers/{c.pk}/field/"
        body = "field=age&value=20"
        response = self.client.generic(
            "PATCH",
            url,
            data=body,
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.age, 20)

    def test_visit_create_post(self):
        c = Customer.objects.create(store=self.store, name="VisitPost")
        response = self.client.post(
            "/s/visits/create/",
            {
                "customer_id": str(c.pk),
                "conversation_memo": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        v = Visit.objects.filter(customer=c).order_by("-pk").first()
        self.assertIsNotNone(v)
        self.assertEqual(v.visited_at, date.today())
        self.assertEqual(v.staff_id, self.staff.pk)

    def test_visit_create_with_memo(self):
        c = Customer.objects.create(store=self.store, name="VisitMemo")
        memo = "桃のフレーバーが好み"
        response = self.client.post(
            "/s/visits/create/",
            {
                "customer_id": str(c.pk),
                "conversation_memo": memo,
            },
        )
        self.assertEqual(response.status_code, 200)
        v = Visit.objects.filter(customer=c).order_by("-pk").first()
        self.assertEqual(v.conversation_memo, memo)

    def test_visit_create_empty_memo(self):
        c = Customer.objects.create(store=self.store, name="VisitEmpty")
        response = self.client.post(
            "/s/visits/create/",
            {
                "customer_id": str(c.pk),
                "conversation_memo": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        v = Visit.objects.filter(customer=c).order_by("-pk").first()
        self.assertEqual(v.conversation_memo, "")

    def test_visit_create_hx_trigger(self):
        c = Customer.objects.create(store=self.store, name="HxTrig")
        response = self.client.post(
            "/s/visits/create/",
            {"customer_id": str(c.pk), "conversation_memo": ""},
        )
        hx = response.headers.get("HX-Trigger", "")
        self.assertIn("showToast", hx)

    def test_visit_create_updates_count_and_segment(self):
        c = Customer.objects.create(store=self.store, name="SegVisit")
        response = self.client.post(
            "/s/visits/create/",
            {"customer_id": str(c.pk), "conversation_memo": ""},
        )
        hx = response.headers.get("HX-Trigger", "")
        self.assertIn("visitCreated", hx)

    def test_session_header_fragment(self):
        c = Customer.objects.create(store=self.store, name="HdrFrag")
        Customer.objects.filter(pk=c.pk).update(visit_count=2)
        c.refresh_from_db()
        response = self.client.get(f"/s/customers/{c.pk}/session/header/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "HdrFrag")
        self.assertContains(response, "来店 2 回")

    def test_session_recent_visits_fragment(self):
        c = Customer.objects.create(store=self.store, name="RecFrag")
        Visit.objects.create(
            store=self.store,
            customer=c,
            staff=self.staff,
            visited_at=timezone.localdate(),
            conversation_memo="hello",
        )
        response = self.client.get(f"/s/customers/{c.pk}/session/recent-visits/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "hello")

    def test_session_header_fragment_store_scope(self):
        c = Customer.objects.create(store=self.other_store, name="NoHdr")
        response = self.client.get(f"/s/customers/{c.pk}/session/header/")
        self.assertEqual(response.status_code, 404)

    def test_visit_create_button_remains_active(self):
        c = Customer.objects.create(store=self.store, name="BtnActive")
        response = self.client.post(
            "/s/visits/create/",
            {"customer_id": str(c.pk), "conversation_memo": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "来店記録を作成する")

    def test_visit_create_button_replaced(self):
        c = Customer.objects.create(store=self.store, name="BtnReplace")
        response = self.client.post(
            "/s/visits/create/",
            {"customer_id": str(c.pk), "conversation_memo": ""},
        )
        self.assertContains(response, "来店記録を作成する")
        self.assertContains(response, "hx-post=\"/s/visits/create/\"")

    def test_visit_create_invalid_customer(self):
        rid = uuid.uuid4()
        response = self.client.post(
            "/s/visits/create/",
            {"customer_id": str(rid), "conversation_memo": ""},
        )
        self.assertEqual(response.status_code, 404)

    def test_visit_create_store_scope(self):
        c = Customer.objects.create(store=self.other_store, name="OtherV")
        response = self.client.post(
            "/s/visits/create/",
            {"customer_id": str(c.pk), "conversation_memo": ""},
        )
        self.assertEqual(response.status_code, 404)

    def test_visit_create_requires_auth(self):
        self.client.logout()
        c = Customer.objects.create(store=self.store, name="VAuth")
        response = self.client.post(
            "/s/visits/create/",
            {"customer_id": str(c.pk), "conversation_memo": ""},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/s/login/"))

    def test_visit_create_duplicate_same_day(self):
        c = Customer.objects.create(store=self.store, name="DupDay")
        for _ in range(2):
            response = self.client.post(
                "/s/visits/create/",
                {"customer_id": str(c.pk), "conversation_memo": "x"},
            )
            self.assertEqual(response.status_code, 200)
        self.assertEqual(Visit.objects.filter(customer=c).count(), 2)

    def test_bottomtab_session_link(self):
        c = Customer.objects.create(store=self.store, name="TabLink")
        response = self.client.get(self._session_url(c))
        self.assertContains(response, f'href="/s/customers/{c.pk}/session/"')
        self.assertContains(response, "接客")
        self.assertContains(response, "text-accent")

    def test_bottomtab_session_disabled_without_context(self):
        response = self.client.get("/s/customers/")
        content = response.content.decode()
        self.assertIn("接客", content)
        m = re.search(r"<nav\s[^>]*>([\s\S]*?)</nav>", content)
        self.assertIsNotNone(m)
        nav = m.group(0)
        self.assertRegex(nav, r"<button[^>]*disabled[^>]*>[\s\S]*接客")
