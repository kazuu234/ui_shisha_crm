# US-02 詳細設計書: Customer Selection + Session Flow

> 基本設計書: `docs/design/UI_BASIC_DESIGN.md` §5 US-02, §7.2
> デザインガイド: `docs/design/UI_DESIGN_GUIDE.md`
> パイプライン: `docs/design/UI_PIPELINE.md` #3, #4

## 1. 概要

### Cluster 情報

| 項目 | 内容 |
|------|------|
| **Cluster** | US-02 (接客フロー) |
| **Slice 数** | 2 本 |
| **パイプライン順序** | S1: #3 / 13、S2: #4 / 13 |

### Slice 1: 顧客選択 + 新規登録

| 項目 | 内容 |
|------|------|
| **ブランチ説明部** | `us02-s1-customer-select` |
| **スコープ** | 顧客選択画面（最近来た順一覧）、検索モーダル（インクリメンタル検索）、新規登録モーダル。US-01 の stub view を本実装に置き換え |

**precondition:**
- US-01 S1 完了（`base_staff.html`、`LoginRequiredMixin`、`StaffRequiredMixin`、`StoreMixin` が動作）
- コア層 C-03 完了（Customer モデル + `CustomerService` が動作）
- コア層 C-05a 完了（`HearingTaskService.generate_tasks()` が動作）

**postcondition:**
- `/s/customers/` で最近来た順の顧客カード一覧（セグメントバッジ、来店回数、最終来店日、未消化タスク数）が表示される（上位 20 件）
- 検索バータップ → モーダル起動 → 文字入力 → インクリメンタル検索結果表示（HTMX、300ms デバウンス）
- 検索結果の顧客タップ → `/s/customers/<id>/session/` にリダイレクト
- 新規登録ボタン → モーダル起動 → 名前入力 → 登録 → `/s/customers/<id>/session/` にリダイレクト
- 顧客作成時に segment='new', visit_count=0 が自動設定される（`CustomerService.create_customer()` の仕様）
- 顧客作成直後に `HearingTaskService.generate_tasks(customer)` が呼ばれ、未入力ヒアリング項目の Open タスクが生成される（C-05a 契約）
- BottomTab の「顧客」タブがアクティブ状態
- 来店記録がない顧客は末尾に表示される

### Slice 2: 接客画面

| 項目 | 内容 |
|------|------|
| **ブランチ説明部** | `us02-s2-session` |
| **スコープ** | 接客画面（タスク表示・消化、メモ入力、来店記録作成）。BottomTab「接客」タブの有効化 |

**precondition:**
- US-02 S1 完了（顧客選択 → `/s/customers/<id>/session/` への遷移が動作）
- コア層 C-04 S2 完了（`VisitService` が動作）
- コア層 C-05a 完了（`HearingTaskService.sync_tasks()` の auto close が動作）
- コア層 C-05b 完了（`HearingTask` の表示クエリが動作）

**postcondition:**
- `/s/customers/<id>/session/` で顧客情報 + タスク一覧 + メモ + 来店記録作成ボタン + 直近来店 5 件が 1 画面に表示される
- タスクゾーンタップ → 展開 → チップ選択 → HTMX PATCH → 顧客フィールド更新 + タスク auto close → ゾーンが filled に変化
- メモゾーンタップ → 展開 → テキスト入力 → 「完了」→ Alpine.js 状態として一時保持（即保存しない）
- 「来店記録を作成する」ボタン → HTMX POST → `VisitService.create_visit(conversation_memo=memo)` → メモが Visit に保存される → トースト表示 → ボタンは再利用可能（同日複数来店は業務上正当）→ `visitCreated` で顧客ヘッダー・直近来店を自動更新
- 全タスク消化済みの場合、タスクセクションに「全てのヒアリングが完了しています」表示
- BottomTab「接客」タブがアクティブリンク（顧客 ID を含む URL）

## 2. ファイル構成

### Slice 1

```
ui/
├── staff/
│   ├── urls.py                      # customers stub → CustomerSelectView に差し替え + 検索・作成 URL 追加
│   ├── views/
│   │   ├── customer.py              # CustomerSelectView, CustomerSearchView, CustomerCreateView
│   │   └── stub.py                  # StubCustomerView は削除（CustomerSelectView が置き換え）
│   └── forms/
│       ├── __init__.py
│       └── customer.py              # CustomerCreateForm
├── templates/ui/
│   └── staff/
│       ├── customer_select.html     # 顧客選択画面（検索モーダル + 新規登録モーダル含む）
│       ├── _customer_card.html      # 顧客カード（一覧・検索結果で再利用）
│       ├── _customer_search_results.html  # 検索結果フラグメント（HTMX）
│       ├── _customer_create_modal.html    # 新規登録モーダル全体（初回表示時に include）
│       └── _customer_create_form_content.html  # モーダル内フォーム部分のみ（エラー時の HTMX 差し替え用）
```

### Slice 2

```
ui/
├── staff/
│   ├── urls.py                      # session, field update, visit create URL 追加
│   ├── views/
│   │   ├── session.py               # SessionView, CustomerFieldUpdateView
│   │   └── visit.py                 # VisitCreateView
├── templates/ui/
│   ├── icons/
│   │   └── check-circle.svg         # タスク完了アイコン（Lucide）
│   └── staff/
│       ├── session.html             # 接客画面（全ゾーン含む）
│       ├── _customer_header.html    # 顧客ヘッダーフラグメント（visitCreated 後の HTMX 差し替え用）
│       ├── _zone_task.html          # タスクゾーンフラグメント（HTMX PATCH 後に差し替え）
│       ├── _zone_memo.html          # メモゾーン（Alpine.js 制御）
│       ├── _visit_button.html       # 来店記録作成ボタン（HTMX POST 後にトースト表示、ボタン再利用可能）
│       └── _recent_visits.html      # 直近来店履歴フラグメント
```

## 3. コア層契約

正式な定義は `docs/reference/cluster/C03_CUSTOMER.md`、`docs/reference/cluster/C04_VISIT_SEGMENT.md`、`docs/reference/cluster/C05A_HEARING_TASK_CORE.md`、`docs/reference/cluster/C05B_HEARING_TASK_DISPLAY.md` を参照。

**import パスについて**: コア層は別リポジトリ（別 Django app）として管理されている場合がある。本設計書では `from core.services.customer import CustomerService` のような統一的な記法を使用するが、実際の import パスはコア層のパッケージ構造に依存する。実装時にコア層の `__init__.py` や実際のモジュール配置を確認すること。

### CustomerService

| メソッド | 引数 | 返り値 | 例外 |
|---------|------|--------|------|
| `create_customer(store, name)` | `Store, str` | `Customer` | `BusinessError(customer.name_required)` |
| `update_customer(customer_id, **fields)` | `UUID, **kwargs` | `Customer` | `BusinessError(customer.not_found)` |

**`create_customer` の自動設定**: `segment='new'`, `visit_count=0`。

### HearingTaskService

| メソッド | 引数 | 返り値 | 備考 |
|---------|------|--------|------|
| `generate_tasks(customer)` | `Customer` | `list[HearingTask]` | 未入力のヒアリング項目（age, area, shisha_experience）に対する Open タスクを生成 |
| `sync_tasks(customer)` | `Customer` | synced tasks | auto_close → generate の順に実行。フィールド空戻し時のタスク再生成にも対応（C-05a 設計） |

### VisitService

| メソッド | 引数 | 返り値 | 備考 |
|---------|------|--------|------|
| `create_visit(store, customer, staff, visited_at, conversation_memo)` | `Store, Customer, Staff, date, str` | `Visit` | 同一顧客の同日複数来店は業務上正当（DB unique 制約なし） |

### Customer モデル（UI が参照するフィールド）

| フィールド | 型 | 備考 |
|-----------|-----|------|
| `name` | CharField | 表示名 |
| `segment` | CharField (`new` / `repeat` / `regular`) | セグメントバッジ表示に使用 |
| `visit_count` | PositiveIntegerField | 来店回数 |
| `age` | CharField (nullable) | ヒアリング対象。選択肢: `10s`, `20s`, `30s`, `40s`, `50s_plus` |
| `area` | CharField (nullable) | ヒアリング対象。テキスト入力 |
| `shisha_experience` | CharField (nullable) | ヒアリング対象。選択肢: `none`, `beginner`, `intermediate`, `advanced` |
| `line_id` | CharField (nullable) | LINE ID |
| `memo` | TextField (nullable) | 顧客メモ |
| `store` | ForeignKey(Store) | 店舗スコープ |

