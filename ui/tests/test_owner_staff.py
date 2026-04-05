import re
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.template.defaultfilters import date as date_filter
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import QRToken, Staff
from tenants.models import Store, StoreGroup

from ui.owner.views.staff_mgmt import StaffDeactivateView

_QR_DATA_URI_RE = re.compile(r"data:image/png;base64,([A-Za-z0-9+/=]+)")


def _first_qr_base64_payload(content: bytes) -> str:
    m = _QR_DATA_URI_RE.search(content.decode())
    if not m:
        raise AssertionError("response に QR の data URI がありません")
    return m.group(1)


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

    def test_deactivated_owner_cannot_access(self):
        self.client.force_login(self.owner)
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])
        response = self.client.get(reverse("owner:staff-list"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/o/login/"))

    def test_deactivated_staff_cannot_access_staff_ui(self):
        """StaffRequiredMixin の is_active ガード回帰テスト。"""
        self.client.force_login(self.staff)
        self.staff.is_active = False
        self.staff.save(update_fields=["is_active"])
        response = self.client.get("/s/customers/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/s/login/"))

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
        self.assertEqual(response.url, reverse("owner:staff-detail", kwargs={"pk": new_staff.pk}))
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

    def test_staff_create_display_name_too_long(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("owner:staff-create"),
            {
                "display_name": "あ" * 101,
                "role": "staff",
                "staff_type": "regular",
            },
        )
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertIn("display_name", form.errors)
        self.assertContains(response, form.errors["display_name"][0])

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
            reverse("owner:staff-detail", kwargs={"pk": staff_user.pk})
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
            reverse("owner:staff-detail", kwargs={"pk": owner_user.pk})
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
            reverse("owner:staff-detail", kwargs={"pk": self.staff.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.staff.display_name)
        self.assertContains(response, "有効")
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
            reverse("owner:staff-detail", kwargs={"pk": inactive.pk})
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
            reverse("owner:staff-qr-issue", kwargs={"pk": self.staff.pk}),
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
            reverse("owner:staff-deactivate", kwargs={"pk": target.pk}),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("owner:staff-list"))
        target.refresh_from_db()
        self.assertFalse(target.is_active)

    def test_deactivate_self(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("owner:staff-deactivate", kwargs={"pk": self.owner.pk}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "自分自身を無効化することはできません")
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active)

    def test_deactivate_last_owner(self):
        """他にアクティブなオーナーがいれば無効化できる。最後の1人だけは拒否される。

        オーナー領域のミックスインは is_active=False を即リダイレクトするため、
        「他にアクティブなオーナーがいない」状態で別の active owner が POST する経路は
        フルスタックでは成立しない。post() 本体のガードは RequestFactory で検証する。
        """
        target_owner = Staff.objects.create_user(
            store=self.store,
            display_name="Target Owner",
            role="owner",
            staff_type="owner",
        )
        self.client.force_login(self.owner)
        response_ok = self.client.post(
            reverse("owner:staff-deactivate", kwargs={"pk": target_owner.pk}),
        )
        self.assertEqual(response_ok.status_code, 302)
        self.assertEqual(response_ok.url, reverse("owner:staff-list"))
        target_owner.refresh_from_db()
        self.assertFalse(target_owner.is_active)

        iso_group = StoreGroup.objects.create(name="Last Owner Iso Group")
        iso_store = Store.objects.create(
            store_group=iso_group, name="Last Owner Iso Store"
        )
        sole_owner = Staff.objects.create_user(
            store=iso_store,
            display_name="Sole Active Owner",
            role="owner",
            staff_type="owner",
        )
        Staff.objects.filter(
            store=iso_store, role="owner", is_active=True
        ).exclude(pk=sole_owner.pk).update(is_active=False)
        inactive_actor = Staff.objects.create_user(
            store=iso_store,
            display_name="Inactive Owner Actor",
            role="owner",
            staff_type="owner",
            is_active=False,
        )
        request = RequestFactory().post(
            reverse("owner:staff-deactivate", kwargs={"pk": sole_owner.pk})
        )
        request.user = inactive_actor
        view = StaffDeactivateView()
        view.store = iso_store
        response_block = view.post(request, sole_owner.pk)
        self.assertEqual(response_block.status_code, 200)
        self.assertContains(response_block, "最後のオーナーは無効化できません")
        sole_owner.refresh_from_db()
        self.assertTrue(sole_owner.is_active)

    def test_sidebar_active_staff(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("owner:staff-list"))
        self.assertEqual(response.context["active_sidebar"], "staff")

    def test_staff_list_has_detail_links(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("owner:staff-list"))
        for s in Staff.objects.filter(store=self.store, is_active=True):
            self.assertContains(
                response, reverse("owner:staff-detail", kwargs={"pk": s.pk})
            )

    def test_qr_url_displayed_as_link(self):
        tok = QRToken.objects.create(
            staff=self.staff,
            token=QRToken.generate_token(),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("owner:staff-detail", kwargs={"pk": self.staff.pk})
        )
        self.assertContains(response, '<a href="/s/login/#token=')
        self.assertContains(response, f"{tok.token}")

    def test_staff_detail_has_qr_image(self):
        QRToken.objects.create(
            staff=self.staff,
            token=QRToken.generate_token(),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("owner:staff-detail", kwargs={"pk": self.staff.pk})
        )
        self.assertEqual(response.status_code, 200)
        qr_image = response.context["qr_image"]
        self.assertIsNotNone(qr_image)
        self.assertTrue(qr_image.startswith("data:image/png;base64,"))

    def test_staff_detail_no_qr_image_when_no_token(self):
        QRToken.objects.filter(staff=self.staff).delete()
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("owner:staff-detail", kwargs={"pk": self.staff.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["qr_image"])

    def test_qr_section_has_img_tag(self):
        QRToken.objects.create(
            staff=self.staff,
            token=QRToken.generate_token(),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("owner:staff-detail", kwargs={"pk": self.staff.pk})
        )
        self.assertContains(response, "<img")

    def test_phase2_note_removed(self):
        QRToken.objects.create(
            staff=self.staff,
            token=QRToken.generate_token(),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("owner:staff-detail", kwargs={"pk": self.staff.pk})
        )
        self.assertNotContains(response, "Phase 2")

    def test_staff_create_with_email(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("owner:staff-create"),
            {
                "display_name": "Email Staff",
                "email": "staff@example.com",
                "role": "staff",
                "staff_type": "regular",
            },
        )
        self.assertEqual(response.status_code, 302)
        created = Staff.objects.get(display_name="Email Staff")
        self.assertEqual(created.email, "staff@example.com")

    def test_staff_create_without_email(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("owner:staff-create"),
            {
                "display_name": "No Email Staff",
                "role": "staff",
                "staff_type": "regular",
            },
        )
        self.assertEqual(response.status_code, 302)
        created = Staff.objects.get(display_name="No Email Staff")
        self.assertEqual(created.email, "")

    def test_staff_edit_get(self):
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("owner:staff-edit", kwargs={"pk": self.staff.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/owner/staff_edit.html")
        self.assertEqual(
            response.context["form"].initial.get("display_name"),
            self.staff.display_name,
        )

    def test_staff_edit_post(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("owner:staff-edit", kwargs={"pk": self.staff.pk}),
            {
                "display_name": "Updated Name",
                "email": "updated@example.com",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("owner:staff-detail", kwargs={"pk": self.staff.pk}),
        )
        self.staff.refresh_from_db()
        self.assertEqual(self.staff.display_name, "Updated Name")
        self.assertEqual(self.staff.email, "updated@example.com")

    def test_staff_edit_invalid_email(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("owner:staff-edit", kwargs={"pk": self.staff.pk}),
            {
                "display_name": self.staff.display_name,
                "email": "not-an-email",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)

    def test_print_button_visible(self):
        QRToken.objects.create(
            staff=self.staff,
            token=QRToken.generate_token(),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("owner:staff-detail", kwargs={"pk": self.staff.pk})
        )
        self.assertContains(response, "window.print()")

    def test_staff_detail_has_email(self):
        self.staff.email = ""
        self.staff.save(update_fields=["email"])
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("owner:staff-detail", kwargs={"pk": self.staff.pk})
        )
        self.assertContains(response, "未設定")

        self.staff.email = "shown@example.com"
        self.staff.save(update_fields=["email"])
        response2 = self.client.get(
            reverse("owner:staff-detail", kwargs={"pk": self.staff.pk})
        )
        self.assertContains(response2, "shown@example.com")

    def test_qr_reissue_has_image(self):
        QRToken.objects.create(
            staff=self.staff,
            token=QRToken.generate_token(),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.client.force_login(self.owner)
        detail_url = reverse("owner:staff-detail", kwargs={"pk": self.staff.pk})
        before_resp = self.client.get(detail_url)
        self.assertEqual(before_resp.status_code, 200)
        before_b64 = _first_qr_base64_payload(before_resp.content)

        response = self.client.post(
            reverse("owner:staff-qr-issue", kwargs={"pk": self.staff.pk}),
        )
        self.assertEqual(response.status_code, 200)
        after_b64 = _first_qr_base64_payload(response.content)
        self.assertNotEqual(before_b64, after_b64)

        self.assertIsNotNone(response.context["qr_image"])
        self.assertTrue(
            response.context["qr_image"].startswith("data:image/png;base64,")
        )
        self.assertContains(response, "<img")

    @patch(
        "ui.owner.views.staff_mgmt.generate_qr_data_uri",
        return_value="data:image/png;base64,xx",
    )
    def test_qr_image_generation_receives_absolute_url(self, mock_gen):
        tok = QRToken.objects.create(
            staff=self.staff,
            token=QRToken.generate_token(),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.client.force_login(self.owner)
        self.client.get(
            reverse("owner:staff-detail", kwargs={"pk": self.staff.pk})
        )
        mock_gen.assert_called()
        encoded_url = mock_gen.call_args[0][0]
        self.assertTrue(
            encoded_url.startswith("http://testserver"),
            msg=f"expected testserver absolute URL, got {encoded_url!r}",
        )
        self.assertIn("/s/login/#token=", encoded_url)
        self.assertIn(tok.token, encoded_url)

        mock_gen.reset_mock()
        self.client.post(
            reverse("owner:staff-qr-issue", kwargs={"pk": self.staff.pk})
        )
        mock_gen.assert_called()
        encoded_url2 = mock_gen.call_args[0][0]
        self.assertTrue(encoded_url2.startswith("http://testserver"))
        self.assertIn("/s/login/#token=", encoded_url2)

    _MIN_PNG_DATA_URI = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@test.example",
    )
    @patch(
        "ui.owner.views.staff_mgmt.generate_qr_data_uri",
        return_value=_MIN_PNG_DATA_URI,
    )
    def test_qr_email_send_success(self, _mock_qr):
        self.staff.email = "recipient@example.com"
        self.staff.save(update_fields=["email"])
        tok = QRToken.objects.create(
            staff=self.staff,
            token=QRToken.generate_token(),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.client.force_login(self.owner)
        mail.outbox.clear()
        response = self.client.post(
            reverse("owner:staff-qr-email", kwargs={"pk": self.staff.pk}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.subject, "【シーシャ CRM】QR ログインコード")
        self.assertEqual(sent.to, ["recipient@example.com"])
        self.assertEqual(sent.from_email, "noreply@test.example")
        self.assertIn("QR ログインコード", sent.body)
        self.assertIn("以下の URL からログインできます:", sent.body)
        expires_line = date_filter(tok.expires_at, "Y/m/d H:i")
        self.assertIn(expires_line, sent.body)
        self.assertTrue(sent.alternatives)
        html, mime = sent.alternatives[0]
        self.assertEqual(mime, "text/html")
        self.assertIn("cid:qr-code", html)
        self.assertIn("http://testserver/s/login/#token=", html)
        raw = sent.message()
        self.assertEqual(raw.get_content_subtype(), "related")
        image_parts = [p for p in raw.walk() if p.get_content_type() == "image/png"]
        self.assertEqual(len(image_parts), 1)
        self.assertEqual(image_parts[0]["Content-ID"], "<qr-code>")

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@test.example",
    )
    @patch(
        "ui.owner.views.staff_mgmt.generate_qr_data_uri",
        return_value=_MIN_PNG_DATA_URI,
    )
    def test_qr_email_contains_qr_url(self, _mock_qr):
        self.staff.email = "u@example.com"
        self.staff.save(update_fields=["email"])
        QRToken.objects.create(
            staff=self.staff,
            token=QRToken.generate_token(),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.client.force_login(self.owner)
        mail.outbox.clear()
        self.client.post(
            reverse("owner:staff-qr-email", kwargs={"pk": self.staff.pk}),
        )
        sent = mail.outbox[0]
        self.assertIn("http://testserver/s/login/#token=", sent.body)
        html, _mime = sent.alternatives[0]
        self.assertIn("http://testserver/s/login/#token=", html)

    def test_qr_email_no_email(self):
        self.staff.email = ""
        self.staff.save(update_fields=["email"])
        QRToken.objects.create(
            staff=self.staff,
            token=QRToken.generate_token(),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("owner:staff-qr-email", kwargs={"pk": self.staff.pk}),
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "メールアドレスが未設定です", status_code=400)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@test.example",
    )
    @patch(
        "ui.owner.views.staff_mgmt.generate_qr_data_uri",
        return_value=_MIN_PNG_DATA_URI,
    )
    def test_qr_email_no_token_issues_new(self, _mock_qr):
        self.staff.email = "newtok@example.com"
        self.staff.save(update_fields=["email"])
        QRToken.objects.filter(staff=self.staff).delete()
        self.assertFalse(QRToken.objects.filter(staff=self.staff).exists())
        self.client.force_login(self.owner)
        mail.outbox.clear()
        response = self.client.post(
            reverse("owner:staff-qr-email", kwargs={"pk": self.staff.pk}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(QRToken.objects.filter(staff=self.staff).exists())
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@test.example",
    )
    @patch(
        "ui.owner.views.staff_mgmt.generate_qr_data_uri",
        return_value=_MIN_PNG_DATA_URI,
    )
    def test_qr_email_used_token_issues_new(self, _mock_qr):
        self.staff.email = "usedtok@example.com"
        self.staff.save(update_fields=["email"])
        QRToken.objects.filter(staff=self.staff).delete()
        QRToken.objects.create(
            staff=self.staff,
            token=QRToken.generate_token(),
            expires_at=timezone.now() + timedelta(hours=1),
            is_used=True,
        )
        before = QRToken.objects.filter(staff=self.staff).count()
        self.client.force_login(self.owner)
        mail.outbox.clear()
        response = self.client.post(
            reverse("owner:staff-qr-email", kwargs={"pk": self.staff.pk}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(QRToken.objects.filter(staff=self.staff).count(), before + 1)
        self.assertEqual(len(mail.outbox), 1)
        latest = (
            QRToken.objects.filter(staff=self.staff).order_by("-created_at").first()
        )
        self.assertFalse(latest.is_used)
        self.assertIn(latest.token, mail.outbox[0].body)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@test.example",
    )
    @patch(
        "ui.owner.views.staff_mgmt.generate_qr_data_uri",
        return_value=_MIN_PNG_DATA_URI,
    )
    def test_qr_email_expired_token_issues_new(self, _mock_qr):
        self.staff.email = "expiredtok@example.com"
        self.staff.save(update_fields=["email"])
        QRToken.objects.filter(staff=self.staff).delete()
        QRToken.objects.create(
            staff=self.staff,
            token=QRToken.generate_token(),
            expires_at=timezone.now() - timedelta(hours=1),
            is_used=False,
        )
        before = QRToken.objects.filter(staff=self.staff).count()
        self.client.force_login(self.owner)
        mail.outbox.clear()
        response = self.client.post(
            reverse("owner:staff-qr-email", kwargs={"pk": self.staff.pk}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(QRToken.objects.filter(staff=self.staff).count(), before + 1)
        self.assertEqual(len(mail.outbox), 1)
        latest = (
            QRToken.objects.filter(staff=self.staff).order_by("-created_at").first()
        )
        self.assertGreater(latest.expires_at, timezone.now())
        self.assertIn(latest.token, mail.outbox[0].body)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@test.example",
    )
    @patch(
        "ui.owner.views.staff_mgmt.generate_qr_data_uri",
        return_value=_MIN_PNG_DATA_URI,
    )
    def test_qr_email_success_message(self, _mock_qr):
        self.staff.email = "ok@example.com"
        self.staff.save(update_fields=["email"])
        QRToken.objects.create(
            staff=self.staff,
            token=QRToken.generate_token(),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("owner:staff-qr-email", kwargs={"pk": self.staff.pk}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/owner/_qr_email_status.html")
        self.assertContains(response, "メールを送信しました")

    def test_qr_email_button_disabled_no_email(self):
        self.staff.email = ""
        self.staff.save(update_fields=["email"])
        QRToken.objects.create(
            staff=self.staff,
            token=QRToken.generate_token(),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("owner:staff-detail", kwargs={"pk": self.staff.pk}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            reverse("owner:staff-qr-email", kwargs={"pk": self.staff.pk}),
        )
        self.assertContains(response, "メールアドレスが未設定です。スタッフ編集から設定してください")

    def test_qr_email_button_enabled_with_email(self):
        self.staff.email = "btn@example.com"
        self.staff.save(update_fields=["email"])
        QRToken.objects.create(
            staff=self.staff,
            token=QRToken.generate_token(),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("owner:staff-detail", kwargs={"pk": self.staff.pk}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("owner:staff-qr-email", kwargs={"pk": self.staff.pk}),
        )
