from types import SimpleNamespace

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import QueryDict
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

        recent_visits = list(
            Visit.objects.for_store(self.store)
            .filter(customer=customer)
            .select_related("staff")
            .order_by("-visited_at")[:5]
        )
        last_visited_at = recent_visits[0].visited_at if recent_visits else None

        context["customer"] = customer
        context["last_visited_at"] = last_visited_at
        context["tasks"] = open_tasks
        context["recent_visits"] = recent_visits
        context["active_tab"] = "session"
        context["session_url"] = f"/s/customers/{customer.pk}/session/"
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
            response = render(
                request,
                "ui/staff/_zone_task.html",
                {
                    "task": task,
                    "config": TASK_FIELD_CONFIG.get(field_name, {}),
                    "customer": customer,
                    "error": err_txt,
                    "filled": False,
                },
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
            .order_by("-visited_at")[:5]
        )
        return render(
            request,
            "ui/staff/_recent_visits.html",
            {"recent_visits": recent_visits, "customer": customer},
        )
