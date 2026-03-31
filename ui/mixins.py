from django.contrib.auth import logout
from django.contrib.auth.mixins import AccessMixin
from django.shortcuts import redirect


class StaffRequiredMixin(AccessMixin):
    """role が staff または owner であることを要求する。"""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.role not in ("staff", "owner"):
            logout(request)
            return redirect("/s/login/")
        return super().dispatch(request, *args, **kwargs)


class StoreMixin:
    """self.store と context["store"] をセットする。"""

    def dispatch(self, request, *args, **kwargs):
        self.store = request.user.store
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["store"] = self.store
        return context