**StoreScopedManager**: `Customer.objects.for_store(store)` でストアスコープフィルタを適用。

### HearingTask モデル（UI が参照するフィールド）

| フィールド | 型 | 備考 |
|-----------|-----|------|
| `customer` | ForeignKey(Customer) | 対象顧客 |
| `field_name` | CharField | 対象フィールド名（`age`, `area`, `shisha_experience`） |
| `status` | CharField (`open` / `closed`) | タスク状態 |

**StoreScopedManager**: `HearingTask.objects.for_store(store)` でストアスコープフィルタを適用。

### Visit モデル（UI が参照するフィールド）

| フィールド | 型 | 備考 |
|-----------|-----|------|
| `customer` | ForeignKey(Customer) | 対象顧客 |
| `staff` | ForeignKey(Staff) | 対応スタッフ |
| `visited_at` | DateField | 来店日 |
| `conversation_memo` | TextField (nullable) | 会話メモ |

**StoreScopedManager**: `Visit.objects.for_store(store)` でストアスコープフィルタを適用。

### タスクゾーンのフィールドマッピング

ヒアリング対象フィールドごとのゾーン表示設定。View と テンプレートの両方で参照する。

```python
# ui/staff/views/session.py

TASK_FIELD_CONFIG = {
    "age": {
        "label": "年齢",
        "type": "selection",
        "choices": [
            ("10s", "10代"),
            ("20s", "20代"),
            ("30s", "30代"),
            ("40s", "40代"),
            ("50s_plus", "50代以上"),
        ],
    },
    "area": {
        "label": "居住エリア",
        "type": "text",
    },
    "shisha_experience": {
        "label": "シーシャ歴",
        "type": "selection",
        "choices": [
            ("none", "なし"),
            ("beginner", "初心者"),
            ("intermediate", "中級"),
            ("advanced", "上級"),
        ],
    },
}
```

## 4. テンプレート

### 4.1 staff/customer_select.html（Slice 1）

`base_staff.html` を継承。顧客選択画面の全体構成。

```
{% extends "ui/base_staff.html" %}
{% load static %}

{% block page_title %}顧客{% endblock %}

{% block content %}
  <!-- 検索バー: タップで検索モーダル起動 -->
  <div @click="showSearch = true">
    <!-- placeholder: "顧客を検索..." + 虫眼鏡アイコン -->
    <!-- 見た目は input だが実際は div（タップでモーダル起動） -->
  </div>

  <!-- 最近来た順の顧客カード一覧 -->
  {% for customer in customers %}
    {% include "ui/staff/_customer_card.html" with customer=customer %}
  {% empty %}
    <div>  <!-- text-center, text-text-secondary, py-16 -->
      <p>顧客がまだ登録されていません</p>
    </div>
  {% endfor %}

  <!-- 新規登録ボタン: フル幅、画面下部に固定 -->
  <button @click="showCreate = true">
    新規顧客を登録
  </button>

  <!-- 検索モーダル（Alpine.js 制御） -->
  <div x-show="showSearch" x-transition
       x-effect="if (showSearch) $nextTick(() => $refs.searchInput.focus())">
    <!-- オーバーレイ + モーダル本体 -->
    <div @click.away="showSearch = false">
      <!-- 検索入力: hx-get, hx-trigger, hx-target -->
      <input type="text"
             placeholder="名前で検索..."
             hx-get="/s/customers/search/"
             hx-trigger="input changed delay:300ms"
             hx-target="#search-results"
             name="q"
             x-ref="searchInput">
      <!-- 検索結果コンテナ -->
      <div id="search-results">
        <!-- HTMX で _customer_search_results.html に差し替えられる -->
      </div>
    </div>
  </div>

  <!-- 新規登録モーダル（Alpine.js 制御） -->
  <div x-show="showCreate" x-transition>
    {% include "ui/staff/_customer_create_modal.html" %}
  </div>
{% endblock %}
```

**Alpine.js 初期状態**: `x-data="{ showSearch: false, showCreate: false }"` を `{% block content %}` の親要素に設定。

### 4.2 staff/_customer_card.html（Slice 1）

一覧画面と検索結果で共有する再利用可能フラグメント。

```
<!-- 顧客カード: タップで接客画面に遷移 -->
<a href="/s/customers/{{ customer.id }}/session/">
  <div>  <!-- bg-bg-surface, shadow-sm, rounded-md, p-5, mb-3 -->

    <!-- 上段: セグメントバッジ + 名前 -->
    <div>
      <span class="badge-{{ customer.segment }}">
        {{ customer.segment_display }}
      </span>
      <span>{{ customer.name }}</span>
    </div>

    <!-- 下段: 来店回数 + 最終来店日 -->
    <div>  <!-- text-text-secondary, text-sm -->
      <span>来店 {{ customer.visit_count }} 回</span>
      {% if customer.last_visited_at %}
        <span>・最終 {{ customer.last_visited_at|date:"n/j" }}</span>
      {% endif %}
    </div>

    <!-- 未消化タスク表示（ある場合のみ） -->
    {% if customer.open_task_count > 0 %}
      <div>  <!-- text-text-muted, text-xs, mt-1 -->
        タスク: {{ customer.open_task_count }} 件未完了
      </div>
    {% endif %}
  </div>
</a>
```

**セグメントバッジの表示名マッピング**: View で `segment_display` を annotate するか、テンプレートフィルタを使う。

| segment | 表示名 | バッジクラス |
|---------|--------|------------|
| `new` | 新規 | `badge-new`（`accent-subtle` bg、`accent` text） |
| `repeat` | リピート | `badge-repeat`（`warning-subtle` bg、`warning-dark` text） |
| `regular` | 常連 | `badge-regular`（`success-subtle` bg、`success` text） |

### 4.3 staff/_customer_search_results.html（Slice 1）

HTMX フラグメント。検索結果を顧客カードのリストとして返す。

```
{% load static %}

{% for customer in customers %}
  {% include "ui/staff/_customer_card.html" with customer=customer %}
{% empty %}
  <div>  <!-- text-center, text-text-secondary, py-8 -->
    <p>見つかりませんでした</p>
  </div>
{% endfor %}
```

### 4.4 staff/_customer_create_modal.html（Slice 1）

新規登録モーダルの本体。HTMX POST で送信。

```
{% load static %}

<div @click.away="showCreate = false">
  <h2>新規顧客登録</h2>

  <div id="create-modal-content">
    <form hx-post="/s/customers/new/"
          hx-target="#create-modal-content"
          hx-swap="innerHTML">
      {% csrf_token %}

      <!-- 名前入力 -->
      <label>{{ form.name.label }}</label>
      {{ form.name }}
      {% if form.name.errors %}<p>{{ form.name.errors.0 }}</p>{% endif %}

      <!-- 登録ボタン -->
      <button type="submit">登録</button>
      <button type="button" @click="showCreate = false">キャンセル</button>
    </form>
  </div>
</div>
```

**成功時の挙動**: View が `HX-Redirect` ヘッダーを返し、HTMX がフルページリダイレクトを実行。モーダルは自動的に閉じる（ページ遷移のため）。

**バリデーションエラー時の挙動**: View がフォーム HTML（モーダルラッパーなし、フォーム内容のみ）を再度返し、`hx-target="#create-modal-content"` + `hx-swap="innerHTML"` で `#create-modal-content` 内を差し替え。エラーメッセージがインライン表示される。モーダルの二重ネストを防止するため、エラー時のレスポンステンプレートはフォーム部分のみを返すこと（`_customer_create_form_content.html` などを分離するか、`_customer_create_modal.html` から form 内部のみを返す）。

### 4.5 staff/session.html（Slice 2）

`base_staff.html` を継承。接客画面の全体構成。

