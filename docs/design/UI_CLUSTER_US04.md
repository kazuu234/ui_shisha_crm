# US-04 詳細設計書: 会計後マッチング

> 基本設計書: `docs/design/UI_BASIC_DESIGN.md` §5 US-04, §7.4
> デザインガイド: `docs/design/UI_DESIGN_GUIDE.md`
> パイプライン: `docs/design/UI_PIPELINE.md` #6
> コア層参照: `docs/reference/cluster/C06_AIRREGI.md` Slice 2（MatchingService, CsvImportRow）

## 1. 概要

### Slice 情報

| 項目 | 内容 |
|------|------|
| **Cluster** | US-04 (会計後マッチング) |
| **Slice** | S1（単一 Slice で完結） |
| **パイプライン順序** | #6 / 13 |
| **ブランチ説明部** | `us04-matching` |

### スコープ

会計後マッチング画面。当日の `pending_review` CsvImportRow 一覧を表示し、行タップで候補顧客一覧を HTMX 遅延ロード、候補タップで確定（confirm）、却下ボタンで reject を行う。1 画面で完結する。BottomTab「マッチング」タブを有効化する。

### precondition

- US-01 S1 完了（`base_staff.html`、`LoginRequiredMixin`、`StaffRequiredMixin`、`StoreMixin` が動作）
- コア層 C-06 全 Slice 完了（`ImportService`、`MatchingService`、`CsvImportRow` モデルが動作）

### postcondition

- `/s/matching/` で当日の `pending_review` CsvImportRow が表示される（`validated` = 候補 0 件の行は表示しない）
- 行タップ → Alpine.js で行が展開 → 候補顧客一覧が HTMX GET `/s/matching/<row_id>/candidates/` で遅延ロードされる（毎回再計算、永続化しない）
- 候補タップ → HTMX PATCH `/s/matching/<row_id>/confirm/` with `visit_id` → confirm（`select_for_update` で排他制御。`visit_id` が候補集合に含まれるか検証）→ 行ステータスが confirmed に更新 → 行が一覧から消える
- 却下ボタン → HTMX PATCH `/s/matching/<row_id>/reject/` → reject（`select_for_update`）→ 行ステータスが rejected に更新 → 行が一覧から消える
- `pending_review` 明細がない場合「マッチ待ちの明細はありません」表示
- BottomTab の「マッチング」タブがアクティブ状態（`<a>` リンクに変更。disabled 解除）
- 全 View が `base_staff.html` を継承し、BottomTab 付き

## 2. ファイル構成

```
ui/
├── staff/
│   ├── urls.py                      # 4 URL 追加（matching-list, matching-candidates, matching-confirm, matching-reject）
│   ├── views/
│   │   └── matching.py              # MatchingView, MatchingCandidatesView, MatchingConfirmView, MatchingRejectView
│   └── forms/
│       └── matching.py              # MatchingConfirmForm
├── templates/ui/
│   └── staff/
│       ├── matching.html            # マッチング一覧画面
│       ├── _matching_row.html       # 行フラグメント（HTMX 差し替え用）
│       └── _matching_candidates.html # 候補一覧フラグメント（HTMX 遅延ロード用）
```

**追加するアイコン**: なし（US-01 で作成済みの `link.svg` を使用）。

## 3. コア層契約

正式な定義は `docs/reference/cluster/C06_AIRREGI.md` Slice 2 を参照。

**import パスについて**: コア層は別リポジトリ（別 Django app）として管理されている場合がある。本設計書では `from core.services.matching import MatchingService` のような統一的な記法を使用するが、実際の import パスはコア層のパッケージ構造に依存する。実装時にコア層の `__init__.py` や実際のモジュール配置を確認すること。

### CsvImportRow モデル（UI が参照するフィールド）

| フィールド | 型 | 備考 |
|-----------|-----|------|
| `id` | UUIDField | PK |
| `csv_import` | ForeignKey(CsvImport) | 親 CsvImport |
| `status` | CharField (`validated` / `pending_review` / `confirmed` / `rejected`) | 行のステータス |
| `business_date` | DateField | 営業日（来店日） |
| `receipt_no` | CharField | 取引No（レシート番号） |
| `normalized_data` | JSONField | 正規化データ。`customer_name`（CSV 顧客名）等を含む |
| `matched_visit` | ForeignKey(Visit, nullable) | 確定済みの来店記録 |
| `store` | ForeignKey(Store) | 店舗スコープ |

**StoreScopedManager**: `CsvImportRow.objects.for_store(store)` でストアスコープフィルタを適用。

### MatchingService

| メソッド | 引数 | 返り値 | 例外 |
|---------|------|--------|------|
| `get_candidates(row, store)` | `CsvImportRow, Store` | `list[dict]` — `[{visit_id, customer{id, name}, visited_at, name_match_score}]` | `BusinessError(business_code='import.candidates_not_available')` — `pending_review` 以外 |
| `confirm_row(row, visit_id, store, request=None)` | `CsvImportRow, UUID, Store, HttpRequest?` | `CsvImportRow` (status='confirmed') | `BusinessError(business_code='import.row_not_pending')`, `BusinessError(business_code='import.row_already_processed')`, `BusinessError(business_code='import.direct_confirm_reject')`, `BusinessError(business_code='import.visit_not_in_candidates')`, `BusinessError(business_code='import.row_conflict')` |
| `reject_row(row, store, request=None)` | `CsvImportRow, Store, HttpRequest?` | `CsvImportRow` (status='rejected') | `BusinessError(business_code='import.row_not_pending')`, `BusinessError(business_code='import.row_already_processed')`, `BusinessError(business_code='import.direct_confirm_reject')`, `BusinessError(business_code='import.row_conflict')` |

