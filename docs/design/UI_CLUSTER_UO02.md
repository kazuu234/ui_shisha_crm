# UO-02 詳細設計書: 顧客管理（Owner UI）

> 基本設計書: `docs/design/UI_BASIC_DESIGN.md` §6 UO-02, §7.6
> デザインガイド: `docs/design/UI_DESIGN_GUIDE.md`
> パイプライン: `docs/design/UI_PIPELINE.md` #8

## 1. 概要

### Slice 情報

| 項目 | 内容 |
|------|------|
| **Cluster** | UO-02 (顧客管理) |
| **Slice** | S1（単一 Slice で完結） |
| **パイプライン順序** | #8 / 13 |
| **ブランチ説明部** | `uo02-customer-mgmt` |

### スコープ

顧客一覧画面（フィルタ・ソート・検索・ページネーション）、顧客詳細画面（全属性 + 来店履歴 + 未消化タスク）、顧客編集画面（Django ModelForm による全フィールド編集）。3 画面は典型的な CRUD であり、1 Slice で完結する。

### precondition

- UO-01 S1 完了（`base_owner.html`、`OwnerRequiredMixin`、`StoreMixin` が動作）
- コア層 C-03 完了（Customer モデル + `CustomerService` が動作）
- コア層 C-05a 完了（`HearingTaskService.sync_tasks()` が動作。顧客編集時のタスク同期に必要）
- コア層 C-05b 完了（`HearingTask` の表示クエリが動作。顧客詳細に未消化タスクを表示するため）

### postcondition

- `/o/customers/` でフィルタ・ソート・検索・ページネーション付きの顧客一覧テーブルが表示される
- テーブル列: 名前（ソート・検索）、セグメント（バッジ・フィルタ）、来店回数（ソート）、最終来店日（ソート、Subquery）、未消化タスク数（annotate Count）
- HTMX でフィルタ・ソート・ページ切替時にテーブル本体のみ差し替え（`hx-push-url="true"` でブラウザ履歴に反映）
- 25 件/ページのページネーション（Django Paginator）
- `/o/customers/<id>/` で全属性 + 来店履歴テーブル + 未消化タスク一覧が表示される
- `/o/customers/<id>/edit/` で Django ModelForm による全フィールド編集 → `CustomerService.update_customer()` → ヒアリング対象項目変更時は `HearingTaskService.sync_tasks(customer)` → 成功: 顧客詳細にリダイレクト + トースト
- nullable フィールド（age, area, shisha_experience, line_id, memo）の空文字列は None に正規化する（strip 後に判定）
- Sidebar の「顧客管理」がアクティブ状態（`active_sidebar = "customers"`）
- 全 View が `LoginRequiredMixin, OwnerRequiredMixin, StoreMixin` を使用

## 2. ファイル構成

```
ui/
├── owner/
│   ├── views/
│   │   └── customer.py              # CustomerListView, CustomerDetailView, CustomerEditView
│   ├── forms/
│   │   └── customer.py              # CustomerEditForm (ModelForm)
│   └── urls.py                      # customers/ 関連 URL を追記
├── templates/ui/
│   └── owner/
│       ├── customer_list.html       # 顧客一覧画面（フィルタバー + テーブル + ページネーション）
│       ├── _customer_table.html     # テーブル本体フラグメント（HTMX 差し替え対象）
│       ├── customer_detail.html     # 顧客詳細画面
│       └── customer_edit.html       # 顧客編集画面
```

**追加するアイコン**: なし（UO-01 S1 で作成済みのアイコンで足りる）。

## 3. コア層契約

正式な定義は `docs/reference/cluster/C03_CUSTOMER.md`、`docs/reference/cluster/C04_VISIT_SEGMENT.md`、`docs/reference/cluster/C05A_HEARING_TASK_CORE.md`、`docs/reference/cluster/C05B_HEARING_TASK_DISPLAY.md` を参照。

**import パスについて**: コア層は別リポジトリ（別 Django app）として管理されている場合がある。本設計書では `from core.services.customer import CustomerService` のような統一的な記法を使用するが、実際の import パスはコア層のパッケージ構造に依存する。実装時にコア層の `__init__.py` や実際のモジュール配置を確認すること。

### Customer モデル直接操作（CustomerService.update_customer 不使用）

> **注意**: コア層に `CustomerService.update_customer()` は存在しない。
> 顧客情報の更新は Django ModelForm の `form.save()` で直接行う。

| 操作 | 方法 | 備考 |
|------|------|------|
| 更新 | `form.save()` （ModelForm） | `name`, `age`, `area`, `shisha_experience`, `line_id`, `memo` を編集可 |

**更新後の sync_tasks 呼び出し**: ヒアリング対象フィールド（`age`, `area`, `shisha_experience`）が変更された場合、View 側で `HearingTaskService.sync_tasks(customer)` を明示的に呼ぶ必要がある（§4.4 参照）。

### HearingTaskService

| メソッド | 引数 | 返り値 | 備考 |
|---------|------|--------|------|
| `sync_tasks(customer)` | `Customer` | `{'closed_count': int, 'created_tasks': list[HearingTask]}` | auto_close → generate の順に実行。ヒアリング対象フィールド変更時に呼ぶ |

**ヒアリング対象フィールド（sync_tasks トリガー対象）**: `age`, `area`, `shisha_experience`。これら以外のフィールド（`name`, `line_id`, `memo`）の変更では sync_tasks を呼ばない。

### Customer モデル（UI が参照するフィールド）

| フィールド | 型 | 備考 |
|-----------|-----|------|
| `name` | CharField | 表示名。必須 |
| `segment` | CharField (`new` / `repeat` / `regular`) | セグメントバッジ表示に使用 |
| `visit_count` | PositiveIntegerField | 来店回数（非正規化。read-only） |
| `age` | IntegerField (nullable) | ヒアリング対象。整数値（C-03 契約準拠: `age?: int`） |
| `area` | CharField (nullable) | ヒアリング対象。テキスト入力 |
| `shisha_experience` | CharField (nullable) | ヒアリング対象。選択肢: `none`, `beginner`, `intermediate`, `advanced` |
| `line_id` | CharField (nullable) | LINE ID |
| `memo` | TextField (nullable) | 顧客メモ |
| `store` | ForeignKey(Store) | 店舗スコープ |
| `created_at` | DateTimeField | 作成日時 |
| `updated_at` | DateTimeField | 更新日時 |

**StoreScopedManager**: `Customer.objects.for_store(store)` でストアスコープフィルタを適用。

### Visit モデル（UI が参照するフィールド）

