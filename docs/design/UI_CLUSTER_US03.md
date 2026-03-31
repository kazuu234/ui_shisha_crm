# US-03 詳細設計書: Customer Detail + Edit + Visit History

> 基本設計書: `docs/design/UI_BASIC_DESIGN.md` §5 US-03, §7.3
> デザインガイド: `docs/design/UI_DESIGN_GUIDE.md`
> パイプライン: `docs/design/UI_PIPELINE.md` #5

## 1. 概要

### Slice 情報

| 項目 | 内容 |
|------|------|
| **Cluster** | US-03 (顧客・来店簡易管理) |
| **Slice** | S1（単一 Slice で完結） |
| **パイプライン順序** | #5 / 13 |
| **ブランチ説明部** | `us03-customer-detail` |

### スコープ

顧客詳細画面（全属性 + セグメントバッジ + 直近来店 5 件）、顧客編集画面（ゾーンベースの即保存 UI、全顧客フィールド対応）、来店履歴一覧画面（表示のみ、直近 20 件）。3 画面はいずれも軽量な補助画面群であり、1 Slice で完結する。

### precondition

- US-01 S1 完了（`base_staff.html`、`LoginRequiredMixin`、`StaffRequiredMixin`、`StoreMixin` が動作）
- コア層 C-03 完了（Customer モデル + `CustomerService` が動作）
- コア層 C-04 S2 完了（`VisitService`、Visit モデルが動作）
- コア層 C-05a 完了（`HearingTaskService.sync_tasks()` が動作。顧客編集時のタスク同期に必要）

### postcondition

- `/s/customers/<id>/` で顧客の全属性（name, segment badge, visit_count, age, area, shisha_experience, line_id, memo）+ 直近来店 5 件が表示される
- `/s/customers/<id>/edit/` でゾーンベースの編集が可能。各ゾーンの変更が hx-patch で即保存される
- ヒアリング対象項目（age, area, shisha_experience）の編集後に `HearingTaskService.sync_tasks()` が呼ばれ、タスクが auto close / 再生成される
- 非ヒアリング項目（name, line_id, memo）の編集は sync_tasks を呼ばない
- `/s/customers/<id>/visits/` で直近 20 件の来店記録が時系列で表示される（表示のみ、編集・削除不可）
- 全 View が `base_staff.html` を継承し、BottomTab 付き
- BottomTab: 詳細・編集画面では「顧客」タブがアクティブ。来店履歴画面でも「顧客」タブをアクティブにする（来店記録の専用タブ `/s/visits/` は未実装のため）
- 「来店記録」タブは引き続き disabled のまま（顧客スコープの `/s/customers/<id>/visits/` は存在するが、グローバルな `/s/visits/` は存在しない）

## 2. ファイル構成

```
ui/
├── staff/
│   ├── urls.py                      # 3 URL 追加（detail, edit, visit-list）
│   ├── views/
│   │   ├── customer.py              # CustomerDetailView, CustomerEditView, CustomerEditFieldView を追記
│   │   └── visit.py                 # VisitListView を追記
│   └── forms/
│       └── customer.py              # CustomerEditFieldForm を追記
├── templates/ui/
│   └── staff/
│       ├── customer_detail.html     # 顧客詳細画面
│       ├── customer_edit.html       # 顧客編集画面（全ゾーン含む）
│       ├── _zone_edit_name.html     # 名前ゾーンフラグメント（HTMX PATCH 後の差し替え用）
│       ├── _zone_edit_age.html      # 年齢ゾーンフラグメント
│       ├── _zone_edit_area.html     # 居住エリアゾーンフラグメント
│       ├── _zone_edit_exp.html      # シーシャ歴ゾーンフラグメント
│       ├── _zone_edit_line_id.html  # LINE ID ゾーンフラグメント
│       ├── _zone_edit_memo.html     # メモゾーンフラグメント
│       └── visit_list.html          # 来店履歴一覧画面
```

**追加するアイコン**: なし（US-01 で作成済みのアイコンで足りる）。

## 3. コア層契約

正式な定義は `docs/reference/cluster/C03_CUSTOMER.md`、`docs/reference/cluster/C04_VISIT_SEGMENT.md`、`docs/reference/cluster/C05A_HEARING_TASK_CORE.md` を参照。

**import パスについて**: コア層は別リポジトリ（別 Django app）として管理されている場合がある。本設計書では `from core.services.customer import CustomerService` のような統一的な記法を使用するが、実際の import パスはコア層のパッケージ構造に依存する。実装時にコア層の `__init__.py` や実際のモジュール配置を確認すること。

### CustomerService

| メソッド | 引数 | 返り値 | 例外 |
|---------|------|--------|------|
| `update_customer(customer_id, **fields)` | `UUID, **kwargs` | `Customer` | `BusinessError(customer.not_found)` |

**`update_customer` が受け付けるフィールド**: `name`, `age`, `area`, `shisha_experience`, `line_id`, `memo`。

### HearingTaskService

| メソッド | 引数 | 返り値 | 備考 |
|---------|------|--------|------|
| `sync_tasks(customer)` | `Customer` | synced tasks | auto_close → generate の順に実行。ヒアリング対象フィールド変更時に呼ぶ。フィールド空戻し時のタスク再生成にも対応（C-05a 設計） |

**ヒアリング対象フィールド（sync_tasks トリガー対象）**: `age`, `area`, `shisha_experience`。これら以外のフィールド（`name`, `line_id`, `memo`）の変更では sync_tasks を呼ばない。

### Customer モデル（UI が参照するフィールド）

| フィールド | 型 | 備考 |
|-----------|-----|------|
| `name` | CharField | 表示名 |
| `segment` | CharField (`new` / `repeat` / `regular`) | セグメントバッジ表示に使用 |
| `visit_count` | PositiveIntegerField | 来店回数 |
| `age` | IntegerField (nullable) | ヒアリング対象。整数値（C-03 契約準拠: `age?: int`） |
| `area` | CharField (nullable) | ヒアリング対象。テキスト入力 |
| `shisha_experience` | CharField (nullable) | ヒアリング対象。選択肢: `none`, `beginner`, `intermediate`, `advanced` |
| `line_id` | CharField (nullable) | LINE ID |
| `memo` | TextField (nullable) | 顧客メモ |
| `store` | ForeignKey(Store) | 店舗スコープ |

**StoreScopedManager**: `Customer.objects.for_store(store)` でストアスコープフィルタを適用。

### Visit モデル（UI が参照するフィールド）

| フィールド | 型 | 備考 |
|-----------|-----|------|
| `customer` | ForeignKey(Customer) | 対象顧客 |
| `staff` | ForeignKey(Staff) | 対応スタッフ |
| `visited_at` | DateField | 来店日 |
| `conversation_memo` | TextField (nullable) | 会話メモ |
| `created_at` | DateTimeField (auto_now_add) | 作成日時。同日来店の安定ソート副キーとして使用 |

