# UO-03 詳細設計書: 来店管理 + セグメント設定

> 基本設計書: `docs/design/UI_BASIC_DESIGN.md` §6 UO-03, §7.7
> デザインガイド: `docs/design/UI_DESIGN_GUIDE.md`
> パイプライン: `docs/design/UI_PIPELINE.md` #9, #10
> コア層仕様: `docs/reference/cluster/C04_VISIT_SEGMENT.md`

## 1. 概要

### Cluster 情報

| 項目 | 内容 |
|------|------|
| **Cluster** | UO-03 (来店管理 + セグメント設定) |
| **Slice 数** | 2 本 |
| **パイプライン順序** | S1: #9 / 13、S2: #10 / 13 |

### Slice 1: 来店一覧 + 編集 + 削除

| 項目 | 内容 |
|------|------|
| **ブランチ説明部** | `uo03-s1-visit-mgmt` |
| **スコープ** | 来店一覧画面（フィルタ・ソート・ページネーション）、来店編集画面、来店削除（確認ダイアログ） |

**precondition:**
- UO-01 S1 完了（`base_owner.html`、`OwnerRequiredMixin`、`StoreMixin` が動作）
- コア層 C-04 S2 完了（`VisitService.update_visit()` / `VisitService.delete_visit()` が動作）

**postcondition:**
- `/o/visits/` でフィルタ・ソート・ページネーション付きの来店一覧テーブルが表示される
- テーブル列: 来店日（ソート・日付範囲フィルタ）、顧客名（ソート・検索）、セグメント（バッジ・フィルタ）、対応スタッフ（フィルタ）、メモ（先頭 30 文字）
- HTMX でフィルタ・ソート・ページ切替時にテーブル本体のみ差し替え（`hx-push-url="true"` でブラウザ履歴に反映）
- 25 件/ページのページネーション（Django Paginator）
- `/o/visits/<id>/edit/` で来店記録を編集できる（`visited_at` と `conversation_memo` のみ。`customer` / `staff` は読み取り専用表示）
- 削除時に確認ダイアログ（Alpine.js モーダル）表示 → 論理削除 → `visit_count` とセグメント再計算（C-04 signal が処理）→ 来店一覧に戻る + トースト
- Sidebar の「来店記録」がアクティブ状態（`active_sidebar = "visits"`）
- 全 View が `LoginRequiredMixin, OwnerRequiredMixin, StoreMixin` を使用

### Slice 2: セグメント閾値設定

| 項目 | 内容 |
|------|------|
| **ブランチ説明部** | `uo03-s2-segment-settings` |
| **スコープ** | 閾値一覧表示、変更フォーム、影響プレビュー（HTMX）、確定 + 一括再計算 |

**precondition:**
- UO-01 S1 完了（`base_owner.html`、`OwnerRequiredMixin`、`StoreMixin` が動作）
- コア層 C-04 全 Slice 完了（`SegmentService.bulk_recalculate_segments(store)` + `SegmentThreshold.validate_store_thresholds()` が動作）

**postcondition:**
- `/o/segments/settings/` で現在の閾値が表示される
- 閾値変更 → 「プレビュー」→ 影響件数が HTMX で表示される
- 「確定」→ 閾値更新 + `SegmentService.bulk_recalculate_segments(store)` → トースト表示
- セグメント再計算後、顧客一覧のセグメントバッジが更新されている
- Sidebar の「セグメント設定」がアクティブ状態（`active_sidebar = "segments"`）
- 全 View が `LoginRequiredMixin, OwnerRequiredMixin, StoreMixin` を使用

## 2. ファイル構成

### Slice 1

```
ui/
├── owner/
│   ├── views/
│   │   └── visit.py                   # VisitListView, VisitEditView, VisitDeleteView
│   ├── forms/
│   │   └── visit.py                   # VisitEditForm
│   └── urls.py                        # visits/ 関連 URL を追記
├── templates/ui/
│   └── owner/
│       ├── visit_list.html            # 来店一覧画面（フィルタバー + テーブル + ページネーション）
│       ├── _visit_table.html          # テーブル本体フラグメント（HTMX 差し替え対象）
│       └── visit_edit.html            # 来店編集画面
```

### Slice 2

```
ui/
├── owner/
│   ├── views/
│   │   └── segment.py                 # SegmentSettingsView, SegmentPreviewView, SegmentApplyView
│   ├── forms/
│   │   └── segment.py                 # SegmentThresholdForm, SegmentThresholdFormSet
│   └── urls.py                        # segments/ 関連 URL を追記
├── templates/ui/
│   └── owner/
│       ├── segment_settings.html      # セグメント閾値設定画面
│       └── _segment_preview.html      # プレビュー結果フラグメント（HTMX 差し替え対象）
```

**追加するアイコン**: なし（UO-01 S1 で作成済みの `sliders.svg`, `calendar.svg` で足りる）。

## 3. コア層契約

正式な定義は `docs/reference/cluster/C04_VISIT_SEGMENT.md` を参照。

**import パスについて**: コア層は別リポジトリ（別 Django app）として管理されている場合がある。本設計書では `from core.services.visit import VisitService` のような統一的な記法を使用するが、実際の import パスはコア層のパッケージ構造に依存する。実装時にコア層の `__init__.py` や実際のモジュール配置を確認すること。

### VisitService

| メソッド | 引数 | 返り値 | 例外 |
|---------|------|--------|------|
| `update_visit(visit_id, **fields)` | `UUID, **kwargs` | `Visit` | `BusinessError(visit.not_found)` |
| `delete_visit(visit_id)` | `UUID` | `None` | `BusinessError(visit.not_found)` |

**`update_visit` が受け付けるフィールド**: `visited_at`, `conversation_memo`。`customer_id` は immutable（C-04 仕様: `visit.customer_immutable`）。

**`delete_visit` の動作**: 論理削除（`is_deleted=True`, `deleted_at` 設定）。signal 経由で `visit_count` と `segment` が自動再計算される。

### SegmentService

| メソッド | 引数 | 返り値 | 備考 |
|---------|------|--------|------|
| `bulk_recalculate_segments(store)` | `Store` | `int`（変更件数） | 全顧客のセグメントを一括再計算。定数回クエリで N+1 なし |
| `determine_segment(visit_count, thresholds)` | `int, list[dict]` | `str` | visit_count と閾値リストからセグメント名を判定。プレビュー等で DB 更新なしに判定する場合に使用。**UI 側でのロジック複製は禁止** |

### SegmentThreshold モデル

| フィールド | 型 | 備考 |
|-----------|-----|------|
| `id` | UUIDField | PK |
| `store` | ForeignKey(Store) | 店舗スコープ |
| `segment_name` | CharField | `new` / `repeat` / `regular` |
| `min_visits` | PositiveIntegerField | 最小来店回数 |
| `max_visits` | PositiveIntegerField (nullable) | 最大来店回数。`regular` は null（上限なし） |
| `display_order` | PositiveIntegerField | 表示順（1, 2, 3） |

**クラスメソッド:**
- `validate_store_thresholds(store)`: Store の閾値セット全体の整合性を検証。3件必須、連続、非重複、`new.min_visits=0`、`regular.max_visits=null`。
- `for_store(store)`: ストアスコープフィルタ。

**デフォルト閾値:**
- `new`: min=0, max=1, display_order=1
- `repeat`: min=2, max=4, display_order=2
- `regular`: min=5, max=null, display_order=3

### Visit モデル（UI が参照するフィールド）

| フィールド | 型 | 備考 |
|-----------|-----|------|
| `id` | UUIDField | PK |
| `customer` | ForeignKey(Customer) | 対象顧客 |
| `staff` | ForeignKey(Staff) | 対応スタッフ |
| `visited_at` | DateField | 来店日 |
| `conversation_memo` | TextField (nullable) | 会話メモ |
| `is_deleted` | BooleanField | 論理削除フラグ（SoftDeleteMixin） |
| `created_at` | DateTimeField (auto_now_add) | 作成日時（安定ソート用） |

**StoreScopedManager**: `Visit.objects.for_store(store)` でストアスコープフィルタを適用。デフォルトで `alive()` により論理削除済みレコードを除外。

### 監査ログ要件（UI 例外実装）

UI の閾値更新 View は ViewSet を経由しないため、`AuditLogMixin` による自動監査ログが適用されない。以下の明示的な監査ログ記録が必要:

- **閾値更新成功時**: `AuditLogger.log(request, action='segment.threshold_update', target_model='SegmentThreshold', target_id=store.pk, changes={thresholds, affected_count})` を呼び出す
- C-04 の `Slice 3 postcondition` にある「閾値一括更新: AuditLogger.log() で明示記録」と整合する

### Customer モデル（UI が参照するフィールド）

| フィールド | 型 | 備考 |
|-----------|-----|------|
| `name` | CharField | 表示名 |
| `segment` | CharField (`new` / `repeat` / `regular`) | セグメントバッジ表示に使用 |
| `visit_count` | PositiveIntegerField | 来店回数（非正規化。signal で自動更新） |

### Staff モデル（UI が参照するフィールド）

| フィールド | 型 | 備考 |
|-----------|-----|------|
| `display_name` | CharField | UI 表示名 |

### セグメントバッジラベルマッピング

```python
SEGMENT_LABELS = {
    "new": "新規",
    "repeat": "リピート",
    "regular": "常連",
}
```

## 4. View 定義

### 4.1 VisitListView（Slice 1）

