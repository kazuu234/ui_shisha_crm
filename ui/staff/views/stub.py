from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView

from customers.models import Customer

from ui.mixins import StaffRequiredMixin, StoreMixin


class StubSessionView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, TemplateView):
    template_name = "ui/staff/stub_session.html"
    login_url = "/s/login/"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        get_object_or_404(Customer.objects.for_store(self.store), pk=self.kwargs["pk"])
        context["active_tab"] = "session"
        return context