```
{% extends "ui/base_staff.html" %}
{% load static %}

{% block page_title %}接客{% endblock %}

{% block content %}
  <div x-data="{ memo: '', memoOpen: false, allDone: false }"
       @all-tasks-done.window="allDone = true">

    <!-- 顧客ヘッダー -->
    {% include "ui/staff/_customer_header.html" %}

    <!-- ヒアリングタスクセクション -->
    <h2>ヒアリングタスク</h2>
    {% if tasks %}
      <div>  <!-- ゾーングループ: bg-bg-surface, shadow-sm, rounded-md, divide-y -->
        {% for task in tasks %}
            {% include "ui/staff/_zone_task.html" with task=task config=task.config customer=customer %}
        {% endfor %}
      </div>
    {% else %}
      <div>  <!-- text-center, text-text-secondary, py-8 -->
        {% include "ui/icons/check-circle.svg" %}
        <p>全てのヒアリングが完了しています</p>
      </div>
    {% endif %}
    <!-- all-tasks-done イベント受信時の完了メッセージ（Alpine.js で表示切替） -->
    <div x-show="allDone" x-transition x-cloak>
      <!-- text-center, text-text-secondary, py-8 -->
      {% include "ui/icons/check-circle.svg" %}
      <p>全てのヒアリングが完了しています</p>
    </div>

    <!-- メモゾーン -->
    <h2>会話メモ（来店記録に保存）</h2>
    {% include "ui/staff/_zone_memo.html" %}

    <!-- 来店記録作成ボタン -->
    <div id="visit-button">
      {% include "ui/staff/_visit_button.html" %}
    </div>

    <!-- 直近来店履歴 -->
    <h2>直近の来店</h2>
    <div id="recent-visits"
         hx-get="/s/customers/{{ customer.id }}/session/recent-visits/"
         hx-trigger="visitCreated from:body"
         hx-swap="innerHTML">
      {% include "ui/staff/_recent_visits.html" %}
    </div>
  </div>
{% endblock %}
```

**HTMX → Alpine.js イベントブリッジ**: HTMX の `HX-Trigger: all-tasks-done` は DOM イベント `all-tasks-done` を body に発火する。Alpine.js は `@all-tasks-done.window` でキャッチし `allDone = true` に設定する。HX-Trigger のイベント名と Alpine.js のリスナーは共にケバブケース（`all-tasks-done`）で統一する。

**BottomTab「接客」タブ**: 接客画面では `active_tab = "session"` をコンテキストに設定。`base_staff.html` の BottomTab で接客タブがアクティブリンクになる。接客タブの URL は `session_url` コンテキスト変数で動的に設定（顧客 ID を含むため）。

### 4.6 staff/_customer_header.html（Slice 2）

顧客ヘッダーフラグメント。session.html で `{% include %}` し、visitCreated 後は HTMX で差し替える。SessionHeaderFragmentView もこのテンプレートを返す。

```
{% load static %}

<div id="customer-header"
     hx-get="/s/customers/{{ customer.id }}/session/header/"
     hx-trigger="visitCreated from:body"
     hx-swap="outerHTML">
  <!-- bg-bg-surface, shadow-sm, rounded-md, p-5, mb-4 -->
  <div>
    <span class="badge-{{ customer.segment }}">{{ customer.segment_display }}</span>
    <span>{{ customer.name }}</span>
  </div>
  <div>  <!-- text-text-secondary, text-sm -->
    来店 {{ customer.visit_count }} 回
    {% if last_visited_at %}
      ・最終 {{ last_visited_at|date:"n/j" }}
    {% endif %}
  </div>
</div>
```

### 4.7 staff/_zone_task.html（Slice 2）

タスクゾーンフラグメント。Alpine.js で展開/折りたたみ、HTMX で値送信。HTMX PATCH 後にこのフラグメント全体が差し替えられる。

```
{% load static %}

<div id="zone-{{ task.field_name }}">

{% if error %}
  <!-- エラー表示（ValidationError 時） -->
  <div>  <!-- error-subtle 背景, error テキスト, rounded-sm, p-2, mb-2 -->
    <p>{{ error }}</p>
  </div>
{% endif %}

{% if filled %}
  <!-- Filled 状態（値入力済み） -->
  <div>  <!-- bg-accent-light, rounded-md, p-4 -->
    <span>{{ config.label }}</span>
    <span>{{ filled_label }}</span>  <!-- 選択された値の表示ラベル -->
    <!-- filled 状態でも再編集可能にする場合は、ここにも展開ボタンを追加（Phase 2） -->
  </div>

{% elif config.type == "selection" %}
  <!-- 選択型ゾーン（age, shisha_experience） -->
  <div x-data="{ open: false }">
    <div @click="open = !open">
      <span>{{ config.label }}</span>
      <span>タップして入力 ▸</span>
    </div>
    <div x-show="open" x-transition>
      {% for value, label in config.choices %}
        <button
          hx-patch="/s/customers/{{ customer.id }}/field/"
          hx-vals='{"field": "{{ task.field_name }}", "value": "{{ value }}"}'
          hx-target="#zone-{{ task.field_name }}"
          hx-swap="outerHTML"
          class="chip">
          {{ label }}
        </button>
      {% endfor %}
    </div>
  </div>

{% elif config.type == "text" %}
  <!-- テキスト型ゾーン（area） -->
  <div x-data="{ open: false, val: '' }">
    <div @click="open = !open">
      <span>{{ config.label }}</span>
      <span>タップして入力 ▸</span>
    </div>
    <div x-show="open" x-transition>
      <input type="text" x-model="val" placeholder="{{ config.placeholder }}">
      <button
        hx-patch="/s/customers/{{ customer.id }}/field/"
        :hx-vals="JSON.stringify({field: '{{ task.field_name }}', value: val})"
        hx-target="#zone-{{ task.field_name }}"
        hx-swap="outerHTML">
        確定
      </button>
    </div>
  </div>
{% endif %}

</div>
```

**HTMX PATCH 後のレスポンス**: View は `_zone_task.html` をレンダリングして返す（更新後のゾーンフラグメント）。actual_value が None/空文字なら filled=False、それ以外なら filled=True を返す。filled 状態では選択済みの値をラベル表示し、再タップ不可とする。全タスクが closed になった場合は追加で `HX-Trigger: all-tasks-done` イベントを発火する。

**filled 状態の表示**: HTMX PATCH 成功後、View は `_zone_task.html` を actual_value に基づく filled コンテキスト（actual_value が None/空文字なら filled=False、それ以外なら filled=True）で返す。テンプレートは filled 時に値のラベルのみを表示する読み取り専用ゾーンをレンダリングする。全タスク closed 時のメッセージ表示は `HX-Trigger: all-tasks-done` イベントで処理する。

### 4.8 staff/_zone_memo.html（Slice 2）

メモゾーン。Alpine.js のみで制御し、来店記録作成時にサーバーに送信する。

```
{% load static %}

<div>  <!-- bg-bg-surface, shadow-sm, rounded-md -->
  <!-- Collapsed 状態 -->
  <div @click="memoOpen = !memoOpen">
    <span>メモ</span>
    <template x-if="memo">
      <span x-text="memo.substring(0, 30) + (memo.length > 30 ? '...' : '')"></span>
    </template>
    <template x-if="!memo">
      <span>タップして入力 ▸</span>
    </template>
  </div>

  <!-- Expanded 状態: テキストエリア -->
  <div x-show="memoOpen" x-transition>
    <textarea x-model="memo"
              placeholder="接客中の会話メモを入力..."
              rows="4">
    </textarea>
    <button type="button" @click="memoOpen = false">完了</button>
  </div>
</div>
```

**memo は session.html の `x-data` で管理**: `_zone_memo.html` は session.html の `x-data="{ memo: '', memoOpen: false }"` スコープ内で展開されるため、`memo` 変数を直接参照できる。

### 4.9 staff/_visit_button.html（Slice 2）

来店記録作成ボタン。HTMX POST で送信後、トーストで通知。ボタンは再利用可能（同日複数来店が正当）。

```
{% load static %}

{% if error %}
  <div>  <!-- error-subtle, p-3, rounded-sm, mb-2 -->
    <p>{{ error }}</p>
  </div>
{% endif %}

<!-- 来店記録は同日複数回作成可能（C-04 仕様）。
     作成成功後はトーストで通知し、ボタンは再利用可能なまま残す。
     memo は作成後にクリアする。 -->
  <button
    hx-post="/s/visits/create/"
    :hx-vals="JSON.stringify({customer_id: '{{ customer.id }}', conversation_memo: memo})"
    hx-target="#visit-button"
    hx-swap="innerHTML"
    class="btn-primary w-full">
    来店記録を作成する
  </button>
```

**memo の送信方法**: Alpine.js の `memo` 変数を HTMX の `hx-vals` に含める。`:hx-vals` で Alpine.js のリアクティブバインディングを使い、送信時点の memo 値を動的に含める。