```python
# ui/owner/views/visit.py

from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import F, Q

from ui.mixins import OwnerRequiredMixin, StoreMixin
from visits.models import Visit
from core.models import Staff

SEGMENT_LABELS = {
    "new": "新規",
    "repeat": "リピート",
    "regular": "常連",
}

# ソート許可フィールド（ホワイトリスト）
ALLOWED_SORT_FIELDS = {
    "visited_at": F("visited_at").asc(),
    "-visited_at": F("visited_at").desc(),
    "customer_name": F("customer__name").asc(),
    "-customer_name": F("customer__name").desc(),
}
DEFAULT_SORT = "-visited_at"

# セグメント許可値
ALLOWED_SEGMENTS = {"new", "repeat", "regular"}


class VisitListView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, ListView):
    template_name = "ui/owner/visit_list.html"
    context_object_name = "visits"
    paginate_by = 25
    login_url = "/o/login/"

    def get_queryset(self):
        qs = Visit.objects.for_store(self.store).select_related("customer", "staff")

        # 顧客名検索（部分一致）
        search = self.request.GET.get("search", "").strip()
        if search:
            qs = qs.filter(customer__name__icontains=search)

        # セグメントフィルタ
        segment = self.request.GET.get("segment", "").strip()
        if segment in ALLOWED_SEGMENTS:
            qs = qs.filter(customer__segment=segment)

        # スタッフフィルタ（UUID 形式を検証し、存在チェック）
        staff_id = self.request.GET.get("staff", "").strip()
        if staff_id:
            try:
                import uuid
                staff_uuid = uuid.UUID(staff_id)
                if Staff.objects.filter(pk=staff_uuid, store=self.store, is_active=True).exists():
                    qs = qs.filter(staff_id=staff_uuid)
                # 存在しない staff_id は無視（フィルタを適用しない）
            except (ValueError, AttributeError):
                pass  # 不正な UUID 形式は無視

        # 日付範囲フィルタ（日付形式を検証し、不正な値は無視）
        from datetime import date as date_type
        date_from = self.request.GET.get("date_from", "").strip()
        date_to = self.request.GET.get("date_to", "").strip()
        if date_from:
            try:
                date_type.fromisoformat(date_from)
                qs = qs.filter(visited_at__gte=date_from)
            except ValueError:
                date_from = ""  # 不正な日付形式は無視
        if date_to:
            try:
                date_type.fromisoformat(date_to)
                qs = qs.filter(visited_at__lte=date_to)
            except ValueError:
                date_to = ""  # 不正な日付形式は無視

        # ソート（F() 式でホワイトリスト制御）
        sort = self.request.GET.get("sort", DEFAULT_SORT).strip()
        if sort in ALLOWED_SORT_FIELDS:
            order_expr = ALLOWED_SORT_FIELDS[sort]
        else:
            order_expr = ALLOWED_SORT_FIELDS[DEFAULT_SORT]
        # created_at で安定ソート（Visit.created_at は auto_now_add）
        qs = qs.order_by(order_expr, "-created_at", "pk")

        return qs

    def get_template_names(self):
        # HTMX リクエスト時はテーブルフラグメントのみ返す
        if self.request.headers.get("HX-Request") == "true":
            return ["ui/owner/_visit_table.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_sidebar"] = "visits"
        context["current_search"] = self.request.GET.get("search", "")
        context["current_segment"] = self.request.GET.get("segment", "")
        context["current_sort"] = self.request.GET.get("sort", DEFAULT_SORT)
        # フィルタ値はバリデーション済みの値を返す（不正な値はコンテキストに渡さない）
        staff_id_raw = self.request.GET.get("staff", "").strip()
        try:
            import uuid
            staff_uuid = uuid.UUID(staff_id_raw)
            # UUID 形式 + 実在チェック
            from core.models import Staff  # canonical import（auth_core.models と同一）
            if Staff.objects.filter(pk=staff_uuid, store=self.store, is_active=True).exists():
                context["current_staff"] = staff_id_raw
            else:
                context["current_staff"] = ""
        except (ValueError, AttributeError):
            context["current_staff"] = ""
        from datetime import date as date_type
        date_from_raw = self.request.GET.get("date_from", "").strip()
        date_to_raw = self.request.GET.get("date_to", "").strip()
        try:
            date_type.fromisoformat(date_from_raw) if date_from_raw else None
            context["current_date_from"] = date_from_raw
        except ValueError:
            context["current_date_from"] = ""
        try:
            date_type.fromisoformat(date_to_raw) if date_to_raw else None
            context["current_date_to"] = date_to_raw
        except ValueError:
            context["current_date_to"] = ""
        context["segment_choices"] = [
            ("", "全て"),
            ("new", "新規"),
            ("repeat", "リピート"),
            ("regular", "常連"),
        ]
        # スタッフ一覧（フィルタ用ドロップダウン）
        context["staff_choices"] = (
            Staff.objects.filter(store=self.store, is_active=True)
            .order_by("display_name")
            .values_list("pk", "display_name")
        )

        # トーストをセッションから取り出し（表示後に削除）
        toast = self.request.session.pop("toast", None)
        if toast:
            context["toast"] = toast

        return context
```

**ソートのホワイトリスト制御**: ユーザー入力のソートフィールドを直接 `order_by()` に渡さない。`ALLOWED_SORT_FIELDS` に定義された `F()` 式のみ許可し、未知の値はデフォルト（`-visited_at`）にフォールバックする。UO-02 と同一パターン。

**安定ソート**: `visited_at` が同一の来店記録は `created_at`（降順）→ `pk` でタイブレークする。`created_at` は auto_now_add のため安定した順序を提供する。

**HTMX リクエスト判定**: `HX-Request` ヘッダーの有無で返すテンプレートを切り替える。フィルタ・ソート・ページ切替はすべて `hx-get` で `_visit_table.html` フラグメントのみを返す。

**フィルタパラメータのバリデーション**: UO-02 と同一パターン。ユーザー入力のフィルタ値を生のまま ORM に渡さない。スタッフ ID は UUID 形式を検証し、DB に存在するかチェックする。日付は `date.fromisoformat()` でパース可能か検証し、不正な値は無視する。コンテキストにもバリデーション済みの値のみ渡す。

**`select_related('customer', 'staff')`**: 基本設計書のデータソース仕様に準拠。テーブル表示で `customer.name`, `customer.segment`, `staff.display_name` を参照するため N+1 を回避。

### 4.2 VisitEditForm（Slice 1）

```python
# ui/owner/forms/visit.py

from django import forms
from visits.models import Visit


class VisitEditForm(forms.ModelForm):
    class Meta:
        model = Visit
        fields = ["visited_at", "conversation_memo"]
        widgets = {
            "visited_at": forms.DateInput(
                attrs={"type": "date", "placeholder": "来店日"},
            ),
            "conversation_memo": forms.Textarea(
                attrs={"placeholder": "会話メモ", "rows": 4},
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
        """空文字列 → None に正規化（strip 後に判定）。"""
        memo = self.cleaned_data.get("conversation_memo")
        if memo is not None:
            memo = memo.strip()
        return memo or None
```

**空文字列 → None 正規化**: `conversation_memo` は nullable フィールド。Django form は空文字列を送信するため、clean メソッドで strip → 空文字列を None に変換する。`visited_at` は DateField のため空 → None は Django が自動処理する（required=True なので空はバリデーションエラー）。

### 4.3 VisitEditView（Slice 1）

```python
from django.views import View
from django.shortcuts import get_object_or_404, redirect, render

from core.exceptions import BusinessError
from core.services.visit import VisitService
from ui.owner.forms.visit import VisitEditForm


class VisitEditView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    template_name = "ui/owner/visit_edit.html"
    login_url = "/o/login/"

    def _get_visit(self):
        return get_object_or_404(
            Visit.objects.for_store(self.store).select_related("customer", "staff"),
            pk=self.kwargs["pk"],
        )

    def get(self, request, pk):
        visit = self._get_visit()
        form = VisitEditForm(instance=visit)
        return render(request, self.template_name, {
            "form": form,
            "visit": visit,
            "active_sidebar": "visits",
        })

    def post(self, request, pk):
        visit = self._get_visit()
        form = VisitEditForm(request.POST, instance=visit)
        if not form.is_valid():
            return render(request, self.template_name, {
                "form": form,
                "visit": visit,
                "active_sidebar": "visits",
            })

        # Service 経由で更新（BusinessError をキャッチ）
        try:
            VisitService.update_visit(
                visit_id=visit.pk,
                **form.cleaned_data,
            )
        except BusinessError as e:
            form.add_error(None, str(e))
            return render(request, self.template_name, {
                "form": form,
                "visit": visit,
                "active_sidebar": "visits",
            })

        # トースト用メッセージをセッションに保存
        request.session["toast"] = {
            "message": "来店記録を更新しました",
            "type": "success",
        }

        return redirect("/o/visits/")
```

**customer / staff は読み取り専用**: フォームには `visited_at` と `conversation_memo` のみ含む。テンプレート側で `visit.customer.name` と `visit.staff.display_name` を読み取り専用で表示する。C-04 仕様で `customer_id` は immutable、`staff` も `VisitUpdateRequest` に含まれないため。

**BusinessError 処理**: `VisitService.update_visit()` が `BusinessError(visit.not_found)` を送出する可能性がある（レース条件で来店記録が削除された場合等）。キャッチして `form.add_error(None, str(e))` で non_field_errors としてフォームに表示する。UO-02 CustomerEditView と同一パターン。