| フィールド | 型 | 備考 |
|-----------|-----|------|
| `customer` | ForeignKey(Customer) | 対象顧客 |
| `staff` | ForeignKey(Staff) | 対応スタッフ |
| `visited_at` | DateField | 来店日 |
| `conversation_memo` | TextField (nullable) | 会話メモ |
| `created_at` | DateTimeField (auto_now_add) | 作成日時 |

**StoreScopedManager**: `Visit.objects.for_store(store)` でストアスコープフィルタを適用。

### HearingTask モデル（UI が参照するフィールド）

| フィールド | 型 | 備考 |
|-----------|-----|------|
| `customer` | ForeignKey(Customer) | 対象顧客 |
| `field_name` | CharField | ヒアリング対象フィールド名 (`age`, `area`, `shisha_experience`) |
| `status` | CharField (`open` / `closed`) | タスク状態 |
| `created_at` | DateTimeField | 作成日時 |

**StoreScopedManager**: `HearingTask.objects.for_store(store)` でストアスコープフィルタを適用。

### フィールドラベルマッピング

顧客詳細のタスク表示で使用する。

```python
HEARING_FIELD_LABELS = {
    "age": "年齢",
    "area": "居住エリア",
    "shisha_experience": "シーシャ歴",
}
```

### shisha_experience 選択肢

顧客詳細の表示と編集フォームで使用する。

```python
SHISHA_EXPERIENCE_CHOICES = [
    ("none", "なし"),
    ("beginner", "初心者"),
    ("intermediate", "中級"),
    ("advanced", "上級"),
]

SHISHA_EXPERIENCE_DISPLAY = dict(SHISHA_EXPERIENCE_CHOICES)
```

## 4. View 定義

### 4.1 CustomerListView

```python
# ui/owner/views/customer.py

from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Count, F, Q, Subquery, OuterRef
from django.template.response import TemplateResponse

from ui.mixins import OwnerRequiredMixin, StoreMixin
from customers.models import Customer
from visits.models import Visit
from tasks.models import HearingTask

HEARING_FIELD_LABELS = {
    "age": "年齢",
    "area": "居住エリア",
    "shisha_experience": "シーシャ歴",
}

SHISHA_EXPERIENCE_CHOICES = [
    ("none", "なし"),
    ("beginner", "初心者"),
    ("intermediate", "中級"),
    ("advanced", "上級"),
]

SHISHA_EXPERIENCE_DISPLAY = dict(SHISHA_EXPERIENCE_CHOICES)

# ソート許可フィールド（ホワイトリスト）
# last_visited_at は null 許容のため F() + nulls_last/nulls_first で未来店顧客を末尾に送る
ALLOWED_SORT_FIELDS = {
    "name": F("name").asc(),
    "-name": F("name").desc(),
    "visit_count": F("visit_count").asc(),
    "-visit_count": F("visit_count").desc(),
    "last_visited_at": F("last_visited_at").asc(nulls_last=True),
    "-last_visited_at": F("last_visited_at").desc(nulls_last=True),
}
DEFAULT_SORT = "-last_visited_at"

# セグメント許可値
ALLOWED_SEGMENTS = {"new", "repeat", "regular"}


class CustomerListView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, ListView):
    template_name = "ui/owner/customer_list.html"
    context_object_name = "customers"
    paginate_by = 25
    login_url = "/o/login/"

    def get_queryset(self):
        qs = Customer.objects.for_store(self.store)

        # 検索（名前部分一致）
        search = self.request.GET.get("search", "").strip()
        if search:
            qs = qs.filter(name__icontains=search)

        # セグメントフィルタ
        segment = self.request.GET.get("segment", "").strip()
        if segment in ALLOWED_SEGMENTS:
            qs = qs.filter(segment=segment)

        # 最終来店日を Subquery でアノテーション
        latest_visit = Visit.objects.filter(
            customer=OuterRef("pk"),
            is_deleted=False,
        ).order_by("-visited_at").values("visited_at")[:1]
        qs = qs.annotate(last_visited_at=Subquery(latest_visit))

        # 未消化タスク数をアノテーション
        # HearingTask.customer FK の related_name は "hearing_tasks"（コア層 tasks/models.py で確認済み）
        qs = qs.annotate(
            open_task_count=Count(
                "hearing_tasks",
                filter=Q(hearing_tasks__status="open"),
            )
        )

        # ソート（F() 式で nulls_last を制御）
        sort = self.request.GET.get("sort", DEFAULT_SORT).strip()
        if sort in ALLOWED_SORT_FIELDS:
            order_expr = ALLOWED_SORT_FIELDS[sort]
        else:
            order_expr = ALLOWED_SORT_FIELDS[DEFAULT_SORT]
        qs = qs.order_by(order_expr, "pk")  # pk で安定ソート

        return qs

    def get_template_names(self):
        # HTMX リクエスト時はテーブルフラグメントのみ返す
        if self.request.headers.get("HX-Request") == "true":
            return ["ui/owner/_customer_table.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_sidebar"] = "customers"

        # 検索文字列を正規化（前後空白を strip。queryset の search と一致させる）
        context["current_search"] = self.request.GET.get("search", "").strip()

        # セグメントをホワイトリストで正規化（不正値 → 空文字列）
        raw_segment = self.request.GET.get("segment", "").strip()
        context["current_segment"] = raw_segment if raw_segment in ALLOWED_SEGMENTS else ""

        # ソートをホワイトリストで正規化（不正値 → DEFAULT_SORT）
        raw_sort = self.request.GET.get("sort", DEFAULT_SORT).strip()
        context["current_sort"] = raw_sort if raw_sort in ALLOWED_SORT_FIELDS else DEFAULT_SORT

        context["segment_choices"] = [
            ("", "全て"),
            ("new", "新規"),
            ("repeat", "リピート"),
            ("regular", "常連"),
        ]
        return context
```

**ソートのホワイトリスト制御**: ユーザー入力のソートフィールドを直接 `order_by()` に渡さない。`ALLOWED_SORT_FIELDS` に定義された `F()` 式のみ許可し、未知の値はデフォルト（`-last_visited_at`）にフォールバックする。`last_visited_at` カラムは null 許容（来店記録がない顧客）のため、`nulls_last=True` を指定して未来店顧客を常にソート末尾に送る（US-02 と同一パターン）。

**HTMX リクエスト判定**: `HX-Request` ヘッダーの有無で返すテンプレートを切り替える。フィルタ・ソート・ページ切替はすべて `hx-get` で `_customer_table.html` フラグメント（フィルタバー + テーブル + ページネーションを含む）のみを返す。フラグメントにフィルタバーを含めることで、HTMX 差し替え後もフィルタ・ソートの状態が常にサーバーレスポンスで最新化される。

