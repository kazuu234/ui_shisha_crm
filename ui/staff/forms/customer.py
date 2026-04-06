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
    initial_visit_count = forms.IntegerField(
        label="過去の来店回数",
        required=False,
        min_value=0,
        initial=0,
        widget=forms.NumberInput(
            attrs={
                "placeholder": "0",
                "class": (
                    "w-full border border-border-default rounded-sm p-3 "
                    "text-[17px] bg-bg-surface text-text-primary"
                ),
            }
        ),
        help_text="常連の方を登録する場合、CRM導入以前の来店回数を入力してください",
    )


EDIT_FIELD_CHOICES = {
    "name": None,
    "age": "int",
    "area": None,
    "shisha_experience": ["none", "beginner", "intermediate", "advanced"],
    "line_id": None,
    "memo": None,
}


class CustomerEditFieldForm(forms.Form):
    field = forms.CharField(max_length=50)
    value = forms.CharField(required=False)

    NULLABLE_FIELDS = {"age", "area", "shisha_experience", "line_id", "memo"}

    def clean(self):
        cleaned = super().clean()
        field_name = cleaned.get("field")
        value = cleaned.get("value")

        if field_name not in EDIT_FIELD_CHOICES:
            raise forms.ValidationError(f"無効なフィールド: {field_name}")

        if field_name == "name":
            if not value or not str(value).strip():
                raise forms.ValidationError("名前を入力してください")
            cleaned["value"] = str(value).strip()
            return cleaned

        if value is not None and isinstance(value, str):
            value = value.strip()
            cleaned["value"] = value

        if field_name in self.NULLABLE_FIELDS and (value is None or value == ""):
            cleaned["value"] = None
            return cleaned

        if field_name == "age":
            try:
                cleaned["value"] = int(value)
            except (ValueError, TypeError):
                raise forms.ValidationError("年齢は整数で入力してください") from None
            if cleaned["value"] < 0 or cleaned["value"] > 150:
                raise forms.ValidationError("年齢は 0〜150 の範囲で入力してください")
            return cleaned

        allowed = EDIT_FIELD_CHOICES[field_name]
        if isinstance(allowed, list) and value not in allowed:
            raise forms.ValidationError(f"無効な値: {value}")

        return cleaned


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