### 4.4 VisitDeleteView（Slice 1）

```python
from django.views import View
from django.shortcuts import get_object_or_404, redirect, render

from core.exceptions import BusinessError
from core.services.visit import VisitService


class VisitDeleteView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    login_url = "/o/login/"

    def post(self, request, pk):
        visit = get_object_or_404(
            Visit.objects.for_store(self.store).select_related("customer"),
            pk=self.kwargs["pk"],
        )

        try:
            VisitService.delete_visit(visit_id=visit.pk)
        except BusinessError as e:
            # 削除失敗時: 来店一覧にリダイレクト + エラートースト
            request.session["toast"] = {
                "message": str(e),
                "type": "error",
            }
            return redirect("/o/visits/")

        # 成功: 来店一覧にリダイレクト + トースト
        request.session["toast"] = {
            "message": "来店記録を削除しました",
            "type": "success",
        }
        return redirect("/o/visits/")
```

**削除確認ダイアログ**: テンプレート側で Alpine.js モーダルを実装する（§5.3 参照）。VisitDeleteView は POST のみ受け付け、GET は提供しない。確認ダイアログで「削除」を押した時に POST が送信される。

**BusinessError 処理**: `VisitService.delete_visit()` がエラーを送出した場合（レース条件等）、エラートーストを表示して来店一覧にリダイレクトする。422 ではなくリダイレクト + トーストパターンを使用（削除操作は HTMX ではなく通常の POST/Redirect/GET）。

**signal による自動再計算**: `VisitService.delete_visit()` が論理削除すると、C-04 の signal ハンドラが `SegmentService.recalculate_segment(customer)` を自動実行する。UI View から明示的に再計算を呼ぶ必要はない。

### 4.5 SegmentSettingsView（Slice 2）

```python
# ui/owner/views/segment.py

from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render

from ui.mixins import OwnerRequiredMixin, StoreMixin
from visits.models import SegmentThreshold
from ui.owner.forms.segment import SegmentThresholdFormSet


class SegmentSettingsView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    template_name = "ui/owner/segment_settings.html"
    login_url = "/o/login/"

    def get(self, request):
        thresholds = (
            SegmentThreshold.objects.filter(store=self.store)
            .order_by("display_order")
        )
        formset = SegmentThresholdFormSet(
            initial=[
                {
                    "segment_name": t.segment_name,
                    "min_visits": t.min_visits,
                    "max_visits": t.max_visits,
                    "display_order": t.display_order,
                }
                for t in thresholds
            ],
        )

        # トーストをセッションから取り出し
        toast = request.session.pop("toast", None)

        return render(request, self.template_name, {
            "formset": formset,
            "thresholds": thresholds,
            "active_sidebar": "segments",
            "toast": toast,
        })
```

**閾値の表示**: `SegmentThreshold.objects.filter(store=self.store)` で現在の閾値を取得。`order_by('display_order')` で表示順を保証。FormSet に `initial` として現在の値を渡す。

### 4.6 SegmentThresholdForm / SegmentThresholdFormSet（Slice 2）

```python
# ui/owner/forms/segment.py

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

    def clean_max_visits(self):
        """空文字列 → None に正規化。regular の max_visits は null 固定。"""
        max_visits = self.cleaned_data.get("max_visits")
        segment_name = self.cleaned_data.get("segment_name")
        if segment_name == "regular":
            return None  # regular の max_visits は常に null
        return max_visits

    @property
    def segment_label(self):
        """テンプレートで日本語ラベルを表示するためのプロパティ。"""
        return SEGMENT_NAME_LABELS.get(
            self.initial.get("segment_name", ""), ""
        )


class BaseSegmentThresholdFormSet(forms.BaseFormSet):
    """閾値セット全体の相互整合性を検証する。

    C-04 の SegmentThreshold.validate_store_thresholds() と同等の
    クライアントサイドバリデーションを FormSet レベルで実施する。
    これにより Preview / Apply の両方で同じ検証が働く。
    """

    def clean(self):
        if any(self.errors):
            return  # 個別フォームにエラーがあれば相互検証はスキップ

        forms_data = []
        for form in self.forms:
            if form.cleaned_data:
                forms_data.append(form.cleaned_data)

        # display_order はクライアント送信値を無視し、C-04 固定値（1,2,3）を強制設定する。
        # hidden input の改ざん対策。
        FIXED_DISPLAY_ORDER = {"new": 1, "repeat": 2, "regular": 3}
        for d in forms_data:
            name = d.get("segment_name")
            if name in FIXED_DISPLAY_ORDER:
                d["display_order"] = FIXED_DISPLAY_ORDER[name]

        if len(forms_data) != 3:
            raise forms.ValidationError("閾値は new, repeat, regular の 3 件が必要です。")

        # segment_name でソート（display_order 順に整列）
        by_name = {d["segment_name"]: d for d in forms_data}

        # 必須セグメント名の存在確認
        required_segments = {"new", "repeat", "regular"}
        if set(by_name.keys()) != required_segments:
            raise forms.ValidationError(
                f"閾値は {', '.join(sorted(required_segments))} の 3 種が必要です。"
            )

        # new.min_visits == 0
        if by_name["new"]["min_visits"] != 0:
            raise forms.ValidationError("新規の最小来店回数は 0 である必要があります。")

        # regular.max_visits == None
        if by_name["regular"]["max_visits"] is not None:
            raise forms.ValidationError("常連の最大来店回数は上限なし（空）である必要があります。")

        # 範囲の連続性・非重複チェック
        # new.max + 1 == repeat.min, repeat.max + 1 == regular.min
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
                f"新規の最大({new_max}) + 1 がリピートの最小({repeat_min})と一致しません。範囲は連続である必要があります。"
            )
        if repeat_max + 1 != regular_min:
            raise forms.ValidationError(
                f"リピートの最大({repeat_max}) + 1 が常連の最小({regular_min})と一致しません。範囲は連続である必要があります。"
            )

        # min <= max の確認（regular は max=null なのでスキップ）
        for name in ["new", "repeat"]:
            d = by_name[name]
            if d["max_visits"] is not None and d["min_visits"] > d["max_visits"]:
                label = SEGMENT_NAME_LABELS.get(name, name)
                raise forms.ValidationError(
                    f"{label}の最小来店回数({d['min_visits']})が最大来店回数({d['max_visits']})を超えています。"
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
```

**FormSet**: 閾値は常に 3 件（new, repeat, regular）。`extra=0, min_num=3, max_num=3` で固定。

**BaseSegmentThresholdFormSet.clean()**: C-04 の `SegmentThreshold.validate_store_thresholds()` と同等の相互整合性検証を FormSet レベルで実装する。`formset.is_valid()` を呼ぶだけで、個別フォームの検証に加えてセット全体の整合性（3件必須、連続、非重複、`new.min=0`、`regular.max=null`）が検証される。これにより Preview / Apply の両方で同じ検証が自動的に働く。

**display_order の改ざん対策**: `display_order` は hidden input で送信されるため、クライアントサイドで改ざん可能。`clean()` 内でクライアント送信値を無視し、C-04 が定める固定値（new=1, repeat=2, regular=3）をサーバーサイドで強制設定する。

### 4.7 SegmentPreviewView（Slice 2）

```python
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.db.models import Q

from customers.models import Customer
from visits.models import SegmentThreshold
from core.services.segment import SegmentService

from ui.owner.forms.segment import SegmentThresholdFormSet


class SegmentPreviewView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    login_url = "/o/login/"

    def post(self, request):
        formset = SegmentThresholdFormSet(request.POST)
        if not formset.is_valid():
            # バリデーションエラー: エラー付きフラグメントを返す
            html = render_to_string(
                "ui/owner/_segment_preview.html",
                {"formset": formset, "preview_error": True},
                request=request,
            )
            return HttpResponse(html, status=422)

        # 新閾値でプレビュー計算（DB 更新はしない）
        new_thresholds = []
        for form in formset:
            new_thresholds.append({
                "segment_name": form.cleaned_data["segment_name"],
                "min_visits": form.cleaned_data["min_visits"],
                "max_visits": form.cleaned_data["max_visits"],
            })

        # 現在の閾値を取得
        current_thresholds = list(
            SegmentThreshold.objects.filter(store=self.store)
            .order_by("display_order")
            .values("segment_name", "min_visits", "max_visits")
        )

        # 全顧客の visit_count を取得し、新旧閾値で判定して影響件数を計算
        # プレビューのセグメント判定はコア層の SegmentService.determine_segment(visit_count, thresholds) を使用する。
        # UI 側でのロジック複製は禁止。
        customers = Customer.objects.for_store(self.store).values("visit_count", "segment")
        affected_count = 0

        for customer in customers:
            new_segment = SegmentService.determine_segment(
                customer["visit_count"], new_thresholds
            )
            if new_segment != customer["segment"]:
                affected_count += 1

        # 各セグメントの顧客数（変更後）
        segment_counts = {"new": 0, "repeat": 0, "regular": 0}
        for customer in customers:
            new_segment = SegmentService.determine_segment(
                customer["visit_count"], new_thresholds
            )
            segment_counts[new_segment] = segment_counts.get(new_segment, 0) + 1

        html = render_to_string(
            "ui/owner/_segment_preview.html",
            {
                "affected_count": affected_count,
                "segment_counts": segment_counts,
                "preview_error": False,
            },
            request=request,
        )
        return HttpResponse(html)


```