**Subquery の `is_deleted=False`**: Visit モデルは SoftDeleteMixin を継承しており、論理削除された来店記録を最終来店日の算出から除外する。

### 4.2 CustomerDetailView

```python
from django.views.generic import DetailView
from django.shortcuts import get_object_or_404


class CustomerDetailView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, DetailView):
    template_name = "ui/owner/customer_detail.html"
    context_object_name = "customer"
    login_url = "/o/login/"

    def get_object(self):
        return get_object_or_404(
            Customer.objects.for_store(self.store),
            pk=self.kwargs["pk"],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer = self.object

        # 来店履歴（スタッフ情報を select_related で N+1 回避）
        context["visits"] = (
            Visit.objects.for_store(self.store)
            .filter(customer=customer)
            .select_related("staff")
            .order_by("-visited_at", "-created_at")
        )

        # 未消化タスク一覧（status='open' のみ）
        open_tasks = (
            HearingTask.objects.for_store(self.store)
            .filter(customer=customer, status="open")
            .order_by("created_at")
        )
        # field_label を付与
        context["open_tasks"] = [
            {
                "field_name": task.field_name,
                "field_label": HEARING_FIELD_LABELS.get(task.field_name, task.field_name),
                "created_at": task.created_at,
            }
            for task in open_tasks
        ]

        # shisha_experience の日本語ラベルを解決して渡す
        context["shisha_experience_label"] = (
            SHISHA_EXPERIENCE_DISPLAY.get(customer.shisha_experience)
            if customer.shisha_experience
            else None
        )

        # トーストをセッションから取り出し（表示後に削除）
        toast = self.request.session.pop("toast", None)
        if toast:
            context["toast"] = toast

        context["active_sidebar"] = "customers"
        return context
```

### 4.3 CustomerEditForm

```python
# ui/owner/forms/customer.py

from django import forms
from customers.models import Customer

SHISHA_EXPERIENCE_CHOICES = [
    ("", "---"),  # 未選択（nullable を表現）
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
            "name": forms.TextInput(attrs={"placeholder": "顧客の名前"}),
            "age": forms.NumberInput(attrs={"placeholder": "例: 25", "min": 0}),
            "area": forms.TextInput(attrs={"placeholder": "例: 渋谷"}),
            "shisha_experience": forms.Select(choices=SHISHA_EXPERIENCE_CHOICES),
            "line_id": forms.TextInput(attrs={"placeholder": "LINE ID"}),
            "memo": forms.Textarea(attrs={"placeholder": "顧客メモ", "rows": 4}),
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

    def clean_age(self):
        """age は IntegerField(nullable)。空文字列 → None に正規化。"""
        age = self.cleaned_data.get("age")
        return age  # NumberInput は空 → None を自動処理

    def clean_area(self):
        """空文字列 → None に正規化（strip 後に判定）。"""
        area = self.cleaned_data.get("area")
        if area is not None:
            area = area.strip()
        return area or None

    def clean_shisha_experience(self):
        """空文字列 → None に正規化。"""
        exp = self.cleaned_data.get("shisha_experience")
        if exp is not None:
            exp = exp.strip()
        return exp or None

    def clean_line_id(self):
        """空文字列 → None に正規化（strip 後に判定）。"""
        line_id = self.cleaned_data.get("line_id")
        if line_id is not None:
            line_id = line_id.strip()
        return line_id or None

    def clean_memo(self):
        """空文字列 → None に正規化（strip 後に判定）。"""
        memo = self.cleaned_data.get("memo")
        if memo is not None:
            memo = memo.strip()
        return memo or None
```

**空文字列 → None 正規化**: C-03 契約では nullable フィールドの型は `int?` / `string?` であり、空文字列は「未入力」を意味する。Django の form は空文字列を送信するため、clean メソッドで strip → 空文字列を None に変換する。これにより `HearingTaskService.sync_tasks()` のトリガー判定（null vs non-null）が正しく動作する。

### 4.4 CustomerEditView

```python
from django.views import View
from django.shortcuts import get_object_or_404, redirect, render

from core.services.hearing_task import HearingTaskService
from ui.owner.forms.customer import CustomerEditForm

# ヒアリング対象フィールド（sync_tasks トリガー対象）
HEARING_FIELDS = {"age", "area", "shisha_experience"}


class CustomerEditView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    template_name = "ui/owner/customer_edit.html"
    login_url = "/o/login/"

    def _get_customer(self):
        return get_object_or_404(
            Customer.objects.for_store(self.store),
            pk=self.kwargs["pk"],
        )

    def get(self, request, pk):
        customer = self._get_customer()
        form = CustomerEditForm(instance=customer)
        return render(request, self.template_name, {
            "form": form,
            "customer": customer,
            "active_sidebar": "customers",
        })

    def post(self, request, pk):
        customer = self._get_customer()
        form = CustomerEditForm(request.POST, instance=customer)
        if not form.is_valid():
            return render(request, self.template_name, {
                "form": form,
                "customer": customer,
                "active_sidebar": "customers",
            })

        # 変更前のヒアリング対象フィールドの値を記録
        old_hearing_values = {
            field: getattr(customer, field) for field in HEARING_FIELDS
        }

        # ModelForm.save() で直接更新（CustomerService 不使用）
        updated_customer = form.save()

        # ヒアリング対象フィールドが変更された場合のみ sync_tasks を呼ぶ
        new_hearing_values = {
            field: form.cleaned_data.get(field) for field in HEARING_FIELDS
        }
        if old_hearing_values != new_hearing_values:
            HearingTaskService.sync_tasks(updated_customer)

        # トースト用メッセージをセッションに保存
        request.session["toast"] = {
            "message": "顧客情報を更新しました",
            "type": "success",
        }

        return redirect(f"/o/customers/{customer.pk}/")
```

**ヒアリング対象フィールドの変更検知**: 更新前と更新後のヒアリング対象フィールドの値を比較し、変更がある場合のみ `sync_tasks()` を呼ぶ。これはコア層の `CustomerViewSet.perform_update()` と同一の責務を UI View で果たすもの（基本設計書 §6 O-CUSTOMER-EDIT に準拠）。

**CustomerService 不使用の理由**: コア層に `CustomerService.update_customer()` は存在しない。顧客情報の更新は ModelForm の `form.save()` で直接行う。バリデーションは Django form 層で完結する。

**トースト表示**: セッションに toast メッセージを保存し、リダイレクト先の詳細画面で表示・消去する。`CustomerDetailView.get_context_data()` で `self.request.session.pop("toast", None)` により取り出し後に自動削除。テンプレートは `base_owner.html` の `{% block toast %}` を使用する。

## 5. テンプレート

