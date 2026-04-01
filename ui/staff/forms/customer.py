from django import forms


HEARING_FIELD_CHOICES = {
    "age": [10, 20, 30, 40, 50],
    "area": None,
    "shisha_experience": ["none", "beginner", "intermediate", "advanced"],
}


class CustomerCreateForm(forms.Form):
    name = forms.CharField(
        label="名前",
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "placeholder": "顧客の名前を入力",
                "autocomplete": "off",
                "autofocus": True,
                "class": (
                    "w-full border border-border-default rounded-sm p-3 "
                    "text-[17px] bg-bg-surface text-text-primary"
                ),
            }
        ),
        error_messages={"required": "名前を入力してください"},
    )


class CustomerFieldUpdateForm(forms.Form):
    field = forms.CharField(max_length=50)
    value = forms.CharField(max_length=255, required=False)

    NULLABLE_FIELDS = {"age", "area", "shisha_experience"}

    def clean(self):
        cleaned = super().clean()
        field_name = cleaned.get("field")
        value = cleaned.get("value")

        if field_name not in HEARING_FIELD_CHOICES:
            raise forms.ValidationError(f"無効なフィールド: {field_name}")

        if field_name in self.NULLABLE_FIELDS and (value == "" or value is None):
            cleaned["value"] = None
            return cleaned

        allowed = HEARING_FIELD_CHOICES[field_name]
        if field_name == "age" and value not in (None, ""):
            try:
                ivalue = int(value)
            except (ValueError, TypeError):
                raise forms.ValidationError(f"無効な値: {value}") from None
            if allowed is not None and ivalue not in allowed:
                raise forms.ValidationError(f"無効な値: {value}")
            cleaned["value"] = ivalue
            return cleaned

        if allowed is not None and value not in allowed:
            raise forms.ValidationError(f"無効な値: {value}")

        return cleaned


class VisitCreateForm(forms.Form):
    customer_id = forms.UUIDField()
    conversation_memo = forms.CharField(
        required=False,
        widget=forms.Textarea,
    )