**プレビュー計算**: DB を更新せずに、全顧客の `visit_count` と新閾値でセグメントを判定し、現在のセグメントと比較して影響件数を算出する。プレビューのセグメント判定はコア層の `SegmentService.determine_segment(visit_count, thresholds)` を使用する。**UI 側でのロジック複製は禁止**。`_determine_segment_from_thresholds` のような View ローカルの判定関数を作らず、常にコア層の公開メソッドを呼ぶこと。

**422 エラー時のフラグメント返却**: FormSet のバリデーションエラー時は 422 ステータスでエラー付きフラグメントを返す。`base.html` の HTMX 設定で `hx-swap="innerHTML"` に 422 を許可済みのため、エラーメッセージがプレビューゾーンに表示される。

### 4.8 SegmentApplyView（Slice 2）

```python
from django.core.exceptions import ValidationError
from django.db import transaction

from core.exceptions import BusinessError
from visits.models import SegmentThreshold
from core.services.segment import SegmentService
from core.audit import AuditLogger

from ui.owner.forms.segment import SegmentThresholdFormSet


class SegmentApplyView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    login_url = "/o/login/"

    def post(self, request):
        formset = SegmentThresholdFormSet(request.POST)
        if not formset.is_valid():
            # バリデーションエラー: エラー付きフラグメントを返す
            html = render_to_string(
                "ui/owner/_segment_preview.html",
                {"formset": formset, "preview_error": True},
                request=request,
            )
            return HttpResponse(html, status=422)

        # 閾値を組み立て
        threshold_data = []
        for form in formset:
            threshold_data.append({
                "segment_name": form.cleaned_data["segment_name"],
                "min_visits": form.cleaned_data["min_visits"],
                "max_visits": form.cleaned_data["max_visits"],
                "display_order": form.cleaned_data["display_order"],
            })

        # モデル層バリデーション（C-04 validate_store_thresholds 相当）
        # 閾値一括更新 + 再計算をトランザクションで実行
        try:
            with transaction.atomic():
                # 行ロック取得（C-04 仕様: 閾値更新時は select_for_update で排他制御）
                # QuerySet を list() で強制評価してロックを確実に取得する
                locked_thresholds = list(
                    SegmentThreshold.objects.select_for_update().filter(
                        store=self.store
                    ).order_by("display_order")
                )

                # 閾値を一括更新
                for data in threshold_data:
                    SegmentThreshold.objects.filter(
                        store=self.store,
                        segment_name=data["segment_name"],
                    ).update(
                        min_visits=data["min_visits"],
                        max_visits=data["max_visits"],
                        display_order=data["display_order"],
                    )

                # モデル層の整合性検証
                SegmentThreshold.validate_store_thresholds(self.store)

                # 全顧客の一括再計算（Service 経由）
                changed_count = SegmentService.bulk_recalculate_segments(self.store)

        except (ValidationError, BusinessError) as e:
            # バリデーションエラーまたはビジネスエラーのみキャッチ。
            # DB エラー等の予期しない例外は Django の 500 ハンドラに委譲する。
            html = render_to_string(
                "ui/owner/_segment_preview.html",
                {"apply_error": str(e), "preview_error": True},
                request=request,
            )
            return HttpResponse(html, status=422)

        # 監査ログ記録（UI は ViewSet 経由ではないため AuditLogMixin が適用されない。明示的に記録する）
        AuditLogger.log(
            request,
            action="segment.threshold_update",
            target_model="SegmentThreshold",
            target_id=str(self.store.pk),
            changes={"thresholds": threshold_data, "affected_count": changed_count},
        )

        # 成功: トースト付きでセグメント設定画面にリダイレクト
        request.session["toast"] = {
            "message": f"セグメント閾値を更新しました。{changed_count} 件の顧客のセグメントが再計算されました",
            "type": "success",
        }
        # HX-Redirect ヘッダーで HTMX にリダイレクトを指示
        response = HttpResponse(status=200)
        response["HX-Redirect"] = "/o/segments/settings/"
        return response
```

**「write は Service 必須」の例外**: 基本設計書 §1.1 に従い、閾値更新は ViewSet 相当のロジックを UI View で再現する。閾値バリデーションは `SegmentThreshold.validate_store_thresholds()` クラスメソッド（モデル層）を利用。再計算は `SegmentService.bulk_recalculate_segments(store)` を Service 経由で呼び出す。

**行ロック（select_for_update）**: C-04 仕様に従い、閾値更新前に `SegmentThreshold.objects.select_for_update().filter(store=self.store)` で行ロックを取得する。concurrent な閾値更新リクエストによるデータ不整合を防止する。

**監査ログ**: UI は ViewSet 経由ではないため `AuditLogMixin` が自動適用されない。`AuditLogger.log()` を明示的に呼び出し、閾値更新操作を監査ログに記録する。

**例外処理**: `ValidationError`（モデル層の `validate_store_thresholds` 由来）と `BusinessError` のみキャッチする。DB 接続エラー等の予期しない例外は Django の 500 ハンドラに委譲し、握り潰さない。

**トランザクション**: 行ロック取得 → 閾値更新 → 整合性検証 → 一括再計算を `transaction.atomic()` で一括実行。検証失敗時はロールバック。

**HTMX リダイレクト**: 確定操作は HTMX POST（`hx-post`）で行うため、通常の `redirect()` は使えない。`HX-Redirect` レスポンスヘッダーで HTMX にフルページリダイレクトを指示する。

## 5. テンプレート

### 5.1 owner/visit_list.html（Slice 1）

```
{% extends "ui/base_owner.html" %}
{% load static %}

{% block page_title %}来店記録{% endblock %}

{% block toast %}
  {% if toast %}
    <div x-data="{ show: true }"
         x-show="show"
         x-init="setTimeout(() => { show = false }, 3000)"
         x-transition
         class="toast-{{ toast.type }}">
      {{ toast.message }}
    </div>
  {% endif %}
{% endblock %}

{% block content %}
  <div id="visit-list-container">
    {% include "ui/owner/_visit_table.html" %}
  </div>
{% endblock %}
```

**設計方針**: UO-02 と同一。フィルタバー + テーブル + ページネーションを全て `_visit_table.html` フラグメントに含め、`#visit-list-container` ごと HTMX 差し替えする。

### 5.2 owner/_visit_table.html（HTMX フラグメント、Slice 1）

フィルタバー + テーブル + ページネーションを含む。HTMX 差し替え時はこのフラグメント全体が `#visit-list-container` に差し込まれる。

