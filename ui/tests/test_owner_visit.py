from datetime import date, timedelta
from uuid import uuid4

from django.db.models import F
from django.test import TestCase
from django.urls import reverse

from accounts.models import Staff
from customers.models import Customer
from tenants.models import Store, StoreGroup
from visits.models import SegmentThreshold, Visit


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


class OwnerVisitViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store_group = StoreGroup.objects.create(name="Owner Visit Group")
        cls.store = Store.objects.create(
            store_group=cls.store_group, name="Test Store"
        )
        cls.other_store = Store.objects.create(
            store_group=cls.store_group, name="Other Store"
        )

    def setUp(self):
        _seed_segment_thresholds(self.store)
        self.owner = Staff.objects.create_user(
            store=self.store,
            display_name="Owner",
            role="owner",
            staff_type="owner",
        )
        self.staff_user = Staff.objects.create_user(
            store=self.store,
            display_name="Staff A",
            role="staff",
            staff_type="regular",
        )
        self.staff_b = Staff.objects.create_user(
            store=self.store,
            display_name="Staff B",
            role="staff",
            staff_type="regular",
        )
        self.staff_other = Staff.objects.create_user(
            store=self.other_store,
            display_name="Other Staff",
            role="staff",
            staff_type="regular",
        )
        self.customer = Customer.objects.create(store=self.store, name="山田太郎")
        self.customer_b = Customer.objects.create(store=self.store, name="田中花子")
        self.visit = Visit.objects.create(
            store=self.store,
            customer=self.customer,
            staff=self.staff_user,
            visited_at=date(2026, 1, 15),
            conversation_memo="フルーツ系好み",
        )
        self.client.force_login(self.owner)

    # --- List #1–3 ---

    def test_visit_list_owner(self):
        response = self.client.get(reverse("owner:visit-list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/owner/visit_list.html")
        self.assertContains(response, "山田太郎")
        self.assertContains(response, "来店記録")

    def test_visit_list_unauthenticated(self):
        self.client.logout()
        response = self.client.get(reverse("owner:visit-list"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/o/login/"))

    def test_visit_list_staff_redirect(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("owner:visit-list"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/customers/")

    # --- List #4–7 ---

    def test_visit_list_search(self):
        Visit.objects.create(
            store=self.store,
            customer=self.customer_b,
            staff=self.staff_user,
            visited_at=date(2026, 2, 1),
        )
        response = self.client.get(reverse("owner:visit-list"), {"search": "山田"})
        self.assertContains(response, "山田太郎")
        self.assertNotContains(response, "田中花子")

    def test_visit_list_segment_filter(self):
        Visit.objects.create(
            store=self.store,
            customer=self.customer_b,
            staff=self.staff_user,
            visited_at=date(2026, 2, 1),
        )
        Visit.objects.create(
            store=self.store,
            customer=self.customer_b,
            staff=self.staff_user,
            visited_at=date(2026, 2, 2),
        )
        response = self.client.get(reverse("owner:visit-list"), {"segment": "new"})
        self.assertContains(response, "山田太郎")
        self.assertNotContains(response, "田中花子")

    def test_visit_list_staff_filter(self):
        Visit.objects.create(
            store=self.store,
            customer=self.customer_b,
            staff=self.staff_b,
            visited_at=date(2026, 2, 1),
        )
        response = self.client.get(
            reverse("owner:visit-list"),
            {"staff": str(self.staff_b.pk)},
        )
        self.assertNotContains(response, "山田太郎")
        self.assertContains(response, "田中花子")

    def test_visit_list_date_range_filter(self):
        Visit.objects.create(
            store=self.store,
            customer=self.customer_b,
            staff=self.staff_user,
            visited_at=date(2026, 3, 1),
        )
        response = self.client.get(
            reverse("owner:visit-list"),
            {"date_from": "2026-02-01", "date_to": "2026-02-28"},
        )
        self.assertNotContains(response, "山田太郎")
        self.assertNotContains(response, "田中花子")

        r2 = self.client.get(
            reverse("owner:visit-list"),
            {"date_from": "2026-01-01", "date_to": "2026-12-31"},
        )
        self.assertContains(r2, "山田太郎")
        self.assertContains(r2, "田中花子")

    # --- List #8–12 ---

    def test_visit_list_sort_visited_at(self):
        Visit.objects.create(
            store=self.store,
            customer=self.customer_b,
            staff=self.staff_user,
            visited_at=date(2026, 3, 1),
        )
        response = self.client.get(
            reverse("owner:visit-list"), {"sort": "visited_at"}
        )
        content = response.content
        self.assertLess(content.find(b"\xe5\xb1\xb1\xe7\x94\xb0"), content.find(b"\xe7\x94\xb0\xe4\xb8\xad"))
        # 山田 before 田中 in ascending by date: 山田 1/15, 田中 3/1

    def test_visit_list_sort_visited_at_desc(self):
        Visit.objects.create(
            store=self.store,
            customer=self.customer_b,
            staff=self.staff_user,
            visited_at=date(2026, 3, 1),
        )
        response = self.client.get(reverse("owner:visit-list"))
        content = response.content
        self.assertLess(content.find(b"\xe7\x94\xb0\xe4\xb8\xad"), content.find(b"\xe5\xb1\xb1\xe7\x94\xb0"))

    def test_visit_list_sort_customer_name(self):
        Visit.objects.create(
            store=self.store,
            customer=self.customer_b,
            staff=self.staff_user,
            visited_at=date(2026, 2, 1),
        )
        response = self.client.get(
            reverse("owner:visit-list"), {"sort": "customer_name"}
        )
        expected = list(
            Visit.objects.for_store(self.store)
            .order_by(F("customer__name").asc(), "-created_at", "pk")
            .values_list("pk", flat=True)
        )
        got = [v.pk for v in response.context["visits"]]
        self.assertEqual(got, expected[: len(got)])

    def test_visit_list_sort_invalid(self):
        Visit.objects.create(
            store=self.store,
            customer=self.customer_b,
            staff=self.staff_user,
            visited_at=date(2026, 2, 1),
        )
        r_bad = self.client.get(
            reverse("owner:visit-list"), {"sort": "xxx"}
        )
        r_default = self.client.get(reverse("owner:visit-list"))
        self.assertEqual(
            [v.pk for v in r_bad.context["visits"]],
            [v.pk for v in r_default.context["visits"]],
        )

    def test_visit_list_pagination(self):
        for i in range(25):
            c = Customer.objects.create(
                store=self.store, name=f"P{i:02d}", segment="new", visit_count=0
            )
            Visit.objects.create(
                store=self.store,
                customer=c,
                staff=self.staff_user,
                visited_at=date(2026, 4, 1) + timedelta(days=i),
            )
        r1 = self.client.get(reverse("owner:visit-list"))
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(len(r1.context["visits"]), 25)
        r2 = self.client.get(reverse("owner:visit-list"), {"page": 2})
        self.assertEqual(len(r2.context["visits"]), 1)

    def test_visit_list_htmx_fragment(self):
        response = self.client.get(
            reverse("owner:visit-list"),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/owner/_visit_table.html")
        self.assertTemplateNotUsed(response, "ui/owner/visit_list.html")

    def test_visit_list_store_scope(self):
        oc = Customer.objects.create(
            store=self.other_store, name="他店客", segment="new", visit_count=1
        )
        Visit.objects.create(
            store=self.other_store,
            customer=oc,
            staff=self.staff_other,
            visited_at=date(2026, 1, 20),
        )
        response = self.client.get(reverse("owner:visit-list"))
        self.assertContains(response, "山田太郎")
        self.assertNotContains(response, "他店客")

    def test_visit_list_select_related(self):
        Visit.objects.create(
            store=self.store,
            customer=self.customer_b,
            staff=self.staff_b,
            visited_at=date(2026, 2, 1),
        )
        # session + user + store + count + staff dropdown + visit page
        with self.assertNumQueries(6):
            response = self.client.get(reverse("owner:visit-list"))
        self.assertEqual(response.status_code, 200)

    def test_visit_list_memo_truncate(self):
        long_memo = "あ" * 35
        Visit.objects.create(
            store=self.store,
            customer=self.customer_b,
            staff=self.staff_user,
            visited_at=date(2026, 2, 1),
            conversation_memo=long_memo,
        )
        response = self.client.get(reverse("owner:visit-list"))
        self.assertContains(response, "あ" * 27)
        self.assertNotContains(response, long_memo)

    def test_visit_list_segment_badge(self):
        response = self.client.get(reverse("owner:visit-list"))
        self.assertContains(response, "bg-accent-subtle")
        self.assertContains(response, "新規")

    def test_visit_list_stable_sort(self):
        d = date(2026, 5, 1)
        v_first = Visit.objects.create(
            store=self.store,
            customer=self.customer,
            staff=self.staff_user,
            visited_at=d,
            conversation_memo="first",
        )
        v_second = Visit.objects.create(
            store=self.store,
            customer=self.customer_b,
            staff=self.staff_user,
            visited_at=d,
            conversation_memo="second",
        )
        response = self.client.get(
            reverse("owner:visit-list"), {"sort": "visited_at"}
        )
        same_day = [v for v in response.context["visits"] if v.visited_at == d]
        self.assertEqual(same_day[0].pk, v_second.pk)
        self.assertEqual(same_day[1].pk, v_first.pk)

    # --- Edit #19–27 ---

    def test_visit_edit_get(self):
        response = self.client.get(
            reverse("owner:visit-edit", args=[self.visit.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/owner/visit_edit.html")
        self.assertContains(response, "2026-01-15")
        self.assertContains(response, "フルーツ系好み")

    def test_visit_edit_get_readonly_fields(self):
        response = self.client.get(
            reverse("owner:visit-edit", args=[self.visit.pk])
        )
        self.assertContains(response, "山田太郎")
        self.assertContains(response, "Staff A")

    def test_visit_edit_post_valid(self):
        response = self.client.post(
            reverse("owner:visit-edit", args=[self.visit.pk]),
            {
                "visited_at": "2026-02-20",
                "conversation_memo": "更新メモ",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("owner:visit-list"))
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.visited_at, date(2026, 2, 20))
        self.assertEqual(self.visit.conversation_memo, "更新メモ")
        r2 = self.client.get(response.url)
        self.assertContains(r2, "来店記録を更新しました")

    def test_visit_edit_post_invalid_date_empty(self):
        response = self.client.post(
            reverse("owner:visit-edit", args=[self.visit.pk]),
            {"visited_at": "", "conversation_memo": "x"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "来店日を入力してください")

    def test_visit_edit_empty_memo_stays_empty(self):
        self.visit.conversation_memo = "before"
        self.visit.save(update_fields=["conversation_memo"])
        response = self.client.post(
            reverse("owner:visit-edit", args=[self.visit.pk]),
            {
                "visited_at": "2026-01-15",
                "conversation_memo": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.conversation_memo, "")

    def test_visit_edit_unauthenticated(self):
        self.client.logout()
        response = self.client.get(
            reverse("owner:visit-edit", args=[self.visit.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/o/login/"))

    def test_visit_edit_staff_redirect(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(
            reverse("owner:visit-edit", args=[self.visit.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/customers/")

    def test_visit_edit_not_found(self):
        response = self.client.get(
            reverse("owner:visit-edit", args=[uuid4()])
        )
        self.assertEqual(response.status_code, 404)

    def test_visit_edit_other_store(self):
        oc = Customer.objects.create(
            store=self.other_store, name="他", segment="new", visit_count=1
        )
        ov = Visit.objects.create(
            store=self.other_store,
            customer=oc,
            staff=self.staff_other,
            visited_at=date(2026, 1, 1),
        )
        response = self.client.get(reverse("owner:visit-edit", args=[ov.pk]))
        self.assertEqual(response.status_code, 404)

    def test_visit_edit_save_error(self):
        """form.save() が例外を送出した場合は non_field_errors として表示される"""
        from unittest.mock import patch

        with patch(
            "ui.owner.forms.visit.VisitEditForm.save",
            side_effect=Exception("保存エラー"),
        ):
            response = self.client.post(
                reverse("owner:visit-edit", args=[self.visit.pk]),
                {"visited_at": "2026-02-20", "conversation_memo": "x"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "保存エラー")

    # --- Delete #28–33 ---

    def test_visit_delete_post(self):
        vid = self.visit.pk
        response = self.client.post(
            reverse("owner:visit-delete", args=[vid]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("owner:visit-list"))
        self.assertEqual(Visit.objects.filter(pk=vid).count(), 0)
        deleted = Visit.objects.all_with_deleted().get(pk=vid)
        self.assertTrue(deleted.is_deleted)
        r2 = self.client.get(response.url)
        self.assertContains(r2, "来店記録を削除しました")

    def test_visit_delete_get_not_allowed(self):
        response = self.client.get(
            reverse("owner:visit-delete", args=[self.visit.pk])
        )
        self.assertEqual(response.status_code, 405)

    def test_visit_delete_unauthenticated(self):
        self.client.logout()
        response = self.client.post(
            reverse("owner:visit-delete", args=[self.visit.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/o/login/"))

    def test_visit_delete_staff_redirect(self):
        self.client.force_login(self.staff_user)
        response = self.client.post(
            reverse("owner:visit-delete", args=[self.visit.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/customers/")

    def test_visit_delete_not_found(self):
        response = self.client.post(reverse("owner:visit-delete", args=[uuid4()]))
        self.assertEqual(response.status_code, 404)

    def test_visit_delete_other_store(self):
        oc = Customer.objects.create(
            store=self.other_store, name="他", segment="new", visit_count=1
        )
        ov = Visit.objects.create(
            store=self.other_store,
            customer=oc,
            staff=self.staff_other,
            visited_at=date(2026, 1, 1),
        )
        response = self.client.post(reverse("owner:visit-delete", args=[ov.pk]))
        self.assertEqual(response.status_code, 404)

    def test_visit_delete_error(self):
        """soft_delete() が例外を送出した場合、エラートースト + リダイレクト"""
        from unittest.mock import patch

        with patch.object(Visit, "soft_delete", side_effect=Exception("削除失敗")):
            response = self.client.post(
                reverse("owner:visit-delete", args=[self.visit.pk]),
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("owner:visit-list"))
        r2 = self.client.get(response.url)
        self.assertContains(r2, "削除失敗")

    # --- Misc #34–39 ---

    def test_sidebar_active_visits(self):
        r_list = self.client.get(reverse("owner:visit-list"))
        self.assertEqual(r_list.context["active_sidebar"], "visits")
        r_edit = self.client.get(
            reverse("owner:visit-edit", args=[self.visit.pk])
        )
        self.assertEqual(r_edit.context["active_sidebar"], "visits")

    def test_visit_list_toast_display(self):
        session = self.client.session
        session["toast"] = {"message": "トースト検証", "type": "success"}
        session.save()
        response = self.client.get(reverse("owner:visit-list"))
        self.assertContains(response, "トースト検証")
        self.assertNotIn("toast", self.client.session)

    def test_visit_list_combined_filters(self):
        Visit.objects.create(
            store=self.store,
            customer=self.customer_b,
            staff=self.staff_b,
            visited_at=date(2026, 6, 10),
        )
        Visit.objects.create(
            store=self.store,
            customer=self.customer_b,
            staff=self.staff_b,
            visited_at=date(2026, 6, 15),
            conversation_memo="combo",
        )
        response = self.client.get(
            reverse("owner:visit-list"),
            {
                "search": "田中",
                "segment": "repeat",
                "staff": str(self.staff_b.pk),
                "date_from": "2026-06-01",
                "date_to": "2026-06-30",
            },
        )
        self.assertContains(response, "田中花子")
        self.assertNotContains(response, "山田太郎")

    def test_visit_list_invalid_staff_uuid(self):
        Visit.objects.create(
            store=self.store,
            customer=self.customer_b,
            staff=self.staff_b,
            visited_at=date(2026, 2, 1),
        )
        response = self.client.get(
            reverse("owner:visit-list"), {"staff": "not-a-uuid"}
        )
        names = [v.customer.name for v in response.context["visits"]]
        self.assertIn("山田太郎", names)
        self.assertIn("田中花子", names)

    def test_visit_list_nonexistent_staff_uuid(self):
        Visit.objects.create(
            store=self.store,
            customer=self.customer_b,
            staff=self.staff_b,
            visited_at=date(2026, 2, 1),
        )
        fake = uuid4()
        while Staff.objects.filter(pk=fake).exists():
            fake = uuid4()
        response = self.client.get(
            reverse("owner:visit-list"), {"staff": str(fake)}
        )
        names = [v.customer.name for v in response.context["visits"]]
        self.assertIn("山田太郎", names)
        self.assertIn("田中花子", names)

    def test_visit_list_invalid_date_format(self):
        Visit.objects.create(
            store=self.store,
            customer=self.customer_b,
            staff=self.staff_user,
            visited_at=date(2026, 2, 1),
        )
        response = self.client.get(
            reverse("owner:visit-list"), {"date_from": "invalid"}
        )
        names = [v.customer.name for v in response.context["visits"]]
        self.assertIn("山田太郎", names)
        self.assertIn("田中花子", names)
