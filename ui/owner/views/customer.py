from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Count, F, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, ListView

from core.exceptions import BusinessError
from customers.models import Customer
from tasks.models import HearingTask
from tasks.services import HearingTaskService
from visits.models import Visit

from ui.mixins import OwnerRequiredMixin, StoreMixin
from ui.owner.forms.customer import CustomerEditForm

HEARING_FIELD_LABELS = {
    "age": "年齢",
    "area": "居住エリア",
    "shisha_experience": "シーシャ歴",
}

SHISHA_EXPERIENCE_CHOICES = [
    ("none", "なし"),
    ("beginner", "初心者"),
    ("intermediate", "中級"),
    ("advanced", "上級"),
]

SHISHA_EXPERIENCE_DISPLAY = dict(SHISHA_EXPERIENCE_CHOICES)

ALLOWED_SORT_FIELDS = {
    "name": F("name").asc(),
    "-name": F("name").desc(),
    "visit_count": F("visit_count").asc(),
    "-visit_count": F("visit_count").desc(),
    "last_visited_at": F("last_visited_at").asc(nulls_last=True),
    "-last_visited_at": F("last_visited_at").desc(nulls_last=True),
}
DEFAULT_SORT = "-last_visited_at"
ALLOWED_SEGMENTS = {"new", "repeat", "regular"}

HEARING_FIELDS = frozenset({"age", "area", "shisha_experience"})


class CustomerListView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, ListView):
    template_name = "ui/owner/customer_list.html"
    context_object_name = "customers"
    paginate_by = 25
    login_url = "/o/login/"

    def get_queryset(self):
        qs = Customer.objects.for_store(self.store)

        search = self.request.GET.get("search", "").strip()
        if search:
            qs = qs.filter(name__icontains=search)

        segment = self.request.GET.get("segment", "").strip()
        if segment in ALLOWED_SEGMENTS:
            qs = qs.filter(segment=segment)

        latest_visit = (
            Visit.objects.filter(
                customer=OuterRef("pk"),
                is_deleted=False,
            )
            .order_by("-visited_at")
            .values("visited_at")[:1]
        )
        qs = qs.annotate(last_visited_at=Subquery(latest_visit))

        qs = qs.annotate(
            open_task_count=Count(
                "hearing_tasks",
                filter=Q(hearing_tasks__status="open"),
            )
        )

        sort = self.request.GET.get("sort", DEFAULT_SORT).strip()
        if sort in ALLOWED_SORT_FIELDS:
            order_expr = ALLOWED_SORT_FIELDS[sort]
        else:
            order_expr = ALLOWED_SORT_FIELDS[DEFAULT_SORT]
        qs = qs.order_by(order_expr, "pk")

        return qs

    def get_template_names(self):
        if self.request.headers.get("HX-Request") == "true":
            return ["ui/owner/_customer_table.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_sidebar"] = "customers"

        context["current_search"] = self.request.GET.get("search", "").strip()

        raw_segment = self.request.GET.get("segment", "").strip()
        context["current_segment"] = (
            raw_segment if raw_segment in ALLOWED_SEGMENTS else ""
        )

        raw_sort = self.request.GET.get("sort", DEFAULT_SORT).strip()
        current_sort = raw_sort if raw_sort in ALLOWED_SORT_FIELDS else DEFAULT_SORT
        context["current_sort"] = current_sort

        context["sort_toggle_name"] = "-name" if current_sort == "name" else "name"
        context["sort_toggle_visit_count"] = (
            "-visit_count" if current_sort == "visit_count" else "visit_count"
        )
        context["sort_toggle_last_visited"] = (
            "-last_visited_at"
            if current_sort == "last_visited_at"
            else "last_visited_at"
        )

        context["segment_choices"] = [
            ("", "全て"),
            ("new", "新規"),
            ("repeat", "リピート"),
            ("regular", "常連"),
        ]
        context["customer_list_url"] = reverse("owner:customer-list")
        return context


class CustomerDetailView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, DetailView):
    template_name = "ui/owner/customer_detail.html"
    context_object_name = "customer"
    login_url = "/o/login/"

    def get_object(self):
        return get_object_or_404(
            Customer.objects.for_store(self.store),
            pk=self.kwargs["pk"],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer = self.object

        context["visits"] = (
            Visit.objects.for_store(self.store)
            .filter(customer=customer)
            .select_related("staff")
            .order_by("-visited_at", "-created_at")
        )

        open_tasks = (
            HearingTask.objects.for_store(self.store)
            .filter(customer=customer, status="open")
            .order_by("created_at")
        )
        context["open_tasks"] = [
            {
                "field_name": task.field_name,
                "field_label": HEARING_FIELD_LABELS.get(
                    task.field_name, task.field_name
                ),
                "created_at": task.created_at,
            }
            for task in open_tasks
        ]

        context["shisha_experience_label"] = (
            SHISHA_EXPERIENCE_DISPLAY.get(customer.shisha_experience)
            if customer.shisha_experience
            else None
        )

        toast = self.request.session.pop("toast", None)
        if toast:
            context["toast"] = toast

        context["active_sidebar"] = "customers"
        return context


class CustomerEditView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    template_name = "ui/owner/customer_edit.html"
    login_url = "/o/login/"

    def _get_customer(self):
        return get_object_or_404(
            Customer.objects.for_store(self.store),
            pk=self.kwargs["pk"],
        )

    def _render(self, request, form, customer):
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "customer": customer,
                "active_sidebar": "customers",
            },
        )

    def get(self, request, pk):
        customer = self._get_customer()
        form = CustomerEditForm(instance=customer)
        return self._render(request, form, customer)

    def post(self, request, pk):
        customer = self._get_customer()
        old_hearing_values = {f: getattr(customer, f) for f in HEARING_FIELDS}
        form = CustomerEditForm(request.POST, instance=customer)
        if not form.is_valid():
            return self._render(request, form, customer)

        new_hearing_values = {f: form.cleaned_data.get(f) for f in HEARING_FIELDS}

        try:
            with transaction.atomic():
                updated_customer = form.save()
                if old_hearing_values != new_hearing_values:
                    HearingTaskService.sync_tasks(updated_customer)
        except BusinessError as exc:
            detail = getattr(exc, "detail", str(exc))
            form.add_error(None, str(detail))
            return self._render(request, form, customer)

        request.session["toast"] = {
            "message": "顧客情報を更新しました",
            "type": "success",
        }
        return redirect(
            reverse("owner:customer-detail", kwargs={"pk": customer.pk}),
        )