```
{% load static %}

<div hx-target="#visit-list-container"
     hx-indicator="#visit-table-loading"
     hx-push-url="true">

  <!-- フィルタバー -->
  <div>  <!-- flex flex-wrap items-center gap-4 mb-6 -->
    <!-- 顧客名検索 -->
    <input type="text"
           name="search"
           value="{{ current_search }}"
           placeholder="顧客名で検索"
           hx-get="/o/visits/"
           hx-trigger="input changed delay:300ms"
           hx-include="[name='segment'],[name='staff'],[name='sort'],[name='date_from'],[name='date_to']" />

    <!-- セグメントフィルタ -->
    <select name="segment"
            hx-get="/o/visits/"
            hx-trigger="change"
            hx-include="[name='search'],[name='staff'],[name='sort'],[name='date_from'],[name='date_to']">
      {% for value, label in segment_choices %}
        <option value="{{ value }}" {% if value == current_segment %}selected{% endif %}>{{ label }}</option>
      {% endfor %}
    </select>

    <!-- スタッフフィルタ -->
    <select name="staff"
            hx-get="/o/visits/"
            hx-trigger="change"
            hx-include="[name='search'],[name='segment'],[name='sort'],[name='date_from'],[name='date_to']">
      <option value="">全スタッフ</option>
      {% for pk, name in staff_choices %}
        <option value="{{ pk }}" {% if pk|slugify == current_staff %}selected{% endif %}>{{ name }}</option>
      {% endfor %}
    </select>

    <!-- 日付範囲フィルタ -->
    <input type="date"
           name="date_from"
           value="{{ current_date_from }}"
           hx-get="/o/visits/"
           hx-trigger="change"
           hx-include="[name='search'],[name='segment'],[name='staff'],[name='sort'],[name='date_to']" />
    <span>〜</span>
    <input type="date"
           name="date_to"
           value="{{ current_date_to }}"
           hx-get="/o/visits/"
           hx-trigger="change"
           hx-include="[name='search'],[name='segment'],[name='staff'],[name='sort'],[name='date_from']" />

    <!-- ソートの hidden input -->
    <input type="hidden" name="sort" value="{{ current_sort }}" />
  </div>

  <!-- ローディング表示 -->
  <div id="visit-table-loading" class="htmx-indicator">
    <div class="skeleton-table">
      {% for i in "12345" %}
        <div class="skeleton-row animate-pulse bg-surface-alt"></div>
      {% endfor %}
    </div>
  </div>

  <table>
    <thead>
      <tr>
        <th>
          <a href="#"
             hx-get="/o/visits/"
             hx-vals='{"sort": "{% if current_sort == 'visited_at' %}-visited_at{% else %}visited_at{% endif %}"}'
             hx-include="[name='search'],[name='segment'],[name='staff'],[name='date_from'],[name='date_to']">
            来店日
            {% if current_sort == "visited_at" %}<span class="text-accent">▲</span>{% elif current_sort == "-visited_at" %}<span class="text-accent">▼</span>{% else %}<span class="text-text-muted">▲</span>{% endif %}
          </a>
        </th>
        <th>
          <a href="#"
             hx-get="/o/visits/"
             hx-vals='{"sort": "{% if current_sort == 'customer_name' %}-customer_name{% else %}customer_name{% endif %}"}'
             hx-include="[name='search'],[name='segment'],[name='staff'],[name='date_from'],[name='date_to']">
            顧客名
            {% if current_sort == "customer_name" %}<span class="text-accent">▲</span>{% elif current_sort == "-customer_name" %}<span class="text-accent">▼</span>{% else %}<span class="text-text-muted">▲</span>{% endif %}
          </a>
        </th>
        <th>セグメント</th>
        <th>対応スタッフ</th>
        <th>メモ</th>
        <th>操作</th>
      </tr>
    </thead>
    <tbody>
      {% for visit in visits %}
        <tr>
          <td>{{ visit.visited_at|date:"Y/m/d" }}</td>
          <td>
            <a href="/o/customers/{{ visit.customer.pk }}/">{{ visit.customer.name }}</a>
          </td>
          <td>
            {% if visit.customer.segment == "new" %}
              <span class="badge-new">新規</span>
            {% elif visit.customer.segment == "repeat" %}
              <span class="badge-repeat">リピート</span>
            {% elif visit.customer.segment == "regular" %}
              <span class="badge-regular">常連</span>
            {% endif %}
          </td>
          <td>{{ visit.staff.display_name }}</td>
          <td>{{ visit.conversation_memo|default:""|truncatechars:30 }}</td>
          <td>
            <a href="/o/visits/{{ visit.pk }}/edit/" class="btn-ghost text-sm">編集</a>
            <!-- 削除ボタン: Alpine.js モーダルをトリガー -->
            <button type="button"
                    class="btn-ghost text-sm text-error"
                    @click="$dispatch('open-delete-modal', { id: '{{ visit.pk }}', name: '{{ visit.customer.name }}', date: '{{ visit.visited_at|date:"Y/m/d" }}' })">
              削除
            </button>
          </td>
        </tr>
      {% empty %}
        <tr>
          <td colspan="6">来店記録がありません</td>
        </tr>
      {% endfor %}
    </tbody>
  </table>

  <!-- ページネーション -->
  {% if is_paginated %}
    <div>  <!-- flex items-center justify-center gap-4 mt-6 -->
      {% if page_obj.has_previous %}
        <a href="#"
           hx-get="/o/visits/"
           hx-vals='{"page": "{{ page_obj.previous_page_number }}"}'
           hx-include="[name='search'],[name='segment'],[name='staff'],[name='sort'],[name='date_from'],[name='date_to']"
           class="btn-secondary">前へ</a>
      {% endif %}
      <span>{{ page_obj.number }} / {{ page_obj.paginator.num_pages }}</span>
      {% if page_obj.has_next %}
        <a href="#"
           hx-get="/o/visits/"
           hx-vals='{"page": "{{ page_obj.next_page_number }}"}'
           hx-include="[name='search'],[name='segment'],[name='staff'],[name='sort'],[name='date_from'],[name='date_to']"
           class="btn-secondary">次へ</a>
      {% endif %}
    </div>
  {% endif %}

</div>
```

**セグメントバッジ**: UO-02 と同一パターン。`badge-new`, `badge-repeat`, `badge-regular`。

**メモの先頭 30 文字**: `truncatechars:30` テンプレートフィルタで切り詰め。`conversation_memo` が null の場合は `default:""` でフォールバック。

**操作列**: 各行に「編集」リンクと「削除」ボタンを配置。「削除」ボタンは Alpine.js のカスタムイベント `open-delete-modal` をディスパッチし、モーダルを開く。

### 5.3 削除確認モーダル（visit_list.html 内、Slice 1）

`visit_list.html` の `{% block modal %}` に配置する。

```
{% block modal %}
  <div x-data="{ open: false, deleteId: '', customerName: '', visitDate: '' }"
       @open-delete-modal.window="open = true; deleteId = $event.detail.id; customerName = $event.detail.name; visitDate = $event.detail.date"
       x-show="open"
       x-transition
       class="modal-overlay">
    <div class="modal-content" @click.outside="open = false">
      <h3>来店記録の削除</h3>
      <p>
        <span x-text="visitDate"></span> の <span x-text="customerName"></span> の来店記録を削除しますか？
      </p>
      <p class="text-text-secondary text-sm">
        削除すると来店回数とセグメントが再計算されます。
      </p>
      <div>  <!-- flex gap-4 mt-4 -->
        <form method="post" :action="'/o/visits/' + deleteId + '/delete/'">
          {% csrf_token %}
          <button type="submit" class="btn-danger">削除</button>
        </form>
        <button type="button" class="btn-secondary" @click="open = false">キャンセル</button>
      </div>
    </div>
  </div>
{% endblock %}
```

**Alpine.js モーダル**: 基本設計書の仕様「確認ダイアログ（Alpine.js モーダル）」に準拠。`@open-delete-modal.window` でカスタムイベントを受信し、対象の来店記録情報をモーダルに渡す。`@click.outside` でモーダル外クリック時に閉じる。

**CSRF トークン**: `{% csrf_token %}` を `<form>` 内に配置。削除は通常の POST（HTMX ではない）で行い、POST/Redirect/GET パターンに従う。

### 5.4 owner/visit_edit.html（Slice 1）

```
{% extends "ui/base_owner.html" %}
{% load static %}

{% block page_title %}来店記録 - 編集{% endblock %}

{% block content %}
  <!-- 読み取り専用情報 -->
  <section>  <!-- mb-6 -->
    <dl>
      <dt>顧客名</dt><dd>{{ visit.customer.name }}</dd>
      <dt>対応スタッフ</dt><dd>{{ visit.staff.display_name }}</dd>
    </dl>
  </section>

  <form method="post">
    {% csrf_token %}

    <!-- 来店日（必須） -->
    <div>
      <label for="{{ form.visited_at.id_for_label }}">{{ form.visited_at.label }}</label>
      {{ form.visited_at }}
      {% if form.visited_at.errors %}<p class="text-error">{{ form.visited_at.errors.0 }}</p>{% endif %}
    </div>

    <!-- 会話メモ（任意） -->
    <div>
      <label for="{{ form.conversation_memo.id_for_label }}">{{ form.conversation_memo.label }}</label>
      {{ form.conversation_memo }}
      {% if form.conversation_memo.errors %}<p class="text-error">{{ form.conversation_memo.errors.0 }}</p>{% endif %}
    </div>

    <!-- non_field_errors -->
    {% if form.non_field_errors %}
      <div class="error-subtle">
        {% for error in form.non_field_errors %}
          <p>{{ error }}</p>
        {% endfor %}
      </div>
    {% endif %}

    <!-- ボタン -->
    <div>  <!-- flex gap-4 mt-6 -->
      <button type="submit" class="btn-primary">保存</button>
      <a href="/o/visits/" class="btn-secondary">キャンセル</a>
    </div>
  </form>
{% endblock %}
```

### 5.5 owner/segment_settings.html（Slice 2）

```
{% extends "ui/base_owner.html" %}
{% load static %}

{% block page_title %}セグメント閾値設定{% endblock %}

{% block toast %}
  {% if toast %}
    <div x-data="{ show: true }"
         x-show="show"
         x-init="setTimeout(() => { show = false }, 3000)"
         x-transition
         class="toast-{{ toast.type }}">
      {{ toast.message }}
    </div>
  {% endif %}
{% endblock %}

{% block content %}
  <!-- 現在の閾値テーブル -->
  <section>
    <h2>現在の閾値</h2>
    <table>
      <thead>
        <tr>
          <th>セグメント</th>
          <th>最小来店回数</th>
          <th>最大来店回数</th>
          <th>表示順</th>
        </tr>
      </thead>
      <tbody>
        {% for t in thresholds %}
          <tr>
            <td>
              {% if t.segment_name == "new" %}
                <span class="badge-new">新規</span>
              {% elif t.segment_name == "repeat" %}
                <span class="badge-repeat">リピート</span>
              {% elif t.segment_name == "regular" %}
                <span class="badge-regular">常連</span>
              {% endif %}
            </td>
            <td>{{ t.min_visits }}</td>
            <td>{% if t.max_visits is not None %}{{ t.max_visits }}{% else %}<span class="text-text-muted">上限なし</span>{% endif %}</td>
            <td>{{ t.display_order }}</td>
          </tr>
        {% endfor %}
      </tbody>
    </table>
  </section>

  <!-- 閾値変更フォーム -->
  <section x-data="{ previewShown: false }">
    <h2>閾値変更</h2>
    <form id="threshold-form">
      {% csrf_token %}
      {{ formset.management_form }}

      {% for form in formset %}
        <div>  <!-- flex items-center gap-4 mb-4 -->
          {{ form.segment_name }}
          {{ form.display_order }}
          <span class="font-medium">{{ form.segment_label }}</span>

          <label>最小</label>
          <div x-bind:class="{ 'pointer-events-none opacity-60': previewShown }">
            {{ form.min_visits }}
          </div>
          {% if form.min_visits.errors %}<p class="text-error">{{ form.min_visits.errors.0 }}</p>{% endif %}

          <label>最大</label>
          {% if form.initial.segment_name == "regular" %}
            <span class="text-text-muted">上限なし</span>
          {% else %}
            <div x-bind:class="{ 'pointer-events-none opacity-60': previewShown }">
              {{ form.max_visits }}
            </div>
            {% if form.max_visits.errors %}<p class="text-error">{{ form.max_visits.errors.0 }}</p>{% endif %}
          {% endif %}
        </div>
      {% endfor %}

      <!-- non_form_errors -->
      {% if formset.non_form_errors %}
        <div class="error-subtle">
          {% for error in formset.non_form_errors %}
            <p>{{ error }}</p>
          {% endfor %}
        </div>
      {% endif %}

      <div>  <!-- flex gap-4 mt-6 -->
        <button type="button"
                x-show="!previewShown"
                class="btn-secondary"
                hx-post="/o/segments/preview/"
                hx-target="#preview-zone"
                hx-include="#threshold-form"
                hx-swap="innerHTML"
                hx-indicator="#preview-loading"
                @htmx:after-settle.window="if($event.detail.target.id === 'preview-zone' && !$event.detail.xhr.status.toString().startsWith('4')) previewShown = true">
          プレビュー
        </button>
        <button type="button"
                x-show="previewShown"
                class="btn-secondary"
                @click="previewShown = false; document.getElementById('preview-zone').innerHTML = ''">
          変更する
        </button>
      </div>
    </form>
  </section>

  <!-- プレビュー結果ゾーン -->
  <section>
    <div id="preview-zone">
      <!-- HTMX でプレビュー結果が差し込まれる -->
    </div>
    <div id="preview-loading" class="htmx-indicator">
      <span>計算中...</span>
    </div>
  </section>
{% endblock %}
```