### 5.1 owner/customer_list.html

```
{% extends "ui/base_owner.html" %}
{% load static %}

{% block page_title %}顧客管理{% endblock %}

{% block content %}
  <div id="customer-list-container">
    {% include "ui/owner/_customer_table.html" %}
  </div>
{% endblock %}
```

**設計方針**: フィルタバー + テーブル + ページネーションを全て `_customer_table.html` フラグメントに含め、`#customer-list-container` ごと HTMX 差し替えする。これにより、ソート・検索・フィルタの各操作後にフィルタバーの状態（検索文字列、セグメント選択、現在のソート）が常にサーバーレスポンスで最新化される。ソート状態の非同期ずれ（hidden input の更新漏れ）を構造的に防止する。

### 5.2 owner/_customer_table.html（HTMX フラグメント）

フィルタバー + テーブル + ページネーションを含む。HTMX 差し替え時はこのフラグメント全体が `#customer-list-container` に差し込まれる。

```
{% load static %}

<!-- 
  フラグメント全体を 1 つの div で包み、共通属性を継承させる:
  - hx-target: 全操作で #customer-list-container ごと差し替え
  - hx-indicator: 全操作でスケルトンローダーを表示
  - hx-push-url: 全操作でブラウザ URL を更新
  
  パラメータ伝搬方式:
  - 検索・セグメント・ソートの各値は hidden input / input / select で保持
  - 全ての HTMX 発火元は hx-include="[name='search'],[name='segment'],[name='sort']" で
    フォーム要素から値を収集し、query string の手動組み立てを回避する
  - これにより検索語に & 等の予約文字が含まれても安全（HTMX が自動エンコード）
-->

<div hx-target="#customer-list-container"
     hx-indicator="#customer-table-loading"
     hx-push-url="true">

  <!-- フィルタバー -->
  <div>  <!-- flex items-center gap-4 mb-6 -->
    <!-- 検索 -->
    <input type="text"
           name="search"
           value="{{ current_search }}"
           placeholder="顧客名で検索"
           hx-get="/o/customers/"
           hx-trigger="input changed delay:300ms"
           hx-include="[name='segment'],[name='sort']" />

    <!-- セグメントフィルタ -->
    <select name="segment"
            hx-get="/o/customers/"
            hx-trigger="change"
            hx-include="[name='search'],[name='sort']">
      {% for value, label in segment_choices %}
        <option value="{{ value }}" {% if value == current_segment %}selected{% endif %}>{{ label }}</option>
      {% endfor %}
    </select>

    <!-- 選択中フィルタのチップ表示 + 個別解除（デザインガイド §テーブルフィルタ 準拠） -->
    <!--
      チップ解除リンクの設計:
      - 検索チップ解除: segment と sort を保持、search を送らない → hx-include で segment/sort のみ収集
      - セグメントチップ解除: search と sort を保持、segment を送らない → hx-include で search/sort のみ収集
      - hx-vals やテンプレート文字列連結は使わず、hx-include で既存の input/select から値を収集する
      - これにより検索語に特殊文字が含まれても安全（HTMX が自動エンコード）
    -->
    {% if current_search or current_segment %}
      <div>  <!-- flex items-center gap-2 -->
        {% if current_search %}
          <span class="chip-active">
            "{{ current_search }}"
            <a href="#"
               hx-get="/o/customers/"
               hx-include="[name='segment'],[name='sort']">&#x2715;</a>
          </span>
        {% endif %}
        {% if current_segment %}
          <span class="chip-active">
            {% if current_segment == "new" %}新規{% elif current_segment == "repeat" %}リピート{% elif current_segment == "regular" %}常連{% endif %}
            <a href="#"
               hx-get="/o/customers/"
               hx-include="[name='search'],[name='sort']">&#x2715;</a>
          </span>
        {% endif %}
        <!-- 全解除ボタン（検索 + セグメントの両方をクリア。sort のみ保持） -->
        <a href="#"
           hx-get="/o/customers/"
           hx-include="[name='sort']"
           class="btn-ghost text-sm">すべてクリア</a>
      </div>
    {% endif %}

    <!-- ソートの hidden input（フラグメント内に含めることで HTMX 差し替え後も最新化される） -->
    <input type="hidden" name="sort" value="{{ current_sort }}" />
    <!-- ページの hidden input（ソート変更やフィルタ変更時はページ 1 にリセット） -->
    <input type="hidden" name="page" value="{{ page_obj.number|default:1 }}" />
  </div>

  <!-- ローディング表示（HTMX リクエスト中のインジケーター。親 div の hx-indicator で全操作に適用） -->
  <div id="customer-table-loading" class="htmx-indicator">
    <!-- スケルトンローダー: bg-surface-alt のパルスアニメーション（デザインガイド §テーブルローディング 準拠） -->
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
             hx-get="/o/customers/"
             hx-vals='{"sort": "{% if current_sort == 'name' %}-name{% else %}name{% endif %}"}'
             hx-include="[name='search'],[name='segment']">
            名前
            {% if current_sort == "name" %}<span class="text-accent">▲</span>{% elif current_sort == "-name" %}<span class="text-accent">▼</span>{% else %}<span class="text-text-secondary">▲</span>{% endif %}
          </a>
        </th>
        <th>セグメント</th>
        <th>
          <a href="#"
             hx-get="/o/customers/"
             hx-vals='{"sort": "{% if current_sort == 'visit_count' %}-visit_count{% else %}visit_count{% endif %}"}'
             hx-include="[name='search'],[name='segment']">
            来店回数
            {% if current_sort == "visit_count" %}<span class="text-accent">▲</span>{% elif current_sort == "-visit_count" %}<span class="text-accent">▼</span>{% else %}<span class="text-text-secondary">▲</span>{% endif %}
          </a>
        </th>
        <th>
          <a href="#"
             hx-get="/o/customers/"
             hx-vals='{"sort": "{% if current_sort == 'last_visited_at' %}-last_visited_at{% else %}last_visited_at{% endif %}"}'
             hx-include="[name='search'],[name='segment']">
            最終来店日
            {% if current_sort == "last_visited_at" %}<span class="text-accent">▲</span>{% elif current_sort == "-last_visited_at" %}<span class="text-accent">▼</span>{% else %}<span class="text-text-secondary">▲</span>{% endif %}
          </a>
        </th>
        <th>未消化タスク</th>
      </tr>
    </thead>
    <tbody>
      {% for customer in customers %}
        <tr class="cursor-pointer hover:bg-accent-light" onclick="location.href='/o/customers/{{ customer.pk }}/'">
          <td>
            <a href="/o/customers/{{ customer.pk }}/">{{ customer.name }}</a>
          </td>
          <td>
            {% if customer.segment == "new" %}
              <span class="badge-new">新規</span>
            {% elif customer.segment == "repeat" %}
              <span class="badge-repeat">リピート</span>
            {% elif customer.segment == "regular" %}
              <span class="badge-regular">常連</span>
            {% endif %}
          </td>
          <td>{{ customer.visit_count }}</td>
          <td>
            {% if customer.last_visited_at %}
              {{ customer.last_visited_at|date:"Y/m/d" }}
            {% else %}
              <span class="text-text-muted">未来店</span>
            {% endif %}
          </td>
          <td>{{ customer.open_task_count }}</td>
        </tr>
      {% empty %}
        <tr>
          <td colspan="5">顧客がまだ登録されていません</td>
        </tr>
      {% endfor %}
    </tbody>
  </table>

  <!-- ページネーション -->
  {% if is_paginated %}
    <div>  <!-- flex items-center justify-center gap-4 mt-6 -->
      {% if page_obj.has_previous %}
        <a href="#"
           hx-get="/o/customers/"
           hx-vals='{"page": "{{ page_obj.previous_page_number }}"}'
           hx-include="[name='search'],[name='segment'],[name='sort']"
           class="btn-secondary">前へ</a>
      {% endif %}
      <span>{{ page_obj.number }} / {{ page_obj.paginator.num_pages }}</span>
      {% if page_obj.has_next %}
        <a href="#"
           hx-get="/o/customers/"
           hx-vals='{"page": "{{ page_obj.next_page_number }}"}'
           hx-include="[name='search'],[name='segment'],[name='sort']"
           class="btn-secondary">次へ</a>
      {% endif %}
    </div>
  {% endif %}

</div>
```