**StoreScopedManager**: `Visit.objects.for_store(store)` でストアスコープフィルタを適用。

### 編集フィールド設定マッピング

顧客編集画面の全ゾーンで使用する設定。View と テンプレートの両方で参照する。US-02 S2 の `TASK_FIELD_CONFIG`（ヒアリング対象のみ）とは異なり、全顧客フィールドを網羅する。

```python
# ui/staff/views/customer.py

EDIT_FIELD_CONFIG = {
    "name": {
        "label": "名前",
        "type": "text",
        "placeholder": "顧客の名前",
        "is_hearing": False,
    },
    "age": {
        "label": "年齢",
        "type": "number",
        "placeholder": "例: 25",
        "is_hearing": True,
    },
    "area": {
        "label": "居住エリア",
        "type": "text",
        "placeholder": "例: 渋谷",
        "is_hearing": True,
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
        "is_hearing": True,
    },
    "line_id": {
        "label": "LINE ID",
        "type": "text",
        "placeholder": "LINE ID を入力",
        "is_hearing": False,
    },
    "memo": {
        "label": "メモ",
        "type": "textarea",
        "placeholder": "顧客に関するメモ",
        "is_hearing": False,
    },
}

# ヒアリング対象フィールド（sync_tasks トリガー対象）
HEARING_FIELDS = {k for k, v in EDIT_FIELD_CONFIG.items() if v.get("is_hearing")}

# nullable フィールド（空文字 → None に正規化する対象）
NULLABLE_FIELDS = {"age", "area", "shisha_experience", "line_id", "memo"}
```

### セグメント表示名マッピング

US-02 で定義済みの `SEGMENT_DISPLAY` を再利用する。共通定数として `ui/staff/constants.py` に配置することを推奨するが、US-03 時点では既存コードの配置に従う。

```python
SEGMENT_DISPLAY = {"new": "新規", "repeat": "リピート", "regular": "常連"}
```

## 4. テンプレート

### 4.1 staff/customer_detail.html

`base_staff.html` を継承。顧客の全属性と直近来店 5 件を表示する読み取り専用画面。

```
{% extends "ui/base_staff.html" %}
{% load static %}

{% block page_title %}{{ customer.name }}{% endblock %}

{% block content %}
  <!-- 顧客情報カード -->
  <div>  <!-- bg-bg-surface, shadow-sm, rounded-md, p-5, mb-4 -->

    <!-- 上段: セグメントバッジ + 名前 + 編集ボタン -->
    <div>  <!-- flex items-center justify-between -->
      <div>
        <span class="badge-{{ customer.segment }}">{{ customer.segment_display }}</span>
        <span>{{ customer.name }}</span>  <!-- text-lg, font-semibold -->
      </div>
      <a href="/s/customers/{{ customer.id }}/edit/">  <!-- accent テキスト -->
        編集
      </a>
    </div>

    <!-- 来店回数 -->
    <div>  <!-- text-text-secondary, text-sm, mt-2 -->
      来店 {{ customer.visit_count }} 回
    </div>

    <!-- 属性一覧 -->
    <dl>  <!-- mt-4, divide-y divide-border-default -->
      <!-- 年齢 -->
      <div>  <!-- py-3, flex justify-between -->
        <dt>年齢</dt>  <!-- text-text-secondary -->
        <dd>{{ customer.age_display|default:"未入力" }}</dd>
      </div>

      <!-- 居住エリア -->
      <div>
        <dt>居住エリア</dt>
        <dd>{{ customer.area|default:"未入力" }}</dd>
      </div>

      <!-- シーシャ歴 -->
      <div>
        <dt>シーシャ歴</dt>
        <dd>{{ customer.shisha_experience_display|default:"未入力" }}</dd>
      </div>

      <!-- LINE ID -->
      <div>
        <dt>LINE ID</dt>
        <dd>{{ customer.line_id|default:"未入力" }}</dd>
      </div>

      <!-- メモ -->
      <div>
        <dt>メモ</dt>
        <dd>{{ customer.memo|default:"未入力" }}</dd>  <!-- whitespace-pre-wrap -->
      </div>
    </dl>
  </div>

  <!-- 直近来店セクション -->
  <div>  <!-- mt-6 -->
    <div>  <!-- flex items-center justify-between, mb-3 -->
      <h2>直近の来店</h2>  <!-- text-base, font-semibold -->
      {% if recent_visits %}
        <a href="/s/customers/{{ customer.id }}/visits/">  <!-- accent テキスト, text-sm -->
          すべて見る
        </a>
      {% endif %}
    </div>

    <div>  <!-- bg-bg-surface, shadow-sm, rounded-md -->
      {% for visit in recent_visits %}
        <div>  <!-- py-3, px-5, border-b border-border-default, last:border-b-0 -->
          <div>
            <span>{{ visit.visited_at|date:"Y/n/j" }}</span>  <!-- font-medium -->
            <span>{{ visit.staff.display_name }}</span>  <!-- text-text-secondary, text-sm -->
          </div>
          {% if visit.conversation_memo %}
            <p>  <!-- text-text-secondary, text-sm, mt-1, truncate -->
              {{ visit.conversation_memo|truncatechars:50 }}
            </p>
          {% endif %}
        </div>
      {% empty %}
        <div>  <!-- text-center, text-text-secondary, py-8, px-5 -->
          <p>来店記録はまだありません</p>
        </div>
      {% endfor %}
    </div>
  </div>
{% endblock %}
```

**「すべて見る」リンク**: 来店が 1 件以上ある場合のみ表示。`/s/customers/<id>/visits/` に遷移。

**属性の表示ラベル**: `age` は整数値のため `age_display`（例: "25歳"）、`shisha_experience` は選択値のため `shisha_experience_display` を View で customer オブジェクトに付与する。`area`, `line_id`, `memo` はそのまま表示。未入力（None）の場合は「未入力」と表示する。

### 4.2 staff/customer_edit.html

`base_staff.html` を継承。ゾーンベースの編集画面。各ゾーンは独立した HTMX PATCH で即保存される。

```
{% extends "ui/base_staff.html" %}
{% load static %}

{% block page_title %}{{ customer.name }} を編集{% endblock %}

{% block content %}
  <!-- 戻るボタン -->
  <div>  <!-- mb-4 -->
    <a href="/s/customers/{{ customer.id }}/">  <!-- text-accent, flex items-center -->
      ← 戻る
    </a>
  </div>

  <!-- 編集ゾーングループ -->
  <div>  <!-- bg-bg-surface, shadow-sm, rounded-md, divide-y divide-border-default -->
    {% include "ui/staff/_zone_edit_name.html" with customer=customer config=name_config %}
    {% include "ui/staff/_zone_edit_age.html" with customer=customer config=age_config %}
    {% include "ui/staff/_zone_edit_area.html" with customer=customer config=area_config %}
    {% include "ui/staff/_zone_edit_exp.html" with customer=customer config=exp_config %}
    {% include "ui/staff/_zone_edit_line_id.html" with customer=customer config=line_id_config %}
    {% include "ui/staff/_zone_edit_memo.html" with customer=customer config=memo_config %}
  </div>
{% endblock %}
```