### 5.6 owner/_segment_preview.html（HTMX フラグメント、Slice 2）

```
{% load static %}

{% if preview_error %}
  {% if apply_error %}
    <div class="error-subtle">
      <p>閾値の更新に失敗しました: {{ apply_error }}</p>
    </div>
  {% elif formset %}
    <div class="error-subtle">
      <p>入力内容にエラーがあります。</p>
      {% if formset.non_form_errors %}
        {% for error in formset.non_form_errors %}
          <p>{{ error }}</p>
        {% endfor %}
      {% endif %}
      {% for form in formset %}
        {% for field, errors in form.errors.items %}
          {% for error in errors %}
            <p>{{ error }}</p>
          {% endfor %}
        {% endfor %}
      {% endfor %}
    </div>
  {% endif %}
{% else %}
  <div>  <!-- bg-surface rounded-md p-4 -->
    <h3>プレビュー結果</h3>
    <p>この変更で <strong>{{ affected_count }}</strong> 件の顧客のセグメントが変わります。</p>

    <table>
      <thead>
        <tr>
          <th>セグメント</th>
          <th>変更後の顧客数</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><span class="badge-new">新規</span></td>
          <td>{{ segment_counts.new }} 件</td>
        </tr>
        <tr>
          <td><span class="badge-repeat">リピート</span></td>
          <td>{{ segment_counts.repeat }} 件</td>
        </tr>
        <tr>
          <td><span class="badge-regular">常連</span></td>
          <td>{{ segment_counts.regular }} 件</td>
        </tr>
      </tbody>
    </table>

    <!-- 確定ボタン -->
    <div>  <!-- flex gap-4 mt-4 -->
      <button type="button"
              class="btn-primary"
              hx-post="/o/segments/apply/"
              hx-include="#threshold-form"
              hx-target="#preview-zone"
              hx-swap="innerHTML">
        確定
      </button>
      <button type="button"
              class="btn-secondary"
              @click="previewShown = false; document.getElementById('preview-zone').innerHTML = ''">
        キャンセル
      </button>
    </div>
  </div>
{% endif %}
```

**プレビュー → 確定フロー**: 基本設計書 §6 O-SEGMENT-SETTINGS の影響プレビューフローに準拠。「プレビュー」ボタンで `hx-post="/o/segments/preview/"` → プレビュー結果表示 → 「確定」ボタンで `hx-post="/o/segments/apply/"` → 閾値更新 + 再計算 → `HX-Redirect` でページリロード + トースト。

**プレビュー後のフォーム無効化**: プレビュー表示後にフォーム入力を変更するとプレビュー結果と実際の適用内容が不整合になる。Alpine.js の `previewShown` フラグで、プレビュー表示中はフォームの数値入力を `pointer-events-none` で無効化する。「変更する」ボタンでフォームを再有効化し、プレビュー結果をクリアする。「確定」ボタンはプレビュー表示中のみ表示される。

**non_form_errors の表示**: HTMX フラグメント内で `formset.non_form_errors`（範囲重複・非連続等の FormSet レベルエラー）を表示する。個別フィールドエラーのみでは FormSet の `clean()` が検出した相互整合性エラーが表示されない。

### 5.7 HTMX CSRF 設定

UO-01 S1 で `base.html` に HTMX CSRF トークン自動付与（`htmx:configRequest`）が追加済みのため、UO-03 では追加の CSRF 設定は不要。`hx-get` は CSRF 不要、`hx-post` は `htmx:configRequest` イベントで自動付与、`form method="post"` は `{% csrf_token %}` で対応。

422 レスポンスの swap 許可は `base.html` で設定済み（`htmx.config.responseHandling` で 422 を swap 許可）。

## 6. URL 設定

### ui/owner/urls.py（追記）

```python
# 既存の UO-01 / UO-02 の urlpatterns に追記

from ui.owner.views.visit import (
    VisitListView, VisitEditView, VisitDeleteView,
)
from ui.owner.views.segment import (
    SegmentSettingsView, SegmentPreviewView, SegmentApplyView,
)

# UO-03 S1: 来店管理
path("visits/", VisitListView.as_view(), name="visit-list"),
path("visits/<uuid:pk>/edit/", VisitEditView.as_view(), name="visit-edit"),
path("visits/<uuid:pk>/delete/", VisitDeleteView.as_view(), name="visit-delete"),

# UO-03 S2: セグメント閾値設定
path("segments/settings/", SegmentSettingsView.as_view(), name="segment-settings"),
path("segments/preview/", SegmentPreviewView.as_view(), name="segment-preview"),
path("segments/apply/", SegmentApplyView.as_view(), name="segment-apply"),
```

**Sidebar リンクの有効化**: UO-01 S1 で配置済みの `<a href="/o/visits/">来店記録</a>` と `<a href="/o/segments/settings/">セグメント設定</a>` が、UO-03 の URL 追加により遷移可能になる。追加のテンプレート変更は不要。

## 7. テストケース

### 7.1 Django TestClient（Slice 1: 来店管理）

| # | テスト | 検証内容 |
|---|--------|---------|
| 1 | `test_visit_list_owner` | owner で GET `/o/visits/` → 200、テーブル表示 |
| 2 | `test_visit_list_unauthenticated` | 未認証 → 302 `/o/login/` |
| 3 | `test_visit_list_staff_redirect` | staff で GET → 302 `/s/customers/` |
| 4 | `test_visit_list_search` | `?search=山田` → 顧客名に「山田」を含む来店記録のみ表示 |
| 5 | `test_visit_list_segment_filter` | `?segment=new` → 顧客の segment='new' の来店記録のみ表示 |
| 6 | `test_visit_list_staff_filter` | `?staff=<uuid>` → 該当スタッフの来店記録のみ表示 |
| 7 | `test_visit_list_date_range_filter` | `?date_from=2026-01-01&date_to=2026-01-31` → 該当期間の来店記録のみ表示 |
| 8 | `test_visit_list_sort_visited_at` | `?sort=visited_at` → 来店日昇順 |
| 9 | `test_visit_list_sort_visited_at_desc` | デフォルトソート → 来店日降順 |
| 10 | `test_visit_list_sort_customer_name` | `?sort=customer_name` → 顧客名昇順 |
| 11 | `test_visit_list_sort_invalid` | `?sort=invalid_field` → デフォルト（来店日降順）にフォールバック |
| 12 | `test_visit_list_pagination` | 26 件登録 → 1 ページ目 25 件 + 2 ページ目 1 件 |
| 13 | `test_visit_list_htmx_fragment` | `HX-Request: true` ヘッダー付き → `_visit_table.html` フラグメントのみ返却 |
| 14 | `test_visit_list_store_scope` | 他店舗の来店記録が表示されない |
| 15 | `test_visit_list_select_related` | `select_related('customer', 'staff')` で N+1 回避（クエリ数確認） |
| 16 | `test_visit_list_memo_truncate` | メモが 30 文字で切り詰められている |
| 17 | `test_visit_list_segment_badge` | セグメントバッジが正しく表示される |
| 18 | `test_visit_list_stable_sort` | 同一 visited_at の来店記録が created_at → pk で安定ソートされる |
| 19 | `test_visit_edit_get` | GET `/o/visits/<id>/edit/` → 200、フォームに既存値がプリセット |
| 20 | `test_visit_edit_get_readonly_fields` | レスポンスに顧客名とスタッフ名が読み取り専用で表示される |
| 21 | `test_visit_edit_post_valid` | POST valid → VisitService.update_visit 呼び出し + 302 来店一覧 + セッションに toast |
| 22 | `test_visit_edit_post_invalid_date_empty` | POST visited_at="" → 200、「来店日を入力してください」エラー |
| 23 | `test_visit_edit_empty_memo_to_none` | 空文字列の conversation_memo が None に正規化される |
| 24 | `test_visit_edit_business_error` | VisitService.update_visit が BusinessError を送出 → フォームに non_field_errors 表示 |
| 25 | `test_visit_edit_unauthenticated` | 未認証 → 302 `/o/login/` |
| 26 | `test_visit_edit_staff_redirect` | staff で GET → 302 `/s/customers/` |
| 27 | `test_visit_edit_not_found` | 存在しない来店 ID → 404 |
| 28 | `test_visit_edit_other_store` | 他店舗の来店 ID → 404 |
| 29 | `test_visit_delete_post` | POST `/o/visits/<id>/delete/` → 論理削除 + 302 来店一覧 + トースト |
| 30 | `test_visit_delete_get_not_allowed` | GET `/o/visits/<id>/delete/` → 405 Method Not Allowed |
| 31 | `test_visit_delete_unauthenticated` | 未認証 → 302 `/o/login/` |
| 32 | `test_visit_delete_staff_redirect` | staff で POST → 302 `/s/customers/` |
| 33 | `test_visit_delete_not_found` | 存在しない来店 ID → 404 |
| 34 | `test_visit_delete_other_store` | 他店舗の来店 ID → 404 |
| 35 | `test_visit_delete_business_error` | VisitService.delete_visit が BusinessError を送出 → エラートースト + 302 来店一覧 |
| 36 | `test_sidebar_active_visits` | `/o/visits/` で active_sidebar == "visits" |
| 37 | `test_visit_list_toast_display` | セッションに toast あり → トーストが表示され、セッションから削除 |
| 38 | `test_visit_list_combined_filters` | 検索 + セグメント + スタッフ + 日付範囲の組み合わせフィルタ |

