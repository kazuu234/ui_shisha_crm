from django import forms

from customers.models import Customer

_FIELD_CLASS = (
    "w-full max-w-md border border-border-default rounded-sm p-3 "
    "text-[15px] bg-bg-surface text-text-primary"
)

SHISHA_EXPERIENCE_CHOICES = [
    ("", "---"),
    ("none", "なし"),
    ("beginner", "初心者"),
    ("intermediate", "中級"),
    ("advanced", "上級"),
]


class CustomerEditForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["name", "age", "area", "shisha_experience", "line_id", "memo"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "placeholder": "顧客の名前",
                    "class": _FIELD_CLASS,
                }
            ),
            "age": forms.NumberInput(
                attrs={"placeholder": "例: 25", "min": 0, "class": _FIELD_CLASS}
            ),
            "area": forms.TextInput(
                attrs={"placeholder": "例: 渋谷", "class": _FIELD_CLASS}
            ),
            "shisha_experience": forms.Select(
                choices=SHISHA_EXPERIENCE_CHOICES,
                attrs={"class": _FIELD_CLASS},
            ),
            "line_id": forms.TextInput(
                attrs={"placeholder": "LINE ID", "class": _FIELD_CLASS}
            ),
            "memo": forms.Textarea(
                attrs={
                    "placeholder": "顧客メモ",
                    "rows": 4,
                    "class": _FIELD_CLASS,
                }
            ),
        }
        labels = {
            "name": "名前",
            "age": "年齢",
            "area": "居住エリア",
            "shisha_experience": "シーシャ歴",
            "line_id": "LINE ID",
            "memo": "メモ",
        }
        error_messages = {
            "name": {"required": "名前を入力してください"},
        }

    def clean_area(self):
        area = self.cleaned_data.get("area")
        if area is not None:
            area = area.strip()
        return area or None

    def clean_shisha_experience(self):
        exp = self.cleaned_data.get("shisha_experience")
        if exp is not None:
            exp = exp.strip()
        return exp or None

    def clean_line_id(self):
        line_id = self.cleaned_data.get("line_id")
        if line_id is not None:
            line_id = line_id.strip()
        return line_id or None

    def clean_memo(self):
        memo = self.cleaned_data.get("memo")
        if memo is None:
            return ""
        return memo.strip()
