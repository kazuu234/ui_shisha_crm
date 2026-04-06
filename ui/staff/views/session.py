from types import SimpleNamespace

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Max
from django.http import HttpResponse, QueryDict
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.generic import TemplateView

from customers.models import Customer
from tasks.models import HearingTask
from tasks.services import HearingTaskService
from visits.models import Visit

from ui.mixins import StaffRequiredMixin, StoreMixin
from ui.staff.forms.customer import CustomerFieldUpdateForm

TASK_FIELD_CONFIG = {
    "age": {
        "label": "年齢",
        "type": "selection",
        "choices": [
            (10, "10代"),
            (20, "20代"),
            (30, "30代"),
            (40, "40代"),
            (50, "50代以上"),
        ],
    },
    "area": {
        "label": "居住エリア",
        "type": "text",
        "placeholder": "例: 渋谷周辺",
    },
    "shisha_experience": {
        "label": "シーシャ歴",
        "type": "selection",
        "choices": [
            ("none", "なし"),
            ("beginner", "初心者"),
            ("intermediate", "中級"),
            ("advanced", "上級"),
        ],
    },
}

SEGMENT_DISPLAY = {
    "new": "新規",
    "repeat": "リピート",
    "regular": "常連",
}


def _get_recent_areas(store, limit=10):
    """Store 内の Customer から最近入力された area のユニーク値を取得する。"""
    rows = (
        Customer.objects.for_store(store)
        .filter(area__isnull=False)
        .exclude(area="")
        .values("area")
        .annotate(last_updated=Max("updated_at"))
        .order_by("-last_updated")[:limit]
    )
    return [row["area"] for row in rows]


def _build_hearing_summary(customer):
    hearing_summary = []
    for field_name, config in TASK_FIELD_CONFIG.items():
        raw_value = getattr(customer, field_name, None)
        if raw_value is not None and raw_value != "":
            if config.get("type") == "selection":
                display = raw_value
                for choice_val, label in config.get("choices", []):
                    if choice_val == raw_value:
                        display = label
                        break
            else:
                display = str(raw_value)
        else:
            display = None
        hearing_summary.append(
            {
                "label": config["label"],
                "value": display,
            }
        )
    return hearing_summary


class SessionView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, TemplateView):
    template_name = "ui/staff/session.html"
    login_url = "/s/login/"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer = get_object_or_404(
            Customer.objects.for_store(self.store),
            pk=self.kwargs["pk"],
        )
        customer.segment_display = SEGMENT_DISPLAY.get(customer.segment, customer.segment)

        open_tasks = list(
            HearingTask.objects.for_store(self.store)
            .filter(customer=customer, status=HearingTask.STATUS_OPEN)
            .order_by("field_name")
        )
        for task in open_tasks:
            task.config = TASK_FIELD_CONFIG.get(task.field_name, {})

        area_task_open = any(t.field_name == "area" for t in open_tasks)
        if area_task_open:
            context["recent_areas"] = _get_recent_areas(self.store)
        else:
            context["recent_areas"] = []

        recent_visits = list(
            Visit.objects.for_store(self.store)
            .filter(customer=customer)
            .select_related("staff")
            .order_by("-visited_at", "-created_at")[:5]
        )
        last_visited_at = recent_visits[0].visited_at if recent_visits else None

        hearing_summary = _build_hearing_summary(customer)

        context["customer"] = customer
        context["last_visited_at"] = last_visited_at
        context["tasks"] = open_tasks
        context["recent_visits"] = recent_visits
        context["active_tab"] = "session"
        context["session_url"] = f"/s/customers/{customer.pk}/session/"
        context["hearing_summary"] = hearing_summary
        return context


