from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import QRToken, Staff
from tenants.models import Store, StoreGroup


class OwnerAuthViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store_group = StoreGroup.objects.create(name="Owner Test Group")
        cls.store = Store.objects.create(store_group=cls.store_group, name="Owner Test Store")
        cls.staff = Staff.objects.create_user(
            store=cls.store,
            display_name="Test Staff",
            role="staff",
            staff_type="regular",
        )
        cls.staff.set_unusable_password()
        cls.staff.save()
        cls.owner = Staff.objects.create_user(
            store=cls.store,
            display_name="Test Owner",
            role="owner",
            staff_type="owner",
        )
        cls.owner.set_unusable_password()
        cls.owner.save()

    def _make_token(self, staff, *, expires_at, is_used=False):
        return QRToken.objects.create(
            staff=staff,
            token=QRToken.generate_token(),
            expires_at=expires_at,
            is_used=is_used,
        )

    def test_owner_login_get(self):
        response = self.client.get("/o/login/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/owner/login.html")

    def test_owner_login_valid_token(self):
        tok = self._make_token(
            self.owner,
            expires_at=timezone.now() + timedelta(hours=24),
        )
        response = self.client.post("/o/login/", {"token": tok.token})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/o/dashboard/")
        self.assertIn("_auth_user_id", self.client.session)
        tok.refresh_from_db()
        self.assertTrue(tok.is_used)

    def test_owner_login_staff_token(self):
        tok = self._make_token(
            self.staff,
            expires_at=timezone.now() + timedelta(hours=24),
        )
        response = self.client.post("/o/login/", {"token": tok.token})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "オーナー専用です")
        tok.refresh_from_db()
        self.assertFalse(tok.is_used)

    def test_owner_login_invalid_token(self):
        response = self.client.post("/o/login/", {"token": "not-a-real-token"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "QR コードが無効です")

    def test_owner_login_expired_token(self):
        tok = self._make_token(
            self.owner,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        response = self.client.post("/o/login/", {"token": tok.token})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "有効期限が切れています")

    def test_owner_login_used_token(self):
        tok = self._make_token(
            self.owner,
            expires_at=timezone.now() + timedelta(hours=24),
            is_used=True,
        )
        response = self.client.post("/o/login/", {"token": tok.token})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "既に使用されています")

    def test_owner_login_redirect_if_authenticated(self):
        self.client.force_login(self.owner)
        response = self.client.get("/o/login/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/o/dashboard/")

    def test_owner_login_show_form_if_staff(self):
        self.client.force_login(self.staff)
        response = self.client.get("/o/login/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/owner/login.html")

    def test_owner_logout(self):
        self.client.force_login(self.owner)
        response = self.client.post("/o/logout/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/o/login/")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_dashboard_owner_renders(self):
        self.client.force_login(self.owner)
        response = self.client.get("/o/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/owner/dashboard.html")
        self.assertContains(response, 'id="chart-daily"')

    def test_dashboard_stub_unauthenticated(self):
        response = self.client.get("/o/dashboard/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/o/login/"))

    def test_dashboard_stub_staff_redirect(self):
        self.client.force_login(self.staff)
        response = self.client.get("/o/dashboard/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/customers/")

    def test_sidebar_links(self):
        self.client.force_login(self.owner)
        response = self.client.get("/o/dashboard/")
        self.assertContains(response, 'href="/o/dashboard/"')
        self.assertContains(response, 'href="/o/customers/"')
        self.assertContains(response, 'href="/o/visits/"')
        self.assertContains(response, 'href="/o/staff/"')
        self.assertContains(response, 'href="/o/segments/settings/"')
        self.assertContains(response, 'href="/o/imports/upload/"')

    def test_header_logout_form(self):
        self.client.force_login(self.owner)
        response = self.client.get("/o/dashboard/")
        html = response.content.decode()
        self.assertIn('action="/o/logout/"', html)
        self.assertIn("csrfmiddlewaretoken", html)
        self.assertIn('name="csrfmiddlewaretoken"', html)
