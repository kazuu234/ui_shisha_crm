from types import SimpleNamespace

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views import View

from core.audit import AuditLogger
from customers.models import Customer
from visits.models import SegmentThreshold
from visits.services import SegmentService

from ui.mixins import OwnerRequiredMixin, StoreMixin
from ui.owner.forms.segment import SegmentThresholdFormSet


def _preview_error_response(request, formset=None, apply_error=None):
    html = render_to_string(
        "ui/owner/_segment_preview.html",
        {
            "formset": formset,
            "preview_error": True,
            "apply_error": apply_error,
        },
        request=request,
    )
    return HttpResponse(html, status=422)


def _threshold_objects_from_formset(formset):
    rows = [f.cleaned_data for f in formset.forms if f.cleaned_data]
    rows.sort(key=lambda d: d["display_order"])
    return [
        SimpleNamespace(
            segment_name=d["segment_name"],
            min_visits=d["min_visits"],
            max_visits=d["max_visits"],
        )
        for d in rows
    ]


class SegmentSettingsView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    template_name = "ui/owner/segment_settings.html"
    login_url = "/o/login/"

    def get(self, request):
        thresholds = (
            SegmentThreshold.objects.filter(store=self.store).order_by("display_order")
        )
        formset = SegmentThresholdFormSet(
            initial=[
                {
                    "segment_name": t.segment_name,
                    "min_visits": t.min_visits,
                    "max_visits": t.max_visits,
                    "display_order": t.display_order,
                }
                for t in thresholds
            ],
        )

        toast = request.session.pop("toast", None)

        return render(
            request,
            self.template_name,
            {
                "formset": formset,
                "thresholds": thresholds,
                "active_sidebar": "segments",
                "toast": toast,
                "store": self.store,
            },
        )


class SegmentPreviewView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    login_url = "/o/login/"

    def post(self, request):
        formset = SegmentThresholdFormSet(request.POST)
        if not formset.is_valid():
            return _preview_error_response(request, formset=formset)

        threshold_objects = _threshold_objects_from_formset(formset)

        customers = list(
            Customer.objects.for_store(self.store).values("pk", "visit_count", "segment"),
        )

        affected_count = 0
        segment_counts = {"new": 0, "repeat": 0, "regular": 0}

        for customer in customers:
            new_segment = SegmentService._determine_segment(
                customer["visit_count"],
                threshold_objects,
            )
            segment_counts[new_segment] = segment_counts.get(new_segment, 0) + 1
            if new_segment != customer["segment"]:
                affected_count += 1

        html = render_to_string(
            "ui/owner/_segment_preview.html",
            {
                "affected_count": affected_count,
                "segment_counts": segment_counts,
                "preview_error": False,
            },
            request=request,
        )
        return HttpResponse(html)


class SegmentApplyView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    login_url = "/o/login/"

    def post(self, request):
        formset = SegmentThresholdFormSet(request.POST)
        if not formset.is_valid():
            return _preview_error_response(request, formset=formset)

        threshold_data = []
        for form in formset:
            threshold_data.append(
                {
                    "segment_name": form.cleaned_data["segment_name"],
                    "min_visits": form.cleaned_data["min_visits"],
                    "max_visits": form.cleaned_data["max_visits"],
                    "display_order": form.cleaned_data["display_order"],
                }
            )

        try:
            with transaction.atomic():
                list(
                    SegmentThreshold.objects.select_for_update()
                    .filter(store=self.store)
                    .order_by("display_order"),
                )

                for data in threshold_data:
                    SegmentThreshold.objects.filter(
                        store=self.store,
                        segment_name=data["segment_name"],
                    ).update(
                        min_visits=data["min_visits"],
                        max_visits=data["max_visits"],
                        display_order=data["display_order"],
                    )

                SegmentThreshold.validate_store_thresholds(self.store)

                before = dict(
                    Customer.objects.for_store(self.store).values_list(
                        "pk",
                        "segment",
                    ),
                )

                SegmentService.bulk_recalculate_segments(self.store)

                after = dict(
                    Customer.objects.for_store(self.store).values_list(
                        "pk",
                        "segment",
                    ),
                )
                affected_count = sum(
                    1 for pk, seg in before.items() if after.get(pk) != seg
                )

        except ValidationError as e:
            messages = getattr(e, "messages", None)
            msg = "; ".join(messages) if messages else str(e)
            return _preview_error_response(request, apply_error=msg)
        except Exception as e:
            return _preview_error_response(
                request,
                apply_error=str(e) or "予期しないエラーが発生しました。",
            )

        AuditLogger.log(
            request,
            "segment.threshold_update",
            "SegmentThreshold",
            str(self.store.pk),
            {"thresholds": threshold_data, "affected_count": affected_count},
            store=self.store,
        )

        request.session["toast"] = {
            "message": (
                "セグメント閾値を更新しました。"
                f"{affected_count} 件の顧客のセグメントが再計算されました。"
            ),
            "type": "success",
        }

        response = HttpResponse(status=200)
        response["HX-Redirect"] = reverse("owner:segment-settings")
        return response
