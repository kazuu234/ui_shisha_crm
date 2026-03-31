from django import forms


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