**get_candidates の仕様**:
- `pending_review` 以外のステータスで呼ばれた場合は `BusinessError(business_code='import.candidates_not_available')` を raise する
- 候補は毎回再計算（永続化しない）。同一 Store × 同一営業日の Visit から候補を算出する
- 候補のソート順: `name_match_score` 降順。顧客名なし or 同スコアの場合は `customer.name` 昇順（五十音順）
- `name_match_score`: CSV の customer_name と CRM Customer.name の部分一致度（0.0〜1.0）。顧客名が CSV にない場合は null

**confirm_row の仕様**（旧名: `confirm_match`）:
- `select_for_update` で排他制御。`visit_id` がその時点の候補集合に含まれるか検証する
- 同時操作の場合、先行が勝ち、後続は `import.row_conflict` (409) エラー

**reject_row の仕様**（旧名: `reject_match`）:
- `select_for_update` で排他制御。ステータスを `rejected` に更新する
- 同時操作の場合、先行が勝ち、後続は `import.row_conflict` (409) エラー

### BusinessError コード一覧（UI が処理するもの）

UI は MatchingService を直接呼び出す（コア層 API エンドポイント経由ではない）ため、BusinessError を catch して処理する。C-06 が定義する HTTP ステータス（400, 409）はコア層 API 用であり、UI View では BusinessError の `business_code` でメッセージを分岐する。

**エラー処理方針（View 種別ごと）**:

- **HTMX PATCH View（MatchingConfirmView, MatchingRejectView）**: 全 BusinessError を 422 + `HX-Reswap: none` + トースト（`HX-Trigger: showToast`）で返す。DOM 変更なし、トーストでユーザーにフィードバック。`ERROR_MESSAGES` dict でコードからメッセージを解決する
- **HTMX GET View（MatchingCandidatesView）**: `import.candidates_not_available` は UI 上到達しない（pending_review のみ表示するため）防御コード。発生時は `HttpResponseBadRequest("候補を取得できません")` で 400 テキストを返す。HTMX GET のエラーはトースト対象外（PATCH 操作のフィードバック用途とは異なるため）

| コード | C-06 定義の HTTP | 意味 | UI の対応 |
|--------|-----------------|------|----------|
| `import.candidates_not_available` | 400 | `pending_review` 以外で候補取得 | 防御コード。400 テキスト「候補を取得できません」（MatchingCandidatesView） |
| `import.row_not_pending` | 400 | pending_review 以外で confirm/reject | 422 + トースト「この明細は既に処理されています」（PATCH View） |
| `import.row_already_processed` | 400 | confirmed/rejected 行の再操作 | 422 + トースト「この明細は既に処理されています」（PATCH View） |
| `import.direct_confirm_reject` | 400 | validated 行の直接 confirm/reject | 422 + トースト「この明細はまだマッチング未実行です」（PATCH View） |
| `import.visit_not_in_candidates` | 400 | confirm 時の visit_id が候補集合に不在 | 422 + トースト「選択した候補は無効です。再読み込みしてください」（PATCH View） |
| `import.row_conflict` | 409 | 同時操作の競合 | 422 + トースト「他のスタッフが先に処理しました」（PATCH View） |

**C-06 との整合性**: UI では `pending_review` の行のみ表示するため、`import.row_already_processed`、`import.direct_confirm_reject`、`import.candidates_not_available` は通常到達しない。ただし、HTMX 非同期操作のタイミングによっては到達しうるため（例: 行表示中に別端末でステータスが変わった場合）、C-06 が定義する全コードを処理対象に含める。

## 4. テンプレート

### 4.1 staff/matching.html

`base_staff.html` を継承。当日の pending_review CsvImportRow 一覧を表示する。

```
{% extends "ui/base_staff.html" %}
{% load static %}

{% block page_title %}マッチング{% endblock %}

{% block content %}
  <div>  <!-- bg-bg-surface, shadow-sm, rounded-md -->
    {% for row in rows %}
      {% include "ui/staff/_matching_row.html" with row=row %}
    {% empty %}
      <div>  <!-- text-center, text-text-secondary, py-8, px-5 -->
        <p>マッチ待ちの明細はありません</p>
      </div>
    {% endfor %}
  </div>
{% endblock %}
```

**一覧の条件**: `CsvImportRow.objects.for_store(store).filter(status='pending_review', business_date=today).select_related('csv_import')`。`validated`（候補 0 件）の行は表示しない。

### 4.2 staff/_matching_row.html

行フラグメント。Alpine.js で展開/折りたたみを制御し、展開時に HTMX で候補を遅延ロードする。

