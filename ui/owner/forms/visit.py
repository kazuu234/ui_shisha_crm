from django import forms

from visits.models import Visit

_FIELD_CLASS = (
    "w-full max-w-md border border-border-default rounded-sm p-3 "
    "text-[15px] bg-bg-surface text-text-primary"
)


class VisitEditForm(forms.ModelForm):
    class Meta:
        model = Visit
        fields = ["visited_at", "conversation_memo"]
        widgets = {
            "visited_at": forms.DateInput(
                attrs={"type": "date", "class": _FIELD_CLASS},
            ),
            "conversation_memo": forms.Textarea(
                attrs={"placeholder": "会話メモ", "rows": 4, "class": _FIELD_CLASS},
            ),
        }
        labels = {
            "visited_at": "来店日",
            "conversation_memo": "会話メモ",
        }
        error_messages = {
            "visited_at": {"required": "来店日を入力してください"},
        }

    def clean_conversation_memo(self):
        """strip のみ。conversation_memo は TextField(blank=True, default='') で非 nullable。"""
        memo = self.cleaned_data.get("conversation_memo")
        if memo is None:
            return ""
        return memo.strip()
