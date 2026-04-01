from django import forms

SEGMENT_NAME_LABELS = {
    "new": "新規",
    "repeat": "リピート",
    "regular": "常連",
}


class SegmentThresholdForm(forms.Form):
    segment_name = forms.CharField(widget=forms.HiddenInput())
    min_visits = forms.IntegerField(
        min_value=0,
        widget=forms.NumberInput(attrs={"min": 0}),
        label="最小来店回数",
    )
    max_visits = forms.IntegerField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={"min": 0}),
        label="最大来店回数",
    )
    display_order = forms.IntegerField(widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        seg = None
        if self.is_bound:
            seg = self.data.get(self.add_prefix("segment_name"))
        if not seg:
            seg = (self.initial or {}).get("segment_name")
        if seg == "regular":
            self.fields["max_visits"].widget = forms.HiddenInput()
        field_cls = (
            "w-full max-w-[8rem] border border-border-default rounded-sm p-2 "
            "text-[15px] bg-bg-surface text-text-primary"
        )
        if "min_visits" in self.fields:
            self.fields["min_visits"].widget.attrs.setdefault("class", field_cls)
        if "max_visits" in self.fields and seg != "regular":
            self.fields["max_visits"].widget.attrs.setdefault("class", field_cls)

    def clean_max_visits(self):
        max_visits = self.cleaned_data.get("max_visits")
        segment_name = self.cleaned_data.get("segment_name")
        if segment_name == "regular":
            return None
        return max_visits

    @property
    def segment_label(self):
        if self.is_bound:
            name = self.data.get(self.add_prefix("segment_name"), "")
        else:
            name = self.initial.get("segment_name", "")
        return SEGMENT_NAME_LABELS.get(name, "")


class BaseSegmentThresholdFormSet(forms.BaseFormSet):
    def clean(self):
        if any(self.errors):
            return

        forms_data = []
        for form in self.forms:
            if form.cleaned_data:
                forms_data.append(form.cleaned_data)

        fixed_display_order = {"new": 1, "repeat": 2, "regular": 3}
        for d in forms_data:
            name = d.get("segment_name")
            if name in fixed_display_order:
                d["display_order"] = fixed_display_order[name]

        if len(forms_data) != 3:
            raise forms.ValidationError(
                "閾値は new, repeat, regular の 3 件が必要です。",
            )

        by_name = {d["segment_name"]: d for d in forms_data}
        required_segments = {"new", "repeat", "regular"}
        if set(by_name.keys()) != required_segments:
            raise forms.ValidationError(
                f"閾値は {', '.join(sorted(required_segments))} の 3 種が必要です。",
            )

        if by_name["new"]["min_visits"] != 0:
            raise forms.ValidationError(
                "新規の最小来店回数は 0 である必要があります。",
            )

        if by_name["regular"]["max_visits"] is not None:
            raise forms.ValidationError(
                "常連の最大来店回数は上限なし（空）である必要があります。",
            )

        new_max = by_name["new"]["max_visits"]
        repeat_min = by_name["repeat"]["min_visits"]
        repeat_max = by_name["repeat"]["max_visits"]
        regular_min = by_name["regular"]["min_visits"]

        if new_max is None:
            raise forms.ValidationError("新規の最大来店回数を入力してください。")
        if repeat_max is None:
            raise forms.ValidationError("リピートの最大来店回数を入力してください。")

        if new_max + 1 != repeat_min:
            raise forms.ValidationError(
                f"新規の最大({new_max}) + 1 がリピートの最小({repeat_min})と一致しません。"
                "範囲は連続である必要があります。",
            )
        if repeat_max + 1 != regular_min:
            raise forms.ValidationError(
                f"リピートの最大({repeat_max}) + 1 が常連の最小({regular_min})と一致しません。"
                "範囲は連続である必要があります。",
            )

        for name in ("new", "repeat"):
            d = by_name[name]
            if d["max_visits"] is not None and d["min_visits"] > d["max_visits"]:
                label = SEGMENT_NAME_LABELS.get(name, name)
                raise forms.ValidationError(
                    f"{label}の最小来店回数({d['min_visits']})が"
                    f"最大来店回数({d['max_visits']})を超えています。",
                )


SegmentThresholdFormSet = forms.formset_factory(
    SegmentThresholdForm,
    formset=BaseSegmentThresholdFormSet,
    extra=0,
    min_num=3,
    max_num=3,
    validate_min=True,
    validate_max=True,
)