### 7.2 Django TestClient（Slice 2: セグメント設定）

| # | テスト | 検証内容 |
|---|--------|---------|
| 1 | `test_segment_settings_get` | owner で GET `/o/segments/settings/` → 200、閾値テーブル表示 |
| 2 | `test_segment_settings_unauthenticated` | 未認証 → 302 `/o/login/` |
| 3 | `test_segment_settings_staff_redirect` | staff で GET → 302 `/s/customers/` |
| 4 | `test_segment_preview_valid` | POST `/o/segments/preview/` → 200、影響件数が表示される |
| 5 | `test_segment_preview_invalid_formset` | 不正な FormSet → 422、エラーメッセージ表示 |
| 6 | `test_segment_preview_affected_count` | 閾値変更で影響を受ける顧客数が正しく計算される |
| 7 | `test_segment_preview_segment_counts` | 変更後の各セグメント顧客数が正しく表示される |
| 8 | `test_segment_apply_valid` | POST `/o/segments/apply/` → 200 + HX-Redirect + 閾値更新 + 再計算 |
| 9 | `test_segment_apply_invalid_formset` | 不正な FormSet → 422、エラーメッセージ表示 |
| 10 | `test_segment_apply_validation_error` | 非連続な閾値範囲 → 422、バリデーションエラー |
| 11 | `test_segment_apply_toast` | 確定後のリダイレクト先でトーストが表示される |
| 12 | `test_segment_apply_recalculate_called` | SegmentService.bulk_recalculate_segments が呼ばれる |
| 13 | `test_segment_apply_transaction_rollback` | validate_store_thresholds 失敗時に閾値がロールバックされる |
| 14 | `test_segment_settings_store_scope` | 他店舗の閾値が表示されない |
| 15 | `test_sidebar_active_segments` | `/o/segments/settings/` で active_sidebar == "segments" |
| 16 | `test_segment_settings_toast_display` | セッションに toast あり → トーストが表示され、セッションから削除 |
| 17 | `test_segment_preview_unauthenticated` | 未認証 → 302 `/o/login/` |
| 18 | `test_segment_apply_unauthenticated` | 未認証 → 302 `/o/login/` |
| 19 | `test_segment_preview_staff_access_denied` | staff で POST `/o/segments/preview/` → 302 `/s/customers/`（オーナー権限なし） |
| 20 | `test_segment_apply_staff_access_denied` | staff で POST `/o/segments/apply/` → 302 `/s/customers/`（オーナー権限なし） |
| 21 | `test_segment_apply_display_order_tamper_ignored` | display_order を改ざん（例: 3,1,2）して POST → サーバーサイドで 1,2,3 に強制修正され正常に更新される |
| 22 | `test_visit_list_invalid_staff_uuid` | `?staff=not-a-uuid` → フィルタが無視され全件表示 |
| 23 | `test_visit_list_nonexistent_staff_uuid` | `?staff=<存在しないUUID>` → フィルタが無視され全件表示 |
| 24 | `test_visit_list_invalid_date_format` | `?date_from=invalid` → 日付フィルタが無視され全件表示 |
| 25 | `test_segment_preview_then_apply_values_match` | プレビューで送った閾値と Apply で送った閾値が一致していること（サーバー側で検証可能な部分のみ） |

### 7.3 Browser smoke test（Slice 1）

| # | 対象 URL | 手順 | 期待結果 |
|---|---------|------|---------|
| 1 | `/o/visits/` | 来店一覧表示 | テーブルにデータ表示、セグメントバッジ正常 |
| 2 | `/o/visits/` | 検索欄に文字入力 | 300ms 後に HTMX でテーブル差し替え |
| 3 | `/o/visits/` | セグメントフィルタ変更 | HTMX でテーブル差し替え、ブラウザ URL 変更 |
| 4 | `/o/visits/` | スタッフフィルタ変更 | HTMX でテーブル差し替え |
| 5 | `/o/visits/` | 日付範囲フィルタ設定 | HTMX でテーブル差し替え |
| 6 | `/o/visits/` | テーブルヘッダーのソートクリック | HTMX でテーブル差し替え、ソート矢印表示 |
| 7 | `/o/visits/` | ページネーション「次へ」 | HTMX でテーブル差し替え |
| 8 | `/o/visits/` | 行の「編集」クリック | 来店編集画面に遷移、フォームに既存値 |
| 9 | `/o/visits/<id>/edit/` | フォーム編集 → 保存 | 来店一覧にリダイレクト + トースト |
| 10 | `/o/visits/<id>/edit/` | 来店日を空にして保存 | バリデーションエラー表示 |
| 11 | `/o/visits/` | 行の「削除」クリック | 確認モーダル表示 |
| 12 | `/o/visits/` | 確認モーダルで「削除」クリック | 論理削除 + 来店一覧にリダイレクト + トースト |
| 13 | `/o/visits/` | 確認モーダルで「キャンセル」クリック | モーダル閉じる、削除されない |
| 14 | `/o/visits/` | 確認モーダル外クリック | モーダル閉じる |
| 15 | `/o/visits/` | 検索中にスケルトンローダー表示確認 | HTMX リクエスト中にスケルトンローダー表示 |

### 7.4 Browser smoke test（Slice 2）

| # | 対象 URL | 手順 | 期待結果 |
|---|---------|------|---------|
| 1 | `/o/segments/settings/` | セグメント設定画面表示 | 現在の閾値テーブルと変更フォーム表示 |
| 2 | `/o/segments/settings/` | 閾値変更 → 「プレビュー」ボタンクリック | 影響件数がプレビューゾーンに HTMX で表示 |
| 3 | `/o/segments/settings/` | プレビュー後「確定」ボタンクリック | 閾値更新 + ページリロード + トースト表示 |
| 4 | `/o/segments/settings/` | プレビュー後「キャンセル」ボタンクリック | プレビュー結果が消える。フォーム入力が再び編集可能になる |
| 5 | `/o/segments/settings/` | プレビュー表示中にフォーム入力を試みる | フォームが無効化されており編集不可（previewShown=true） |
| 6 | `/o/segments/settings/` | プレビュー表示中に「変更する」ボタンクリック | フォーム再有効化 + プレビューがクリアされる |
| 7 | `/o/segments/settings/` | 不正な閾値で「プレビュー」 | エラーメッセージ表示（422 swap） |
| 8 | `/o/segments/settings/` | 閾値確定後に `/o/customers/` で確認 | セグメントバッジが再計算後の値に更新 |
| 9 | `/o/segments/settings/` | regular の最大来店回数が「上限なし」表示 | 正常表示 |

## 8. Gherkin シナリオ