**HX-Trigger**: View が `HX-Trigger: showToast` ヘッダーを返し、`base_staff.html` の Toast コンポーネントがトースト表示をトリガーする。

### 4.10 staff/_recent_visits.html（Slice 2）

直近来店履歴。表示のみのフラグメント。

```
{% load static %}

{% for visit in recent_visits %}
  <!-- 来店詳細への遷移先は US-03 S1 で実装。US-02 時点では表示のみ -->
  <div class="block">  <!-- py-3, border-b border-border-default, last:border-b-0 -->
    <div>
      <span>{{ visit.visited_at|date:"n/j" }}</span>
      <span>{{ visit.staff.display_name }}</span>
    </div>
    {% if visit.conversation_memo %}
      <p>  <!-- text-text-secondary, text-sm, truncate -->
        {{ visit.conversation_memo|truncatechars:50 }}
      </p>
    {% endif %}
  </div>
{% empty %}
  <div>  <!-- text-text-muted, text-sm -->
    <p>来店記録はまだありません</p>
  </div>
{% endfor %}
```

## 5. Form 定義

### 5.1 CustomerCreateForm（Slice 1）

```python
# ui/staff/forms/customer.py

from django import forms


class CustomerCreateForm(forms.Form):
    name = forms.CharField(
        label="名前",
        max_length=150,
        widget=forms.TextInput(attrs={
            "placeholder": "顧客の名前を入力",
            "autocomplete": "off",
            "autofocus": True,
        }),
        error_messages={"required": "名前を入力してください"},
    )
```

### 5.2 CustomerFieldUpdateForm（Slice 2）

タスクゾーンからの HTMX PATCH で送信されるフォーム。`field` と `value` のバリデーションを行う。

```python
# ui/staff/forms/customer.py に追記

HEARING_FIELD_CHOICES = {
    "age": ["10s", "20s", "30s", "40s", "50s_plus"],
    "area": None,  # テキスト入力。値のバリデーションはなし
    "shisha_experience": ["none", "beginner", "intermediate", "advanced"],
}


class CustomerFieldUpdateForm(forms.Form):
    field = forms.CharField(max_length=50)
    value = forms.CharField(max_length=255, required=False)  # 空文字を許可（None に正規化する）

    # nullable なヒアリングフィールド: 空文字列を None に正規化する対象
    NULLABLE_FIELDS = {"age", "area", "shisha_experience"}

    def clean(self):
        cleaned = super().clean()
        field_name = cleaned.get("field")
        value = cleaned.get("value")

        if field_name not in HEARING_FIELD_CHOICES:
            raise forms.ValidationError(f"無効なフィールド: {field_name}")

        # C-05a 互換: 空文字列を None に正規化（nullable フィールド）
        if field_name in self.NULLABLE_FIELDS and value == "":
            cleaned["value"] = None
            return cleaned

        allowed = HEARING_FIELD_CHOICES[field_name]
        if allowed is not None and value not in allowed:
            raise forms.ValidationError(f"無効な値: {value}")

        return cleaned
```

### 5.3 VisitCreateForm（Slice 2）

```python
# ui/staff/forms/customer.py に追記

class VisitCreateForm(forms.Form):
    customer_id = forms.UUIDField()
    conversation_memo = forms.CharField(
        required=False,
        widget=forms.Textarea,
    )
```

## 6. View 定義

### Slice 1

#### 6.1 CustomerSelectView

US-01 の `StubCustomerView` を置き換える。

```python
# ui/staff/views/customer.py

from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Subquery, OuterRef, Count, Q, F
from django.shortcuts import render

from ui.mixins import StaffRequiredMixin, StoreMixin


class CustomerSelectView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, TemplateView):
    """顧客選択画面。最近来た順の顧客カード一覧 + 検索モーダル + 新規登録モーダル。"""
    template_name = "ui/staff/customer_select.html"
    login_url = "/s/login/"

    def get_context_data(self, **kwargs):
        # 循環 import 回避のためローカル import。実際のパスはコア層のパッケージ構造に依存する
        from core.models import Customer, Visit

        context = super().get_context_data(**kwargs)

        # N+1 防止: last_visited_at と open_task_count を annotate
        # order_by は annotate 済みフィールド名を参照する（Subquery の重複を避ける）
        # 注意: "hearingtask" は Django デフォルトの逆参照名。コア層で related_name が
        # 明示的に設定されている場合はそちらに合わせること。
        customers = (
            Customer.objects.for_store(self.store)
            .annotate(
                last_visited_at=Subquery(
                    Visit.objects.filter(customer=OuterRef("pk"))
                    .order_by("-visited_at")
                    .values("visited_at")[:1]
                ),
                open_task_count=Count(
                    "hearingtask",
                    filter=Q(hearingtask__status="open"),
                ),
            )
            .order_by(F("last_visited_at").desc(nulls_last=True))[:20]
        )

        # テンプレートが customer.segment_display を参照するため付与
        # SEGMENT_DISPLAY は session.py で定義（共通化が望ましいが Slice 1 時点では customer.py でも定義可）
        SEGMENT_DISPLAY = {"new": "新規", "repeat": "リピート", "regular": "常連"}
        customers = list(customers)
        for c in customers:
            c.segment_display = SEGMENT_DISPLAY.get(c.segment, c.segment)

        context["customers"] = customers
        context["active_tab"] = "customers"
        # 新規登録モーダル用フォーム
        from ui.staff.forms.customer import CustomerCreateForm
        context["form"] = CustomerCreateForm()
        return context
```

**`SEGMENT_DISPLAY` の共通化**: `SEGMENT_DISPLAY` マッピングは `session.py` と `customer.py` の両方で使用する。共通定数として `ui/staff/constants.py` に配置し、両 View から import することを推奨する。Customer モデルに `get_segment_display()` メソッドがある場合（segment が Django choices フィールドの場合）はそちらを優先すること。

**N+1 防止の QuerySet 設計**:
- `last_visited_at`: `Visit` テーブルへの `Subquery` で最終来店日を取得
- `open_task_count`: `Count` + `filter` で未消化タスク数を annotate。逆参照名 `"hearingtask"` は Django デフォルト（`<model_name>` 小文字）。コア層で `related_name` が明示されている場合はそちらに合わせること
- `order_by`: annotate 済みの `last_visited_at` フィールドを `F()` で参照し `desc(nulls_last=True)`。`Subquery` を `order_by` 内で再記述しない

**注意**: import を `get_context_data` 内に配置している理由は循環 import の回避。コア層のモデルを UI app から参照するため、トップレベル import で循環する可能性がある。実装時にトップレベルに移動可能であればそうすること。

#### 6.2 CustomerSearchView

```python
# ui/staff/views/customer.py に追記

from django.views import View
from django.db.models import Subquery, OuterRef, Count, Q


class CustomerSearchView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, View):
    """HTMX GET: インクリメンタル検索。フラグメントを返す。"""
    login_url = "/s/login/"

    def get(self, request):
        from core.models import Customer, Visit

        q = request.GET.get("q", "").strip()
        if not q:
            return render(request, "ui/staff/_customer_search_results.html", {"customers": []})

        last_visit_subquery = (
            Visit.objects.filter(customer=OuterRef("pk"))
            .order_by("-visited_at")
            .values("visited_at")[:1]
        )
        customers = (
            Customer.objects.for_store(self.store)
            .filter(name__icontains=q)
            .annotate(
                last_visited_at=Subquery(last_visit_subquery),
                open_task_count=Count(
                    "hearingtask",
                    filter=Q(hearingtask__status="open"),
                ),
            )[:20]
        )

        # テンプレートが customer.segment_display を参照するため付与
        SEGMENT_DISPLAY = {"new": "新規", "repeat": "リピート", "regular": "常連"}
        customers = list(customers)
        for c in customers:
            c.segment_display = SEGMENT_DISPLAY.get(c.segment, c.segment)

        return render(request, "ui/staff/_customer_search_results.html", {"customers": customers})
```

#### 6.3 CustomerCreateView

