from django import forms


class QROwnerLoginForm(forms.Form):
    token = forms.CharField(
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "placeholder": "QR コードを入力",
                "autocomplete": "off",
                "autofocus": True,
                "class": (
                    "w-full border border-border-default rounded-sm p-3 "
                    "text-[17px] bg-bg-surface text-text-primary"
                ),
            }
        ),
        error_messages={"required": "QR コードを入力してください"},
    )
