from django import forms


class CsvUploadForm(forms.Form):
    file = forms.FileField(
        label="CSV ファイル",
        help_text="Airレジの「会計明細CSV」をアップロードしてください",
    )

    def clean_file(self):
        f = self.cleaned_data.get("file")
        if f:
            if not f.name.lower().endswith(".csv"):
                raise forms.ValidationError("CSV ファイルを選択してください")
            if f.size > 10 * 1024 * 1024:
                raise forms.ValidationError("ファイルサイズは 10MB 以下にしてください")
        return f


class MatchingConfirmForm(forms.Form):
    visit_id = forms.UUIDField()