**ゾーンの並び順**: name → age → area → shisha_experience → line_id → memo。基本設計書の記載順に従う。

### 4.3 staff/_zone_edit_name.html

名前ゾーン。テキスト入力型。名前は必須フィールドのため、空文字送信時にエラーを返す。

> **基本設計書との差異（F-05）**: 基本設計書は「名前（テキスト、モーダル）」と記載しているが、他のゾーンとの一貫性のためインライン展開型で実装する。基本設計書を参照する際はこの詳細設計が優先する。

```
{% load static %}

<div id="zone-name">  <!-- p-4 -->

  {% if error %}
    <div>  <!-- error-subtle 背景, error テキスト, rounded-sm, p-2, mb-2 -->
      <p>{{ error }}</p>
    </div>
  {% endif %}

  <div x-data="{ editing: false, val: '{{ customer.name|escapejs }}' }">
    <!-- 表示状態 -->
    <div x-show="!editing" @click="editing = true; $nextTick(() => $refs.nameInput.focus())">
      <span>{{ config.label }}</span>  <!-- text-text-secondary, text-sm -->
      <span>{{ customer.name }}</span>  <!-- font-medium -->
      <span>タップして編集 ▸</span>  <!-- text-text-muted, text-xs -->
    </div>

    <!-- 編集状態 -->
    <div x-show="editing" x-transition>
      <label>{{ config.label }}</label>  <!-- text-text-secondary, text-sm -->
      <input type="text"
             x-model="val"
             x-ref="nameInput"
             placeholder="{{ config.placeholder }}"
             class="w-full border border-border-default rounded-sm p-3 mt-1">
      <div>  <!-- flex gap-2, mt-2 -->
        <button
          hx-patch="/s/customers/{{ customer.id }}/edit/field/"
          :hx-vals="JSON.stringify({field: 'name', value: val})"
          hx-target="#zone-name"
          hx-swap="outerHTML">
          保存
        </button>
        <button type="button" @click="editing = false">
          キャンセル
        </button>
      </div>
    </div>
  </div>
</div>
```

**名前のバリデーション**: `CustomerEditFieldForm` で `name` フィールドの空文字を拒否する（`name` は `NULLABLE_FIELDS` に含まれないため、空文字 → None 正規化は行わない）。

### 4.4 staff/_zone_edit_age.html

年齢ゾーン。数値入力型（C-03 契約準拠: `age?: int`）。

```
{% load static %}

<div id="zone-age">  <!-- p-4 -->

  {% if error %}
    <div>  <!-- error-subtle, rounded-sm, p-2, mb-2 -->
      <p>{{ error }}</p>
    </div>
  {% endif %}

  <div x-data="{ open: false, val: '{{ customer.age|default:""|escapejs }}' }">
    <!-- 表示状態 -->
    <div @click="open = !open; if (open) $nextTick(() => $refs.ageInput.focus())">
      <span>{{ config.label }}</span>  <!-- text-text-secondary, text-sm -->
      {% if customer.age is not None %}
        <span>{{ customer.age_display }}</span>  <!-- font-medium -->
      {% else %}
        <span>タップして入力 ▸</span>  <!-- text-text-muted, text-xs -->
      {% endif %}
    </div>

    <!-- 編集状態: 数値入力 -->
    <div x-show="open" x-transition>
      <input type="number"
             x-model="val"
             x-ref="ageInput"
             placeholder="{{ config.placeholder }}"
             min="0"
             max="150"
             class="w-full border border-border-default rounded-sm p-3 mt-1">
      <div>  <!-- flex gap-2, mt-2 -->
        <button
          hx-patch="/s/customers/{{ customer.id }}/edit/field/"
          :hx-vals="JSON.stringify({field: 'age', value: val})"
          hx-target="#zone-age"
          hx-swap="outerHTML">
          保存
        </button>
        <button type="button" @click="open = false">
          キャンセル
        </button>
      </div>
    </div>
  </div>
</div>
```

**数値入力**: `type="number"` で整数のみ入力可能。空送信は Form で None に正規化 → `sync_tasks` でタスク再生成。

### 4.5 staff/_zone_edit_area.html

居住エリアゾーン。テキスト入力型。

```
{% load static %}

<div id="zone-area">  <!-- p-4 -->

  {% if error %}
    <div>  <!-- error-subtle, rounded-sm, p-2, mb-2 -->
      <p>{{ error }}</p>
    </div>
  {% endif %}

  <div x-data="{ open: false, val: '{{ customer.area|default:""|escapejs }}' }">
    <!-- 表示状態 -->
    <div @click="open = !open; if (open) $nextTick(() => $refs.areaInput.focus())">
      <span>{{ config.label }}</span>
      {% if customer.area %}
        <span>{{ customer.area }}</span>
      {% else %}
        <span>タップして入力 ▸</span>
      {% endif %}
    </div>

    <!-- 編集状態 -->
    <div x-show="open" x-transition>
      <input type="text"
             x-model="val"
             x-ref="areaInput"
             placeholder="{{ config.placeholder }}"
             class="w-full border border-border-default rounded-sm p-3 mt-1">
      <div>  <!-- flex gap-2, mt-2 -->
        <button
          hx-patch="/s/customers/{{ customer.id }}/edit/field/"
          :hx-vals="JSON.stringify({field: 'area', value: val})"
          hx-target="#zone-area"
          hx-swap="outerHTML">
          保存
        </button>
        <button type="button" @click="open = false">
          キャンセル
        </button>
      </div>
    </div>
  </div>
</div>
```

### 4.6 staff/_zone_edit_exp.html

シーシャ歴ゾーン。選択型。構造は `_zone_edit_age.html` と同一パターン。

```
{% load static %}

<div id="zone-shisha_experience">  <!-- p-4 -->

  {% if error %}
    <div>  <!-- error-subtle, rounded-sm, p-2, mb-2 -->
      <p>{{ error }}</p>
    </div>
  {% endif %}

  <div x-data="{ open: false }">
    <div @click="open = !open">
      <span>{{ config.label }}</span>
      {% if customer.shisha_experience %}
        <span>{{ customer.shisha_experience_display }}</span>
      {% else %}
        <span>タップして選択 ▸</span>
      {% endif %}
    </div>

    <div x-show="open" x-transition>
      {% for value, label in config.choices %}
        <button
          hx-patch="/s/customers/{{ customer.id }}/edit/field/"
          hx-vals='{"field": "shisha_experience", "value": "{{ value }}"}'
          hx-target="#zone-shisha_experience"
          hx-swap="outerHTML"
          class="chip {% if customer.shisha_experience == value %}chip-active{% endif %}">
          {{ label }}
        </button>
      {% endfor %}
      {% if customer.shisha_experience %}
        <button
          hx-patch="/s/customers/{{ customer.id }}/edit/field/"
          hx-vals='{"field": "shisha_experience", "value": ""}'
          hx-target="#zone-shisha_experience"
          hx-swap="outerHTML"
          class="chip chip-clear">
          クリア
        </button>
      {% endif %}
    </div>
  </div>
</div>
```