**セグメントバッジ**: デザインガイド §5 のバッジパターンに準拠。`badge-new`（`--accent-subtle` bg, `--accent` text）、`badge-repeat`（`--warning-subtle` bg, `--warning-dark` text）、`badge-regular`（`--success-subtle` bg, `--success` text）。

**空状態**: テーブルに顧客がない場合は `--text-secondary` の「顧客がまだ登録されていません」を表示（デザインガイド テーブル §空状態）。

**「未来店」表示**: `last_visited_at` が null（来店記録なし）の場合、`--text-muted` の「未来店」を表示。これは情報伝達に必須でないテキストであり、`--text-muted` の使用制限（デザインガイド §2）に適合する。

### 5.3 owner/customer_detail.html

```
{% extends "ui/base_owner.html" %}
{% load static %}

{% block page_title %}{{ customer.name }}{% endblock %}

{% block toast %}
  {% if toast %}
    <div x-data="{ show: true }"
         x-show="show"
         x-init="setTimeout(() => { show = false }, 3000)"
         x-transition
         class="toast-success">
      {{ toast.message }}
    </div>
  {% endif %}
{% endblock %}

{% block content %}
  <!-- 編集ボタン -->
  <div>  <!-- flex justify-end mb-4 -->
    <a href="/o/customers/{{ customer.pk }}/edit/" class="btn-primary">編集</a>
  </div>

  <!-- 基本情報 -->
  <section>
    <h2>基本情報</h2>
    <dl>
      <dt>名前</dt><dd>{{ customer.name }}</dd>
      <dt>セグメント</dt>
      <dd>
        {% if customer.segment == "new" %}
          <span class="badge-new">新規</span>
        {% elif customer.segment == "repeat" %}
          <span class="badge-repeat">リピート</span>
        {% elif customer.segment == "regular" %}
          <span class="badge-regular">常連</span>
        {% endif %}
      </dd>
      <dt>来店回数</dt><dd>{{ customer.visit_count }}回</dd>
      <dt>年齢</dt><dd>{% if customer.age is not None %}{{ customer.age }}歳{% else %}<span class="text-text-muted">未入力</span>{% endif %}</dd>
      <dt>居住エリア</dt><dd>{% if customer.area %}{{ customer.area }}{% else %}<span class="text-text-muted">未入力</span>{% endif %}</dd>
      <dt>シーシャ歴</dt><dd>{% if shisha_experience_label %}{{ shisha_experience_label }}{% else %}<span class="text-text-muted">未入力</span>{% endif %}</dd>
      <dt>LINE ID</dt><dd>{% if customer.line_id %}{{ customer.line_id }}{% else %}<span class="text-text-muted">未入力</span>{% endif %}</dd>
      <dt>メモ</dt><dd>{% if customer.memo %}{{ customer.memo|linebreaksbr }}{% else %}<span class="text-text-muted">未入力</span>{% endif %}</dd>
      <dt>作成日</dt><dd>{{ customer.created_at|date:"Y/m/d H:i" }}</dd>
      <dt>更新日</dt><dd>{{ customer.updated_at|date:"Y/m/d H:i" }}</dd>
    </dl>
  </section>

  <!-- 未消化タスク -->
  <section>
    <h2>未消化ヒアリングタスク</h2>
    {% if open_tasks %}
      <ul>
        {% for task in open_tasks %}
          <li>{{ task.field_label }}（{{ task.created_at|date:"Y/m/d" }} 作成）</li>
        {% endfor %}
      </ul>
    {% else %}
      <p class="text-text-secondary">全てのヒアリングが完了しています</p>
    {% endif %}
  </section>

  <!-- 来店履歴 -->
  <section>
    <h2>来店履歴</h2>
    {% if visits %}
      <table>
        <thead>
          <tr>
            <th>来店日</th>
            <th>対応スタッフ</th>
            <th>メモ</th>
          </tr>
        </thead>
        <tbody>
          {% for visit in visits %}
            <tr>
              <td>{{ visit.visited_at|date:"Y/m/d" }}</td>
              <td>{{ visit.staff.display_name }}</td>
              <td>{% if visit.conversation_memo %}{{ visit.conversation_memo|truncatechars:50 }}{% else %}<span class="text-text-muted">-</span>{% endif %}</td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    {% else %}
      <p class="text-text-secondary">来店記録がありません</p>
    {% endif %}
  </section>
{% endblock %}
```

**シーシャ歴の表示**: View 側で `SHISHA_EXPERIENCE_DISPLAY` 辞書を使い、内部値（`none`, `beginner` 等）を日本語ラベルに解決してからテンプレートに `shisha_experience_label` として渡す。テンプレートでは辞書ルックアップを行わず、解決済みの文字列をそのまま表示する。

**トースト表示**: `CustomerDetailView.get_context_data()` で `self.request.session.pop("toast", None)` を使い、セッションから toast を取り出す（取り出し後に自動削除）。テンプレートでは `base_owner.html` の `{% block toast %}` を使い、Alpine.js の `x-init` で 3 秒後に自動消去する。UO-01 で定義済みの toast ブロックのパターンに準拠。