```python
# ui/staff/views/customer.py に追記

from django.http import HttpResponse

from core.exceptions import BusinessError
from core.services.customer import CustomerService
from core.services.hearing import HearingTaskService
from ui.staff.forms.customer import CustomerCreateForm


ERROR_MESSAGES = {
    "customer.name_required": "名前を入力してください",
}


class CustomerCreateView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, View):
    """HTMX POST: 新規顧客登録 → generate_tasks → HX-Redirect で接客画面に遷移。"""
    login_url = "/s/login/"

    def get(self, request):
        """モーダル内フォームの初期表示（HTMX GET の場合）"""
        form = CustomerCreateForm()
        return render(request, "ui/staff/_customer_create_modal.html", {"form": form})

    def post(self, request):
        form = CustomerCreateForm(request.POST)
        if not form.is_valid():
            # hx-target="#create-modal-content" に合わせ、フォーム内容のみ返す（モーダルラッパーなし）
            return render(request, "ui/staff/_customer_create_form_content.html", {"form": form})

        name = form.cleaned_data["name"]
        try:
            customer = CustomerService.create_customer(store=self.store, name=name)
        except BusinessError as e:
            form.add_error(None, ERROR_MESSAGES.get(e.code, "登録に失敗しました"))
            return render(request, "ui/staff/_customer_create_form_content.html", {"form": form})

        # C-05a 契約: 顧客作成直後にタスク生成を明示呼び出し
        HearingTaskService.generate_tasks(customer)

        # HTMX: HX-Redirect で接客画面にフルページリダイレクト
        response = HttpResponse(status=204)
        response["HX-Redirect"] = f"/s/customers/{customer.pk}/session/"
        return response
```

**HX-Redirect の仕様**: HTMX が `HX-Redirect` ヘッダーを検出すると、`window.location` によるフルページリダイレクトを実行する。モーダル内の HTMX 送信でもページ全体が遷移する。

### Slice 2

#### 6.4 SessionView

```python
# ui/staff/views/session.py

from datetime import date

from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.db.models import Subquery, OuterRef

from ui.mixins import StaffRequiredMixin, StoreMixin

# タスクフィールド設定（§3 コア層契約のマッピング）
TASK_FIELD_CONFIG = {
    "age": {
        "label": "年齢",
        "type": "selection",
        "choices": [
            ("10s", "10代"),
            ("20s", "20代"),
            ("30s", "30代"),
            ("40s", "40代"),
            ("50s_plus", "50代以上"),
        ],
    },
    "area": {
        "label": "居住エリア",
        "type": "text",
    },
    "shisha_experience": {
        "label": "シーシャ歴",
        "type": "selection",
        "choices": [
            ("none", "なし"),
            ("beginner", "初心者"),
            ("intermediate", "中級"),
            ("advanced", "上級"),
        ],
    },
}

# セグメント表示名マッピング
SEGMENT_DISPLAY = {
    "new": "新規",
    "repeat": "リピート",
    "regular": "常連",
}


class SessionView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, TemplateView):
    """接客画面。顧客情報 + タスク + メモ + 来店記録作成 + 直近来店。"""
    template_name = "ui/staff/session.html"
    login_url = "/s/login/"

    def get_context_data(self, **kwargs):
        from core.models import Customer, HearingTask, Visit

        context = super().get_context_data(**kwargs)
        customer_id = self.kwargs["pk"]

        customer = get_object_or_404(
            Customer.objects.for_store(self.store),
            pk=customer_id,
        )

        # 最終来店日（Subquery）
        last_visit_subquery = (
            Visit.objects.filter(customer=customer)
            .order_by("-visited_at")
            .values("visited_at")[:1]
        )

        # Open タスク一覧 + config 付与
        open_tasks = list(
            HearingTask.objects.for_store(self.store)
            .filter(customer=customer, status="open")
        )
        for task in open_tasks:
            task.config = TASK_FIELD_CONFIG.get(task.field_name, {})

        # 直近来店 5 件
        recent_visits = (
            Visit.objects.for_store(self.store)
            .filter(customer=customer)
            .select_related("staff")
            .order_by("-visited_at")[:5]
        )

        # 最終来店日を取得（recent_visits から取れるが明示的に）
        last_visited_at = recent_visits[0].visited_at if recent_visits else None

        # 来店記録ボタンは常に作成可能。同日複数来店は業務上正当（C-04 仕様）。

        # テンプレートが customer.segment_display を参照するため、customer オブジェクトに付与
        customer.segment_display = SEGMENT_DISPLAY.get(customer.segment, customer.segment)

        context["customer"] = customer
        context["last_visited_at"] = last_visited_at
        context["tasks"] = open_tasks
        context["recent_visits"] = recent_visits
        # visit_created は不要（ボタンは常にアクティブ）
        context["active_tab"] = "session"
        context["session_url"] = f"/s/customers/{customer.pk}/session/"
        return context
```

**BottomTab「接客」タブの URL**: `session_url` をコンテキストに渡し、`base_staff.html` の BottomTab テンプレートで使用する。US-01 時点で disabled だった接客タブを、US-02 S2 で `<a>` リンクに変更する。

**注意**: `base_staff.html` の BottomTab を以下のように変更する（US-02 S2 の実装スコープ）:

```
<!-- 接客タブ: US-02 S2 で有効化 -->
{% if session_url %}
  <a href="{{ session_url }}">{% include "ui/icons/message-circle.svg" %} 接客</a>
{% else %}
  <button disabled aria-disabled="true">{% include "ui/icons/message-circle.svg" %} 接客</button>
{% endif %}
```

#### 6.5 CustomerFieldUpdateView

```python
# ui/staff/views/session.py に追記

from django.views import View
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, QueryDict

from core.exceptions import BusinessError
from core.services.customer import CustomerService
from core.services.hearing import HearingTaskService
from ui.staff.forms.customer import CustomerFieldUpdateForm


class CustomerFieldUpdateView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, View):
    """HTMX PATCH: タスクゾーンのチップ選択 → 顧客フィールド更新 + タスク同期。"""
    login_url = "/s/login/"

    def patch(self, request, pk):
        from core.models import Customer, HearingTask

        customer = get_object_or_404(
            Customer.objects.for_store(self.store),
            pk=pk,
        )

        # Django は PATCH body を request.POST にパースしないため QueryDict で手動パース
        data = QueryDict(request.body)
        form = CustomerFieldUpdateForm(data)
        if not form.is_valid():
            # ValidationError: エラー内容を含む HTML フラグメントを 422 で返す
            response = render(request, "ui/staff/_zone_task.html", {
                "task": HearingTask.objects.for_store(self.store).filter(
                    customer=customer, field_name=data.get("field", "")
                ).first(),
                "config": TASK_FIELD_CONFIG.get(data.get("field", ""), {}),
                "customer": customer,
                "error": form.errors.as_text(),
            })
            response.status_code = 422
            return response

        field_name = form.cleaned_data["field"]
        value = form.cleaned_data["value"]

        # CustomerService で顧客フィールドを更新
        try:
            customer = CustomerService.update_customer(
                customer_id=customer.pk,
                **{field_name: value},
            )
        except BusinessError as e:
            # BusinessError: HX-Trigger でトーストにエラーメッセージを表示
            response = HttpResponse(status=422)
            response["HX-Trigger"] = '{"showToast": {"message": "更新に失敗しました", "type": "error"}}'
            return response

        # C-05a 契約: sync_tasks を明示呼び出し（auto_close → generate）
        HearingTaskService.sync_tasks(customer)

        # 更新後のタスク状態を確認
        remaining_tasks = (
            HearingTask.objects.for_store(self.store)
            .filter(customer=customer, status="open")
        )

        # 更新されたタスクを取得（sync_tasks 後は closed + 再生成 open が同居しうるため、
        # 最新の 1 件を取得する。open があれば open、なければ最新の closed）
        task = (
            HearingTask.objects.for_store(self.store)
            .filter(customer=customer, field_name=field_name)
            .order_by("-status", "-created_at")  # open > closed、新しい順
            .first()
        )
        task.config = TASK_FIELD_CONFIG.get(task.field_name, {})

        # 更新後の値が None（空文字正規化 or 明示的クリア）の場合は未入力状態に戻す
        actual_value = getattr(customer, field_name)
        is_filled = actual_value is not None and actual_value != ""

        response = render(request, "ui/staff/_zone_task.html", {
            "task": task,
            "config": task.config,
            "customer": customer,
            "filled": is_filled,
            "filled_label": self._get_filled_label(field_name, actual_value) if is_filled else "",
        })

        if not remaining_tasks.exists():
            # 全タスク完了: HX-Trigger で完了メッセージ表示
            # イベント名は kebab-case（all-tasks-done）で統一。Alpine.js の @all-tasks-done.window と一致
            response["HX-Trigger"] = "all-tasks-done"

        return response

    def _get_filled_label(self, field_name, value):
        """選択値の表示ラベルを返す。テキストフィールドはそのまま返す。"""
        config = TASK_FIELD_CONFIG.get(field_name, {})
        if config.get("type") == "selection":
            for choice_value, label in config.get("choices", []):
                if choice_value == value:
                    return label
        return value
```