### 4.7 staff/_zone_edit_line_id.html

LINE ID ゾーン。テキスト入力型。構造は `_zone_edit_area.html` と同一パターン。

```
{% load static %}

<div id="zone-line_id">  <!-- p-4 -->

  {% if error %}
    <div>  <!-- error-subtle, rounded-sm, p-2, mb-2 -->
      <p>{{ error }}</p>
    </div>
  {% endif %}

  <div x-data="{ open: false, val: '{{ customer.line_id|default:""|escapejs }}' }">
    <div @click="open = !open; if (open) $nextTick(() => $refs.lineIdInput.focus())">
      <span>{{ config.label }}</span>
      {% if customer.line_id %}
        <span>{{ customer.line_id }}</span>
      {% else %}
        <span>タップして入力 ▸</span>
      {% endif %}
    </div>

    <div x-show="open" x-transition>
      <input type="text"
             x-model="val"
             x-ref="lineIdInput"
             placeholder="{{ config.placeholder }}"
             class="w-full border border-border-default rounded-sm p-3 mt-1">
      <div>
        <button
          hx-patch="/s/customers/{{ customer.id }}/edit/field/"
          :hx-vals="JSON.stringify({field: 'line_id', value: val})"
          hx-target="#zone-line_id"
          hx-swap="outerHTML">
          保存
        </button>
        <button type="button" @click="open = false">
          キャンセル
        </button>
      </div>
    </div>
  </div>
</div>
```

### 4.8 staff/_zone_edit_memo.html

メモゾーン。テキストエリア型。

```
{% load static %}

<div id="zone-memo">  <!-- p-4 -->

  {% if error %}
    <div>  <!-- error-subtle, rounded-sm, p-2, mb-2 -->
      <p>{{ error }}</p>
    </div>
  {% endif %}

  <div x-data="{ open: false, val: '{{ customer.memo|default:""|escapejs }}' }">
    <div @click="open = !open; if (open) $nextTick(() => $refs.memoInput.focus())">
      <span>{{ config.label }}</span>
      {% if customer.memo %}
        <span>{{ customer.memo|truncatechars:30 }}</span>
      {% else %}
        <span>タップして入力 ▸</span>
      {% endif %}
    </div>

    <div x-show="open" x-transition>
      <textarea x-model="val"
                x-ref="memoInput"
                placeholder="{{ config.placeholder }}"
                rows="4"
                class="w-full border border-border-default rounded-sm p-3 mt-1">
      </textarea>
      <div>
        <button
          hx-patch="/s/customers/{{ customer.id }}/edit/field/"
          :hx-vals="JSON.stringify({field: 'memo', value: val})"
          hx-target="#zone-memo"
          hx-swap="outerHTML">
          保存
        </button>
        <button type="button" @click="open = false">
          キャンセル
        </button>
      </div>
    </div>
  </div>
</div>
```

### 4.9 staff/visit_list.html

`base_staff.html` を継承。来店履歴一覧。表示のみ（スタッフ UI では来店の編集・削除はできない）。

```
{% extends "ui/base_staff.html" %}
{% load static %}

{% block page_title %}{{ customer.name }} の来店履歴{% endblock %}

{% block content %}
  <!-- 戻るボタン -->
  <div>  <!-- mb-4 -->
    <a href="/s/customers/{{ customer.id }}/">
      ← {{ customer.name }}
    </a>
  </div>

  <!-- 来店一覧 -->
  <div>  <!-- bg-bg-surface, shadow-sm, rounded-md -->
    {% for visit in visits %}
      <div>  <!-- py-3, px-5, border-b border-border-default, last:border-b-0 -->
        <div>  <!-- flex items-center justify-between -->
          <span>{{ visit.visited_at|date:"Y/n/j" }}</span>  <!-- font-medium -->
          <span>{{ visit.staff.display_name }}</span>  <!-- text-text-secondary, text-sm -->
        </div>
        {% if visit.conversation_memo %}
          <p>  <!-- text-text-secondary, text-sm, mt-1 -->
            {{ visit.conversation_memo|truncatechars:50 }}
          </p>
        {% endif %}
      </div>
    {% empty %}
      <div>  <!-- text-center, text-text-secondary, py-8, px-5 -->
        <p>来店記録はまだありません</p>
      </div>
    {% endfor %}
  </div>
{% endblock %}
```

**表示制限**: 直近 20 件。ページネーションは MVP では実装しない（20 件表示で十分）。

## 5. Form 定義

### 5.1 CustomerEditFieldForm

編集画面からの HTMX PATCH で送信されるフォーム。`field` と `value` のバリデーションを行う。US-02 S2 の `CustomerFieldUpdateForm` を拡張し、全顧客フィールド（ヒアリング対象 + 非ヒアリング対象）に対応する。

```python
# ui/staff/forms/customer.py に追記

EDIT_FIELD_CHOICES = {
    "name": None,          # テキスト入力。必須（空文字不可）
    "age": "int",          # 整数入力（C-03 契約準拠: age?: int）
    "area": None,          # テキスト入力
    "shisha_experience": ["none", "beginner", "intermediate", "advanced"],
    "line_id": None,       # テキスト入力
    "memo": None,          # テキストエリア入力
}


class CustomerEditFieldForm(forms.Form):
    field = forms.CharField(max_length=50)
    value = forms.CharField(required=False)  # max_length なし。MVP では UI 上限を設けない（F-07）。空文字許可

    # nullable なフィールド: 空文字列を None に正規化する対象
    NULLABLE_FIELDS = {"age", "area", "shisha_experience", "line_id", "memo"}

    def clean(self):
        cleaned = super().clean()
        field_name = cleaned.get("field")
        value = cleaned.get("value")

        if field_name not in EDIT_FIELD_CHOICES:
            raise forms.ValidationError(f"無効なフィールド: {field_name}")

        # name は必須。空文字を拒否
        if field_name == "name":
            if not value or not value.strip():
                raise forms.ValidationError("名前を入力してください")
            cleaned["value"] = value.strip()
            return cleaned

        # テキスト系フィールド: strip() してから空判定（F-02: 空白のみ入力の正規化）
        if value is not None and isinstance(value, str):
            value = value.strip()
            cleaned["value"] = value

        # nullable フィールド: 空文字列を None に正規化（C-05a 互換）
        if field_name in self.NULLABLE_FIELDS and (value is None or value == ""):
            cleaned["value"] = None
            return cleaned

        # age フィールド: 整数バリデーション（C-03 契約準拠: age?: int）
        if field_name == "age":
            try:
                cleaned["value"] = int(value)
            except (ValueError, TypeError):
                raise forms.ValidationError("年齢は整数で入力してください")
            if cleaned["value"] < 0 or cleaned["value"] > 150:
                raise forms.ValidationError("年齢は 0〜150 の範囲で入力してください")
            return cleaned

        # 選択型フィールド: 許可された値のみ受け付け
        allowed = EDIT_FIELD_CHOICES[field_name]
        if isinstance(allowed, list) and value not in allowed:
            raise forms.ValidationError(f"無効な値: {value}")

        return cleaned
```

