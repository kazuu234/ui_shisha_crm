from django import forms


class MatchingConfirmForm(forms.Form):
    visit_id = forms.UUIDField()
