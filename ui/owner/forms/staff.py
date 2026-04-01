from django import forms

_FIELD_CLASS = (
    "w-full max-w-md border border-border-default rounded-sm p-3 "
    "text-[15px] bg-bg-surface text-text-primary"
)


class StaffCreateForm(forms.Form):
    display_name = forms.CharField(
        label="表示名",
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "name",
                "autofocus": True,
                "class": _FIELD_CLASS,
            }
        ),
        error_messages={"required": "表示名を入力してください"},
    )
    role = forms.ChoiceField(
        label="ロール",
        choices=[("staff", "スタッフ"), ("owner", "オーナー")],
        widget=forms.Select(attrs={"class": _FIELD_CLASS}),
    )
    staff_type = forms.ChoiceField(
        label="種別",
        choices=[
            ("regular", "レギュラー"),
            ("temporary", "テンポラリー"),
            ("owner", "オーナー"),
        ],
        widget=forms.Select(attrs={"class": _FIELD_CLASS}),
    )

    def clean_display_name(self):
        name = (self.cleaned_data.get("display_name") or "").strip()
        if len(name) > 100:
            raise forms.ValidationError(
                "表示名は100文字以内で入力してください。",
            )
        return name