```
{% load static %}

<div id="matching-row-{{ row.id }}"
     x-data="{ open: false }"
     class="border-b border-border-default last:border-b-0">

  <!-- 行ヘッダー（タップで展開。展開のたびに候補を再取得する） -->
  <div @click="open = !open; if (open) { $nextTick(() => htmx.trigger($refs.candidateArea, 'loadCandidates')) }"
       class="py-3 px-5 cursor-pointer">
    <div>  <!-- flex items-center justify-between -->
      <div>
        <span>{{ row.business_date|date:"n/j" }}</span>  <!-- font-medium -->
        <span>No.{{ row.receipt_no }}</span>  <!-- text-text-secondary, text-sm, ml-2 -->
      </div>
      <span x-text="open ? '▾' : '▸'"></span>  <!-- text-text-muted -->
    </div>
    {% if row.csv_customer_name %}
      <p>  <!-- text-text-secondary, text-sm, mt-1 -->
        CSV 顧客名: {{ row.csv_customer_name }}
      </p>
    {% endif %}
  </div>

  <!-- 候補エリア（展開時に HTMX で遅延ロード） -->
  <div x-show="open" x-transition x-ref="candidateArea"
       hx-get="/s/matching/{{ row.id }}/candidates/"
       hx-trigger="loadCandidates"
       hx-swap="innerHTML"
       class="px-5 pb-3">
    <!-- 初期状態: ローディング表示 -->
    <div>  <!-- text-center, text-text-muted, py-4 -->
      <p>候補を読み込み中...</p>
    </div>
  </div>
</div>
```

**csv_customer_name の取得**: View で `row.normalized_data.get('customer_name')` から抽出し、テンプレートコンテキストとして `row.csv_customer_name` に付与する。

**遅延ロードのトリガー**: 行を展開するたびに `htmx.trigger()` でカスタムイベント `loadCandidates` を発火し、候補一覧を HTMX GET で再取得する。C-06 の設計に従い、候補は毎回再計算される（永続化しない）。展開のたびに最新の候補が表示されるため、Visit の追加・更新・削除が反映される。

### 4.3 staff/_matching_candidates.html

候補一覧フラグメント。HTMX GET の応答として返される。

```
{% load static %}

{% if candidates %}
  <div>  <!-- divide-y divide-border-default -->
    {% for candidate in candidates %}
      <div>  <!-- py-2, flex items-center justify-between -->
        <div>
          <span>{{ candidate.customer_name }}</span>  <!-- font-medium。View で flat 化済み -->
          <span>{{ candidate.visited_at }}</span>  <!-- text-text-secondary, text-sm, ml-2 -->
          {% if candidate.name_match_score is not None %}
            <span>  <!-- text-xs, ml-1 -->
              {% if candidate.name_match_score == 1.0 %}
                <span class="text-success">完全一致</span>
              {% elif candidate.name_match_score == 0.5 %}
                <span class="text-warning">部分一致</span>
              {% endif %}
            </span>
          {% endif %}
        </div>
        <button
          hx-patch="/s/matching/{{ row_id }}/confirm/"
          hx-vals='{"visit_id": "{{ candidate.visit_id }}"}'
          hx-target="#matching-row-{{ row_id }}"
          hx-swap="outerHTML"
          class="text-sm text-accent font-medium">
          確定
        </button>
      </div>
    {% endfor %}
  </div>

  <!-- 却下ボタン -->
  <div>  <!-- mt-3, pt-3, border-t border-border-default -->
    <button
      hx-patch="/s/matching/{{ row_id }}/reject/"
      hx-target="#matching-row-{{ row_id }}"
      hx-swap="outerHTML"
      class="text-sm text-error font-medium">
      この明細を却下
    </button>
  </div>
{% else %}
  <div>  <!-- text-center, text-text-muted, py-4 -->
    <p>候補が見つかりませんでした</p>
  </div>
  <!-- 候補 0 件でも却下は可能 -->
  <div>  <!-- mt-3, pt-3, border-t border-border-default -->
    <button
      hx-patch="/s/matching/{{ row_id }}/reject/"
      hx-target="#matching-row-{{ row_id }}"
      hx-swap="outerHTML"
      class="text-sm text-error font-medium">
      この明細を却下
    </button>
  </div>
{% endif %}
```

**confirm の HTMX ターゲット**: `hx-target="#matching-row-{{ row_id }}"` で行全体を差し替える。confirm/reject 成功後は空の HTML を返し、行が消える（一覧から除去）。

**reject ボタンの配置**: 候補一覧の下に配置する。候補が 0 件の場合でも却下操作は可能とする（オペレーターがマッチング不要と判断した場合）。

**確定ボタンの hx-vals**: `visit_id` を JSON で送信する。CSRF トークンは `base.html` の `htmx:configRequest` イベントハンドラで自動付与される。

### 4.4 BottomTab 変更（base_staff.html）

US-01 で disabled だった「マッチング」タブを `<a>` リンクに変更する。

**変更前（US-01 時点）:**
```html
<button disabled aria-disabled="true">{% include "ui/icons/link.svg" %} マッチング</button>
```

**変更後（US-04 完了後）:**
```html
<a href="/s/matching/" {% if active_tab == "matching" %}class="active"{% endif %}>
  {% include "ui/icons/link.svg" %} マッチング
</a>
```

**影響範囲**: `base_staff.html` の BottomTab セクションのみ。他の Slice で追加されたタブ（顧客、接客）には影響しない。「来店記録」タブは引き続き disabled のまま。

## 5. Form 定義

### 5.1 MatchingConfirmForm

confirm 操作で送信される `visit_id` のバリデーションを行う。