**HTMX PATCH リクエストのボディパース**: Django は PATCH リクエストのボディを `request.POST` に自動パースしない。HTMX は `hx-patch` で `application/x-www-form-urlencoded` を送信するため、`QueryDict` で手動パースする。上記 View コード中の `request.POST` はこの手動パース結果に置き換えること:

```python
from django.http import QueryDict

class CustomerFieldUpdateView(...):
    def patch(self, request, pk):
        ...
        data = QueryDict(request.body)
        form = CustomerFieldUpdateForm(data)
        ...
```

この方式を `CustomerFieldUpdateView` で一貫して使用する。`request.POST` を PATCH で直接参照してはならない。

#### 6.6 VisitCreateView

```python
# ui/staff/views/visit.py

from datetime import date

from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse

from core.exceptions import BusinessError
from core.services.visit import VisitService
from ui.mixins import StaffRequiredMixin, StoreMixin
from ui.staff.forms.customer import VisitCreateForm


class VisitCreateView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, View):
    """HTMX POST: 来店記録作成 → ボタン差し替え + トースト。"""
    login_url = "/s/login/"

    def post(self, request):
        from core.models import Customer

        form = VisitCreateForm(request.POST)
        if not form.is_valid():
            # ValidationError: エラー HTML フラグメントを 422 で返す
            # customer_id が取れる場合は customer を渡して再送可能にする
            customer_id = request.POST.get("customer_id")
            customer = None
            if customer_id:
                customer = Customer.objects.for_store(self.store).filter(pk=customer_id).first()
            response = render(request, "ui/staff/_visit_button.html", {
                "customer": customer,
                "error": "入力内容に誤りがあります",
            })
            response.status_code = 422
            return response

        customer = get_object_or_404(
            Customer.objects.for_store(self.store),
            pk=form.cleaned_data["customer_id"],
        )

        memo = form.cleaned_data.get("conversation_memo", "")

        try:
            VisitService.create_visit(
                store=self.store,
                customer=customer,
                staff=request.user,
                visited_at=date.today(),
                conversation_memo=memo,
            )
        except BusinessError as e:
            # BusinessError: HX-Trigger でトーストにエラーメッセージを表示
            response = HttpResponse(status=422)
            response["HX-Trigger"] = '{"showToast": {"message": "来店記録の作成に失敗しました", "type": "error"}}'
            return response

        # 成功: ボタンを再利用可能な状態で再描画 + トースト + visitCreated
        # 同日複数来店が業務上正当のため、ボタンは無効化しない
        response = render(request, "ui/staff/_visit_button.html", {
            "customer": customer,
        })
        response["HX-Trigger"] = '{"showToast": {"message": "来店記録を作成しました", "type": "success"}, "visitCreated": {}}'
        return response
```

#### 6.7 SessionHeaderFragmentView / SessionRecentVisitsFragmentView

visitCreated イベントで呼ばれるフラグメント View。

```python
# ui/staff/views/session.py に追加

from django.shortcuts import get_object_or_404, render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from ui.mixins import StaffRequiredMixin, StoreMixin
from core.models import Customer, Visit

class SessionHeaderFragmentView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, View):
    """顧客ヘッダーのフラグメントを返す（visitCreated 後の部分更新用）"""
    login_url = "/s/login/"

    def get(self, request, pk):
        customer = get_object_or_404(Customer.objects.for_store(self.store), pk=pk)
        customer.segment_display = SEGMENT_DISPLAY.get(customer.segment, customer.segment)
        last_visited_at = (
            Visit.objects.filter(customer=customer)
            .order_by("-visited_at").values_list("visited_at", flat=True).first()
        )
        return render(request, "ui/staff/_customer_header.html", {
            "customer": customer, "last_visited_at": last_visited_at,
        })

class SessionRecentVisitsFragmentView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, View):
    """直近来店履歴のフラグメントを返す"""
    login_url = "/s/login/"

    def get(self, request, pk):
        customer = get_object_or_404(Customer.objects.for_store(self.store), pk=pk)
        recent_visits = (
            Visit.objects.for_store(self.store)
            .filter(customer=customer).select_related("staff")
            .order_by("-visited_at")[:5]
        )
        return render(request, "ui/staff/_recent_visits.html", {
            "recent_visits": recent_visits, "customer": customer,
        })
```

**`visitCreated` イベントによる画面更新**: 来店記録作成後、visit_count・segment・直近来店が古いデータのままになる。`HX-Trigger: visitCreated` を追加し、session.html 内の以下の要素が自動更新される:
- `#customer-header`: `hx-trigger="visitCreated from:body"` で顧客ヘッダーを再取得（visit_count、segment が最新になる）
- `#recent-visits`: `hx-trigger="visitCreated from:body"` で直近来店履歴を再取得

**HX-Trigger のトースト連携**: `base_staff.html` の Toast コンポーネントで `htmx:trigger` イベントをリッスンし、`showToast` イベントを受信したらトーストを表示する。

```javascript
// base_staff.html の Toast 実装
document.body.addEventListener("showToast", function(evt) {
    // Alpine.js の toast コンポーネントに message と type を渡す
    const detail = evt.detail || {};
    // Alpine.js のイベントバスで toast を表示
});
```

## 7. URL 設定

### HTMX 422 swap 許可（base.html への追加。US-01 設計書への波及）

HTMX はデフォルトで 2xx 以外のレスポンスを swap しない。422（バリデーションエラー）の HTML フラグメントを描画するため、`base.html` の CSRF スクリプトの後に以下を追加:

```html
<script>
  document.body.addEventListener("htmx:beforeSwap", function(evt) {
    if (evt.detail.xhr.status === 422) {
      evt.detail.shouldSwap = true;
      evt.detail.isError = false;
    }
  });
</script>
```

これにより 422 レスポンスも `hx-target` に swap される。

### ui/staff/urls.py（Slice 1 + Slice 2）

US-01 の stub を置き換え、新規 URL を追加する。

```python
from django.urls import path
from ui.staff.views.auth import LoginView, LogoutView
from ui.staff.views.customer import (
    CustomerSelectView, CustomerSearchView, CustomerCreateView,
)
from ui.staff.views.session import (
    SessionView, CustomerFieldUpdateView,
    SessionHeaderFragmentView, SessionRecentVisitsFragmentView,
)
from ui.staff.views.visit import VisitCreateView

app_name = "staff"

urlpatterns = [
    # US-01: 認証
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),

    # US-02 S1: 顧客選択（stub から差し替え）
    path("customers/", CustomerSelectView.as_view(), name="customers"),
    path("customers/search/", CustomerSearchView.as_view(), name="customer-search"),
    path("customers/new/", CustomerCreateView.as_view(), name="customer-create"),

    # US-02 S2: 接客画面
    path("customers/<uuid:pk>/session/", SessionView.as_view(), name="session"),
    path("customers/<uuid:pk>/field/", CustomerFieldUpdateView.as_view(), name="customer-field-update"),

    # US-02 S2: 来店記録作成
    path("visits/create/", VisitCreateView.as_view(), name="visit-create"),

    # US-02 S2: HTMX フラグメント（visitCreated 後の部分更新用）
    path("customers/<uuid:pk>/session/header/", SessionHeaderFragmentView.as_view(), name="session-header"),
    path("customers/<uuid:pk>/session/recent-visits/", SessionRecentVisitsFragmentView.as_view(), name="session-recent-visits"),
]
```

**変更点（US-01 からの差分）**:
- `StubCustomerView` の import を削除
- `customers/` パスを `CustomerSelectView` に差し替え
- `customers/search/`, `customers/new/` を追加（Slice 1）
- `customers/<uuid:pk>/session/`, `customers/<uuid:pk>/field/`, `visits/create/` を追加（Slice 2）

**stub.py の扱い**: `StubCustomerView` が不要になるため、`ui/staff/views/stub.py` を削除する。他の View が stub.py に存在しないことを確認の上で削除。

## 8. テストケース

