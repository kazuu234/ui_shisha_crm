from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import Staff
from customers.models import Customer
from tasks.models import HearingTask
from tenants.models import Store, StoreGroup
from ui.staff.forms.customer import CustomerCreateForm
from visits.models import Visit


class CustomerSelectAndSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store_group = StoreGroup.objects.create(name="Cust Test Group")
        cls.store = Store.objects.create(store_group=cls.store_group, name="Cust Test Store")
        cls.other_store = Store.objects.create(store_group=cls.store_group, name="Other Store")
        cls.staff = Staff.objects.create_user(
            store=cls.store,
            display_name="Cust Staff",
            role="staff",
            staff_type="regular",
        )
        cls.owner = Staff.objects.create_user(
            store=cls.store,
            display_name="Cust Owner",
            role="owner",
            staff_type="owner",
        )

    def setUp(self):
        self.client.force_login(self.staff)

    def test_customer_select_get(self):
        response = self.client.get("/s/customers/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/staff/customer_select.html")

    def test_customer_select_requires_auth(self):
        self.client.logout()
        response = self.client.get("/s/customers/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/s/login/"))

    def test_customer_select_rejects_non_staff_role(self):
        self.client.force_login(self.staff)
        Staff.objects.filter(pk=self.staff.pk).update(role="invalid_role")
        response = self.client.get("/s/customers/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/login/")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_customer_select_active_tab(self):
        response = self.client.get("/s/customers/")
        self.assertEqual(response.context["active_tab"], "customers")

    def test_customer_select_recent_order(self):
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        ca = Customer.objects.create(store=self.store, name="A")
        cb = Customer.objects.create(store=self.store, name="B")
        cc = Customer.objects.create(store=self.store, name="C")
        Visit.objects.create(
            store=self.store,
            customer=ca,
            staff=self.staff,
            visited_at=today,
        )
        Visit.objects.create(
            store=self.store,
            customer=cb,
            staff=self.staff,
            visited_at=yesterday,
        )
        response = self.client.get("/s/customers/")
        names = [c.name for c in response.context["customers"]]
        self.assertEqual(names[:3], ["A", "B", "C"])

    def test_customer_select_limit_20(self):
        for i in range(25):
            Customer.objects.create(store=self.store, name=f"Bulk{i}")
        response = self.client.get("/s/customers/")
        self.assertEqual(len(response.context["customers"]), 20)

    def test_customer_select_annotate_last_visited(self):
        c = Customer.objects.create(store=self.store, name="VisitMe")
        Visit.objects.create(
            store=self.store,
            customer=c,
            staff=self.staff,
            visited_at=timezone.localdate(),
        )
        response = self.client.get("/s/customers/")
        cust = response.context["customers"][0]
        self.assertIsNotNone(cust.last_visited_at)

    def test_customer_select_annotate_open_task_count(self):
        c = Customer.objects.create(store=self.store, name="Tasky")
        HearingTask.objects.create(
            store=self.store,
            customer=c,
            field_name="age",
            status=HearingTask.STATUS_OPEN,
        )
        response = self.client.get("/s/customers/")
        cust = next(x for x in response.context["customers"] if x.pk == c.pk)
        self.assertEqual(cust.open_task_count, 1)

    def test_customer_select_segment_badge(self):
        Customer.objects.create(store=self.store, name="Seg", segment="new")
        response = self.client.get("/s/customers/")
        self.assertContains(response, "badge-new")

    def test_customer_select_store_scope(self):
        Customer.objects.create(store=self.store, name="Mine")
        Customer.objects.create(store=self.other_store, name="Theirs")
        response = self.client.get("/s/customers/")
        names = [c.name for c in response.context["customers"]]
        self.assertIn("Mine", names)
        self.assertNotIn("Theirs", names)

    def test_customer_select_empty(self):
        response = self.client.get("/s/customers/")
        self.assertContains(response, "顧客がまだ登録されていません")

    def test_customer_search_get(self):
        Customer.objects.create(store=self.store, name="山田太郎")
        Customer.objects.create(store=self.store, name="佐藤")
        response = self.client.get("/s/customers/search/", {"q": "山田"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "山田太郎")
        self.assertNotContains(response, "佐藤")

    def test_customer_search_empty_query(self):
        Customer.objects.create(store=self.store, name="X")
        response = self.client.get("/s/customers/search/", {"q": ""})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "X")

    def test_customer_search_no_results(self):
        response = self.client.get("/s/customers/search/", {"q": "存在しない名前"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "見つかりませんでした")

    def test_customer_search_limit_20(self):
        for i in range(25):
            Customer.objects.create(store=self.store, name=f"検索テスト{i}")
        response = self.client.get("/s/customers/search/", {"q": "検索テスト"})
        html = response.content.decode()
        self.assertEqual(html.count('href="/s/customers/'), 20)

    def test_customer_search_store_scope(self):
        Customer.objects.create(store=self.store, name="店内検索")
        Customer.objects.create(store=self.other_store, name="店内検索他店")
        response = self.client.get("/s/customers/search/", {"q": "店内検索"})
        self.assertContains(response, "店内検索")
        self.assertNotContains(response, "店内検索他店")

    def test_customer_create_get(self):
        response = self.client.get("/s/customers/new/")
        self.assertEqual(response.status_code, 200)

    def test_customer_create_post_valid(self):
        response = self.client.post("/s/customers/new/", {"name": "テスト太郎"})
        self.assertEqual(response.status_code, 204)
        loc = response.headers.get("HX-Redirect", "")
        c = Customer.objects.get(name="テスト太郎")
        self.assertIn(f"/s/customers/{c.pk}/session/", loc)
        self.assertEqual(c.segment, "new")
        self.assertEqual(c.visit_count, 0)
        self.assertEqual(c.initial_visit_count, 0)

    def test_customer_create_with_initial_visit_count(self):
        response = self.client.post(
            "/s/customers/new/",
            {"name": "過去回数あり", "initial_visit_count": "3"},
        )
        self.assertEqual(response.status_code, 204)
        c = Customer.objects.get(name="過去回数あり")
        self.assertEqual(c.initial_visit_count, 3)

    def test_customer_create_without_initial_visit_count(self):
        response = self.client.post("/s/customers/new/", {"name": "過去回数なし"})
        self.assertEqual(response.status_code, 204)
        c = Customer.objects.get(name="過去回数なし")
        self.assertEqual(c.initial_visit_count, 0)

    def test_customer_create_negative_initial_visit_count(self):
        response = self.client.post(
            "/s/customers/new/",
            {"name": "負の値", "initial_visit_count": "-1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Customer.objects.filter(name="負の値").exists())
        self.assertIn("initial_visit_count", response.context["form"].errors)

    def test_create_form_has_initial_visit_count_field(self):
        form = CustomerCreateForm()
        self.assertIn("initial_visit_count", form.fields)

    def test_customer_create_generates_tasks(self):
        self.client.post("/s/customers/new/", {"name": "タスク生成"})
        customer = Customer.objects.get(name="タスク生成")
        tasks = list(HearingTask.objects.filter(customer=customer))
        self.assertEqual(len(tasks), 3)
        fields = {t.field_name for t in tasks}
        self.assertEqual(fields, {"age", "area", "shisha_experience"})
        for t in tasks:
            self.assertEqual(t.status, "open")

    def test_customer_create_empty_name(self):
        response = self.client.post("/s/customers/new/", {"name": ""})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "名前を入力してください")

    def test_customer_create_requires_auth(self):
        self.client.logout()
        response = self.client.post("/s/customers/new/", {"name": "X"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/s/login/"))

    def test_customer_card_link(self):
        c = Customer.objects.create(store=self.store, name="LinkMe")
        response = self.client.get("/s/customers/")
        self.assertContains(response, f'/s/customers/{c.pk}/session/')

    def test_customer_select_has_create_form(self):
        response = self.client.get("/s/customers/")
        self.assertContains(response, 'hx-post="/s/customers/new/"')

    def test_customer_select_has_search_input(self):
        response = self.client.get("/s/customers/")
        self.assertContains(response, 'hx-get="/s/customers/search/"')

    def test_session_page_reachable(self):
        customer = Customer.objects.create(store=self.store, name="SessionUser")
        url = f"/s/customers/{customer.pk}/session/"
        for user in (self.staff, self.owner):
            self.client.force_login(user)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertTemplateUsed(response, "ui/staff/session.html")
            self.assertEqual(response.context["active_tab"], "session")

    def test_create_customer_modal_error_no_double_nest(self):
        response = self.client.post("/s/customers/new/", {"name": ""})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "@click.away")