```python
# ui/staff/forms/matching.py

from django import forms
import uuid


class MatchingConfirmForm(forms.Form):
    visit_id = forms.UUIDField()
```

**シンプルな理由**: confirm 操作のバリデーション（visit_id が候補集合に含まれるか）は `MatchingService.confirm_row()` が担う。Form はリクエストボディの型チェックのみ。

## 6. View 定義

### 6.1 MatchingView

```python
# ui/staff/views/matching.py

from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.views.generic import TemplateView

from ui.mixins import StaffRequiredMixin, StoreMixin


class MatchingView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, TemplateView):
    """会計後マッチング一覧画面。当日の pending_review CsvImportRow を表示する。"""
    template_name = "ui/staff/matching.html"
    login_url = "/s/login/"

    def get_context_data(self, **kwargs):
        from core.models import CsvImportRow

        context = super().get_context_data(**kwargs)
        today = timezone.localdate()

        rows = (
            CsvImportRow.objects.for_store(self.store)
            .filter(status="pending_review", business_date=today)
            .select_related("csv_import")
            .order_by("receipt_no")
        )

        # normalized_data から csv_customer_name を抽出してテンプレート用に付与
        for row in rows:
            row.csv_customer_name = (row.normalized_data or {}).get("customer_name")

        context["rows"] = rows
        context["active_tab"] = "matching"
        return context
```

**Mixin 順序**: `LoginRequiredMixin, StaffRequiredMixin, StoreMixin, TemplateView`。US-01 の設計原則に準拠。

**ストアスコープ**: `CsvImportRow.objects.for_store(self.store)` で他店舗のデータにアクセスできないことを保証。

**当日判定**: `timezone.localdate()` を使用する（`date.today()` ではない）。Django の `TIME_ZONE` 設定に従ったローカル日付を返すため、サーバーの OS タイムゾーンとアプリケーションのタイムゾーンがずれた場合でも正しい営業日を取得できる。

**ソート順**: `receipt_no` 昇順。同一営業日内でレシート番号順に表示する。

**csv_customer_name の付与**: `normalized_data` は JSONField であり、テンプレートから直接 dict キーにアクセスするのは可読性が低い。View で `row.csv_customer_name` としてプロパティ的に付与する。

### 6.2 MatchingCandidatesView

```python
# ui/staff/views/matching.py に追記

from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.views import View

from core.exceptions import BusinessError
from core.services.matching import MatchingService


class MatchingCandidatesView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, View):
    """HTMX GET: 候補一覧を遅延ロードする。"""
    login_url = "/s/login/"

    def get(self, request, row_id):
        from core.models import CsvImportRow

        row = get_object_or_404(
            CsvImportRow.objects.for_store(self.store),
            pk=row_id,
        )

        try:
            raw_candidates = MatchingService.get_candidates(row, self.store)
        except BusinessError:
            return HttpResponseBadRequest("候補を取得できません")

        # C-06 契約の返り値: [{visit_id, customer{id, name}, visited_at, name_match_score}]
        # テンプレート用に flat 化する
        candidates = []
        for c in raw_candidates:
            candidates.append({
                "visit_id": c["visit_id"],
                "customer_name": c["customer"]["name"],
                "customer_id": c["customer"]["id"],
                "visited_at": c["visited_at"],
                "name_match_score": c["name_match_score"],
            })

        return render(request, "ui/staff/_matching_candidates.html", {
            "candidates": candidates,
            "row_id": str(row.pk),
        })
```

**BusinessError の処理**: `import.candidates_not_available` は UI 上ありえない（pending_review のみ表示するため）。発生した場合は 400 テキストで返す。

**候補の毎回再計算**: `MatchingService.get_candidates(row, self.store)` は候補を永続化せず毎回再計算する（C-06 設計に準拠）。

**候補データの flat 化**: C-06 の `get_candidates()` はネストされた dict `{visit_id, customer{id, name}, visited_at, name_match_score}` を返す。テンプレートでの `{{ candidate.customer.name }}` のような dict ネストアクセスは Django テンプレートで動作するが、可読性と明示性のため View で flat 化する（`customer_name`, `customer_id` として展開）。

### 6.3 MatchingConfirmView

```python
# ui/staff/views/matching.py に追記

from django.http import HttpResponse, QueryDict

from ui.staff.forms.matching import MatchingConfirmForm


ERROR_MESSAGES = {
    "import.row_not_pending": "この明細は既に処理されています",
    "import.row_already_processed": "この明細は既に処理されています",
    "import.direct_confirm_reject": "この明細はまだマッチング未実行です",
    "import.visit_not_in_candidates": "選択した候補は無効です。再読み込みしてください",
    "import.row_conflict": "他のスタッフが先に処理しました",
}


class MatchingConfirmView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, View):
    """HTMX PATCH: 候補を確定する。"""
    login_url = "/s/login/"

    def patch(self, request, row_id):
        from core.models import CsvImportRow

        row = get_object_or_404(
            CsvImportRow.objects.for_store(self.store),
            pk=row_id,
        )

        # PATCH body を手動パース（Django は PATCH を request.POST にパースしない）
        data = QueryDict(request.body)
        form = MatchingConfirmForm(data)

        if not form.is_valid():
            return HttpResponseBadRequest("無効なリクエストです")

        visit_id = form.cleaned_data["visit_id"]

        try:
            MatchingService.confirm_row(row, visit_id, self.store, request=request)
        except BusinessError as e:
            # エラーメッセージをトーストで表示し、行はそのまま残す
            message = ERROR_MESSAGES.get(e.business_code, "確定に失敗しました")
            response = HttpResponse(status=422)
            response["HX-Trigger"] = (
                '{"showToast": {"message": "' + message + '", "type": "error"}}'
            )
            response["HX-Reswap"] = "none"
            return response

        # 成功: 行を空にして一覧から消す + トースト
        response = HttpResponse("")
        response["HX-Trigger"] = '{"showToast": {"message": "確定しました", "type": "success"}}'
        return response
```