### 5.4 owner/customer_edit.html

```
{% extends "ui/base_owner.html" %}
{% load static %}

{% block page_title %}{{ customer.name }} - 編集{% endblock %}

{% block content %}
  <form method="post">
    {% csrf_token %}

    <!-- 名前（必須） -->
    <div>
      <label for="{{ form.name.id_for_label }}">{{ form.name.label }}</label>
      {{ form.name }}
      {% if form.name.errors %}<p class="text-error">{{ form.name.errors.0 }}</p>{% endif %}
    </div>

    <!-- 年齢（任意） -->
    <div>
      <label for="{{ form.age.id_for_label }}">{{ form.age.label }}</label>
      {{ form.age }}
      {% if form.age.errors %}<p class="text-error">{{ form.age.errors.0 }}</p>{% endif %}
    </div>

    <!-- 居住エリア（任意） -->
    <div>
      <label for="{{ form.area.id_for_label }}">{{ form.area.label }}</label>
      {{ form.area }}
      {% if form.area.errors %}<p class="text-error">{{ form.area.errors.0 }}</p>{% endif %}
    </div>

    <!-- シーシャ歴（任意） -->
    <div>
      <label for="{{ form.shisha_experience.id_for_label }}">{{ form.shisha_experience.label }}</label>
      {{ form.shisha_experience }}
      {% if form.shisha_experience.errors %}<p class="text-error">{{ form.shisha_experience.errors.0 }}</p>{% endif %}
    </div>

    <!-- LINE ID（任意） -->
    <div>
      <label for="{{ form.line_id.id_for_label }}">{{ form.line_id.label }}</label>
      {{ form.line_id }}
      {% if form.line_id.errors %}<p class="text-error">{{ form.line_id.errors.0 }}</p>{% endif %}
    </div>

    <!-- メモ（任意） -->
    <div>
      <label for="{{ form.memo.id_for_label }}">{{ form.memo.label }}</label>
      {{ form.memo }}
      {% if form.memo.errors %}<p class="text-error">{{ form.memo.errors.0 }}</p>{% endif %}
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
      <a href="/o/customers/{{ customer.pk }}/" class="btn-secondary">キャンセル</a>
    </div>
  </form>
{% endblock %}
```

### 5.5 HTMX CSRF 設定

UO-01 S2 で `base.html` に HTMX CSRF トークン自動付与（`htmx:configRequest`）が追加済みのため、UO-02 では追加の CSRF 設定は不要。`hx-get` はCSRF 不要、`form method="post"` は `{% csrf_token %}` で対応。

## 6. URL 設定

### ui/owner/urls.py（追記）

```python
# 既存の UO-01 S1/S2 の urlpatterns に追記

from ui.owner.views.customer import (
    CustomerListView, CustomerDetailView, CustomerEditView,
)

# UO-02 S1: 顧客管理
path("customers/", CustomerListView.as_view(), name="customer-list"),
path("customers/<uuid:pk>/", CustomerDetailView.as_view(), name="customer-detail"),
path("customers/<uuid:pk>/edit/", CustomerEditView.as_view(), name="customer-edit"),
```

**Sidebar リンクの有効化**: UO-01 S1 で配置済みの `<a href="/o/customers/">顧客管理</a>` が、UO-02 の URL 追加により遷移可能になる。追加のテンプレート変更は不要。

## 7. テストケース

### 7.1 Django TestClient

| # | テスト | 検証内容 |
|---|--------|---------|
| 1 | `test_customer_list_owner` | owner で GET `/o/customers/` → 200、テーブル表示 |
| 2 | `test_customer_list_unauthenticated` | 未認証 → 302 `/o/login/` |
| 3 | `test_customer_list_staff_redirect` | staff で GET → 302 `/s/customers/` |
| 4 | `test_customer_list_search` | `?search=山田` → 名前に「山田」を含む顧客のみ表示 |
| 5 | `test_customer_list_segment_filter` | `?segment=new` → segment='new' の顧客のみ表示 |
| 6 | `test_customer_list_sort_name` | `?sort=name` → 名前昇順 |
| 7 | `test_customer_list_sort_visit_count` | `?sort=-visit_count` → 来店回数降順 |
| 8 | `test_customer_list_sort_last_visited` | デフォルトソート → 最終来店日降順。未来店顧客は末尾（nulls_last） |
| 9 | `test_customer_list_sort_invalid` | `?sort=invalid_field` → デフォルト（最終来店日降順）にフォールバック |
| 10 | `test_customer_list_pagination` | 26 件登録 → 1 ページ目 25 件 + 2 ページ目 1 件 |
| 11 | `test_customer_list_htmx_fragment` | `HX-Request: true` ヘッダー付き → `_customer_table.html` フラグメント（フィルタバー + テーブル + ページネーション）のみ返却 |
| 12 | `test_customer_list_store_scope` | 他店舗の顧客が表示されない |
| 13 | `test_customer_list_last_visited_annotation` | 来店記録あり → 最終来店日が表示。来店記録なし → null |
| 14 | `test_customer_list_open_task_count` | 未消化タスクの件数が正しくアノテーションされる |
| 15 | `test_customer_list_deleted_visit_excluded` | 論理削除された来店記録が最終来店日の算出から除外される |
| 16 | `test_customer_detail_owner` | owner で GET `/o/customers/<id>/` → 200、全属性表示 |
| 17 | `test_customer_detail_visits` | 来店履歴テーブルに来店記録が表示される |
| 18 | `test_customer_detail_visits_staff_name` | 来店履歴に対応スタッフ名が表示される（select_related 確認） |
| 19 | `test_customer_detail_open_tasks` | 未消化タスクが表示される。closed タスクは表示されない |
| 20 | `test_customer_detail_all_tasks_done` | 全タスク完了時に「全てのヒアリングが完了しています」表示 |
| 21 | `test_customer_detail_not_found` | 存在しない顧客 ID → 404 |
| 22 | `test_customer_detail_other_store` | 他店舗の顧客 ID → 404 |
| 23 | `test_customer_detail_edit_link` | レスポンスに `/o/customers/<id>/edit/` リンクが含まれる |
| 24 | `test_customer_detail_toast` | セッションに toast あり → トーストが表示され、セッションから削除 |
| 25 | `test_customer_edit_get` | GET `/o/customers/<id>/edit/` → 200、フォームに既存値がプリセット |
| 26 | `test_customer_edit_post_valid` | POST valid → CustomerService.update_customer 呼び出し + 302 詳細画面 + セッションに toast |
| 27 | `test_customer_edit_post_invalid_name_empty` | POST name="" → 200、「名前を入力してください」エラー |
| 28 | `test_customer_edit_sync_tasks_called` | ヒアリング対象フィールド変更時に sync_tasks が呼ばれる |
| 29 | `test_customer_edit_sync_tasks_not_called` | 非ヒアリング対象フィールドのみ変更時に sync_tasks が呼ばれない |
| 30 | `test_customer_edit_empty_to_none` | 空文字列が None に正規化される（age, area, shisha_experience, line_id, memo） |
| 31 | `test_customer_edit_unauthenticated` | 未認証 → 302 `/o/login/` |
| 32 | `test_customer_edit_staff_redirect` | staff で GET → 302 `/s/customers/` |
| 33 | `test_customer_edit_not_found` | 存在しない顧客 ID → 404 |
| 34 | `test_customer_edit_other_store` | 他店舗の顧客 ID → 404 |
| 35 | `test_customer_edit_business_error` | CustomerService.update_customer が BusinessError を送出 → フォームに non_field_errors 表示 |
| 36 | `test_customer_list_nulls_last` | 未来店顧客が来店日降順ソートで末尾に表示される |
| 37 | `test_sidebar_active_customers` | `/o/customers/` で active_sidebar == "customers" |

