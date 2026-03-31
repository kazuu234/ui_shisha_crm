from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from ui.mixins import StaffRequiredMixin, StoreMixin


class StubCustomerView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, TemplateView):
    template_name = "ui/staff/stub.html"
    login_url = "/s/login/"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "customers"
        return context