**confirm 成功時の挙動**: 空の HTML を返し、`hx-swap="outerHTML"` により行要素がDOMから消える。トースト「確定しました」を表示する。

**エラー時の挙動**: 422 + `HX-Reswap: none` で DOM を変更せず、トーストでエラーメッセージを表示する。`base.html` の `htmx:beforeSwap` が 422 を swap 許可しているが、`HX-Reswap: none` で上書きして DOM 変更を抑止する。

**PATCH body パース**: US-02, US-03 と同じく `QueryDict(request.body)` で手動パースする。

### 6.4 MatchingRejectView

```python
# ui/staff/views/matching.py に追記

class MatchingRejectView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, View):
    """HTMX PATCH: 明細を却下する。"""
    login_url = "/s/login/"

    def patch(self, request, row_id):
        from core.models import CsvImportRow

        row = get_object_or_404(
            CsvImportRow.objects.for_store(self.store),
            pk=row_id,
        )

        try:
            MatchingService.reject_row(row, self.store, request=request)
        except BusinessError as e:
            message = ERROR_MESSAGES.get(e.business_code, "却下に失敗しました")
            response = HttpResponse(status=422)
            response["HX-Trigger"] = (
                '{"showToast": {"message": "' + message + '", "type": "error"}}'
            )
            response["HX-Reswap"] = "none"
            return response

        # 成功: 行を空にして一覧から消す + トースト
        response = HttpResponse("")
        response["HX-Trigger"] = '{"showToast": {"message": "却下しました", "type": "success"}}'
        return response
```

**reject 操作にリクエストボディは不要**: reject はステータス遷移のみ。visit_id は不要なため Form も不要。

## 7. URL 設定

### ui/staff/urls.py（追記部分）

US-03 の既存 URL に 4 つの URL を追加する。

```python
# ui/staff/urls.py に追記（既存の US-03 URL の後に追加）

from ui.staff.views.matching import (
    MatchingView,
    MatchingCandidatesView,
    MatchingConfirmView,
    MatchingRejectView,
)

urlpatterns = [
    # ... US-01, US-02, US-03 の既存 URL ...

    # US-04 S1: マッチング一覧
    path("matching/", MatchingView.as_view(), name="matching"),

    # US-04 S1: 候補遅延ロード（HTMX GET）
    path("matching/<uuid:row_id>/candidates/", MatchingCandidatesView.as_view(), name="matching-candidates"),

    # US-04 S1: 候補確定（HTMX PATCH）
    path("matching/<uuid:row_id>/confirm/", MatchingConfirmView.as_view(), name="matching-confirm"),

    # US-04 S1: 明細却下（HTMX PATCH）
    path("matching/<uuid:row_id>/reject/", MatchingRejectView.as_view(), name="matching-reject"),
]
```

**URL パスの設計意図**:
- `/s/matching/`: マッチング一覧（当日の pending_review 行）
- `/s/matching/<row_id>/candidates/`: 候補一覧遅延ロード（HTMX GET）
- `/s/matching/<row_id>/confirm/`: 候補確定（HTMX PATCH）
- `/s/matching/<row_id>/reject/`: 明細却下（HTMX PATCH）

**コア層 API エンドポイントとの関係**: コア層は `/api/v1/imports/csv/:id/rows/:row_id/candidates/` と `/api/v1/imports/csv/:id/rows/:row_id/` を提供する。UI は Service 層を直接呼び出すため、コア層の API エンドポイントは使用しない。URL パスはスタッフ UI の慣例（`/s/` プレフィックス）に従う。

## 8. テストケース

### 8.1 Django TestClient

#### マッチング一覧画面

| # | テスト | 検証内容 |
|---|--------|---------|
| 1 | `test_matching_list_get` | GET `/s/matching/` → 200。`matching.html` 使用 |
| 2 | `test_matching_list_requires_auth` | 未認証で GET → 302 `/s/login/` |
| 3 | `test_matching_list_active_tab` | context に `active_tab == "matching"` |
| 4 | `test_matching_list_shows_pending_review_only` | `pending_review` の行のみ表示。`validated`, `confirmed`, `rejected` は表示されない |
| 5 | `test_matching_list_today_only` | 当日の行のみ表示。昨日の `pending_review` 行は表示されない |
| 5a | `test_matching_list_uses_timezone_localdate` | `timezone.localdate()` を使用して当日判定していることを検証（`freeze_time` で日付境界をテスト。23:59 と 00:00 で結果が変わることを確認） |
| 6 | `test_matching_list_empty_message` | `pending_review` 行が 0 件の場合、「マッチ待ちの明細はありません」が表示される |
| 7 | `test_matching_list_displays_receipt_no` | レスポンスにレシート番号が含まれる |
| 8 | `test_matching_list_displays_csv_customer_name` | CSV 顧客名がある行で、顧客名が表示される |
| 9 | `test_matching_list_no_csv_customer_name` | CSV 顧客名がない行で、顧客名セクションが表示されない |
| 10 | `test_matching_list_store_scope` | 他店舗の `pending_review` 行は表示されない |
| 11 | `test_matching_list_order_by_receipt_no` | 行が `receipt_no` 昇順で表示される |