**US-02 S2 の `CustomerFieldUpdateForm` との関係**: US-02 S2 はヒアリング対象フィールドのみを扱う。US-03 S1 ではヒアリング対象 + 非ヒアリング対象の全フィールドを扱う。`CustomerEditFieldForm` は `CustomerFieldUpdateForm` の上位互換であるが、US-02 のコードは変更しない（接客画面の PATCH エンドポイントは別 URL）。

**`value` の `max_length` について**: MVP では UI 上限を設けない。コア層の Customer.memo は TextField（max_length なし）であり、UI 側で独自の制限を追加しない。将来的に上限が必要な場合はコア層の Model 制約と合わせて定義する。

## 6. View 定義

### 6.1 CustomerDetailView

```python
# ui/staff/views/customer.py に追記

from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404

from ui.mixins import StaffRequiredMixin, StoreMixin

# セグメント表示名マッピング（US-02 で定義済み。共通化推奨）
SEGMENT_DISPLAY = {"new": "新規", "repeat": "リピート", "regular": "常連"}

# 年齢は整数値のため表示変換不要（テンプレートでそのまま表示）

# シーシャ歴の表示ラベル
EXPERIENCE_DISPLAY = {
    "none": "なし", "beginner": "初心者",
    "intermediate": "中級", "advanced": "上級",
}


class CustomerDetailView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, TemplateView):
    """顧客詳細画面。全属性 + 直近来店 5 件を読み取り専用で表示。"""
    template_name = "ui/staff/customer_detail.html"
    login_url = "/s/login/"

    def get_context_data(self, **kwargs):
        from core.models import Customer, Visit

        context = super().get_context_data(**kwargs)
        customer_id = self.kwargs["pk"]

        customer = get_object_or_404(
            Customer.objects.for_store(self.store),
            pk=customer_id,
        )

        # 表示ラベルを customer オブジェクトに付与
        customer.segment_display = SEGMENT_DISPLAY.get(customer.segment, customer.segment)
        customer.age_display = f"{customer.age}歳" if customer.age is not None else None
        customer.shisha_experience_display = EXPERIENCE_DISPLAY.get(customer.shisha_experience) if customer.shisha_experience else None

        # 直近来店 5 件（同日の安定ソートのため created_at を副キーに追加）
        recent_visits = (
            Visit.objects.for_store(self.store)
            .filter(customer=customer)
            .select_related("staff")
            .order_by("-visited_at", "-created_at")[:5]
        )

        context["customer"] = customer
        context["recent_visits"] = recent_visits
        context["active_tab"] = "customers"
        context["session_url"] = f"/s/customers/{customer.pk}/session/"
        return context
```

**Mixin 順序**: `LoginRequiredMixin, StaffRequiredMixin, StoreMixin, TemplateView`。US-01 の設計原則に準拠。

**ストアスコープ**: `Customer.objects.for_store(self.store)` で他店舗の顧客にアクセスできないことを保証。

### 6.2 CustomerEditView

```python
# ui/staff/views/customer.py に追記


class CustomerEditView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, TemplateView):
    """顧客編集画面。ゾーンベースの UI。各ゾーンは HTMX PATCH で独立して保存。"""
    template_name = "ui/staff/customer_edit.html"
    login_url = "/s/login/"

    def get_context_data(self, **kwargs):
        from core.models import Customer

        context = super().get_context_data(**kwargs)
        customer_id = self.kwargs["pk"]

        customer = get_object_or_404(
            Customer.objects.for_store(self.store),
            pk=customer_id,
        )

        # 表示ラベルを customer オブジェクトに付与
        customer.segment_display = SEGMENT_DISPLAY.get(customer.segment, customer.segment)
        customer.age_display = f"{customer.age}歳" if customer.age is not None else None
        customer.shisha_experience_display = EXPERIENCE_DISPLAY.get(customer.shisha_experience) if customer.shisha_experience else None

        context["customer"] = customer
        context["active_tab"] = "customers"
        context["session_url"] = f"/s/customers/{customer.pk}/session/"

        # 各ゾーンの config を個別にコンテキストに渡す
        context["name_config"] = EDIT_FIELD_CONFIG["name"]
        context["age_config"] = EDIT_FIELD_CONFIG["age"]
        context["area_config"] = EDIT_FIELD_CONFIG["area"]
        context["exp_config"] = EDIT_FIELD_CONFIG["shisha_experience"]
        context["line_id_config"] = EDIT_FIELD_CONFIG["line_id"]
        context["memo_config"] = EDIT_FIELD_CONFIG["memo"]
        return context
```

### 6.3 CustomerEditFieldView

