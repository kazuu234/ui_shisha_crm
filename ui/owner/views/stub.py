from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from ui.mixins import OwnerRequiredMixin, StoreMixin


class StubDashboardView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, TemplateView):
    template_name = "ui/owner/stub_dashboard.html"
    login_url = "/o/login/"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_sidebar"] = "dashboard"
        return context