#### 候補遅延ロード

| # | テスト | 検証内容 |
|---|--------|---------|
| 12 | `test_candidates_get` | GET `/s/matching/<row_id>/candidates/` → 200。`_matching_candidates.html` 使用 |
| 13 | `test_candidates_requires_auth` | 未認証で GET → 302 `/s/login/` |
| 14 | `test_candidates_store_scope` | 他店舗の row_id → 404 |
| 15 | `test_candidates_nonexistent_row` | 存在しない row_id → 404 |
| 16 | `test_candidates_displays_customer_name` | 候補の顧客名が表示される |
| 17 | `test_candidates_displays_visited_at` | 候補の来店日時が表示される |
| 18 | `test_candidates_displays_match_score` | `name_match_score` が 1.0 の候補に「完全一致」、0.5 の候補に「部分一致」が表示される |
| 19 | `test_candidates_not_pending_review_validated` | `validated` ステータスの行で GET → 400。レスポンス本文に「候補を取得できません」を含む。`HX-Trigger` ヘッダーが付与されない |
| 19a | `test_candidates_not_pending_review_confirmed` | `confirmed` ステータスの行で GET → 400。レスポンス本文に「候補を取得できません」を含む。`HX-Trigger` ヘッダーが付与されない |
| 19b | `test_candidates_not_pending_review_rejected` | `rejected` ステータスの行で GET → 400。レスポンス本文に「候補を取得できません」を含む。`HX-Trigger` ヘッダーが付与されない |
| 20 | `test_candidates_has_confirm_button` | 各候補に確定ボタン（`hx-patch` 付き）が含まれる |
| 21 | `test_candidates_has_reject_button` | 却下ボタンが含まれる |
| 22 | `test_candidates_empty` | 候補 0 件の場合、「候補が見つかりませんでした」メッセージと却下ボタンが表示される |
| 23 | `test_candidates_row_id_in_context` | レスポンスに `row_id` が含まれる（HTMX ターゲット用） |
| 23a | `test_candidates_sort_order` | 候補が `name_match_score` 降順で表示される。MatchingService を mock し、score=1.0, 0.5, 0.0 の 3 候補を返す → レスポンス HTML で顧客名の出現順が score 降順であることを検証 |
| 23b | `test_candidates_flat_mapping` | View が C-06 のネスト構造 `{customer{id, name}}` をテンプレート用に flat 化（`customer_name`, `customer_id`）していることを検証 |

#### 候補確定（confirm）

| # | テスト | 検証内容 |
|---|--------|---------|
| 24 | `test_confirm_patch` | PATCH `/s/matching/<row_id>/confirm/` with visit_id → 200。CsvImportRow.status == 'confirmed' |
| 25 | `test_confirm_requires_auth` | 未認証で PATCH → 302 `/s/login/` |
| 26 | `test_confirm_store_scope` | 他店舗の row_id → 404 |
| 27 | `test_confirm_nonexistent_row` | 存在しない row_id → 404 |
| 28 | `test_confirm_invalid_visit_id` | PATCH with visit_id="invalid" → 400 「無効なリクエストです」 |
| 29 | `test_confirm_missing_visit_id` | PATCH without visit_id → 400 「無効なリクエストです」 |
| 30 | `test_confirm_visit_not_in_candidates` | MatchingService が `import.visit_not_in_candidates` を raise → 422 + トースト「選択した候補は無効です。再読み込みしてください」 |
| 31 | `test_confirm_row_not_pending` | MatchingService が `import.row_not_pending` を raise → 422 + トースト「この明細は既に処理されています」 |
| 32 | `test_confirm_row_conflict` | MatchingService が `import.row_conflict` を raise → 422 + トースト「他のスタッフが先に処理しました」 |
| 32a | `test_confirm_row_already_processed` | MatchingService が `import.row_already_processed` を raise → 422 + トースト「この明細は既に処理されています」 |
| 32b | `test_confirm_direct_confirm_reject` | MatchingService が `import.direct_confirm_reject` を raise → 422 + トースト「この明細はまだマッチング未実行です」 |
| 33 | `test_confirm_success_removes_row` | 成功時のレスポンス body が空（行がDOMから消える） |
| 34 | `test_confirm_success_toast` | 成功時に `HX-Trigger` ヘッダーに `showToast` イベント（message: "確定しました"）が含まれる |
| 35 | `test_confirm_error_no_dom_change` | エラー時に `HX-Reswap: none` ヘッダーが含まれる（DOM 変更抑止） |
| 36 | `test_confirm_patch_body_parsing` | PATCH with form-encoded body (`visit_id=<uuid>`) → `QueryDict(request.body)` で正しくパースされる |

#### 明細却下（reject）