```python
# ui/staff/views/customer.py に追記

from django.views import View
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseBadRequest, QueryDict

from core.exceptions import BusinessError
from core.services.customer import CustomerService
from core.services.hearing import HearingTaskService
from ui.staff.forms.customer import CustomerEditFieldForm


# ゾーンフラグメントのテンプレートマッピング
ZONE_TEMPLATES = {
    "name": "ui/staff/_zone_edit_name.html",
    "age": "ui/staff/_zone_edit_age.html",
    "area": "ui/staff/_zone_edit_area.html",
    "shisha_experience": "ui/staff/_zone_edit_exp.html",
    "line_id": "ui/staff/_zone_edit_line_id.html",
    "memo": "ui/staff/_zone_edit_memo.html",
}


class CustomerEditFieldView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, View):
    """HTMX PATCH: 編集ゾーンの即保存。フィールド単位で顧客を更新する。"""
    login_url = "/s/login/"

    def patch(self, request, pk):
        from core.models import Customer

        customer = get_object_or_404(
            Customer.objects.for_store(self.store),
            pk=pk,
        )

        # Django は PATCH body を request.POST にパースしないため QueryDict で手動パース
        data = QueryDict(request.body)
        form = CustomerEditFieldForm(data)

        field_name = data.get("field", "")
        template_name = ZONE_TEMPLATES.get(field_name)

        if not form.is_valid():
            # ValidationError: エラー内容を含む HTML フラグメントを 422 で返す
            if not template_name:
                # 未知のフィールド: 400 Bad Request（422 ではない。swap されない）
                return HttpResponseBadRequest("無効なフィールドです")

            # 表示ラベル付与（テンプレートが参照するため）
            customer.age_display = f"{customer.age}歳" if customer.age is not None else None
            customer.shisha_experience_display = EXPERIENCE_DISPLAY.get(customer.shisha_experience) if customer.shisha_experience else None

            response = render(request, template_name, {
                "customer": customer,
                "config": EDIT_FIELD_CONFIG.get(field_name, {}),
                "error": form.errors.as_text(),
            })
            response.status_code = 422
            return response

        field_name = form.cleaned_data["field"]
        value = form.cleaned_data["value"]
        template_name = ZONE_TEMPLATES[field_name]

        # CustomerService で顧客フィールドを更新
        try:
            customer = CustomerService.update_customer(
                customer_id=customer.pk,
                **{field_name: value},
            )
        except BusinessError as e:
            # F-03: 空 422 ではなくゾーンフラグメントにエラーメッセージを含めて返す。
            # 空 body の 422 は htmx が target を空にしてゾーンが消失するため。
            customer.age_display = f"{customer.age}歳" if customer.age is not None else None
            customer.shisha_experience_display = EXPERIENCE_DISPLAY.get(customer.shisha_experience) if customer.shisha_experience else None

            response = render(request, template_name, {
                "customer": customer,
                "config": EDIT_FIELD_CONFIG.get(field_name, {}),
                "error": str(e) or "更新に失敗しました",
            })
            response.status_code = 422
            return response

        # ヒアリング対象フィールドの場合のみ sync_tasks を呼ぶ
        if field_name in HEARING_FIELDS:
            HearingTaskService.sync_tasks(customer)

        # 表示ラベル付与
        customer.age_display = f"{customer.age}歳" if customer.age is not None else None
        customer.shisha_experience_display = EXPERIENCE_DISPLAY.get(customer.shisha_experience) if customer.shisha_experience else None

        # 更新後のゾーンフラグメントを返す
        response = render(request, template_name, {
            "customer": customer,
            "config": EDIT_FIELD_CONFIG[field_name],
        })

        # 成功トーストを表示
        response["HX-Trigger"] = '{"showToast": {"message": "保存しました", "type": "success"}}'

        return response

    def _get_display_label(self, field_name, value):
        """選択値の表示ラベルを返す。テキストフィールドはそのまま返す。"""
        config = EDIT_FIELD_CONFIG.get(field_name, {})
        if config.get("type") == "selection":
            for choice_value, label in config.get("choices", []):
                if choice_value == value:
                    return label
        return value
```

**HTMX PATCH リクエストのボディパース**: US-02 S2 と同じく、`QueryDict(request.body)` で手動パースする。`request.POST` を PATCH で直接参照してはならない。

**sync_tasks の条件呼び出し**: `HEARING_FIELDS` セット（`age`, `area`, `shisha_experience`）に含まれるフィールドの変更時のみ `HearingTaskService.sync_tasks(customer)` を呼ぶ。`name`, `line_id`, `memo` の変更では呼ばない。これは C-05a の設計に準拠する。

**成功トースト**: 保存成功時に `showToast` イベントを HX-Trigger で発火し、`base_staff.html` の Toast コンポーネントが「保存しました」を表示する。

**エラー時のユーザー入力について（F-08）**: 即保存 UI のため、エラー時は DB の最新値に戻す。ユーザーは再度ゾーンを開いて再入力する。これは MVP の制約であり、Phase 2 でエラー時の入力値保持を検討する。

### 6.4 VisitListView

```python
# ui/staff/views/visit.py に追記

from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404

from ui.mixins import StaffRequiredMixin, StoreMixin


class VisitListView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, TemplateView):
    """来店履歴一覧画面。直近 20 件の来店記録を時系列で表示（読み取り専用）。"""
    template_name = "ui/staff/visit_list.html"
    login_url = "/s/login/"

    def get_context_data(self, **kwargs):
        from core.models import Customer, Visit

        context = super().get_context_data(**kwargs)
        customer_id = self.kwargs["pk"]

        customer = get_object_or_404(
            Customer.objects.for_store(self.store),
            pk=customer_id,
        )

        # 同日の安定ソートのため created_at を副キーに追加（F-06）
        visits = (
            Visit.objects.for_store(self.store)
            .filter(customer=customer)
            .select_related("staff")
            .order_by("-visited_at", "-created_at")[:20]
        )

        context["customer"] = customer
        context["visits"] = visits
        context["active_tab"] = "customers"
        context["session_url"] = f"/s/customers/{customer.pk}/session/"
        return context
```

**BottomTab のアクティブ状態**: 来店履歴画面では `active_tab = "customers"` を設定する。グローバルな「来店記録」タブ (`/s/visits/`) は未実装のため、顧客スコープの来店履歴は「顧客」タブの延長として扱う。

## 7. URL 設定

### ui/staff/urls.py（追記部分）

US-02 の既存 URL に 3 つの URL を追加する。

```python
# ui/staff/urls.py に追記（既存の US-02 URL の後に追加）

from ui.staff.views.customer import (
    # US-02 S1 の既存 import
    CustomerSelectView, CustomerSearchView, CustomerCreateView,
    # US-03 S1 追加
    CustomerDetailView, CustomerEditView, CustomerEditFieldView,
)
from ui.staff.views.visit import (
    # US-02 S2 の既存 import
    VisitCreateView,
    # US-03 S1 追加
    VisitListView,
)

urlpatterns = [
    # ... US-01, US-02 の既存 URL ...

    # US-03 S1: 顧客詳細
    path("customers/<uuid:pk>/", CustomerDetailView.as_view(), name="customer-detail"),

    # US-03 S1: 顧客編集
    path("customers/<uuid:pk>/edit/", CustomerEditView.as_view(), name="customer-edit"),

    # US-03 S1: 顧客編集フィールド即保存（HTMX PATCH）
    path("customers/<uuid:pk>/edit/field/", CustomerEditFieldView.as_view(), name="customer-edit-field"),

    # US-03 S1: 来店履歴一覧
    path("customers/<uuid:pk>/visits/", VisitListView.as_view(), name="visit-list"),
]
```

**URL パスの設計意図**:
- `/s/customers/<id>/`: 顧客詳細（読み取り専用）
- `/s/customers/<id>/edit/`: 顧客編集画面（GET でフォーム表示）
- `/s/customers/<id>/edit/field/`: 編集画面のゾーン即保存エンドポイント（HTMX PATCH のみ）
- `/s/customers/<id>/visits/`: 来店履歴一覧

**URL 順序の注意**: Django の URL パターンは先頭一致で評価される。`customers/<uuid:pk>/` は `customers/search/` や `customers/new/` の後に配置すること（uuid パターンが先にあると `search` や `new` を uuid として解釈しようとする可能性がある。ただし `<uuid:pk>` は UUID 形式のみマッチするため実際には競合しないが、可読性のために固定パスを先に配置する慣例に従う）。

**US-02 の `/s/customers/<id>/session/` との共存**: US-02 で `customers/<uuid:pk>/session/` が定義済み。US-03 で `customers/<uuid:pk>/` を追加すると、URL ルーティングは Django の path マッチングで正しく分離される（`session/` サフィックスの有無で区別）。

## 8. テストケース

### 8.1 Django TestClient

#### 顧客詳細画面

