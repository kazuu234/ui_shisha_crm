from datetime import date, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from analytics.services import AnalyticsService
from customers.models import Customer
from ui.mixins import OwnerRequiredMixin, StoreMixin

PERIOD_CHOICES = {
    "7": 7,
    "30": 30,
    "90": 90,
}
DEFAULT_PERIOD = "30"


class DashboardView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, TemplateView):
    template_name = "ui/owner/dashboard.html"
    login_url = "/o/login/"

    def get_period(self):
        period_key = self.request.GET.get("period", DEFAULT_PERIOD).strip()
        if period_key not in PERIOD_CHOICES:
            period_key = DEFAULT_PERIOD
        return period_key, PERIOD_CHOICES[period_key]

    def get_template_names(self):
        if self.request.headers.get("HX-Request") == "true":
            return ["ui/owner/_dashboard_charts.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        store = self.store

        period_key, days = self.get_period()
        date_to = date.today()
        date_from = date_to - timedelta(days=days - 1)

        daily_data = AnalyticsService.daily_summary(store, date_from, date_to)
        segment_data = AnalyticsService.segment_ratio(store, date_from, date_to)
        staff_data = AnalyticsService.staff_summary(store, date_from, date_to)

        today_str = date_to.isoformat()
        today_visits = 0
        for day in daily_data.get("daily", []):
            if day.get("date") == today_str:
                today_visits = day.get("total_visits", 0)
                break

        month_start = date_to.replace(day=1)
        if month_start < date_from:
            month_daily = AnalyticsService.daily_summary(store, month_start, date_to)
        else:
            month_daily = daily_data
        month_visits = 0
        for day in month_daily.get("daily", []):
            day_date = day.get("date", "")
            if day_date >= month_start.isoformat():
                month_visits += day.get("total_visits", 0)

        new_ratio = 0.0
        for seg in segment_data.get("segments", []):
            if seg.get("segment") == "new":
                new_ratio = seg.get("ratio", 0.0)
                break

        active_customer_count = Customer.objects.for_store(store).count()

        total_visits = segment_data.get("total_visits", 0)
        has_data = total_visits > 0

        chart_daily = {
            "labels": [d["date"] for d in daily_data.get("daily", [])],
            "datasets": [
                {
                    "label": "来客数",
                    "data": [d["total_visits"] for d in daily_data.get("daily", [])],
                }
            ],
        }

        segment_labels_map = {"new": "新規", "repeat": "リピート", "regular": "常連"}
        chart_segment = {
            "labels": [
                segment_labels_map.get(s["segment"], s["segment"])
                for s in segment_data.get("segments", [])
            ],
            "datasets": [
                {
                    "data": [s["visit_count"] for s in segment_data.get("segments", [])],
                }
            ],
        }

        chart_staff = {
            "labels": [s["display_name"] for s in staff_data.get("staff", [])],
            "datasets": [
                {
                    "label": "対応数",
                    "data": [s["total_visits"] for s in staff_data.get("staff", [])],
                }
            ],
        }

        context.update(
            {
                "active_sidebar": "dashboard",
                "current_period": period_key,
                "period_choices": [
                    ("7", "7日"),
                    ("30", "30日"),
                    ("90", "90日"),
                ],
                "today_visits": today_visits,
                "month_visits": month_visits,
                "new_ratio": round(new_ratio * 100, 1),
                "active_customer_count": active_customer_count,
                "chart_daily": chart_daily,
                "chart_segment": chart_segment,
                "chart_staff": chart_staff,
                "has_data": has_data,
            }
        )
        return context