| # | テスト | 検証内容 |
|---|--------|---------|
| 37 | `test_reject_patch` | PATCH `/s/matching/<row_id>/reject/` → 200。CsvImportRow.status == 'rejected' |
| 38 | `test_reject_requires_auth` | 未認証で PATCH → 302 `/s/login/` |
| 39 | `test_reject_store_scope` | 他店舗の row_id → 404 |
| 40 | `test_reject_nonexistent_row` | 存在しない row_id → 404 |
| 41 | `test_reject_row_not_pending` | MatchingService が `import.row_not_pending` を raise → 422 + トースト |
| 42 | `test_reject_row_conflict` | MatchingService が `import.row_conflict` を raise → 422 + トースト |
| 42a | `test_reject_row_already_processed` | MatchingService が `import.row_already_processed` を raise → 422 + トースト |
| 42b | `test_reject_direct_confirm_reject` | MatchingService が `import.direct_confirm_reject` を raise → 422 + トースト |
| 43 | `test_reject_success_removes_row` | 成功時のレスポンス body が空 |
| 44 | `test_reject_success_toast` | 成功時に `HX-Trigger` ヘッダーに `showToast` イベント（message: "却下しました"）が含まれる |
| 45 | `test_reject_error_no_dom_change` | エラー時に `HX-Reswap: none` ヘッダーが含まれる |

#### BottomTab

| # | テスト | 検証内容 |
|---|--------|---------|
| 46 | `test_matching_tab_is_link` | `/s/matching/` のレスポンスに `href="/s/matching/"` の `<a>` タグが含まれる（disabled ではない） |
| 47 | `test_matching_tab_active_on_matching_page` | `/s/matching/` で「マッチング」タブがアクティブスタイル |
| 48 | `test_matching_tab_inactive_on_other_pages` | `/s/customers/` で「マッチング」タブが非アクティブ |

### 8.2 Browser smoke test

| # | 対象 URL | 手順 | 期待結果 |
|---|---------|------|---------|
| 1 | `/s/matching/` | 認証済みでアクセス（当日 pending_review 行あり） | pending_review の明細一覧が表示される。営業日、レシート番号、CSV 顧客名が見える |
| 2 | `/s/matching/` | 認証済みでアクセス（当日 pending_review 行なし） | 「マッチ待ちの明細はありません」が表示される |
| 3 | (一覧画面) | 行をタップ | 行が展開し、「候補を読み込み中...」→ 候補一覧がロードされる |
| 4 | (展開行) | 候補の「確定」ボタンをタップ | 行がスライドアウトして消える。トースト「確定しました」が表示される |
| 5 | (展開行) | 「この明細を却下」ボタンをタップ | 行が消える。トースト「却下しました」が表示される |
| 6 | (展開行) | 別タブで同じ行を先に確定した後、元タブで「確定」タップ | トースト「他のスタッフが先に処理しました」が表示される。行は残る |
| 7 | (各画面) | BottomTab 確認 | 「マッチング」タブがアクティブ。「来店記録」タブは disabled のまま |
| 8 | `/s/customers/` | BottomTab 確認 | 「マッチング」タブがリンクとして存在（disabled ではない） |

## 9. Gherkin シナリオ

```gherkin
Feature: 会計後マッチング（US-04 S1）

  Scenario: 当日の pending_review 一覧表示
    Given 認証済みスタッフとしてログインしている
    And 当日の business_date で status="pending_review" の CsvImportRow が 3 件ある
    When /s/matching/ にアクセスする
    Then 3 件の明細が一覧に表示される
    And 各行にレシート番号と営業日が表示される

  Scenario: pending_review 以外の行は表示されない
    Given 当日の CsvImportRow が status="validated" で 2 件、status="pending_review" で 1 件ある
    When /s/matching/ にアクセスする
    Then pending_review の 1 件のみ表示される

  Scenario: 当日以外の行は表示されない
    Given 昨日の business_date で status="pending_review" の CsvImportRow が 1 件ある
    And 当日の pending_review 行が 0 件ある
    When /s/matching/ にアクセスする
    Then 「マッチ待ちの明細はありません」が表示される

  Scenario: 空の一覧表示
    Given 当日の pending_review 行が 0 件ある
    When /s/matching/ にアクセスする
    Then 「マッチ待ちの明細はありません」が表示される

  Scenario: 行タップで候補遅延ロード
    Given pending_review の行が 1 件表示されている
    And 同日の来店記録が 3 件ある
    When 行をタップする
    Then 行が展開され、候補一覧が HTMX でロードされる
    And 3 件の候補が name_match_score 降順で表示される

  Scenario: 候補確定
    Given 展開された行に候補が 2 件表示されている
    When 候補 A の「確定」ボタンをタップする
    Then HTMX PATCH が送信される
    And 行が一覧から消える
    And トースト「確定しました」が表示される
    And CsvImportRow の status が "confirmed" になる

  Scenario: 明細却下
    Given 展開された行に候補が 2 件表示されている
    When 「この明細を却下」ボタンをタップする
    Then HTMX PATCH が送信される
    And 行が一覧から消える
    And トースト「却下しました」が表示される
    And CsvImportRow の status が "rejected" になる

  Scenario: 同時操作の競合
    Given 展開された行に候補が表示されている
    And 別のスタッフが同じ行を先に確定した
    When 候補の「確定」ボタンをタップする
    Then トースト「他のスタッフが先に処理しました」が表示される
    And 行はそのまま残る

  Scenario: BottomTab マッチングタブがアクティブ
    Given 認証済みスタッフとしてログインしている
    When /s/matching/ にアクセスする
    Then BottomTab の「マッチング」タブがアクティブ状態
    And 「マッチング」タブは <a> リンク（disabled ではない）

  Scenario: ストアスコープ
    Given スタッフ A が店舗 X にログインしている
    And 店舗 Y に pending_review の行がある
    When /s/matching/ にアクセスする
    Then 店舗 Y の行は表示されない

  Scenario: 未認証アクセスはリダイレクト
    Given 未認証の状態
    When /s/matching/ にアクセスする
    Then /s/login/ にリダイレクトされる
```