| # | テスト | 検証内容 |
|---|--------|---------|
| 1 | `test_customer_detail_get` | GET `/s/customers/<id>/` → 200。`customer_detail.html` 使用 |
| 2 | `test_customer_detail_requires_auth` | 未認証で GET → 302 `/s/login/` |
| 3 | `test_customer_detail_active_tab` | context に `active_tab == "customers"` |
| 4 | `test_customer_detail_displays_all_attributes` | レスポンスに顧客名、セグメントバッジ、来店回数、年齢、居住エリア、シーシャ歴、LINE ID、メモが含まれる |
| 5 | `test_customer_detail_segment_badge` | レスポンスにセグメントバッジ（`badge-new` / `badge-repeat` / `badge-regular`）が含まれる |
| 6 | `test_customer_detail_null_fields_show_placeholder` | 未入力の属性（age=None 等）で「未入力」が表示される |
| 7 | `test_customer_detail_recent_visits_5` | 直近来店 5 件が表示される。6 件目以降は表示されない |
| 8 | `test_customer_detail_recent_visits_empty` | 来店記録がない場合、「来店記録はまだありません」メッセージ |
| 9 | `test_customer_detail_recent_visits_staff_name` | 来店記録にスタッフ名が表示される |
| 10 | `test_customer_detail_recent_visits_memo_truncated` | 来店メモが 50 文字で truncate される |
| 11 | `test_customer_detail_edit_link` | レスポンスに `/s/customers/<id>/edit/` へのリンクが含まれる |
| 12 | `test_customer_detail_visit_list_link` | 来店記録がある場合、「すべて見る」リンク（`/s/customers/<id>/visits/`）が含まれる |
| 13 | `test_customer_detail_store_scope` | 他店舗の顧客 ID → 404 |
| 14 | `test_customer_detail_nonexistent` | 存在しない顧客 ID → 404 |
| 15 | `test_customer_detail_age_display_label` | age=25 の場合、「25歳」が表示される |
| 16 | `test_customer_detail_experience_display_label` | shisha_experience="beginner" の場合、「初心者」が表示される |

#### 顧客編集画面

| # | テスト | 検証内容 |
|---|--------|---------|
| 17 | `test_customer_edit_get` | GET `/s/customers/<id>/edit/` → 200。`customer_edit.html` 使用 |
| 18 | `test_customer_edit_requires_auth` | 未認証で GET → 302 `/s/login/` |
| 19 | `test_customer_edit_active_tab` | context に `active_tab == "customers"` |
| 20 | `test_customer_edit_has_all_zones` | レスポンスに 6 つのゾーン（name, age, area, shisha_experience, line_id, memo）の id が含まれる |
| 21 | `test_customer_edit_back_link` | レスポンスに `/s/customers/<id>/` への戻るリンクが含まれる |
| 22 | `test_customer_edit_store_scope` | 他店舗の顧客 ID → 404 |
| 23 | `test_customer_edit_displays_current_values` | 既存の値（age, area 等）がゾーン内に表示されている |

#### フィールド即保存（HTMX PATCH）

| # | テスト | 検証内容 |
|---|--------|---------|
| 24 | `test_edit_field_name_patch` | PATCH `/s/customers/<id>/edit/field/` with field=name, value="新しい名前" → 200。Customer.name == "新しい名前" |
| 25 | `test_edit_field_name_empty_rejected` | PATCH with field=name, value="" → 422。「名前を入力してください」エラー |
| 26 | `test_edit_field_name_whitespace_rejected` | PATCH with field=name, value="   " → 422。空白のみは拒否 |
| 27 | `test_edit_field_name_trimmed` | PATCH with field=name, value="  太郎  " → 200。Customer.name == "太郎"（前後の空白がトリム） |
| 28 | `test_edit_field_age_patch` | PATCH with field=age, value="25" → 200。Customer.age == 25（整数） |
| 29 | `test_edit_field_age_invalid_value` | PATCH with field=age, value="invalid" → 422。「年齢は整数で入力してください」 |
| 30 | `test_edit_field_age_clear` | PATCH with field=age, value="" → 200。Customer.age is None（空文字 → None 正規化） |
| 30a | `test_edit_field_age_out_of_range` | PATCH with field=age, value="200" → 422。「年齢は 0〜150 の範囲で入力してください」 |
| 31 | `test_edit_field_area_patch` | PATCH with field=area, value="渋谷" → 200。Customer.area == "渋谷" |
| 32 | `test_edit_field_area_empty_to_null` | PATCH with field=area, value="" → Customer.area is None |
| 33 | `test_edit_field_shisha_experience_patch` | PATCH with field=shisha_experience, value="beginner" → 200。Customer.shisha_experience == "beginner" |
| 34 | `test_edit_field_line_id_patch` | PATCH with field=line_id, value="@example" → 200。Customer.line_id == "@example" |
| 35 | `test_edit_field_line_id_empty_to_null` | PATCH with field=line_id, value="" → Customer.line_id is None |
| 36 | `test_edit_field_memo_patch` | PATCH with field=memo, value="長いメモテキスト..." → 200。Customer.memo == "長いメモテキスト..." |
| 37 | `test_edit_field_memo_empty_to_null` | PATCH with field=memo, value="" → Customer.memo is None |
| 38 | `test_edit_field_invalid_field` | PATCH with field=unknown_field → 400 Bad Request |
| 39 | `test_edit_field_hearing_triggers_sync_tasks` | PATCH with field=age, value="25" → `HearingTaskService.sync_tasks()` が呼ばれた（mock で検証） |
| 40 | `test_edit_field_non_hearing_no_sync_tasks` | PATCH with field=name → `HearingTaskService.sync_tasks()` が呼ばれない（mock で検証） |
| 41 | `test_edit_field_non_hearing_line_id_no_sync_tasks` | PATCH with field=line_id → `HearingTaskService.sync_tasks()` が呼ばれない |
| 42 | `test_edit_field_non_hearing_memo_no_sync_tasks` | PATCH with field=memo → `HearingTaskService.sync_tasks()` が呼ばれない |
| 43 | `test_edit_field_success_toast` | PATCH 成功 → レスポンスに `HX-Trigger` ヘッダー（showToast: "保存しました"）が含まれる |
| 44 | `test_edit_field_returns_zone_fragment` | PATCH with field=age → レスポンスに `id="zone-age"` が含まれる（ゾーンフラグメント） |
| 45 | `test_edit_field_store_scope` | 他店舗の顧客 → 404 |
| 46 | `test_edit_field_requires_auth` | 未認証で PATCH → 302 `/s/login/` |
| 47 | `test_edit_field_patch_body_parsing` | PATCH with form-encoded body (`field=name&value=太郎`) → `QueryDict(request.body)` で正しくパースされ、Customer.name == "太郎" |
| 48a | `test_edit_field_area_whitespace_only_to_null` | PATCH with field=area, value="   " → Customer.area is None（F-02: 空白のみ → strip → 空文字 → None） |
| 48b | `test_edit_field_line_id_whitespace_only_to_null` | PATCH with field=line_id, value="  \t  " → Customer.line_id is None（F-02） |
| 48c | `test_edit_field_memo_whitespace_only_to_null` | PATCH with field=memo, value="   " → Customer.memo is None（F-02） |
| 48d | `test_edit_field_business_error_returns_zone_fragment` | CustomerService.update_customer が BusinessError を raise → 422 レスポンスにゾーンフラグメント（`id="zone-<field>"`）とエラーメッセージが含まれる（F-03） |
| 48e | `test_customer_detail_session_url` | context に `session_url` が `/s/customers/<id>/session/` として含まれる（F-04） |
| 48f | `test_customer_edit_session_url` | context に `session_url` が `/s/customers/<id>/session/` として含まれる（F-04） |
| 48g | `test_visit_list_session_url` | context に `session_url` が `/s/customers/<id>/session/` として含まれる（F-04） |