### 8.1 Slice 1: Django TestClient

| # | テスト | 検証内容 |
|---|--------|---------|
| 1 | `test_customer_select_get` | GET `/s/customers/` → 200。`customer_select.html` 使用 |
| 2 | `test_customer_select_requires_auth` | 未認証で GET `/s/customers/` → 302 `/s/login/` |
| 3 | `test_customer_select_active_tab` | context に `active_tab == "customers"` |
| 4 | `test_customer_select_recent_order` | 来店日が新しい順に表示。来店なしの顧客は末尾 |
| 5 | `test_customer_select_limit_20` | 顧客が 25 人いる場合、20 件のみ返る |
| 6 | `test_customer_select_annotate_last_visited` | context の `customers` に `last_visited_at` が annotate されている |
| 7 | `test_customer_select_annotate_open_task_count` | context の `customers` に `open_task_count` が annotate されている |
| 8 | `test_customer_select_segment_badge` | レスポンスにセグメントバッジ（`badge-new`, `badge-repeat`, `badge-regular`）が含まれる |
| 9 | `test_customer_select_store_scope` | 他店舗の顧客が表示されない |
| 10 | `test_customer_select_empty` | 顧客ゼロ → 「顧客がまだ登録されていません」メッセージ |
| 11 | `test_customer_search_get` | GET `/s/customers/search/?q=山田` → 200。フラグメントHTML。名前に「山田」を含む顧客が返る |
| 12 | `test_customer_search_empty_query` | GET `/s/customers/search/?q=` → 200。空リスト |
| 13 | `test_customer_search_no_results` | GET `/s/customers/search/?q=存在しない` → 200。「見つかりませんでした」メッセージ |
| 14 | `test_customer_search_limit_20` | 検索結果が 25 件の場合、20 件のみ返る |
| 15 | `test_customer_search_store_scope` | 他店舗の顧客が検索結果に含まれない |
| 16 | `test_customer_create_get` | GET `/s/customers/new/` → 200。モーダルフォーム HTML |
| 17 | `test_customer_create_post_valid` | POST `/s/customers/new/` with name="テスト太郎" → 204。`HX-Redirect` ヘッダーが `/s/customers/<id>/session/` を指す。Customer レコードが作成されている。`segment='new'`, `visit_count=0` |
| 18 | `test_customer_create_generates_tasks` | POST 成功後、HearingTask が 3 件（age, area, shisha_experience）生成されている。全て `status='open'` |
| 19 | `test_customer_create_empty_name` | POST with name="" → 200。エラーメッセージ「名前を入力してください」 |
| 20 | `test_customer_create_requires_auth` | 未認証で POST → 302 `/s/login/` |
| 21 | `test_customer_card_link` | 顧客カードのリンク先が `/s/customers/<id>/session/` である |
| 22 | `test_customer_select_has_create_form` | レスポンスに新規登録フォーム（`hx-post="/s/customers/new/"` ）が含まれる |
| 23 | `test_customer_select_has_search_input` | レスポンスに検索入力（`hx-get="/s/customers/search/"` ）が含まれる |
| 24 | `test_create_customer_modal_error_no_double_nest` | POST `/s/customers/new/` with name="" → レスポンスにモーダルラッパー（`@click.away`）が含まれない（フォーム内容のみ返す）。`#create-modal-content` の二重ネストを防止 |

### 8.2 Slice 2: Django TestClient

| # | テスト | 検証内容 |
|---|--------|---------|
| 25 | `test_session_get` | GET `/s/customers/<id>/session/` → 200。`session.html` 使用 |
| 26 | `test_session_requires_auth` | 未認証で GET → 302 `/s/login/` |
| 27 | `test_session_active_tab` | context に `active_tab == "session"` |
| 28 | `test_session_customer_header` | レスポンスに顧客名・セグメントバッジ・来店回数が含まれる |
| 29 | `test_session_open_tasks` | Open タスクがある場合、タスクゾーンが表示される |
| 30 | `test_session_no_tasks` | 全タスク closed の場合、「全てのヒアリングが完了しています」メッセージ |
| 31 | `test_session_recent_visits` | 直近来店 5 件が表示される。6 件目以降は表示されない |
| 32 | `test_session_store_scope` | 他店舗の顧客 ID → 404 |
| 33 | `test_session_nonexistent_customer` | 存在しない顧客 ID → 404 |
| 34 | `test_session_session_url` | context に `session_url` が `/s/customers/<id>/session/` |
| 35 | `test_session_visit_button_always_active` | 本日の Visit が存在しても来店記録ボタンが表示される（同日複数来店が正当） |
| 36 | `test_field_update_patch` | PATCH `/s/customers/<id>/field/` with field=age, value=20s → 200。Customer.age == "20s"。HearingTask(field_name='age') の status == 'closed' |
| 37 | `test_field_update_invalid_field` | PATCH with field=invalid → 422 |
| 38 | `test_field_update_invalid_value` | PATCH with field=age, value=invalid → 422 |
| 39 | `test_field_update_text_field` | PATCH with field=area, value="渋谷" → 200。Customer.area == "渋谷" |
| 40 | `test_field_update_all_tasks_done` | 最後のタスクを完了 → レスポンスに `HX-Trigger: all-tasks-done` |
| 41 | `test_field_update_store_scope` | 他店舗の顧客 → 404 |
| 42 | `test_field_update_requires_auth` | 未認証で PATCH → 302 `/s/login/` |
| 43 | `test_field_update_area_empty_normalized_to_null` | PATCH with field=area, value="" → Customer.area is None（空文字列ではなく None に正規化される。C-05a 互換） |
| 44 | `test_patch_body_parsing` | PATCH with form-encoded body（`field=age&value=20s`）→ `QueryDict(request.body)` で正しくパースされ、Customer.age == "20s" |
| 45 | `test_visit_create_post` | POST `/s/visits/create/` with customer_id, conversation_memo → 200。Visit レコード作成。visited_at == today。staff == request.user |
| 46 | `test_visit_create_with_memo` | POST with conversation_memo="桃のフレーバーが好み" → Visit.conversation_memo に保存 |
| 47 | `test_visit_create_empty_memo` | POST with conversation_memo="" → Visit 作成成功。conversation_memo=="" |
| 48 | `test_visit_create_hx_trigger` | レスポンスに `HX-Trigger` ヘッダー（showToast）が含まれる |
| 49 | `test_visit_create_updates_count_and_segment` | POST 成功後、レスポンスの `HX-Trigger` に `visitCreated` イベントが含まれる |
| 50 | `test_session_header_fragment` | GET `/s/customers/<id>/session/header/` → 200、顧客名・visit_count を含む HTML フラグメント |
| 51 | `test_session_recent_visits_fragment` | GET `/s/customers/<id>/session/recent-visits/` → 200、来店履歴を含む HTML フラグメント |
| 52 | `test_session_header_fragment_store_scope` | 他店舗の顧客 ID → 404 |
| 53 | `test_visit_create_button_remains_active` | POST 成功後、レスポンスのボタンが再クリック可能（visit_created 分岐なし） |
| 54 | `test_visit_create_button_replaced` | レスポンスのボタンが再利用可能な状態で再描画される |
| 55 | `test_visit_create_invalid_customer` | POST with invalid customer_id → 404 |
| 56 | `test_visit_create_store_scope` | POST with 他店舗の顧客 → 404 |
| 57 | `test_visit_create_requires_auth` | 未認証で POST → 302 `/s/login/` |
| 58 | `test_visit_create_duplicate_same_day` | 同一顧客の同日2回目の POST → 成功（業務上正当。C-04 仕様） |
| 59 | `test_bottomtab_session_link` | 接客画面のレスポンスに接客タブのアクティブリンクが含まれる |
| 60 | `test_bottomtab_session_disabled_without_context` | 顧客選択画面（session_url なし）では接客タブが disabled のまま |

### 8.3 Browser smoke test