## 10. Closure Audit チェックリスト

- US-01 S1 → US-04 S1: `base_staff.html` の BottomTab に「マッチング」タブが `<a>` リンクとして存在するか
- US-01 S1 → US-04 S1: `LoginRequiredMixin`, `StaffRequiredMixin`, `StoreMixin` が全 View で正しく適用されているか
- C-06 → US-04 S1: `CsvImportRow.objects.for_store(store)` が正しくストアスコープを適用しているか
- C-06 → US-04 S1: `MatchingService.get_candidates(row, self.store)` の返り値が candidates テンプレートで正しく描画されるか
- C-06 → US-04 S1: `MatchingService.confirm_row(row, visit_id, store, request)` のエラーコードが View の ERROR_MESSAGES マッピングで網羅されているか
- C-06 → US-04 S1: `MatchingService.reject_row(row, store, request)` のエラーコードが View の ERROR_MESSAGES マッピングで網羅されているか
- confirm/reject のトースト表示が `base_staff.html` の Toast コンポーネントと連携するか
- HTMX CSRF 自動付与（`base.html` の `htmx:configRequest`）が PATCH リクエストに適用されるか
- 422 swap 許可（`base.html` の `htmx:beforeSwap`）+ `HX-Reswap: none` によるエラー時の DOM 変更抑止が正しく動作するか
- `pending_review` 以外のステータスの行が一覧に表示されないか
- 当日以外の `pending_review` 行が表示されないか
- confirmed/rejected 後に行が一覧から消えるか

## Review Log

- [2026-03-31] 初版作成
- [2026-03-31] Codex 1回目レビュー (gpt-5.4): 76/100 FAIL。4 件を修正
  - F-01 (high): 候補テンプレートが C-06 の `get_candidates()` 返り値構造 `{customer{id, name}}` と不整合。View で flat 化（`customer_name`, `customer_id`）する変換層を追加
  - F-02 (high): `loaded` フラグで候補再取得を抑止していた問題。C-06 の「毎回再計算」要件に従い、展開のたびに HTMX GET で候補を再取得するように変更
  - F-03 (medium): 候補ソート順（`name_match_score` 降順）を検証するテストが不在。テスト 23a, 23b を追加
  - F-04 (low): ファイル構成の URL 数記載「3 URL」→「4 URL」に修正
- [2026-03-31] Codex 2回目レビュー (gpt-5.4): 88/100 FAIL。2 件を修正
  - F-05 (high): confirm/reject のエラー契約が C-06 と不整合。C-06 の全 BusinessError コード（`import.row_already_processed`, `import.direct_confirm_reject`）を ERROR_MESSAGES に追加。UI は Service 直接呼び出しのため全 BusinessError を 422 + トーストで処理する方針を明記。テスト 32a, 32b, 42a, 42b 追加
  - F-06 (medium): candidates の status ガードテストが `validated` のみ。`confirmed`, `rejected` のテスト 19a, 19b を追加
- [2026-03-31] Codex 3回目レビュー (gpt-5.4): 94/100 FAIL。2 件を修正
  - F-07 (high): MatchingService 契約表の例外に `import.row_already_processed`, `import.direct_confirm_reject` が未記載。契約表を C-06 と一致させた
  - F-08 (medium): BusinessError の UI 方針が自己矛盾（「全て 422 + トースト」と言いつつ candidates は 400 テキスト）。View 種別ごとの方針を明記し、candidates_not_available の扱いを防御コードとして整理
- [2026-03-31] Codex 4回目レビュー (gpt-5.4): 97/100 FAIL。2 件を修正
  - F-09 (medium): 当日判定が `date.today()` でタイムゾーン境界問題。`timezone.localdate()` に変更し、日付境界テスト 5a を追加
  - F-10 (medium): candidates の 400 防御コードテストがレスポンス本文と HX-Trigger 非付与を検証していない。テスト 19, 19a, 19b を強化
- [2026-03-31] Codex 5回目レビュー (gpt-5.4): **100/100 PASS**
- [2026-04-01] orchestrator 再設計依頼（Issue #21 経由）: コア層実態との乖離修正
  - R-01 (high): `MatchingService` メソッド名・シグネチャを実態に合わせて修正: `confirm_match` → `confirm_row(row, visit_id, store, request=None)`, `reject_match` → `reject_row(row, store, request=None)`, `get_candidates(row)` → `get_candidates(row, store)`
  - R-02 (high): `BusinessError` 属性アクセスを `.business_code` / `.detail` に修正（`.code` は `.business_code`、フォールバックは `.detail`）
  - R-03 (medium): Closure audit チェックリストの MatchingService メソッド名を更新
