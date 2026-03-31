from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import QRToken, Staff
from tenants.models import Store, StoreGroup


class StaffAuthViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store_group = StoreGroup.objects.create(name="Test Group")
        cls.store = Store.objects.create(store_group=cls.store_group, name="Test Store")
        cls.staff = Staff.objects.create_user(
            store=cls.store,
            display_name="Test Staff",
            role="staff",
            staff_type="regular",
        )
        cls.owner = Staff.objects.create_user(
            store=cls.store,
            display_name="Test Owner",
            role="owner",
            staff_type="owner",
        )

    def _make_token(self, staff, *, expires_at, is_used=False):
        return QRToken.objects.create(
            staff=staff,
            token=QRToken.generate_token(),
            expires_at=expires_at,
            is_used=is_used,
        )

    def test_login_page_get(self):
        response = self.client.get("/s/login/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/staff/login.html")

    def test_login_valid_token(self):
        tok = self._make_token(
            self.staff,
            expires_at=timezone.now() + timedelta(hours=24),
        )
        response = self.client.post("/s/login/", {"token": tok.token})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/customers/")
        self.assertIn("_auth_user_id", self.client.session)
        tok.refresh_from_db()
        self.assertTrue(tok.is_used)
        follow = self.client.get("/s/customers/")
        self.assertEqual(follow.status_code, 200)

    def test_login_invalid_token(self):
        response = self.client.post("/s/login/", {"token": "not-a-real-token"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "QR コードが無効です")

    def test_login_expired_token(self):
        tok = self._make_token(
            self.staff,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        response = self.client.post("/s/login/", {"token": tok.token})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "有効期限が切れています")

    def test_login_empty_token(self):
        response = self.client.post("/s/login/", {"token": ""})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "QR コードを入力してください")

    def test_login_redirect_if_authenticated(self):
        self.client.force_login(self.staff)
        response = self.client.get("/s/login/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/customers/")

    def test_logout_post(self):
        self.client.force_login(self.staff)
        response = self.client.post("/s/logout/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/login/")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_get_not_allowed(self):
        response = self.client.get("/s/logout/")
        self.assertEqual(response.status_code, 405)

    def test_stub_requires_auth(self):
        response = self.client.get("/s/customers/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/s/login/"))

    def test_stub_authenticated(self):
        self.client.force_login(self.staff)
        response = self.client.get("/s/customers/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/staff/stub.html")

    def test_stub_active_tab(self):
        self.client.force_login(self.staff)
        response = self.client.get("/s/customers/")
        self.assertEqual(response.context["active_tab"], "customers")

    def test_base_staff_topbar(self):
        self.client.force_login(self.staff)
        response = self.client.get("/s/customers/")
        self.assertContains(response, self.staff.display_name)

    def test_base_staff_bottomtab(self):
        self.client.force_login(self.staff)
        response = self.client.get("/s/customers/")
        self.assertContains(response, 'href="/s/customers/"')
        self.assertContains(response, "接客")
        self.assertContains(response, "来店記録")
        self.assertContains(response, "マッチング")

    def test_login_used_token(self):
        tok = self._make_token(
            self.owner,
            expires_at=timezone.now() + timedelta(hours=24),
            is_used=True,
        )
        response = self.client.post("/s/login/", {"token": tok.token})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "既に使用されています")

    def test_login_inactive_staff(self):
        inactive = Staff.objects.create_user(
            store=self.store,
            display_name="Inactive",
            role="staff",
            staff_type="regular",
            is_active=False,
        )
        tok = self._make_token(
            inactive,
            expires_at=timezone.now() + timedelta(hours=24),
        )
        response = self.client.post("/s/login/", {"token": tok.token})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "無効化されています")

    def test_stub_rejects_non_staff_role(self):
        self.client.force_login(self.staff)
        Staff.objects.filter(pk=self.staff.pk).update(role="invalid_role")
        response = self.client.get("/s/customers/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/login/")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_bottomtab_disabled_tabs(self):
        self.client.force_login(self.staff)
        response = self.client.get("/s/customers/")
        html = response.content.decode()
        self.assertEqual(html.count('aria-disabled="true"'), 3)

    def test_topbar_logout_form(self):
        self.client.force_login(self.staff)
        response = self.client.get("/s/customers/")
        html = response.content.decode()
        self.assertIn('action="/s/logout/"', html)
        self.assertIn("csrfmiddlewaretoken", html)
        self.assertIn('name="csrfmiddlewaretoken"', html)