| # | 対象 URL | 手順 | 期待結果 |
|---|---------|------|---------|
| 1 | `/s/customers/` | 認証済みでアクセス | 顧客カード一覧表示。セグメントバッジ・来店回数・最終来店日あり |
| 2 | `/s/customers/` | 検索バータップ | モーダル起動。入力フィールドにフォーカス |
| 3 | (検索モーダル) | 「山田」と入力して 300ms 待つ | インクリメンタル検索結果がモーダル内に表示（ページ遷移なし） |
| 4 | (検索モーダル) | 検索結果の顧客カードタップ | `/s/customers/<id>/session/` に遷移 |
| 5 | `/s/customers/` | 新規登録ボタンタップ | 新規登録モーダル起動 |
| 6 | (新規登録モーダル) | 名前入力 → 「登録」 | 接客画面に遷移。URL が `/s/customers/<id>/session/` |
| 7 | `/s/customers/<id>/session/` | アクセス | 顧客ヘッダー + タスクゾーン + メモゾーン + 来店記録ボタン + 直近来店 |
| 8 | (接客画面) | タスクゾーンタップ | ゾーン展開。チップ表示 |
| 9 | (接客画面) | チップ選択（例: 年齢 → 20代） | HTMX PATCH → ゾーンが filled 状態（選択済みの値表示、再タップ不可）に変化（ページ遷移なし） |
| 10 | (接客画面) | メモゾーンタップ → テキスト入力 → 「完了」 | ゾーン折りたたみ。メモ内容が要約表示される |
| 11 | (接客画面) | 「来店記録を作成する」ボタンタップ | HTMX POST → トースト「来店記録を作成しました」表示。ボタンは再利用可能。顧客ヘッダー・来店履歴が自動更新 |
| 12 | (接客画面) | 全タスク消化後 | 「全てのヒアリングが完了しています」表示 |
| 13 | (接客画面) | BottomTab 確認 | 「接客」タブがアクティブ状態 |

## Review Log

- [2026-03-31] 初版作成
- [2026-03-31] レビュー F-01〜F-15 の 15 件を修正（R1）
  - F-01 (High): モーダルエラー時の hx-target を `#create-modal-content` に変更。フォーム内容を `_customer_create_form_content.html` で返し二重ネスト防止
  - F-02 (High): タスク完了レスポンスを統一。`_zone_task.html` を actual_value に基づく filled 判定（None/空文字なら False、それ以外なら True）で返す。空レスポンス削除
  - F-03 (High): イベント名を `all-tasks-done`（kebab-case）に統一。session.html に Alpine.js `@all-tasks-done.window` ハンドラー追加
  - F-04 (High): `segment_display` を CustomerSelectView / CustomerSearchView / SessionView の全てで customer オブジェクトに付与。SEGMENT_DISPLAY 共通化の注記追加
  - F-05 (High): QuerySet の order_by を `F("last_visited_at").desc(nulls_last=True)` に変更。Subquery 重複排除。逆参照名の注意書き追加
  - F-06 (High): 参照ドキュメントパスを実ファイル名（C04_VISIT_SEGMENT.md, C05A/C05B）に修正。import パス規約の注記追加。accounts.models → core.models に統一
  - F-07 (High): CustomerFieldUpdateForm.clean() で空文字列を None に正規化（NULLABLE_FIELDS）。value フィールドを required=False に変更
  - F-08 (High): VisitCreateView のレスポンスに `visitCreated` イベント追加。session.html の顧客ヘッダーと直近来店に `hx-trigger="visitCreated from:body"` 追加
  - F-09 (Medium): _visit_button.html の静的 hx-vals 削除。Alpine `:hx-vals` のみ残す
  - F-10 (Medium): PATCH body パースを `QueryDict(request.body)` に確定。View コードと説明文の両方を修正。矛盾する記述削除
  - F-11 (Medium): CustomerFieldUpdateView と VisitCreateView のエラー UX 改善。ValidationError → エラー HTML 422、BusinessError → HX-Trigger トースト 422
  - F-12 (Medium): SessionView に `visit_created` コンテキスト追加。本日の Visit 存在チェックで初期状態を決定。`from datetime import date` 追加
  - F-13 (Medium): _recent_visits.html の各エントリを `<a href="/s/customers/<id>/visits/">` でラップしてクリッカブルに
  - F-14 (Medium): 検索モーダルに `x-effect` + `$nextTick` + `$refs.searchInput.focus()` でオープン時自動フォーカス。autofocus → x-ref に変更
  - F-15 (Medium): テストケース 5 件追加（#24 modal error no double nest, #35 visit_created initial state, #43 area empty normalized to null, #44 patch body parsing, #49 visit create updates count and segment）。既存テスト番号を再採番
- [2026-03-31] Codex 2回目レビュー (gpt-5.4 high): 66/100 FAIL。6 件を修正
  - F-16 (high): visitCreated の再取得先 URL（session/header/, session/recent-visits/）を urls.py に追加。SessionHeaderFragmentView / SessionRecentVisitsFragmentView を新設
  - F-17 (high): allTasksDone → all-tasks-done（kebab-case）に統一。HX-Trigger と Alpine @all-tasks-done.window が一致
  - F-18 (high): _zone_task.html に filled 分岐・error 表示・テキスト型ゾーンを追加。id="zone-{field_name}" でラップ
  - F-19 (high): 空文字→None 時の filled 判定を修正。actual_value が None/空文字なら filled=False を返す。C-05a のタスク再生成と整合
  - F-20 (medium): _visit_button.html にエラー表示領域を追加
  - F-21 (low): Review Log のテスト追加件数を「4 件」→「5 件」に修正
- [2026-03-31] Codex 3回目レビュー findings 5 件を修正（R3）
  - F-22 (High): session.html のタスクゾーン id 重複を修正。session.html のラッパー div から id="zone-{field_name}" を除去し、_zone_task.html 側の id のみに統一
  - F-23 (High): _zone_task.html のテキスト型ゾーン重複ブロックを削除。filled/selection/text の if/elif チェーン内のもののみ残す
  - F-24 (High): allTasksDone（camelCase）を all-tasks-done（kebab-case）に全箇所統一。テンプレートコメント・説明文・テスト期待値・Review Log を修正
  - F-25 (Medium): 顧客ヘッダーを _customer_header.html に抽出。session.html を {% include %} に変更。ファイル構成・テンプレートセクション（§4.6）を追加。SessionHeaderFragmentView が同テンプレートを返す
  - F-26 (Medium): 「常に filled=True を返す」の記述を修正。actual_value が None/空文字なら filled=False、それ以外なら filled=True を返す実際のロジックに更新
- [2026-03-31] Codex 4回目レビュー (gpt-5.4 high): 64/100 FAIL。4 件を修正
  - F-27 (high): 同日複数来店を許可する設計に合わせ、visit_created の初期値を常に False に変更。ボタンは作成 POST 後の差し替えでのみ「作成済み」になる
  - F-28 (high): HearingTask の取得を get() → filter().order_by().first() に変更。sync_tasks 後の closed + open 同居で MultipleObjectsReturned を回避
  - F-29 (high): base.html に htmx:beforeSwap で 422 を swap 許可するスクリプトを追加（US-01 設計書にも波及）
  - F-30 (medium): VisitCreateView のバリデーションエラー時に customer を渡して再送可能にする
- [2026-03-31] Codex 5回目レビュー (gpt-5.4 high): 68/100 FAIL。5 件を修正
  - F-31 (high): 来店記録ボタンを作成後も再利用可能に変更。visit_created 分岐・ボタン無効化を削除。同日複数来店の業務ルールと整合
  - F-32 (high): テスト #35 を「ボタンが常にアクティブ」に修正。旧 visit_created テストを削除
  - F-33 (high): SessionHeaderFragmentView / SessionRecentVisitsFragmentView に import を追加（Customer, Visit, get_object_or_404 等）
  - F-34 (medium): フラグメント endpoint のテスト 4 件追加（header fragment 200, recent-visits fragment 200, store scope 404, ボタン再利用可能）
  - F-35 (medium): 直近来店履歴のリンクを表示のみに変更（US-03 まで遷移先なし）
- [2026-03-31] Codex 6回目レビュー (gpt-5.4 high): 84/100 CONDITIONAL。4 件を修正
  - F-36 (high): US-02 設計書内の旧仕様残骸をクリーンアップ。「作成済み」表記・visit_created 分岐・smoke test #11 を修正
  - F-37 (high): UI_BASIC_DESIGN.md の来店記録仕様を「ボタン再利用可能 + visitCreated」に更新。直近来店タップも「US-03 で実装」に修正
  - F-38 (medium): テスト採番の重複（#50-53 が 2 セット）を修正。#54-60 に再採番
  - F-39 (low): SessionView から visit_created コンテキスト変数を完全削除
- [2026-03-31] Codex 7回目レビュー (gpt-5.4 high): **95/100 PASS**
