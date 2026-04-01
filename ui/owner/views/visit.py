import uuid
from datetime import date as date_type

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import ListView

from accounts.models import Staff
from visits.models import Visit

from ui.mixins import OwnerRequiredMixin, StoreMixin
from ui.owner.forms.visit import VisitEditForm

ALLOWED_SORT_FIELDS = {
    "visited_at": F("visited_at").asc(),
    "-visited_at": F("visited_at").desc(),
    "customer_name": F("customer__name").asc(),
    "-customer_name": F("customer__name").desc(),
}
DEFAULT_SORT = "-visited_at"
ALLOWED_SEGMENTS = {"new", "repeat", "regular"}


class VisitListView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, ListView):
    template_name = "ui/owner/visit_list.html"
    context_object_name = "visits"
    paginate_by = 25
    login_url = "/o/login/"

    def get_queryset(self):
        qs = Visit.objects.for_store(self.store).select_related("customer", "staff")

        search = self.request.GET.get("search", "").strip()
        if search:
            qs = qs.filter(customer__name__icontains=search)

        segment = self.request.GET.get("segment", "").strip()
        if segment in ALLOWED_SEGMENTS:
            qs = qs.filter(customer__segment=segment)

        staff_id = self.request.GET.get("staff", "").strip()
        if staff_id:
            try:
                staff_uuid = uuid.UUID(staff_id)
                if Staff.objects.filter(
                    pk=staff_uuid, store=self.store, is_active=True
                ).exists():
                    qs = qs.filter(staff_id=staff_uuid)
            except (ValueError, AttributeError):
                pass

        date_from = self.request.GET.get("date_from", "").strip()
        date_to = self.request.GET.get("date_to", "").strip()
        if date_from:
            try:
                date_type.fromisoformat(date_from)
                qs = qs.filter(visited_at__gte=date_from)
            except ValueError:
                pass
        if date_to:
            try:
                date_type.fromisoformat(date_to)
                qs = qs.filter(visited_at__lte=date_to)
            except ValueError:
                pass

        sort = self.request.GET.get("sort", DEFAULT_SORT).strip()
        if sort in ALLOWED_SORT_FIELDS:
            order_expr = ALLOWED_SORT_FIELDS[sort]
        else:
            order_expr = ALLOWED_SORT_FIELDS[DEFAULT_SORT]
        qs = qs.order_by(order_expr, "-created_at", "pk")

        return qs

    def get_template_names(self):
        if self.request.headers.get("HX-Request") == "true":
            return ["ui/owner/_visit_table.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_sidebar"] = "visits"
        context["current_search"] = self.request.GET.get("search", "").strip()

        raw_segment = self.request.GET.get("segment", "").strip()
        context["current_segment"] = (
            raw_segment if raw_segment in ALLOWED_SEGMENTS else ""
        )

        raw_sort = self.request.GET.get("sort", DEFAULT_SORT).strip()
        current_sort = raw_sort if raw_sort in ALLOWED_SORT_FIELDS else DEFAULT_SORT
        context["current_sort"] = current_sort

        context["sort_toggle_visited_at"] = (
            "-visited_at" if current_sort == "visited_at" else "visited_at"
        )
        context["sort_toggle_customer_name"] = (
            "-customer_name"
            if current_sort == "customer_name"
            else "customer_name"
        )

        staff_id_raw = self.request.GET.get("staff", "").strip()
        try:
            staff_uuid = uuid.UUID(staff_id_raw)
            if Staff.objects.filter(
                pk=staff_uuid, store=self.store, is_active=True
            ).exists():
                context["current_staff"] = staff_id_raw
            else:
                context["current_staff"] = ""
        except (ValueError, AttributeError):
            context["current_staff"] = ""

        for key in ("date_from", "date_to"):
            raw = self.request.GET.get(key, "").strip()
            try:
                date_type.fromisoformat(raw) if raw else None
                context[f"current_{key}"] = raw
            except ValueError:
                context[f"current_{key}"] = ""

        context["segment_choices"] = [
            ("", "全て"),
            ("new", "新規"),
            ("repeat", "リピート"),
            ("regular", "常連"),
        ]

        context["staff_choices"] = (
            Staff.objects.filter(store=self.store, is_active=True)
            .order_by("display_name")
            .values_list("pk", "display_name")
        )

        context["visit_list_url"] = reverse("owner:visit-list")

        toast = self.request.session.pop("toast", None)
        if toast:
            context["toast"] = toast

        return context


class VisitEditView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    template_name = "ui/owner/visit_edit.html"
    login_url = "/o/login/"

    def _get_visit(self):
        return get_object_or_404(
            Visit.objects.for_store(self.store).select_related("customer", "staff"),
            pk=self.kwargs["pk"],
        )

    def _render(self, request, form, visit):
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "visit": visit,
                "active_sidebar": "visits",
            },
        )

    def get(self, request, pk):
        visit = self._get_visit()
        form = VisitEditForm(instance=visit)
        return self._render(request, form, visit)

    def post(self, request, pk):
        visit = self._get_visit()
        form = VisitEditForm(request.POST, instance=visit)
        if not form.is_valid():
            return self._render(request, form, visit)

        form.save()

        request.session["toast"] = {
            "message": "来店記録を更新しました",
            "type": "success",
        }
        return redirect(reverse("owner:visit-list"))


class VisitDeleteView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    login_url = "/o/login/"

    def post(self, request, pk):
        visit = get_object_or_404(
            Visit.objects.for_store(self.store),
            pk=self.kwargs["pk"],
        )

        visit.soft_delete()

        request.session["toast"] = {
            "message": "来店記録を削除しました",
            "type": "success",
        }
        return redirect(reverse("owner:visit-list"))
