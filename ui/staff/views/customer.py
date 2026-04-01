import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, F, OuterRef, Q, Subquery
from django.http import HttpResponse, HttpResponseBadRequest, QueryDict
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.generic import TemplateView

from customers.models import Customer
from tasks.services import HearingTaskService
from visits.models import Visit

from ui.mixins import StaffRequiredMixin, StoreMixin
from ui.staff.forms.customer import CustomerCreateForm, CustomerEditFieldForm

SEGMENT_DISPLAY = {"new": "新規", "repeat": "リピート", "regular": "常連"}

EXPERIENCE_DISPLAY = {
    "none": "なし",
    "beginner": "初心者",
    "intermediate": "中級",
    "advanced": "上級",
}

EDIT_FIELD_CONFIG = {
    "name": {
        "label": "名前",
        "type": "text",
        "placeholder": "顧客の名前",
        "is_hearing": False,
    },
    "age": {
        "label": "年齢",
        "type": "number",
        "placeholder": "例: 25",
        "is_hearing": True,
    },
    "area": {
        "label": "居住エリア",
        "type": "text",
        "placeholder": "例: 渋谷",
        "is_hearing": True,
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
        "is_hearing": True,
    },
    "line_id": {
        "label": "LINE ID",
        "type": "text",
        "placeholder": "LINE ID を入力",
        "is_hearing": False,
    },
    "memo": {
        "label": "メモ",
        "type": "textarea",
        "placeholder": "顧客に関するメモ",
        "is_hearing": False,
    },
}

HEARING_FIELDS = {k for k, v in EDIT_FIELD_CONFIG.items() if v.get("is_hearing")}

ZONE_TEMPLATES = {
    "name": "ui/staff/_zone_edit_name.html",
    "age": "ui/staff/_zone_edit_age.html",
    "area": "ui/staff/_zone_edit_area.html",
    "shisha_experience": "ui/staff/_zone_edit_exp.html",
    "line_id": "ui/staff/_zone_edit_line_id.html",
    "memo": "ui/staff/_zone_edit_memo.html",
}


def _annotate_customer_display(customer):
    customer.segment_display = SEGMENT_DISPLAY.get(customer.segment, customer.segment)
    customer.age_display = f"{customer.age}歳" if customer.age is not None else None
    customer.shisha_experience_display = (
        EXPERIENCE_DISPLAY.get(customer.shisha_experience) if customer.shisha_experience else None
    )


def _annotate_segment_display(customers):
    for c in customers:
        c.segment_display = SEGMENT_DISPLAY.get(c.segment, c.segment)


class CustomerSelectView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, TemplateView):
    template_name = "ui/staff/customer_select.html"
    login_url = "/s/login/"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        last_visit_sq = (
            Visit.objects.filter(customer=OuterRef("pk"), store_id=OuterRef("store_id"))
            .order_by("-visited_at")
            .values("visited_at")[:1]
        )
        customers = (
            Customer.objects.for_store(self.store)
            .annotate(
                last_visited_at=Subquery(last_visit_sq),
                open_task_count=Count(
                    "hearing_tasks",
                    filter=Q(hearing_tasks__status="open"),
                ),
            )
            .order_by(F("last_visited_at").desc(nulls_last=True))[:20]
        )
        customers = list(customers)
        _annotate_segment_display(customers)
        context["customers"] = customers
        context["active_tab"] = "customers"
        context["form"] = CustomerCreateForm()
        return context


class CustomerSearchView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, View):
    login_url = "/s/login/"

    def get(self, request):
        q = request.GET.get("q", "").strip()
        if not q:
            return render(
                request,
                "ui/staff/_customer_search_results.html",
                {"customers": [], "has_query": False},
            )
        last_visit_sq = (
            Visit.objects.filter(customer=OuterRef("pk"), store_id=OuterRef("store_id"))
            .order_by("-visited_at")
            .values("visited_at")[:1]
        )
        customers = (
            Customer.objects.for_store(self.store)
            .filter(name__icontains=q)
            .annotate(
                last_visited_at=Subquery(last_visit_sq),
                open_task_count=Count(
                    "hearing_tasks",
                    filter=Q(hearing_tasks__status="open"),
                ),
            )
            .order_by(F("last_visited_at").desc(nulls_last=True))[:20]
        )
        customers = list(customers)
        _annotate_segment_display(customers)
        return render(
            request,
            "ui/staff/_customer_search_results.html",
            {"customers": customers, "has_query": True},
        )