class CustomerFieldUpdateView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, View):
    login_url = "/s/login/"

    def patch(self, request, pk):
        customer = get_object_or_404(
            Customer.objects.for_store(self.store),
            pk=pk,
        )
        data = QueryDict(request.body)
        form = CustomerFieldUpdateForm(data)
        if not form.is_valid():
            field_name = data.get("field", "") or ""
            task = (
                HearingTask.objects.for_store(self.store)
                .filter(customer=customer, field_name=field_name)
                .order_by("-pk")
                .first()
            )
            if task is None:
                task = SimpleNamespace(field_name=field_name or "unknown")
            err_txt = form.errors.as_text()
            ctx = {
                "task": task,
                "config": TASK_FIELD_CONFIG.get(field_name, {}),
                "customer": customer,
                "error": err_txt,
                "filled": False,
            }
            if field_name == "area":
                area_task_open = HearingTask.objects.for_store(self.store).filter(
                    customer=customer,
                    field_name="area",
                    status=HearingTask.STATUS_OPEN,
                ).exists()
                if area_task_open:
                    ctx["recent_areas"] = _get_recent_areas(self.store)
            response = render(
                request,
                "ui/staff/_zone_task.html",
                ctx,
            )
            response.status_code = 422
            return response

        field_name = form.cleaned_data["field"]
        value = form.cleaned_data["value"]

        setattr(customer, field_name, value)
        customer.save(update_fields=[field_name])
        customer.refresh_from_db()

        HearingTaskService.sync_tasks(customer)

        remaining = HearingTask.objects.for_store(self.store).filter(
            customer=customer,
            status=HearingTask.STATUS_OPEN,
        )

        task = (
            HearingTask.objects.for_store(self.store)
            .filter(customer=customer, field_name=field_name)
            .order_by("-status", "-pk")
            .first()
        )
        config = TASK_FIELD_CONFIG.get(field_name, {})
        if task is None:
            task = SimpleNamespace(field_name=field_name)
        else:
            task.config = config

        actual_value = getattr(customer, field_name)
        is_filled = actual_value is not None and actual_value != ""

        response = render(
            request,
            "ui/staff/_zone_task.html",
            {
                "task": task,
                "config": config,
                "customer": customer,
                "filled": is_filled,
                "filled_label": self._filled_label(field_name, actual_value) if is_filled else "",
            },
        )
        if not remaining.exists():
            response["HX-Trigger"] = "all-tasks-done"
        return response

    def _filled_label(self, field_name, value):
        cfg = TASK_FIELD_CONFIG.get(field_name, {})
        if cfg.get("type") == "selection":
            for choice_value, label in cfg.get("choices", []):
                if choice_value == value:
                    return label
        return str(value) if value is not None else ""


class SessionHeaderFragmentView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, View):
    login_url = "/s/login/"

    def get(self, request, pk):
        customer = get_object_or_404(Customer.objects.for_store(self.store), pk=pk)
        customer.segment_display = SEGMENT_DISPLAY.get(customer.segment, customer.segment)
        last_visited_at = (
            Visit.objects.for_store(self.store)
            .filter(customer=customer)
            .order_by("-visited_at")
            .values_list("visited_at", flat=True)
            .first()
        )
        return render(
            request,
            "ui/staff/_customer_header.html",
            {"customer": customer, "last_visited_at": last_visited_at},
        )


class SessionRecentVisitsFragmentView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, View):
    login_url = "/s/login/"

    def get(self, request, pk):
        customer = get_object_or_404(Customer.objects.for_store(self.store), pk=pk)
        recent_visits = (
            Visit.objects.for_store(self.store)
            .filter(customer=customer)
            .select_related("staff")
            .order_by("-visited_at", "-created_at")[:5]
        )
        return render(
            request,
            "ui/staff/_recent_visits.html",
            {"recent_visits": recent_visits, "customer": customer},
        )


class SessionHearingSummaryFragmentView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, View):
    login_url = "/s/login/"

    def get(self, request, pk):
        customer = get_object_or_404(Customer.objects.for_store(self.store), pk=pk)
        has_open = HearingTask.objects.for_store(self.store).filter(
            customer=customer,
            status=HearingTask.STATUS_OPEN,
        ).exists()
        if has_open:
            return HttpResponse(status=204)
        hearing_summary = _build_hearing_summary(customer)
        return render(
            request,
            "ui/staff/_hearing_summary.html",
            {"hearing_summary": hearing_summary, "customer": customer},
        )
