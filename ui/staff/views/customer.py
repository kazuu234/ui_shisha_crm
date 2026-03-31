from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, F, OuterRef, Q, Subquery
from django.http import HttpResponse
from django.shortcuts import render
from django.views import View
from django.views.generic import TemplateView

from customers.models import Customer
from tasks.services import HearingTaskService
from visits.models import Visit

from ui.mixins import StaffRequiredMixin, StoreMixin
from ui.staff.forms.customer import CustomerCreateForm

SEGMENT_DISPLAY = {"new": "新規", "repeat": "リピート", "regular": "常連"}


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