class CustomerCreateView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, View):
    login_url = "/s/login/"

    def get(self, request):
        form = CustomerCreateForm()
        return render(request, "ui/staff/_customer_create_modal.html", {"form": form})

    def post(self, request):
        form = CustomerCreateForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                "ui/staff/_customer_create_form_content.html",
                {"form": form},
            )

        name = form.cleaned_data["name"]
        customer = Customer.objects.create(store=self.store, name=name)
        HearingTaskService.generate_tasks(customer)

        response = HttpResponse(status=204)
        response["HX-Redirect"] = f"/s/customers/{customer.pk}/session/"
        return response


class CustomerDetailView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, TemplateView):
    template_name = "ui/staff/customer_detail.html"
    login_url = "/s/login/"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer = get_object_or_404(
            Customer.objects.for_store(self.store),
            pk=self.kwargs["pk"],
        )
        _annotate_customer_display(customer)

        recent_visits = (
            Visit.objects.for_store(self.store)
            .filter(customer=customer)
            .select_related("staff")
            .order_by("-visited_at", "-created_at")[:5]
        )

        context["customer"] = customer
        context["recent_visits"] = recent_visits
        context["active_tab"] = "customers"
        context["session_url"] = f"/s/customers/{customer.pk}/session/"
        return context


class CustomerEditView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, TemplateView):
    template_name = "ui/staff/customer_edit.html"
    login_url = "/s/login/"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer = get_object_or_404(
            Customer.objects.for_store(self.store),
            pk=self.kwargs["pk"],
        )
        _annotate_customer_display(customer)

        context["customer"] = customer
        context["active_tab"] = "customers"
        context["session_url"] = f"/s/customers/{customer.pk}/session/"
        context["name_config"] = EDIT_FIELD_CONFIG["name"]
        context["age_config"] = EDIT_FIELD_CONFIG["age"]
        context["area_config"] = EDIT_FIELD_CONFIG["area"]
        context["exp_config"] = EDIT_FIELD_CONFIG["shisha_experience"]
        context["line_id_config"] = EDIT_FIELD_CONFIG["line_id"]
        context["memo_config"] = EDIT_FIELD_CONFIG["memo"]
        return context


class CustomerEditFieldView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, View):
    login_url = "/s/login/"

    def patch(self, request, pk):
        customer = get_object_or_404(
            Customer.objects.for_store(self.store),
            pk=pk,
        )
        data = QueryDict(request.body)
        form = CustomerEditFieldForm(data)

        field_name = data.get("field", "")
        template_name = ZONE_TEMPLATES.get(field_name)

        if not form.is_valid():
            if not template_name:
                return HttpResponseBadRequest("無効なフィールドです")

            _annotate_customer_display(customer)
            response = render(
                request,
                template_name,
                {
                    "customer": customer,
                    "config": EDIT_FIELD_CONFIG.get(field_name, {}),
                    "error": form.errors.as_text(),
                },
            )
            response.status_code = 422
            return response

        field_name = form.cleaned_data["field"]
        value = form.cleaned_data["value"]
        template_name = ZONE_TEMPLATES[field_name]

        if field_name == "memo" and value is None:
            value = ""

        setattr(customer, field_name, value)
        customer.save(update_fields=[field_name])
        customer.refresh_from_db()

        if field_name in HEARING_FIELDS:
            HearingTaskService.sync_tasks(customer)

        _annotate_customer_display(customer)

        response = render(
            request,
            template_name,
            {
                "customer": customer,
                "config": EDIT_FIELD_CONFIG[field_name],
            },
        )
        response["HX-Trigger"] = json.dumps(
            {"showToast": {"message": "保存しました", "type": "success"}}
        )
        return response
