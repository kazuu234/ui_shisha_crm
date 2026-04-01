import json
from datetime import date

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, render
from django.views import View

from customers.models import Customer
from visits.models import Visit

from ui.mixins import StaffRequiredMixin, StoreMixin
from ui.staff.forms.customer import VisitCreateForm


class VisitCreateView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, View):
    login_url = "/s/login/"

    def post(self, request):
        form = VisitCreateForm(request.POST)
        if not form.is_valid():
            customer_id = request.POST.get("customer_id")
            customer = None
            if customer_id:
                customer = Customer.objects.for_store(self.store).filter(pk=customer_id).first()
            response = render(
                request,
                "ui/staff/_visit_button.html",
                {
                    "customer": customer,
                    "error": "入力内容に誤りがあります",
                },
            )
            response.status_code = 422
            return response

        customer = get_object_or_404(
            Customer.objects.for_store(self.store),
            pk=form.cleaned_data["customer_id"],
        )
        memo = form.cleaned_data.get("conversation_memo") or ""

        Visit.objects.create(
            store=self.store,
            customer=customer,
            staff=request.user,
            visited_at=date.today(),
            conversation_memo=memo,
        )

        response = render(
            request,
            "ui/staff/_visit_button.html",
            {"customer": customer},
        )
        response["HX-Trigger"] = json.dumps(
            {
                "showToast": {"message": "来店記録を作成しました", "type": "success"},
                "visitCreated": {},
            }
        )
        return response