```gherkin
Feature: Owner 来店管理

  Scenario: 来店一覧の表示
    Given オーナーとしてログインしている
    And 店舗に来店記録が 3 件登録されている
    When `/o/visits/` にアクセスする
    Then 来店一覧テーブルに 3 件表示される
    And 各行にセグメントバッジが表示される

  Scenario: 顧客名で検索
    Given 顧客 "山田太郎" と "田中花子" の来店記録が存在する
    When 検索欄に "山田" と入力する
    Then "山田太郎" の来店記録のみ表示される

  Scenario: セグメントでフィルタ
    Given segment='new' の顧客と segment='regular' の顧客の来店記録が存在する
    When セグメントフィルタで "新規" を選択する
    Then segment='new' の顧客の来店記録のみ表示される

  Scenario: スタッフでフィルタ
    Given スタッフ A とスタッフ B の来店記録が存在する
    When スタッフフィルタでスタッフ A を選択する
    Then スタッフ A の来店記録のみ表示される

  Scenario: 日付範囲でフィルタ
    Given 2026-01-15 と 2026-02-15 の来店記録が存在する
    When 日付範囲を 2026-01-01 〜 2026-01-31 に設定する
    Then 2026-01-15 の来店記録のみ表示される

  Scenario: 来店日でソート
    Given 来店日が異なる来店記録が複数存在する
    When テーブルヘッダーの「来店日」をクリックする
    Then 来店日の昇順でソートされる
    And もう一度クリックすると降順に切り替わる

  Scenario: ページネーション
    Given 店舗に来店記録が 30 件登録されている
    When `/o/visits/` にアクセスする
    Then 25 件表示される
    And 「次へ」ボタンが表示される
    When 「次へ」をクリックする
    Then 残り 5 件が表示される

  Scenario: 他店舗の来店記録が見えない
    Given Store A に来店記録が存在する
    And Store B に来店記録が存在する
    And Store A のオーナーとしてログインしている
    When 来店一覧にアクセスする
    Then Store A の来店記録のみ表示される

  Scenario: 来店記録の編集
    Given 来店記録（2026-01-15、メモ「フルーツ系好み」）が存在する
    When 来店編集画面で来店日を 2026-01-16 に、メモを「フルーツ系とミント系好み」に変更して保存する
    Then 来店記録が更新される
    And 来店一覧にリダイレクトされる
    And トースト「来店記録を更新しました」が表示される

  Scenario: 来店編集で顧客とスタッフは変更不可
    Given 来店記録が存在する
    When 来店編集画面を開く
    Then 顧客名とスタッフ名は読み取り専用で表示される
    And フォームには来店日と会話メモのみ編集可能

  Scenario: 来店記録の削除
    Given 来店記録が存在する
    And 対象顧客の visit_count が 5（segment="regular"）
    When 来店一覧で「削除」ボタンをクリックする
    Then 確認ダイアログが表示される（「来店回数とセグメントが再計算されます」）
    When 「削除」をクリックする
    Then 来店記録が論理削除される
    And 顧客の visit_count が 4 に、segment が "repeat" に再計算される
    And 来店一覧にリダイレクトされる
    And トースト「来店記録を削除しました」が表示される

  Scenario: 削除確認ダイアログでキャンセル
    Given 来店記録が存在する
    When 「削除」ボタン → 確認ダイアログで「キャンセル」をクリックする
    Then ダイアログが閉じ、来店記録は削除されない

  Scenario: 空文字列の None 正規化
    Given 来店記録（conversation_memo="メモ"）が存在する
    When 来店編集画面で memo を空にして保存する
    Then conversation_memo が None に更新される（空文字列ではない）

  Scenario: 未認証でのアクセス
    Given ログインしていない
    When `/o/visits/` にアクセスする
    Then `/o/login/` にリダイレクトされる

  Scenario: スタッフでのアクセス
    Given staff ロールでログインしている
    When `/o/visits/` にアクセスする
    Then `/s/customers/` にリダイレクトされる

Feature: Owner セグメント閾値設定

  Scenario: 閾値設定画面の表示
    Given オーナーとしてログインしている
    And デフォルト閾値（new=0-1, repeat=2-4, regular=5+）が設定されている
    When `/o/segments/settings/` にアクセスする
    Then 現在の閾値テーブルが表示される
    And 閾値変更フォームが表示される

  Scenario: 閾値変更のプレビュー
    Given 閾値が new=0-1, repeat=2-4, regular=5+ である
    And visit_count=3 の顧客が 2 件存在する
    When repeat の max_visits を 2、regular の min_visits を 3 に変更して「プレビュー」をクリックする
    Then 「2 件の顧客のセグメントが変わります」と表示される
    And 変更後の各セグメント顧客数が表示される

  Scenario: 閾値の確定と再計算
    Given 閾値を変更してプレビュー済み
    When 「確定」ボタンをクリックする
    Then 閾値が更新される
    And 全顧客のセグメントが一括再計算される
    And トースト「セグメント閾値を更新しました。N 件の顧客のセグメントが再計算されました」が表示される

  Scenario: 不正な閾値でプレビュー
    Given 重複する範囲（new=0-2, repeat=2-4, regular=5+）を入力する
    When 「プレビュー」をクリックする
    Then プレビューゾーンにバリデーションエラーが表示される

  Scenario: 確定後のセグメントバッジ反映
    Given 閾値変更によりセグメントが変わった顧客がいる
    When `/o/customers/` にアクセスする
    Then セグメントバッジが再計算後の値で表示される

  Scenario: 未認証でのアクセス
    Given ログインしていない
    When `/o/segments/settings/` にアクセスする
    Then `/o/login/` にリダイレクトされる

  Scenario: スタッフでのアクセス
    Given staff ロールでログインしている
    When `/o/segments/settings/` にアクセスする
    Then `/s/customers/` にリダイレクトされる
```

## 9. Closure Audit チェックリスト

### Slice 間の結合面

- **S1 → S2**: Slice 1 の来店削除で visit_count が変わり、Slice 2 のセグメント閾値設定で bulk_recalculate した結果と整合するか
- **S1 → UO-02**: 来店一覧の顧客名リンク（`/o/customers/<id>/`）が UO-02 の顧客詳細に正しく遷移するか
- **S2 → UO-02**: セグメント再計算後、顧客一覧のセグメントバッジが更新されているか
- **S1 → C-04**: `VisitService.update_visit()` / `VisitService.delete_visit()` が C-04 S2 の仕様通りに動作するか（signal 経由の再計算を含む）
- **S2 → C-04**: `SegmentThreshold.validate_store_thresholds()` と `SegmentService.bulk_recalculate_segments()` が C-04 S3 の仕様通りに動作するか

### Sidebar アクティブ状態

- S1: `active_sidebar = "visits"` → Sidebar の「来店記録」がアクティブ
- S2: `active_sidebar = "segments"` → Sidebar の「セグメント設定」がアクティブ

## 10. Review Log

| 日付 | レビュアー | Finding | 重要度 | 対応 |
|------|-----------|---------|--------|------|
| 2026-03-31 | Codex (gpt-5.4 high) | F-01: SegmentApplyView の閾値更新で `select_for_update()` が欠落 | High | `transaction.atomic()` 内で `SegmentThreshold.objects.select_for_update().filter(store=self.store)` を追加 |
| 2026-03-31 | Codex (gpt-5.4 high) | F-02: UI 例外実装のため監査ログが欠落 | High | `AuditLogger.log()` を明示呼び出し追加。コア層契約セクションに監査ログ要件を追記 |
| 2026-03-31 | Codex (gpt-5.4 high) | F-03: プレビュー後にフォーム編集可能でプレビュー結果と不整合 | High | Alpine.js `previewShown` フラグでプレビュー中はフォーム入力を無効化。「変更する」ボタンで再有効化 |
| 2026-03-31 | Codex (gpt-5.4 high) | F-04: hidden input `display_order` が改ざん可能 | High | `BaseSegmentThresholdFormSet.clean()` 内でクライアント送信値を無視し、C-04 固定値 (1,2,3) をサーバーサイドで強制設定 |
| 2026-03-31 | Codex (gpt-5.4 high) | F-05: HTMX フラグメントで `formset.non_form_errors` が未表示 | High | `_segment_preview.html` に `{% if formset.non_form_errors %}` セクションを追加 |
| 2026-03-31 | Codex (gpt-5.4 high) | F-06: `except Exception as e` で全例外を握り潰し | High | `except (ValidationError, BusinessError) as e` に限定。DB エラー等は Django 500 ハンドラに委譲 |
| 2026-03-31 | Codex (gpt-5.4 high) | F-07: フィルタパラメータ (staff UUID, date) の未検証 | Medium | staff: UUID 形式検証 + 存在チェック。日付: `fromisoformat()` でパース検証。不正値は無視。コンテキストにも検証済み値のみ |
| 2026-03-31 | Codex (gpt-5.4 high) | F-08: SegmentPreviewView でセグメント判定ロジックを複製 | Medium | `_determine_segment_from_thresholds` を削除し `SegmentService.determine_segment()` を使用。コア層契約に `determine_segment` メソッドを追記 |
| 2026-03-31 | Codex (gpt-5.4 high) | F-09: テストケース不足（権限・改ざん・不正入力・プレビュー整合性） | Medium | テスト #19〜#25 を追加（staff アクセス拒否、display_order 改ざん、不正 UUID/日付、プレビュー→編集→確定の不整合） |
| 2026-03-31 | Codex (gpt-5.4 high) R2 | F-10: select_for_update() 未評価 | High | list() で QuerySet を強制評価してロック取得 |
| 2026-03-31 | Codex (gpt-5.4 high) R2 | F-11: キャンセルで previewShown 未解除 | High | @click で previewShown=false を追加 |
| 2026-03-31 | Codex (gpt-5.4 high) R2 | F-12: staff 存在チェックなし | Medium | UUID 形式 + Staff.objects.filter(pk, store, is_active).exists() |
| 2026-03-31 | Codex (gpt-5.4 high) R2 | F-13: Alpine テストを TestClient → smoke test に移動 | Medium | #25 をサーバー検証に変更。smoke test #5-6 を追加 |
| 2026-04-01 | Codex (gpt-5.4 high) R3 | F-14: Staff import パス不一致 | Medium | `from core.models import Staff` に統一 |
| 2026-04-01 | Codex (gpt-5.4 high) R3 | F-15: smoke test 番号重複 | Low | #5-6 + #7-9 に再採番 |