### 7.2 Browser smoke test

| # | 対象 URL | 手順 | 期待結果 |
|---|---------|------|---------|
| 1 | `/o/customers/` | 顧客一覧表示 | テーブルにデータ表示、セグメントバッジ正常 |
| 2 | `/o/customers/` | 検索欄に文字入力 | 300ms 後に HTMX でテーブル差し替え（フルページリロードなし） |
| 3 | `/o/customers/` | セグメントフィルタ変更 | HTMX でテーブル差し替え、ブラウザ URL 変更 |
| 4 | `/o/customers/` | テーブルヘッダーのソートクリック | HTMX でテーブル差し替え、ソート矢印表示 |
| 5 | `/o/customers/` | ページネーション「次へ」 | HTMX でテーブル差し替え |
| 6 | `/o/customers/` | 行クリック | 顧客詳細画面に遷移 |
| 7 | `/o/customers/<id>/` | 詳細画面表示 | 全属性 + 来店履歴 + タスク表示 |
| 8 | `/o/customers/<id>/` | 「編集」ボタンクリック | 編集画面に遷移、フォームに既存値 |
| 9 | `/o/customers/<id>/edit/` | フォーム編集 → 保存 | 詳細画面にリダイレクト + トースト「顧客情報を更新しました」表示（3 秒で消去） |
| 10 | `/o/customers/<id>/edit/` | 名前を空にして保存 | バリデーションエラー表示 |
| 11 | `/o/customers/` | 検索後にフィルタチップ表示確認 | 検索チップが表示される。&#x2715; クリックで検索解除 |
| 12 | `/o/customers/` | セグメントフィルタ選択後にチップ表示確認 | セグメントチップが表示される。&#x2715; クリックでセグメント個別解除。「すべてクリア」で全フィルタ解除 |
| 13 | `/o/customers/` | 検索中にスケルトンローダー表示確認 | HTMX リクエスト中にスケルトンローダーが表示され、レスポンス後に消える |
| 14 | `/o/customers/` | ソートクリック時にスケルトンローダー表示確認 | テーブルヘッダークリック → ローダー表示 → テーブル差し替え |
| 15 | `/o/customers/` | ページネーション時にスケルトンローダー表示確認 | 「次へ」クリック → ローダー表示 → テーブル差し替え |

## 8. Gherkin シナリオ

```gherkin
Feature: Owner 顧客管理

  Scenario: 顧客一覧の表示
    Given オーナーとしてログインしている
    And 店舗に顧客が 3 件登録されている
    When `/o/customers/` にアクセスする
    Then 顧客一覧テーブルに 3 件表示される
    And 各行にセグメントバッジが表示される

  Scenario: 顧客名で検索
    Given 顧客 "山田太郎" と "田中花子" が存在する
    When 検索欄に "山田" と入力する
    Then "山田太郎" のみ表示される

  Scenario: セグメントでフィルタ
    Given segment='new' の顧客と segment='regular' の顧客が存在する
    When セグメントフィルタで "新規" を選択する
    Then segment='new' の顧客のみ表示される

  Scenario: 来店回数でソート
    Given 来店回数が異なる顧客が複数存在する
    When テーブルヘッダーの「来店回数」をクリックする
    Then 来店回数の昇順でソートされる
    And もう一度クリックすると降順に切り替わる

  Scenario: ページネーション
    Given 店舗に顧客が 30 件登録されている
    When `/o/customers/` にアクセスする
    Then 25 件表示される
    And 「次へ」ボタンが表示される
    When 「次へ」をクリックする
    Then 残り 5 件が表示される

  Scenario: 他店舗の顧客が見えない
    Given Store A に顧客 "山田" が存在する
    And Store B に顧客 "田中" が存在する
    And Store A のオーナーとしてログインしている
    When 顧客一覧にアクセスする
    Then "山田" のみ表示される

  Scenario: 顧客詳細の表示
    Given 顧客 "山田太郎" が存在する
    And 山田太郎に来店記録が 2 件ある
    And 山田太郎に未消化タスク（age）が 1 件ある
    When `/o/customers/<山田太郎のID>/` にアクセスする
    Then 全属性（名前、セグメント、来店回数、年齢、エリア、シーシャ歴、LINE ID、メモ、作成日、更新日）が表示される
    And 来店履歴テーブルに 2 件表示される
    And 未消化タスクに「年齢」が表示される

  Scenario: 顧客情報の編集
    Given 顧客 "山田太郎"（age=null）が存在する
    When 山田太郎の編集画面で age を 25 に設定して保存する
    Then 顧客の age が 25 に更新される
    And HearingTaskService.sync_tasks() が呼ばれる
    And 詳細画面にリダイレクトされる
    And トースト「顧客情報を更新しました」が表示される

  Scenario: 非ヒアリング項目の編集で sync_tasks が呼ばれない
    Given 顧客 "山田太郎"（memo=null）が存在する
    When 山田太郎の編集画面で memo を "VIP顧客" に設定して保存する
    Then 顧客の memo が "VIP顧客" に更新される
    And HearingTaskService.sync_tasks() は呼ばれない

  Scenario: 空文字列の None 正規化
    Given 顧客 "山田太郎"（area="渋谷"）が存在する
    When 山田太郎の編集画面で area を空にして保存する
    Then 顧客の area が None に更新される（空文字列ではない）
    And HearingTaskService.sync_tasks() が呼ばれる（area が non-null → null に変化）

  Scenario: 名前の必須バリデーション
    Given 顧客 "山田太郎" の編集画面を開いている
    When name を空にして保存する
    Then 「名前を入力してください」エラーが表示される
    And 顧客情報は更新されない

  Scenario: 未認証でのアクセス
    Given ログインしていない
    When `/o/customers/` にアクセスする
    Then `/o/login/` にリダイレクトされる

  Scenario: スタッフでのアクセス
    Given staff ロールでログインしている
    When `/o/customers/` にアクセスする
    Then `/s/customers/` にリダイレクトされる
```