#### 来店履歴一覧

| # | テスト | 検証内容 |
|---|--------|---------|
| 48 | `test_visit_list_get` | GET `/s/customers/<id>/visits/` → 200。`visit_list.html` 使用 |
| 49 | `test_visit_list_requires_auth` | 未認証で GET → 302 `/s/login/` |
| 50 | `test_visit_list_active_tab` | context に `active_tab == "customers"` |
| 51 | `test_visit_list_displays_visits` | 来店記録が日付・スタッフ名・メモ付きで表示される |
| 52 | `test_visit_list_limit_20` | 来店が 25 件ある場合、20 件のみ返る |
| 53 | `test_visit_list_order_desc` | 来店が新しい順に表示される |
| 53a | `test_visit_list_same_day_order_stable` | 同日に複数来店がある場合、created_at の降順で安定ソートされる（F-06） |
| 53b | `test_customer_detail_same_day_visits_order_stable` | 詳細画面の直近 5 件も同日来店で安定ソート（F-06） |
| 54 | `test_visit_list_memo_truncated` | 会話メモが 50 文字で truncate される |
| 55 | `test_visit_list_empty` | 来店記録がない場合、「来店記録はまだありません」メッセージ |
| 56 | `test_visit_list_store_scope` | 他店舗の顧客 ID → 404 |
| 57 | `test_visit_list_nonexistent_customer` | 存在しない顧客 ID → 404 |
| 58 | `test_visit_list_back_link` | レスポンスに `/s/customers/<id>/` への戻るリンクが含まれる |
| 59 | `test_visit_list_read_only` | 来店記録の編集・削除 UI が存在しないことを確認（POST / PATCH / DELETE endpoint なし） |

### 8.2 Browser smoke test

| # | 対象 URL | 手順 | 期待結果 |
|---|---------|------|---------|
| 1 | `/s/customers/<id>/` | 認証済みでアクセス | 顧客名・セグメントバッジ・来店回数・全属性・直近来店が表示される |
| 2 | `/s/customers/<id>/` | 「編集」ボタンタップ | `/s/customers/<id>/edit/` に遷移 |
| 3 | `/s/customers/<id>/edit/` | アクセス | 6 つの編集ゾーン（名前〜メモ）が表示される。既存の値が表示されている |
| 4 | (編集画面) | 名前ゾーンタップ | ゾーン展開。テキスト入力にフォーカス。現在の名前が入力済み |
| 5 | (編集画面) | 名前を変更して「保存」タップ | HTMX PATCH → ゾーンが新しい名前で更新（ページ遷移なし）。トースト「保存しました」 |
| 6 | (編集画面) | 年齢ゾーンタップ → 数値入力（例: 25）→「保存」 | HTMX PATCH → ゾーンが「25歳」で更新。トースト表示 |
| 7 | (編集画面) | 年齢ゾーンの入力を空にして「保存」 | HTMX PATCH → ゾーンが「タップして入力 ▸」に戻る。トースト表示 |
| 8 | (編集画面) | メモゾーンタップ → テキスト入力 → 「保存」 | HTMX PATCH → ゾーンが更新。メモ冒頭 30 文字が要約表示される |
| 9 | (編集画面) | 「← 戻る」タップ | `/s/customers/<id>/` に遷移。編集内容が反映されている |
| 10 | `/s/customers/<id>/` | 「すべて見る」リンクタップ | `/s/customers/<id>/visits/` に遷移 |
| 11 | `/s/customers/<id>/visits/` | アクセス | 来店記録一覧が時系列で表示。スタッフ名・メモ付き |
| 12 | `/s/customers/<id>/visits/` | 「← 顧客名」リンクタップ | `/s/customers/<id>/` に遷移 |
| 13 | (各画面) | BottomTab 確認 | 「顧客」タブがアクティブ。「来店記録」タブは disabled のまま |

## Review Log

- [2026-03-31] 初版作成
- [2026-03-31] レビュー F-01〜F-08 反映
  - F-01 (High): age を CharField/選択型から IntegerField/数値入力型に変更（C-03 契約準拠: `age?: int`）。Customer モデル表、EDIT_FIELD_CONFIG、EDIT_FIELD_CHOICES、AGE_DISPLAY、age ゾーンテンプレート、Form バリデーション、テストケースを更新
  - F-02 (High): nullable テキストフィールドの clean() に `.strip()` を追加。空白のみ入力 → strip → 空文字 → None に正規化。テスト 48a〜48c 追加
  - F-03 (High): BusinessError 時に空 422 + HX-Trigger ではなく、ゾーンフラグメントにエラーメッセージを含めて 422 で返すように変更。テスト 48d 追加
  - F-04 (Medium-High): CustomerDetailView、CustomerEditView、VisitListView に `session_url` をコンテキストに追加（BottomTab「接客」タブ連携）。テスト 48e〜48g 追加
  - F-05 (Medium): 名前ゾーン（4.3）にインライン展開型採用の経緯と基本設計書との差異に関する注記を追加
  - F-06 (Medium): 来店クエリの order_by に `-created_at` を副キーとして追加（同日来店の安定ソート）。DetailView と VisitListView の両方を修正。テスト 53a〜53b 追加
  - F-07 (Medium): memo フィールドの max_length=2000 を削除。MVP では UI 上限を設けない旨の注記を追加
  - F-08 (Medium): エラー時のユーザー入力消失は MVP の制約であることを明記。Phase 2 で検討する旨の注記を追加
- [2026-03-31] Codex 2回目レビュー (gpt-5.4 high): 88/100 CONDITIONAL。2 件を修正
  - F-09 (medium): unknown_field の 422 → 400 Bad Request に変更（422 swap で壊れない）
  - F-10 (low): Visit モデル要約に created_at を追記（order_by 副キー依存の明文化）
- [2026-03-31] Codex 3回目レビュー (gpt-5.4 high): 88/100 CONDITIONAL。2 件を修正
  - F-11 (medium): HttpResponseBadRequest を import に追加
  - F-12 (low): テスト #38 を 422 → 400 に修正
- [2026-03-31] Codex 4回目レビュー (gpt-5.4 high): **96/100 PASS**
