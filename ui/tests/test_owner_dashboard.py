import re
from datetime import date, timedelta
from unittest.mock import call, patch

from django.test import TestCase
from django.urls import resolve, reverse

from accounts.models import Staff
from customers.models import Customer
from tenants.models import Store, StoreGroup
from ui.owner.views.dashboard import DashboardView


FIXED_TODAY = date(2026, 4, 15)


def _segment_payload(total_visits=10):
    return {
        "period": {"from": "2026-03-17", "to": "2026-04-15"},
        "total_visits": total_visits,
        "segments": [
            {"segment": "new", "visit_count": 4, "ratio": 0.4},
            {"segment": "repeat", "visit_count": 3, "ratio": 0.3},
            {"segment": "regular", "visit_count": 3, "ratio": 0.3},
        ],
    }


def _staff_payload():
    return {
        "period": {"from": "2026-03-17", "to": "2026-04-15"},
        "staff": [
            {"staff_id": "s1", "display_name": "田中", "total_visits": 5},
        ],
    }


class OwnerDashboardViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store_group = StoreGroup.objects.create(name="Dashboard Test Group")
        cls.store = Store.objects.create(
            store_group=cls.store_group, name="Dashboard Store"
        )
        cls.other_store = Store.objects.create(
            store_group=cls.store_group, name="Dashboard Other Store"
        )
        cls.staff_user = Staff.objects.create_user(
            store=cls.store,
            display_name="Dash Staff",
            role="staff",
            staff_type="regular",
        )
        cls.owner = Staff.objects.create_user(
            store=cls.store,
            display_name="Dash Owner",
            role="owner",
            staff_type="owner",
        )

    def setUp(self):
        self.client.force_login(self.owner)

    @patch("ui.owner.views.dashboard.date")
    @patch("ui.owner.views.dashboard.AnalyticsService")
    def test_dashboard_owner(self, mock_analytics, mock_date):
        mock_date.today.return_value = FIXED_TODAY
        mock_analytics.daily_summary.return_value = {
            "period": {"from": "2026-03-17", "to": "2026-04-15"},
            "daily": [
                {"date": "2026-04-15", "total_visits": 1, "new_visits": 0, "repeat_visits": 0, "regular_visits": 1},
            ],
        }
        mock_analytics.segment_ratio.return_value = _segment_payload()
        mock_analytics.staff_summary.return_value = _staff_payload()

        response = self.client.get(reverse("owner:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/owner/dashboard.html")
        self.assertContains(response, 'id="chart-daily"')
        self.assertContains(response, 'id="chart-segment"')
        self.assertContains(response, 'id="chart-staff"')

    def test_dashboard_unauthenticated(self):
        self.client.logout()
        response = self.client.get(reverse("owner:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/o/login/"))

    def test_dashboard_staff_redirect(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("owner:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/customers/")

    @patch("ui.owner.views.dashboard.date")
    @patch("ui.owner.views.dashboard.AnalyticsService")
    def test_dashboard_default_period(self, mock_analytics, mock_date):
        mock_date.today.return_value = FIXED_TODAY
        mock_analytics.daily_summary.return_value = {"period": {}, "daily": []}
        mock_analytics.segment_ratio.return_value = _segment_payload(0)
        mock_analytics.staff_summary.return_value = {"period": {}, "staff": []}

        response = self.client.get(reverse("owner:dashboard"))
        self.assertEqual(response.context["current_period"], "30")

    @patch("ui.owner.views.dashboard.date")
    @patch("ui.owner.views.dashboard.AnalyticsService")
    def test_dashboard_period_7(self, mock_analytics, mock_date):
        mock_date.today.return_value = FIXED_TODAY
        mock_analytics.daily_summary.return_value = {"period": {}, "daily": []}
        mock_analytics.segment_ratio.return_value = _segment_payload(0)
        mock_analytics.staff_summary.return_value = {"period": {}, "staff": []}

        response = self.client.get(reverse("owner:dashboard"), {"period": "7"})
        self.assertEqual(response.context["current_period"], "7")

    @patch("ui.owner.views.dashboard.date")
    @patch("ui.owner.views.dashboard.AnalyticsService")
    def test_dashboard_period_90(self, mock_analytics, mock_date):
        mock_date.today.return_value = FIXED_TODAY
        mock_analytics.daily_summary.return_value = {"period": {}, "daily": []}
        mock_analytics.segment_ratio.return_value = _segment_payload(0)
        mock_analytics.staff_summary.return_value = {"period": {}, "staff": []}

        response = self.client.get(reverse("owner:dashboard"), {"period": "90"})
        self.assertEqual(response.context["current_period"], "90")

    @patch("ui.owner.views.dashboard.date")
    @patch("ui.owner.views.dashboard.AnalyticsService")
    def test_dashboard_period_invalid(self, mock_analytics, mock_date):
        mock_date.today.return_value = FIXED_TODAY
        mock_analytics.daily_summary.return_value = {"period": {}, "daily": []}
        mock_analytics.segment_ratio.return_value = _segment_payload(0)
        mock_analytics.staff_summary.return_value = {"period": {}, "staff": []}

        response = self.client.get(reverse("owner:dashboard"), {"period": "999"})
        self.assertEqual(response.context["current_period"], "30")

    @patch("ui.owner.views.dashboard.date")
    @patch("ui.owner.views.dashboard.AnalyticsService")
    def test_dashboard_htmx_fragment(self, mock_analytics, mock_date):
        mock_date.today.return_value = FIXED_TODAY
        mock_analytics.daily_summary.return_value = {"period": {}, "daily": []}
        mock_analytics.segment_ratio.return_value = _segment_payload(0)
        mock_analytics.staff_summary.return_value = {"period": {}, "staff": []}

        response = self.client.get(
            reverse("owner:dashboard"), HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/owner/_dashboard_charts.html")
        content = response.content.decode()
        self.assertNotIn("<aside", content)
        self.assertNotIn("Shisha CRM", content)

    @patch("ui.owner.views.dashboard.date")
    @patch("ui.owner.views.dashboard.AnalyticsService")
    def test_dashboard_summary_today_visits(self, mock_analytics, mock_date):
        mock_date.today.return_value = FIXED_TODAY
        mock_analytics.daily_summary.return_value = {
            "period": {},
            "daily": [
                {
                    "date": "2026-04-14",
                    "total_visits": 2,
                    "new_visits": 0,
                    "repeat_visits": 0,
                    "regular_visits": 0,
                },
                {
                    "date": "2026-04-15",
                    "total_visits": 9,
                    "new_visits": 0,
                    "repeat_visits": 0,
                    "regular_visits": 0,
                },
            ],
        }
        mock_analytics.segment_ratio.return_value = _segment_payload()
        mock_analytics.staff_summary.return_value = _staff_payload()

        response = self.client.get(reverse("owner:dashboard"))
        self.assertEqual(response.context["today_visits"], 9)

    @patch("ui.owner.views.dashboard.date")
    @patch("ui.owner.views.dashboard.AnalyticsService")
    def test_dashboard_summary_month_visits(self, mock_analytics, mock_date):
        mock_date.today.return_value = FIXED_TODAY
        daily_rows = []
        d = date(2026, 3, 17)
        while d <= FIXED_TODAY:
            iso = d.isoformat()
            visits = 0
            if iso == "2026-04-10":
                visits = 4
            elif iso == "2026-04-12":
                visits = 6
            daily_rows.append(
                {
                    "date": iso,
                    "total_visits": visits,
                    "new_visits": 0,
                    "repeat_visits": 0,
                    "regular_visits": 0,
                }
            )
            d = d + timedelta(days=1)

        mock_analytics.daily_summary.return_value = {"period": {}, "daily": daily_rows}
        mock_analytics.segment_ratio.return_value = _segment_payload()
        mock_analytics.staff_summary.return_value = _staff_payload()

        response = self.client.get(reverse("owner:dashboard"))
        self.assertEqual(response.context["month_visits"], 10)

    @patch("ui.owner.views.dashboard.date")
    @patch("ui.owner.views.dashboard.AnalyticsService")
    def test_dashboard_summary_new_ratio(self, mock_analytics, mock_date):
        mock_date.today.return_value = FIXED_TODAY
        mock_analytics.daily_summary.return_value = {"period": {}, "daily": []}
        mock_analytics.segment_ratio.return_value = {
            "period": {},
            "total_visits": 8,
            "segments": [
                {"segment": "new", "visit_count": 3, "ratio": 0.375},
                {"segment": "repeat", "visit_count": 3, "ratio": 0.375},
                {"segment": "regular", "visit_count": 2, "ratio": 0.25},
            ],
        }
        mock_analytics.staff_summary.return_value = _staff_payload()

        response = self.client.get(reverse("owner:dashboard"))
        self.assertEqual(response.context["new_ratio"], 37.5)

    @patch("ui.owner.views.dashboard.date")
    @patch("ui.owner.views.dashboard.AnalyticsService")
    def test_dashboard_summary_active_customers(self, mock_analytics, mock_date):
        mock_date.today.return_value = FIXED_TODAY
        mock_analytics.daily_summary.return_value = {"period": {}, "daily": []}
        mock_analytics.segment_ratio.return_value = _segment_payload(0)
        mock_analytics.staff_summary.return_value = {"period": {}, "staff": []}

        Customer.objects.create(store=self.store, name="A")
        Customer.objects.create(store=self.store, name="B")
        Customer.objects.create(store=self.other_store, name="Other")

        response = self.client.get(reverse("owner:dashboard"))
        self.assertEqual(response.context["active_customer_count"], 2)

    @patch("ui.owner.views.dashboard.date")
    @patch("ui.owner.views.dashboard.AnalyticsService")
    def test_dashboard_empty_state(self, mock_analytics, mock_date):
        mock_date.today.return_value = FIXED_TODAY
        mock_analytics.daily_summary.return_value = {"period": {}, "daily": []}
        mock_analytics.segment_ratio.return_value = _segment_payload(0)
        mock_analytics.staff_summary.return_value = {"period": {}, "staff": []}

        response = self.client.get(reverse("owner:dashboard"))
        self.assertFalse(response.context["has_data"])
        self.assertEqual(response.status_code, 200)

    @patch("ui.owner.views.dashboard.date")
    @patch("ui.owner.views.dashboard.AnalyticsService")
    def test_dashboard_chart_data_daily(self, mock_analytics, mock_date):
        mock_date.today.return_value = FIXED_TODAY
        mock_analytics.daily_summary.return_value = {
            "period": {},
            "daily": [
                {
                    "date": "2026-04-14",
                    "total_visits": 1,
                    "new_visits": 0,
                    "repeat_visits": 0,
                    "regular_visits": 0,
                },
            ],
        }
        mock_analytics.segment_ratio.return_value = _segment_payload()
        mock_analytics.staff_summary.return_value = _staff_payload()

        response = self.client.get(reverse("owner:dashboard"))
        chart = response.context["chart_daily"]
        self.assertEqual(chart["labels"], ["2026-04-14"])
        self.assertEqual(len(chart["datasets"]), 1)
        self.assertEqual(chart["datasets"][0]["label"], "来客数")
        self.assertEqual(chart["datasets"][0]["data"], [1])

    @patch("ui.owner.views.dashboard.date")
    @patch("ui.owner.views.dashboard.AnalyticsService")
    def test_dashboard_chart_data_segment(self, mock_analytics, mock_date):
        mock_date.today.return_value = FIXED_TODAY
        mock_analytics.daily_summary.return_value = {"period": {}, "daily": []}
        mock_analytics.segment_ratio.return_value = _segment_payload()
        mock_analytics.staff_summary.return_value = _staff_payload()

        response = self.client.get(reverse("owner:dashboard"))
        chart = response.context["chart_segment"]
        self.assertEqual(chart["labels"], ["新規", "リピート", "常連"])
        self.assertEqual(chart["datasets"][0]["data"], [4, 3, 3])

    @patch("ui.owner.views.dashboard.date")
    @patch("ui.owner.views.dashboard.AnalyticsService")
    def test_dashboard_chart_data_staff(self, mock_analytics, mock_date):
        mock_date.today.return_value = FIXED_TODAY
        mock_analytics.daily_summary.return_value = {"period": {}, "daily": []}
        mock_analytics.segment_ratio.return_value = _segment_payload()
        mock_analytics.staff_summary.return_value = _staff_payload()

        response = self.client.get(reverse("owner:dashboard"))
        chart = response.context["chart_staff"]
        self.assertEqual(chart["labels"], ["田中"])
        self.assertEqual(chart["datasets"][0]["data"], [5])

    @patch("ui.owner.views.dashboard.date")
    @patch("ui.owner.views.dashboard.AnalyticsService")
    def test_dashboard_store_scope(self, mock_analytics, mock_date):
        mock_date.today.return_value = FIXED_TODAY
        mock_analytics.daily_summary.return_value = {"period": {}, "daily": []}
        mock_analytics.segment_ratio.return_value = _segment_payload(0)
        mock_analytics.staff_summary.return_value = {"period": {}, "staff": []}

        self.client.get(reverse("owner:dashboard"))

        expected_from = date(2026, 3, 17)
        expected_to = FIXED_TODAY
        mock_analytics.daily_summary.assert_called_with(
            self.store, expected_from, expected_to
        )
        mock_analytics.segment_ratio.assert_called_with(
            self.store, expected_from, expected_to
        )
        mock_analytics.staff_summary.assert_called_with(
            self.store, expected_from, expected_to
        )

    @patch("ui.owner.views.dashboard.date")
    @patch("ui.owner.views.dashboard.AnalyticsService")
    def test_dashboard_json_script_rendered(self, mock_analytics, mock_date):
        mock_date.today.return_value = FIXED_TODAY
        mock_analytics.daily_summary.return_value = {"period": {}, "daily": []}
        mock_analytics.segment_ratio.return_value = _segment_payload(0)
        mock_analytics.staff_summary.return_value = {"period": {}, "staff": []}

        response = self.client.get(reverse("owner:dashboard"))
        html = response.content.decode()
        self.assertIn('id="daily-data"', html)
        self.assertIn('id="segment-data"', html)
        self.assertIn('id="staff-data"', html)

    @patch("ui.owner.views.dashboard.date")
    @patch("ui.owner.views.dashboard.AnalyticsService")
    def test_dashboard_sidebar_active(self, mock_analytics, mock_date):
        mock_date.today.return_value = FIXED_TODAY
        mock_analytics.daily_summary.return_value = {"period": {}, "daily": []}
        mock_analytics.segment_ratio.return_value = _segment_payload(0)
        mock_analytics.staff_summary.return_value = {"period": {}, "staff": []}

        response = self.client.get(reverse("owner:dashboard"))
        self.assertEqual(response.context["active_sidebar"], "dashboard")

    def test_dashboard_stub_removed(self):
        match = resolve("/o/dashboard/")
        self.assertEqual(match.func.view_class, DashboardView)

    @patch("ui.owner.views.dashboard.date")
    @patch("ui.owner.views.dashboard.AnalyticsService")
    def test_dashboard_daily_zero_fill(self, mock_analytics, mock_date):
        mock_date.today.return_value = FIXED_TODAY
        mock_analytics.daily_summary.return_value = {
            "period": {},
            "daily": [
                {
                    "date": "2026-04-13",
                    "total_visits": 1,
                    "new_visits": 0,
                    "repeat_visits": 0,
                    "regular_visits": 0,
                },
                {
                    "date": "2026-04-14",
                    "total_visits": 0,
                    "new_visits": 0,
                    "repeat_visits": 0,
                    "regular_visits": 0,
                },
                {
                    "date": "2026-04-15",
                    "total_visits": 2,
                    "new_visits": 0,
                    "repeat_visits": 0,
                    "regular_visits": 0,
                },
            ],
        }
        mock_analytics.segment_ratio.return_value = _segment_payload()
        mock_analytics.staff_summary.return_value = _staff_payload()

        response = self.client.get(reverse("owner:dashboard"))
        chart = response.context["chart_daily"]
        self.assertEqual(
            chart["labels"],
            ["2026-04-13", "2026-04-14", "2026-04-15"],
        )
        self.assertEqual(chart["datasets"][0]["data"], [1, 0, 2])

    @patch("ui.owner.views.dashboard.date")
    @patch("ui.owner.views.dashboard.AnalyticsService")
    def test_dashboard_month_visits_independent(self, mock_analytics, mock_date):
        mock_date.today.return_value = FIXED_TODAY

        def daily_side_effect(store, df, dt):
            if df == date(2026, 4, 9):
                return {
                    "period": {},
                    "daily": [
                        {
                            "date": "2026-04-15",
                            "total_visits": 3,
                            "new_visits": 0,
                            "repeat_visits": 0,
                            "regular_visits": 0,
                        },
                    ],
                }
            if df == date(2026, 4, 1):
                return {
                    "period": {},
                    "daily": [
                        {
                            "date": "2026-04-01",
                            "total_visits": 10,
                            "new_visits": 0,
                            "repeat_visits": 0,
                            "regular_visits": 0,
                        },
                        {
                            "date": "2026-04-15",
                            "total_visits": 7,
                            "new_visits": 0,
                            "repeat_visits": 0,
                            "regular_visits": 0,
                        },
                    ],
                }
            return {"period": {}, "daily": []}

        mock_analytics.daily_summary.side_effect = daily_side_effect
        mock_analytics.segment_ratio.return_value = _segment_payload()
        mock_analytics.staff_summary.return_value = _staff_payload()

        response = self.client.get(reverse("owner:dashboard"), {"period": "7"})
        self.assertEqual(response.context["month_visits"], 17)
        self.assertEqual(mock_analytics.daily_summary.call_count, 2)
        mock_analytics.daily_summary.assert_has_calls(
            [
                call(self.store, date(2026, 4, 9), FIXED_TODAY),
                call(self.store, date(2026, 4, 1), FIXED_TODAY),
            ]
        )

    @patch("ui.owner.views.dashboard.date")
    @patch("ui.owner.views.dashboard.AnalyticsService")
    def test_dashboard_canvas_always_rendered(self, mock_analytics, mock_date):
        mock_date.today.return_value = FIXED_TODAY
        mock_analytics.daily_summary.return_value = {"period": {}, "daily": []}
        mock_analytics.segment_ratio.return_value = _segment_payload(0)
        mock_analytics.staff_summary.return_value = {"period": {}, "staff": []}

        response = self.client.get(reverse("owner:dashboard"))
        self.assertFalse(response.context["has_data"])
        html = response.content.decode()
        self.assertEqual(html.count('id="chart-daily"'), 1)
        self.assertEqual(html.count('id="chart-segment"'), 1)
        self.assertEqual(html.count('id="chart-staff"'), 1)

    @patch("ui.owner.views.dashboard.date")
    @patch("ui.owner.views.dashboard.AnalyticsService")
    def test_chart_containers_have_fixed_height(self, mock_analytics, mock_date):
        """チャート親 div に h-[300px] が設定されていること（Issue #36 回帰防止）"""
        mock_date.today.return_value = FIXED_TODAY
        mock_analytics.daily_summary.return_value = {"period": {}, "daily": []}
        mock_analytics.segment_ratio.return_value = _segment_payload(0)
        mock_analytics.staff_summary.return_value = {"period": {}, "staff": []}

        response = self.client.get(reverse("owner:dashboard"))
        content = response.content.decode()
        self.assertEqual(content.count("h-[300px]"), 3)

    @patch("ui.owner.views.dashboard.date")
    @patch("ui.owner.views.dashboard.AnalyticsService")
    def test_canvas_no_fixed_height_attribute(self, mock_analytics, mock_date):
        """canvas に height 属性が残っていないこと（Issue #36 回帰防止）"""
        mock_date.today.return_value = FIXED_TODAY
        mock_analytics.daily_summary.return_value = {"period": {}, "daily": []}
        mock_analytics.segment_ratio.return_value = _segment_payload(0)
        mock_analytics.staff_summary.return_value = {"period": {}, "staff": []}

        response = self.client.get(reverse("owner:dashboard"))
        content = response.content.decode()
        canvas_with_height = re.findall(r"<canvas[^>]*height=", content)
        self.assertEqual(
            len(canvas_with_height),
            0,
            f"canvas に height 属性が残っています: {canvas_with_height}",
        )