## 9. Closure Audit チェックリスト

- UO-01 S1 → UO-02 S1: `base_owner.html` の Sidebar「顧客管理」リンク `/o/customers/` が UO-02 の URL で応答するか
- UO-02 postcondition「Store スコープ」: `Customer.objects.for_store(store)` が全 View で正しく適用されているか
- UO-02 postcondition「HTMX テーブル差し替え」: `_customer_table.html` フラグメント（フィルタバー + テーブル + ページネーション）が `#customer-list-container` に差し込まれ、フィルタ・ソート状態が保持されるか
- UO-02 postcondition「sync_tasks 呼び出し」: CustomerEditView が C-05a の `sync_tasks()` をヒアリング対象フィールド変更時のみ呼ぶか
- UO-02 postcondition「25 件/ページ」: Django Paginator が正しく動作し、HTMX ページ切替でもフラグメントのみ返るか
- UO-02 postcondition「空文字列 → None」: CustomerEditForm の clean メソッドが C-03 の nullable 契約を満たすか
- UO-02 postcondition → C-05a: `sync_tasks()` の入力が `Customer` インスタンスで、auto_close → generate の順序が正しいか
- Visit の Subquery で `is_deleted=False` フィルタが適用され、論理削除された来店記録が除外されるか
- `active_sidebar = "customers"` が全 3 View で設定されているか

## Review Log

- [2026-03-31] 初版作成
- [2026-03-31] Codex レビュー 1回目 (gpt-5.4): 72/100 FAIL。6 件を修正
  - F-01 (high): `last_visited_at` のソートに `F().desc(nulls_last=True)` を追加。未来店顧客がソート末尾に来るよう修正（US-02 と同一パターン）
  - F-02 (high): `open_task_count` の逆参照名 `hearingtask` に注記追加。コア層で `related_name` が明示定義されている場合の確認指示を追記
  - F-03 (high): `shisha_experience` 表示を View 側で解決（`shisha_experience_label` として渡す）。テンプレートの自己矛盾を解消
  - F-04 (medium): `CustomerEditView.post()` に `BusinessError` のキャッチと `form.add_error()` によるエラー表示を追加（US-03 パターン準拠）
  - F-05 (medium): トースト実装を `base_owner.html` の `{% block toast %}` に統一。`session.pop()` を `get_context_data()` で実行。`request` 未定義の問題を `self.request` で解消
  - F-06 (low): テーブルヘッダーの非アクティブ列にも `text-text-muted` の矢印アイコンを追加（デザインガイド テーブル §ソート 準拠）
- [2026-03-31] Codex レビュー 2回目 (gpt-5.4): 82/100 FAIL。3 件を修正
  - F-07 (high): フィルタバー + テーブル + ページネーションを全て `_customer_table.html` に統合し、`#customer-list-container` ごと差し替える設計に変更。ソート状態の非同期ずれを構造的に解消
  - F-08 (medium): 選択中フィルタのチップ表示（検索文字列・セグメント選択）+ クリアボタンを追加（デザインガイド テーブル §フィルタ 準拠）
  - F-09 (low): HTMX リクエスト中のスケルトンローダー表示を追加。`hx-indicator` + `htmx-indicator` クラスで制御（デザインガイド テーブル §ローディング 準拠）
- [2026-03-31] Codex レビュー 3回目 (gpt-5.4): 89/100 FAIL。4 件を修正
  - F-10 (high): `hx-indicator` をフィルタバー親要素に移動し、全 HTMX 操作（検索・フィルタ・ソート・ページネーション・チップ解除）でスケルトンローダーが表示されるよう修正
  - F-11 (medium): フィルタチップ行に「すべてクリア」ボタンを追加。Review Log の記述を「個別解除 + 全解除」に統一
  - F-12 (medium): `open_task_count` の逆参照名をコア層実装確認の上 `hearing_tasks` に確定（`tasks/models.py` の `related_name='hearing_tasks'`）
  - F-13 (low): browser smoke test にチップ解除（#11, #12）とローダー表示（#13）の 3 ケースを追加
- [2026-03-31] Codex レビュー 4回目 (gpt-5.4): 88/100 FAIL。3 件を修正
  - F-14 (high): フラグメント全体を親 div で包み `hx-target` / `hx-indicator` / `hx-push-url` を継承。全 HTMX 操作（検索・フィルタ・ソート・ページネーション・チップ解除）でスケルトンローダーが表示される構造に修正
  - F-15 (medium): query string の手動組み立てを廃止。全 HTMX 発火元で `hx-include` + `hx-vals` を使用し、検索語の特殊文字（`&` 等）が含まれても安全にパラメータが送信される設計に変更
  - F-16 (low): smoke test にソート（#14）とページネーション（#15）のローダー確認を追加
- [2026-03-31] Codex レビュー 5回目 (gpt-5.4): 88/100 FAIL。3 件を修正
  - F-17 (high): チップ解除リンクの `hx-vals` + `urlencode` を廃止。`hx-include` で既存 input/select から値を収集する方式に統一。特殊文字問題を構造的に解消
  - F-18 (medium): `get_context_data()` で `current_sort` / `current_segment` をホワイトリスト正規化。不正値はデフォルトにフォールバック。queryset と context の状態が常に一致する
  - F-19 (low): 非アクティブソート矢印の色を `text-text-muted` → `text-text-secondary` に変更（デザインガイド §2 テーブルヘッダー muted 使用禁止に準拠）
- [2026-03-31] Codex 6回目レビュー (gpt-5.4): **94/100 PASS**。残 2 件を追加修正
  - F-20 (medium): `current_search` を `get_context_data()` で strip 正規化。queryset と context の検索文字列が一致するよう修正
  - F-21 (low): browser smoke test #12 にセグメントチップ個別解除の確認を追記
- [2026-04-01] Owner UI Closure Audit (Issue #25) F-02 修正
  - R-01 (high): `CustomerService.update_customer()` はコア層に存在しない。§3 契約を `form.save()` 直接操作に修正。§4.4 CustomerEditView から `CustomerService` import と try/except BusinessError を除去
