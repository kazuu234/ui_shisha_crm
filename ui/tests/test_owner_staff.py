from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import QRToken, Staff
from tenants.models import Store, StoreGroup


class OwnerStaffViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store_group = StoreGroup.objects.create(name="Staff Mgmt Group")
        cls.store = Store.objects.create(
            store_group=cls.store_group, name="Staff Mgmt Store"
        )
        cls.staff = Staff.objects.create_user(
            store=cls.store,
            display_name="List Staff",
            role="staff",
            staff_type="regular",
        )
        cls.owner = Staff.objects.create_user(
            store=cls.store,
            display_name="List Owner",
            role="owner",
            staff_type="owner",
        )

    def test_staff_list(self):
        inactive = Staff.objects.create_user(
            store=self.store,
            display_name="Inactive Hidden",
            role="staff",
            staff_type="regular",
            is_active=False,
        )
        self.client.force_login(self.owner)
        response = self.client.get(reverse("owner:staff-list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/owner/staff_list.html")
        self.assertContains(response, self.staff.display_name)
        self.assertContains(response, self.owner.display_name)
        self.assertNotContains(response, inactive.display_name)

    def test_staff_list_unauthenticated(self):
        response = self.client.get(reverse("owner:staff-list"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/o/login/"))

    def test_staff_list_staff_redirect(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("owner:staff-list"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/customers/")

    def test_staff_create_get(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("owner:staff-create"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/owner/staff_create.html")

    def test_staff_create_post(self):
        self.client.force_login(self.owner)
        before_staff = Staff.objects.filter(store=self.store).count()
        before_tokens = QRToken.objects.count()
        response = self.client.post(
            reverse("owner:staff-create"),
            {
                "display_name": "New From Form",
                "role": "staff",
                "staff_type": "regular",
            },
        )
        self.assertEqual(response.status_code, 302)
        new_staff = Staff.objects.get(display_name="New From Form")
        self.assertEqual(response.url, reverse("owner:staff-detail", pk=new_staff.pk))
        self.assertEqual(Staff.objects.filter(store=self.store).count(), before_staff + 1)
        self.assertEqual(QRToken.objects.count(), before_tokens + 1)
        self.assertTrue(
            QRToken.objects.filter(staff=new_staff, is_used=False).exists()
        )

    def test_staff_create_invalid(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("owner:staff-create"),
            {
                "display_name": "",
                "role": "staff",
                "staff_type": "regular",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "表示名を入力してください")

    def test_staff_create_qr_url_role(self):
        self.client.force_login(self.owner)

        r_staff = self.client.post(
            reverse("owner:staff-create"),
            {
                "display_name": "QR Staff Role",
                "role": "staff",
                "staff_type": "temporary",
            },
        )
        self.assertEqual(r_staff.status_code, 302)
        staff_user = Staff.objects.get(display_name="QR Staff Role")
        detail = self.client.get(
            reverse("owner:staff-detail", pk=staff_user.pk)
        )
        self.assertContains(detail, "/s/login/#token=")

        r_owner = self.client.post(
            reverse("owner:staff-create"),
            {
                "display_name": "QR Owner Role",
                "role": "owner",
                "staff_type": "owner",
            },
        )
        self.assertEqual(r_owner.status_code, 302)
        owner_user = Staff.objects.get(display_name="QR Owner Role")
        detail_o = self.client.get(
            reverse("owner:staff-detail", pk=owner_user.pk)
        )
        self.assertContains(detail_o, "/o/login/#token=")

    def test_staff_detail(self):
        tok = QRToken.objects.create(
            staff=self.staff,
            token=QRToken.generate_token(),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("owner:staff-detail", pk=self.staff.pk)
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.staff.display_name)
        self.assertContains(response, f"#token={tok.token}")

    def test_staff_detail_inactive_404(self):
        inactive = Staff.objects.create_user(
            store=self.store,
            display_name="Gone",
            role="staff",
            staff_type="regular",
            is_active=False,
        )
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("owner:staff-detail", pk=inactive.pk)
        )
        self.assertEqual(response.status_code, 404)

    def test_qr_reissue(self):
        old = QRToken.objects.create(
            staff=self.staff,
            token=QRToken.generate_token(),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.client.force_login(self.owner)
        before = QRToken.objects.filter(staff=self.staff).count()
        response = self.client.post(
            reverse("owner:staff-qr-issue", pk=self.staff.pk),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(QRToken.objects.filter(staff=self.staff).count(), before + 1)
        latest = (
            QRToken.objects.filter(staff=self.staff).order_by("-created_at").first()
        )
        self.assertNotEqual(latest.token, old.token)
        self.assertContains(response, latest.token)
        self.assertContains(response, "QR 再発行")

    def test_deactivate(self):
        target = Staff.objects.create_user(
            store=self.store,
            display_name="To Deactivate",
            role="staff",
            staff_type="regular",
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("owner:staff-deactivate", pk=target.pk),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("owner:staff-list"))
        target.refresh_from_db()
        self.assertFalse(target.is_active)

    def test_deactivate_self(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("owner:staff-deactivate", pk=self.owner.pk),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "自分自身を無効化することはできません")
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active)

    def test_deactivate_last_owner(self):
        other_owner = Staff.objects.create_user(
            store=self.store,
            display_name="Other Owner",
            role="owner",
            staff_type="owner",
        )
        self.client.force_login(self.owner)
        with mock.patch(
            "ui.owner.views.staff_mgmt._other_active_owner_count",
            return_value=0,
        ):
            response = self.client.post(
                reverse("owner:staff-deactivate", pk=other_owner.pk),
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "最後のオーナーは無効化できません")
        other_owner.refresh_from_db()
        self.assertTrue(other_owner.is_active)

    def test_sidebar_active_staff(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("owner:staff-list"))
        self.assertEqual(response.context["active_sidebar"], "staff")

    def test_staff_list_has_detail_links(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("owner:staff-list"))
        for s in Staff.objects.filter(store=self.store, is_active=True):
            self.assertContains(
                response, reverse("owner:staff-detail", pk=s.pk)
            )

    def test_qr_url_displayed_as_link(self):
        tok = QRToken.objects.create(
            staff=self.staff,
            token=QRToken.generate_token(),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("owner:staff-detail", pk=self.staff.pk)
        )
        self.assertContains(response, '<a href="/s/login/#token=')
        self.assertContains(response, f"{tok.token}")
