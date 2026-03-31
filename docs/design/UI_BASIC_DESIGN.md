# UI 基本設計書

> 企画書: `docs/design/UI_PROPOSAL.md` (PASS 93/100)
> 実装方針書: `docs/design/UI_DESIGN_GUIDE.md` (PASS 100/100)
> スタイルガイド: `docs/design/assets/styleguide.html`
> コア層基本設計書: `docs/reference/BASIC_DESIGN.md` (PASS 93/100)
> 本書は企画書で定義した 9 Cluster の「何を表示し、どの Service/Manager を呼び、どう操作するか」を確定する基本設計書である。

## 1. スコープと前提

### 本書のスコープ

| 含む | 含まない |
|------|---------|
| 各画面の表示項目・データソース（Service/Manager） | HTML マークアップ・Tailwind クラス（→ 詳細設計） |
| 画面間の遷移とナビゲーション構造 | コンポーネントの CSS 実装（→ UI_DESIGN_GUIDE.md + styleguide.html） |
| HTMX / Alpine.js の適用ポイント | 個々の `hx-*` / `x-*` 属性の詳細（→ 詳細設計） |
| 各 Cluster の Slice 分割・pre/postcondition | Gherkin シナリオ（→ 詳細設計の Cluster Spec） |
| 未決事項 D-03, D-04, D-05 の決定 | デプロイ手順（→ docs/ops/） |

### 前提

- コア層の全 Service / Manager / Model は `docs/reference/BASIC_DESIGN.md` および `docs/reference/cluster/*.md` に定義済み
- デザイントークン・コンポーネントパターンは `UI_DESIGN_GUIDE.md` で確定済み
- UI View の責務境界は企画書セクション 1「オペレータ層の責務境界」で確定済み
  - **read は Manager 直接参照可、write は Service 必須**

### §1.1 「write は Service 必須」の例外

企画書の原則「データ変更は必ず Service 層を経由する」に対し、以下の 2 操作はコア層が standalone Service を公開していないため例外とする。

| 操作 | コア層の実装箇所 | UI View の対応 | 理由 |
|------|----------------|---------------|------|
| **スタッフ作成** (O-STAFF-CREATE) | `StaffViewSet.perform_create()` (C-02 Slice 2) | ViewSet の perform_create 相当のロジックを UI View で再現（store 自動設定 + ORM create）。QR 発行は `QRAuthService` 経由 | C-02 は Staff CRUD を ViewSet 内に実装しており、StaffService を公開していない |
| **セグメント閾値更新** (O-SEGMENT-SETTINGS) | `SegmentThresholdViewSet` (C-04 Slice 3) | 閾値バリデーションは `SegmentThreshold.validate_store_thresholds()` クラスメソッド（Model 層）を利用。閾値一括更新は ViewSet 相当のロジックを再現。**再計算は `SegmentService.bulk_recalculate_segments(store)` を Service 経由で呼び出す** | C-04 は閾値更新を ViewSet 内に実装。再計算のみ Service として公開 |

**対策**: Phase 2 で `StaffService` と `ThresholdService` の抽出を検討し、UI View と API ViewSet の両方が共通 Service を利用する構造に移行する。MVP では上記の例外を許容し、各 UI View に ViewSet と同一のビジネスルール（ガード条件・バリデーション）を適用する。

## 2. 未決事項の決定

### D-03: Alpine.js の採用 → 採用する

| 項目 | 内容 |
|------|------|
| **決定** | Alpine.js v3 を採用する |
| **理由** | スタッフ UI のゾーンパターン（展開/折りたたみ・チップ選択状態管理・モーダル開閉）が UI の根幹であり、`x-data` / `x-show` / `x-on:click` の宣言的記述が実装品質を安定させる |
| **HTMX との連携** | HTMX がサーバーから HTML を取得し DOM を更新、Alpine.js が DOM 内の状態（開閉・選択）を管理する。公式で連携が推奨されている組み合わせ |
| **読み込み** | CDN（`<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js">`）を `base.html` で読み込む |
| **使用箇所** | ゾーン展開/折りたたみ、チップ選択、モーダル開閉、タブ切替、トースト自動消去、ドロップダウン |
| **使わない箇所** | データの CRUD（HTMX + Django View の責務）、画面遷移（通常のリンク or HTMX） |

### D-04: E2E テスト範囲 → 主要フロー + ログインのみ

| 項目 | 内容 |
|------|------|
| **決定** | MVP では Playwright E2E テストを **クリティカルパスのみ** に適用する |
| **対象フロー** | (1) スタッフ QR ログイン → セッション確立 (2) 顧客検索 → 選択 → 接客画面 → タスク消化 → 来店記録作成 (3) オーナーログイン → ダッシュボード表示 |
| **理由** | HTMX パーシャル更新の結合が Django TestClient では検証不可。ただし全 Cluster 正常系は過剰投資。「壊れると CRM が使えなくなるパス」に絞る |
| **Django TestClient** | 全 View に対して正常系 + 権限エラーをカバー（企画書テスト方針の通り） |
| **ビジュアルリグレッション** | MVP 外（Phase 2 で検討） |

### D-05: チャートライブラリ → Chart.js

| 項目 | 内容 |
|------|------|
| **決定** | Chart.js v4 を採用する |
| **理由** | 必要な 3 種のグラフ（折れ線: 日別来客推移、円: セグメント比率、棒: スタッフ別対応数）に必要十分。65KB (gzip)。Cursor が正確に設定ベースのコードを生成できる |
| **代替の不採用理由** | ApexCharts は 130KB で MVP には過剰機能。ECharts は 300KB+ |
| **データ渡し方式** | Django テンプレートで `{{ chart_data\|json_script:"chart-data" }}` → JS で `JSON.parse(document.getElementById('chart-data').textContent)` |
| **読み込み** | CDN（`<script src="https://cdn.jsdelivr.net/npm/chart.js@4">`）を `base_owner.html` で読み込む。スタッフ UI では読み込まない |

## 3. 共通設計

### 3.1 テンプレート継承

```
templates/ui/
  base.html                          # <html>, charset, viewport, HTMX, Alpine.js, Tailwind CSS
  ├── base_staff.html                # Topbar + BottomTab + content block
  │     └── staff/*.html
  └── base_owner.html                # Sidebar + Header + content block + Chart.js
        └── owner/*.html
```

#### base.html が読み込む共通リソース

| リソース | 方式 | 備考 |
|---------|------|------|
| **Tailwind CSS** | ビルド済み CSS (`static/ui/css/output.css`) | `npx tailwindcss` でビルド |
| **HTMX** | CDN | 全画面で使用 |
| **Alpine.js** | CDN (`defer`) | 全画面で使用 |
| **Inter + Noto Sans JP** | Google Fonts CDN | `wght@400;500;600;700` |
| **Lucide Icons** | SVG テンプレートインクルード | `{% include "ui/icons/xxx.svg" %}` |

#### base_staff.html の構造

```
{% block topbar %}
  <header>ページタイトル + 操作者名バッジ (request.user.display_name) + ログアウトボタン (POST form)</header>
{% endblock %}

{% block content %}
  <!-- 各画面がここを埋める -->
{% endblock %}

{% block bottomtab %}
  <nav>顧客 | 接客 | 来店記録 | マッチング</nav>
{% endblock %}

{% block toast %}
  <!-- Alpine.js で制御するトースト領域 -->
{% endblock %}
```

#### base_owner.html の構造

```
{% block sidebar %}
  <nav>ブランド名 + ナビ項目（ダッシュボード / 顧客管理 / 来店記録 / スタッフ管理 / セグメント設定 / Airレジ連携）</nav>
{% endblock %}

{% block header %}
  <header>ページタイトル + ログインユーザー名</header>
{% endblock %}

{% block content %}{% endblock %}

{% block modal %}
  <!-- 確認ダイアログ用の Alpine.js マウントポイント -->
{% endblock %}

{% block toast %}{% endblock %}
```

### 3.2 View Mixin

| Mixin | 責務 | 適用対象 |
|-------|------|---------|
| `LoginRequiredMixin` | 未認証 → ログイン画面にリダイレクト | 全 View（ログイン View 除く） |
| `StaffRequiredMixin` | role が staff or owner であること。role 不正 → `logout()` + `/s/login/` にリダイレクト | スタッフ UI 全 View |
| `OwnerRequiredMixin` | role が owner であること。staff がアクセス → スタッフ UI ホームにリダイレクト（403 ページではない） | オーナー UI 全 View |
| `StoreMixin` | `self.store = request.user.store` をセット。テンプレートコンテキストにも `store` を渡す | 全業務 View |

### 3.3 HTMX パターン

UI 全体で使用する HTMX の共通パターン。

| パターン | 用途 | 仕組み |
|---------|------|--------|
| **Partial Replace** | 検索結果の更新、タスク消化後の再描画 | `hx-get="/s/customers/search/?q=..."` → `hx-target="#customer-list"` → View が HTML フラグメントを返す |
| **Form Submit** | 来店記録作成、顧客登録 | `hx-post="/s/visits/create/"` → `hx-target="#content"` → 成功時はリダイレクト or トースト |
| **Inline Edit** | ゾーン展開内のチップ選択確定 | `hx-patch="/s/customers/<id>/field/"` → `hx-target="closest .zone"` → ゾーンが filled 状態に更新 |
| **Delete + Swap** | タスク完了 | `hx-delete` → `hx-swap="outerHTML"` → 要素が消える |

#### HTMX View のルール

| ルール | 内容 |
|--------|------|
| HTMX View は通常 View とは別にする | `CustomerSearchView`（HTMX、フラグメント返却）と `CustomerSelectView`（フルページ）を分離する |
| フラグメントテンプレートの命名 | `_` プレフィックス: `_customer_list.html`, `_task_card.html` |
| `HX-Request` ヘッダーの判定 | `request.headers.get('HX-Request')` で HTMX リクエストかを判定し、フラグメント / フルページを出し分ける |
| エラー時 | Service 層の ValidationError → `hx-target` にエラーメッセージの HTML フラグメントを返す |

### 3.4 Alpine.js パターン

| パターン | 用途 | 例 |
|---------|------|-----|
| **ゾーン開閉** | `x-data="{ open: false }"` + `x-show="open"` | ゾーンのタップで展開/折りたたみ |
| **チップ選択** | `x-data="{ selected: '' }"` + `x-on:click="selected = 'value'"` | シーシャ歴の 4 択 |
| **モーダル** | `x-data="{ showModal: false }"` + `x-show="showModal"` + `x-transition` | 検索モーダル、確認ダイアログ |
| **トースト** | `x-data="{ show: false, message: '' }"` + `x-init="setTimeout(() => show = false, 3000)"` | 操作完了フィードバック |
| **タブ** | `x-data="{ tab: 'active' }"` | 表示の切替（JS のみ、サーバー不要の場合） |

### 3.5 エラーハンドリング

| エラー種別 | Service 層の挙動 | UI の表示 |
|-----------|-----------------|----------|
| **ValidationError** | `raise ValidationError({"field": ["message"]})` | フィールド横にインラインメッセージ。HTMX の場合はフラグメントでエラー表示を返す |
| **BusinessError** | `raise BusinessError(code, message)` | トーストでエラーメッセージ表示 |
| **PermissionDenied** | Django の PermissionDenied | スタッフ UI ホーム or ログイン画面にリダイレクト |
| **ObjectDoesNotExist** | `get_object_or_404()` | Django 標準 404 ページ |
| **サーバーエラー (500)** | 未キャッチ例外 | 「エラーが発生しました」ページ。ユーザーに技術情報を見せない |

### 3.6 フォーム設計共通

#### スタッフ UI: ゾーンベース

スタッフ UI のデータ入力はゾーンパターンで統一する。Django Form はバックエンドバリデーションに使うが、テンプレートでの `{{ form.as_p }}` レンダリングは **使わない**。代わりにゾーン UI をカスタム描画し、`<input type="hidden">` で値を送信する。

```
[ゾーングループ（カード）]
  ├── ゾーン: 年齢         → x-data で開閉制御 → チップ選択 → hidden input に値セット → hx-patch で保存
  ├── ゾーン: 居住エリア    → 同上
  ├── ゾーン: シーシャ歴    → 同上
  └── ゾーン: メモ         → x-data で開閉制御 → textarea 展開 → Alpine.js 状態として一時保持（即保存しない。来店記録作成時に Visit.conversation_memo として送信）
```

#### オーナー UI: 標準フォーム

オーナー UI は Django Form の標準レンダリングを活用する。ただしスタイルは Tailwind クラスで上書きする。

### 3.7 ページネーション

| UI | 方式 | 件数 |
|----|------|------|
| スタッフ UI | なし（最近来た順で上位 N 件。全件表示は不要） | 直近 20 件 |
| オーナー UI | テーブル下部に「前へ」「次へ」ボタン + ページ番号 | 25 件/ページ |

オーナー UI のページネーションは HTMX でテーブル本体のみを差し替える（`hx-get` + `hx-target="#table-body"`）。

## 4. 画面遷移図

### 4.1 スタッフ UI 画面遷移

```
[QR ログイン]
    │
    ▼
[顧客タブ] ◄──────────────────────────────────────┐
    │                                              │
    ├── 顧客検索（モーダル）── 結果タップ ──┐      │
    │                                       │      │
    ├── 最近来た順リスト ── タップ ──────────┤      │
    │                                       ▼      │
    │                               [接客画面]     │
    │                                 │ タスク表示  │
    │                                 │ メモ入力    │
    │                                 │ 来店記録作成│
    │                                 │            │
    │                                 └── 完了 ────┘
    │
    ├── 新規登録（モーダル）── 登録完了 → [接客画面]
    │
    ▼
[接客タブ] = 顧客選択済みの場合の接客画面（顧客タブから遷移後と同一画面）
    │
    ▼
[来店記録タブ]
    │
    └── 直近の来店記録一覧（簡易表示）
         └── タップ → [顧客簡易表示]
              └── 基本編集（/s/customers/<id>/edit/）
    │
    ▼
[マッチングタブ]
    │
    └── 未マッチ Airレジ明細一覧
         └── タップで候補表示 → 確定/スキップ
```

**ボトムタブのアクティブ状態:**

| タブ | アイコン(Lucide) | URL | アクティブ条件 |
|------|-----------------|-----|---------------|
| 顧客 | `users` | `/s/customers/` | `/s/customers/*` に一致 |
| 接客 | `message-circle` | `/s/customers/<id>/session/` | `/s/customers/*/session/*` に一致。顧客未選択時はグレーアウト |
| 来店記録 | `calendar` | `/s/visits/` | `/s/visits/*` に一致 |
| マッチング | `link` | `/s/matching/` | `/s/matching/*` に一致 |

### 4.2 オーナー UI 画面遷移

```
[ログイン]
    │
    ▼
[ダッシュボード] (/o/dashboard/)
    │
    ├── サイドバー: 顧客管理
    │     └── [顧客一覧] (/o/customers/)
    │           ├── 行クリック → [顧客詳細] (/o/customers/<id>/)
    │           │                  └── 編集ボタン → [顧客編集] (/o/customers/<id>/edit/)
    │           └── フィルタ・ソート・検索（HTMX でテーブル更新）
    │
    ├── サイドバー: 来店記録
    │     └── [来店一覧] (/o/visits/)
    │           ├── 行クリック → [来店編集] (/o/visits/<id>/edit/)
    │           └── 削除ボタン → [来店削除確認]（モーダル） → 論理削除
    │
    ├── サイドバー: スタッフ管理
    │     └── [スタッフ一覧] (/o/staff/)
    │           ├── 行クリック → [スタッフ詳細] (/o/staff/<id>/)
    │           │                  └── 無効化ボタン → 確認ダイアログ → 無効化
    │           │                  └── QR 発行ボタン → QR 表示
    │           └── 新規作成ボタン → [スタッフ作成] (/o/staff/new/)
    │
    ├── サイドバー: セグメント設定
    │     └── [セグメント閾値設定] (/o/segments/settings/)
    │           └── 閾値変更 → 影響件数プレビュー → 確定 → 一括再計算
    │
    └── サイドバー: Airレジ連携
          └── [CSV アップロード] (/o/imports/upload/)
                └── アップロード完了 → [インポート行一覧] (/o/imports/<id>/rows/)
                      └── マッチングボタン → [マッチング管理] (/o/imports/<id>/matching/)
                            └── 各行の確定/却下
```

**サイドバーのナビ構造:**

| メニュー | アイコン(Lucide) | URL | アクティブ条件 |
|---------|-----------------|-----|---------------|
| ダッシュボード | `bar-chart-2` | `/o/dashboard/` | `/o/dashboard/` に一致 |
| 顧客管理 | `users` | `/o/customers/` | `/o/customers/*` に一致 |
| 来店記録 | `calendar` | `/o/visits/` | `/o/visits/*` に一致 |
| スタッフ管理 | `user-cog` | `/o/staff/` | `/o/staff/*` に一致 |
| セグメント設定 | `sliders` | `/o/segments/settings/` | `/o/segments/*` に一致 |
| Airレジ連携 | `upload` | `/o/imports/upload/` | `/o/imports/*` に一致 |

## 5. Staff UI 画面設計

### US-01: ログイン

#### S-LOGIN: QR ログイン画面

| 項目 | 内容 |
|------|------|
| **URL** | `/s/login/` |
| **View** | `staff.views.auth.LoginView` |
| **テンプレート** | `staff/login.html`（`base.html` を直接継承。BottomTab なし） |
| **表示項目** | ブランドロゴ、QR トークン入力フィールド、ログインボタン |
| **データソース** | なし（入力のみ） |
| **操作** | QR トークンを入力 → POST → `QRAuthService.authenticate(token)` → セッション確立 → `/s/customers/` にリダイレクト |
| **エラー** | 無効なトークン → インラインエラー「QR コードが無効です」。期限切れ → 「QR コードの有効期限が切れています」 |
| **Alpine.js** | なし |
| **HTMX** | なし（通常の POST submit） |
| **QR リンク経由** | URL が `/s/login/#token={token}` の場合、ページ読み込み時に JS が `location.hash` から token を読み取り、`history.replaceState(null, '', location.pathname)` で hash を除去した後、入力フィールドにセットして自動 POST する。hash 除去により戻る/再読込で token が再送されない。hash fragment はサーバーに送信されないため、サーバーログに token が記録されない |

**補足**: 実運用では QR コードをカメラで読み取り → ブラウザが `/s/login/#token=...` を開く → 自動ログインの流れ。MVP ではトークン文字列の手動入力でも動作確認可能。カメラ読み取り UI は Phase 2。

#### S-LOGOUT: ログアウト

| 項目 | 内容 |
|------|------|
| **URL** | `/s/logout/` |
| **View** | `staff.views.auth.LogoutView` |
| **操作** | POST → Django `logout()` → セッション破棄 → `/s/login/` にリダイレクト |

### US-02: 接客フロー

US-02 はスタッフ UI の核。顧客選択 → 接客画面（タスク・メモ・来店記録）を 1 つのフローとして設計する。

#### S-CUSTOMER-SELECT: 顧客選択画面

| 項目 | 内容 |
|------|------|
| **URL** | `/s/customers/` |
| **View** | `staff.views.customer.CustomerSelectView` |
| **テンプレート** | `staff/customer_select.html` |
| **表示項目** | (1) 検索バー（タップでモーダル起動） (2) 最近来た順の顧客カード一覧（直近 20 件） (3) 新規登録ボタン |
| **データソース** | `Customer.objects.for_store(store)` に最終来店日を `Subquery`（`Visit.objects.filter(customer=OuterRef('pk')).order_by('-visited_at').values('visited_at')[:1]`）で annotate し、`order_by('-last_visited_at')[:20]`。各顧客に `segment` を表示（セグメントバッジ）。来店記録がない顧客は末尾に表示される |
| **操作** | 顧客カードタップ → `/s/customers/<id>/session/` に遷移。検索バータップ → 検索モーダル起動。新規登録ボタン → 新規登録モーダル起動 |
| **Alpine.js** | 検索モーダルの開閉: `x-data="{ showSearch: false }"` |
| **HTMX** | 検索モーダル内のインクリメンタル検索: `hx-get="/s/customers/search/"` → `hx-trigger="input changed delay:300ms"` → `hx-target="#search-results"` |

**顧客カードの表示項目:**

```
┌──────────────────────────────┐
│ [セグメントバッジ] 山田太郎    │
│ 来店 12 回 ・ 最終 3/28       │
│ タスク: 居住エリア未取得       │  ← 未消化タスクがある場合のみ
└──────────────────────────────┘
```

| データ | ソース |
|--------|--------|
| 名前 | `customer.name` |
| セグメント | `customer.segment` → バッジ色分け（UI_DESIGN_GUIDE.md 参照） |
| 来店回数 | `customer.visit_count` |
| 最終来店日 | annotate 済みの `last_visited_at`（Subquery。一覧クエリで取得済み） |
| 未消化タスク数 | `HearingTask.objects.for_store(store).filter(customer=customer, status='open').count()` |

**パフォーマンス注記**: 最終来店日とタスク数は N+1 になりうる。View で `Subquery` / `annotate` を使って 1 クエリに集約する。具体的な QuerySet 設計は詳細設計で確定する。

#### S-CUSTOMER-SEARCH: 顧客検索（HTMX フラグメント）

| 項目 | 内容 |
|------|------|
| **URL** | `/s/customers/search/?q=<query>` |
| **View** | `staff.views.customer.CustomerSearchView` |
| **テンプレート** | `staff/_customer_search_results.html`（フラグメント） |
| **データソース** | `Customer.objects.for_store(store).filter(name__icontains=q)[:20]` |
| **レスポンス** | 顧客カードのリスト HTML。タップで `/s/customers/<id>/session/` に遷移 |

#### S-CUSTOMER-CREATE: 新規顧客登録（モーダル）

| 項目 | 内容 |
|------|------|
| **URL** | `/s/customers/new/` |
| **View** | `staff.views.customer.CustomerCreateView` |
| **テンプレート** | `staff/_customer_create_modal.html`（モーダル内フラグメント） |
| **入力** | 名前（必須、テキスト入力） |
| **操作** | 名前入力 → 「登録」ボタン → `CustomerService.create_customer(store=store, name=name)` → `HearingTaskService.generate_tasks(customer)` → 登録成功 → `/s/customers/<id>/session/` にリダイレクト |
| **Service** | `CustomerService.create_customer()` — segment='new', visit_count=0 が自動設定される。作成直後に `HearingTaskService.generate_tasks(customer)` を明示呼び出しし、未入力のヒアリング項目（age, area, shisha_experience）に対する Open タスクを生成する（C-05a 契約: `perform_create()` → `generate_tasks()`） |
| **エラー** | 名前が空 → インラインエラー |
| **Alpine.js** | モーダル開閉は親画面の `x-data` で制御 |
| **HTMX** | `hx-post="/s/customers/new/"` → 成功時 `HX-Redirect` ヘッダーで接客画面に遷移 |

#### S-SESSION: 接客画面

US-02 の核心。顧客を選択した後に表示される 1 画面で、タスク表示・消化、メモ入力、来店記録作成が完結する。

| 項目 | 内容 |
|------|------|
| **URL** | `/s/customers/<id>/session/` |
| **View** | `staff.views.session.SessionView` |
| **テンプレート** | `staff/session.html` |
| **レイアウト** | 上から: 顧客ヘッダー → タスクゾーングループ → 会話メモゾーン（Visit.conversation_memo に保存） → 来店記録作成ボタン → 直近来店履歴 |

**画面構成:**

```
┌─────────────────────────────────────┐
│ Topbar: 接客                 田中    │
├─────────────────────────────────────┤
│                                     │
│ [常連バッジ] 山田太郎               │
│ 来店 12 回 ・ 最終 3/28             │
│                                     │
│ ─── ヒアリングタスク ────────────── │
│ ┌─────────────────────────────────┐ │
│ │ ゾーン: 居住エリア              │ │  ← open タスクのみ表示
│ │   タップして入力  ▸              │ │
│ ├─────────────────────────────────┤ │
│ │ ゾーン: シーシャ歴              │ │
│ │   タップして入力  ▸              │ │
│ └─────────────────────────────────┘ │
│                                     │
│ ─── 会話メモ（来店記録に保存） ─── │
│ ┌─────────────────────────────────┐ │
│ │ ゾーン: メモ                    │ │
│ │   タップして入力  ▸              │ │  ← Visit.conversation_memo に保存
│ └─────────────────────────────────┘ │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │       来店記録を作成する         │ │  ← Primary ボタン（フル幅）
│ └─────────────────────────────────┘ │
│                                     │
│ ─── 直近の来店 ──────────────────── │
│ 3/28 田中 「前回は桃のフレーバー..」 │
│ 3/21 鈴木 「次は抹茶を試したい..」   │
│                                     │
├─────────────────────────────────────┤
│ 顧客 | [接客] | 来店記録 | マッチング │
└─────────────────────────────────────┘
```

**データソース:**

| 表示項目 | ソース | read/write |
|---------|--------|-----------|
| 顧客基本情報 | `Customer.objects.for_store(store).get(pk=id)` | read |
| セグメントバッジ | `customer.segment` | read |
| 来店回数 | `customer.visit_count` | read |
| 未消化タスク一覧 | `HearingTask.objects.for_store(store).filter(customer=customer, status='open')` | read |
| 直近来店履歴 | `Visit.objects.for_store(store).filter(customer=customer).select_related('staff').order_by('-visited_at')[:5]` | read |

**操作:**

| 操作 | HTMX / Alpine | Service | 詳細 |
|------|--------------|---------|------|
| タスクゾーンタップ → 展開 | Alpine.js: `x-data` で開閉 | なし | クライアントサイドの状態変更のみ |
| タスクの選択肢タップ（例: シーシャ歴 = 中級） | HTMX: `hx-patch="/s/customers/<id>/field/"` | View 内で `CustomerService.update_customer()` → `HearingTaskService.sync_tasks(customer)` を明示呼び出し（C-05a の設計に従い、Service 内部自動ではなく View/ViewSet が明示的に呼ぶ） | ゾーンが filled 状態に変化。タスクカードが消える |
| メモゾーンタップ → 展開 → テキスト入力 → 完了 | Alpine.js: 開閉。メモは即保存せず、来店記録作成時に `conversation_memo` として一緒に送信する | なし（メモは Alpine.js の状態として一時保持。来店記録作成ボタン押下時にサーバーに送信） | ゾーンが filled 状態に |
| 「来店記録を作成する」ボタン | HTMX: `hx-post="/s/visits/create/"` | `VisitService.create_visit(store, customer, staff=request.user, visited_at=today, conversation_memo=memo)` | トースト「来店記録を作成しました」。ボタンは再利用可能（同日複数来店正当）。`visitCreated` で画面部分更新 |
| 直近来店タップ | 表示のみ（US-03 S1 で `/s/customers/<id>/visits/` への遷移を実装） | なし | US-02 時点では遷移なし |

**タスク消化のフロー（ゾーン操作の詳細）:**

```
1. タスクゾーン（collapsed, empty）をタップ
2. Alpine.js: x-show="open" → ゾーンが展開
3. 選択チップが表示される（例: なし / 初心者 / 中級 / 上級）
4. チップをタップ
5. Alpine.js: selected = 'intermediate' → hidden input にセット
6. HTMX: hx-patch 発火 → サーバーに PATCH 送信
7. View: CustomerService.update_customer(id, shisha_experience='intermediate')
8. View: HearingTaskService.sync_tasks(customer) を明示呼び出し（C-05a 設計。sync_tasks は auto_close → generate の順に実行し、フィールド空戻し時のタスク再生成にも対応）
9. View: 更新後のゾーンフラグメントを返す（filled 状態）
10. HTMX: ゾーンが filled 状態に更新。タスクセクションからこのタスクが消える
```

#### S-VISIT-CREATE: 来店記録作成（HTMX）

| 項目 | 内容 |
|------|------|
| **URL** | `/s/visits/create/` |
| **View** | `staff.views.visit.VisitCreateView` |
| **HTMX 専用** | `hx-post` で呼ばれる。フルページ View ではない |
| **入力** | `customer_id`（hidden）、`visited_at`（default: today、hidden）、`conversation_memo`（メモゾーンの入力値。空文字可） |
| **Service** | `VisitService.create_visit(store=store, customer=customer, staff=request.user, visited_at=today, conversation_memo=memo)` |
| **レスポンス** | 成功: ボタンを再利用可能な状態で再描画 + `HX-Trigger: showToast, visitCreated` でトースト発火・画面部分更新。同日複数来店が正当のためボタンは無効化しない |
| **備考** | 同一顧客の同日複数来店は業務上正当（C-04 仕様: DB unique 制約なし）。重複チェックは行わない |

### US-03: 顧客・来店の簡易管理

#### S-CUSTOMER-DETAIL: 顧客簡易表示

| 項目 | 内容 |
|------|------|
| **URL** | `/s/customers/<id>/` |
| **View** | `staff.views.customer.CustomerDetailView` |
| **テンプレート** | `staff/customer_detail.html` |
| **表示項目** | 名前、セグメントバッジ、来店回数、年齢、居住エリア、シーシャ歴、LINE ID、メモ、直近来店 5 件 |
| **データソース** | `Customer.objects.for_store(store).get(pk=id)` + `Visit.objects.for_store(store).filter(customer=customer).select_related('staff').order_by('-visited_at')[:5]` |
| **操作** | 「編集」ボタン → `/s/customers/<id>/edit/` に遷移。来店タップ → 来店詳細（MVP ではタップ先なし、表示のみ） |

#### S-CUSTOMER-EDIT: 顧客基本編集

| 項目 | 内容 |
|------|------|
| **URL** | `/s/customers/<id>/edit/` |
| **View** | `staff.views.customer.CustomerEditView` |
| **テンプレート** | `staff/customer_edit.html` |
| **表示** | ゾーングループ: 名前（テキスト、モーダル）、年齢（選択）、居住エリア（テキスト）、シーシャ歴（選択）、LINE ID（テキスト）、メモ（テキスト） |
| **Service** | `CustomerService.update_customer()` → ヒアリング対象項目（age, area, shisha_experience）の変更時は `HearingTaskService.sync_tasks(customer)` を明示呼び出し（C-05a 設計） |
| **操作** | 各ゾーンで入力 → hx-patch で即保存。戻るボタン → `/s/customers/<id>/` |

#### S-VISIT-LIST: 来店履歴簡易表示

| 項目 | 内容 |
|------|------|
| **URL** | `/s/customers/<id>/visits/` |
| **View** | `staff.views.visit.VisitListView` |
| **テンプレート** | `staff/visit_list.html` |
| **表示項目** | 来店日、対応スタッフ名、会話メモ（先頭 50 文字）の一覧 |
| **データソース** | `Visit.objects.for_store(store).filter(customer=customer).select_related('staff').order_by('-visited_at')[:20]` |
| **操作** | 表示のみ（スタッフ UI では来店の編集・削除はできない） |

### US-04: 会計後マッチング

#### S-MATCHING: 会計後マッチング画面

| 項目 | 内容 |
|------|------|
| **URL** | `/s/matching/` |
| **View** | `staff.views.matching.MatchingView` |
| **テンプレート** | `staff/matching.html` |
| **表示項目** | `pending_review` の CsvImportRow 一覧（当日分）。各行: 営業日、レシート番号、CSV 顧客名（参考）。候補は行ごとに遅延ロード |
| **データソース** | `CsvImportRow.objects.for_store(store).filter(status='pending_review', business_date=today).select_related('csv_import')` |
| **操作** | 行タップ → 候補顧客一覧を HTMX で遅延ロード。候補タップ → 確定（HTMX PATCH）。「却下」→ rejected に更新 |
| **補足** | `validated`（候補 0 件）の行はスタッフ UI に表示しない（マッチング不可のため）。`pending_review` のみ表示する。C-06 の candidates API は `pending_review` 以外で 400 を返すため、ステータスガードと整合する |

**マッチング操作フロー:**

| ステップ | 操作 | HTMX / Alpine | Service |
|---------|------|--------------|---------|
| 1 | pending_review 行タップ | Alpine.js: 行を展開 | なし |
| 2 | 候補一覧を遅延ロード | HTMX: `hx-get="/s/matching/<row_id>/candidates/"` → candidates API 相当（毎回再計算） | candidates は永続化しない。同一 Store × 同一営業日の Visit から候補を算出 |
| 3 | 候補タップ（確定） | HTMX: `hx-patch="/s/matching/<row_id>/confirm/"` | confirm（`select_for_update` で排他制御。visit_id が候補集合に含まれるか検証） |
| 4 | 却下 | HTMX: `hx-patch="/s/matching/<row_id>/reject/"` | reject（`select_for_update`。ステータスを `rejected` に更新。オーナーが後から再検討する場合は Phase 2） |

## 6. Owner UI 画面設計

### UO-01: ログイン・スタッフ管理

#### O-LOGIN: ログイン画面

| 項目 | 内容 |
|------|------|
| **URL** | `/o/login/` |
| **View** | `owner.views.auth.OwnerLoginView` |
| **テンプレート** | `owner/login.html`（`base.html` を直接継承。Sidebar なし） |
| **表示** | ブランドロゴ、QR トークン入力フィールド、ログインボタン |
| **操作** | QR トークン入力 → POST → `QRAuthService.authenticate(token)` → role チェック → owner でなければエラー → セッション確立 → `/o/dashboard/` にリダイレクト |
| **エラー** | 無効なトークン、期限切れ、role が owner でない → インラインエラー |
| **QR リンク経由** | URL が `/o/login/#token={token}` の場合、ページ読み込み時に JS が `location.hash` から token を読み取り、`history.replaceState` で hash を除去した後、自動 POST する（staff login と同じ仕組み） |

#### O-STAFF-LIST: スタッフ一覧

| 項目 | 内容 |
|------|------|
| **URL** | `/o/staff/` |
| **View** | `owner.views.staff_mgmt.StaffListView` |
| **テンプレート** | `owner/staff_list.html` |
| **表示項目** | テーブル: 表示名、ロール（owner/staff）、種別（owner/regular/temporary）、作成日 |
| **データソース** | `Staff.objects.filter(store=store, is_active=True).order_by('display_name')` |
| **操作** | 行クリック → `/o/staff/<id>/`。「新規スタッフ作成」ボタン → `/o/staff/new/` |

**備考**: Staff モデルは `StoreScopedManager` ではなく Django の標準 Manager を使用するため（AbstractUser 継承の制約）、`filter(store=store)` を明示的に書く。C-02 仕様に従い、無効化済み（`is_active=False`）のスタッフは一覧に表示しない。無効化済みスタッフの詳細画面（`/o/staff/<id>/`）への直接 URL アクセスも 404 として扱う。

#### O-STAFF-CREATE: スタッフ作成

| 項目 | 内容 |
|------|------|
| **URL** | `/o/staff/new/` |
| **View** | `owner.views.staff_mgmt.StaffCreateView` |
| **テンプレート** | `owner/staff_create.html` |
| **入力** | 表示名（必須）、ロール（選択: owner/staff）、種別（選択: owner/regular/temporary） |
| **Service** | (1) スタッフ作成: `StaffViewSet.perform_create()` 相当のロジックで `store=request.user.store` を自動設定してスタッフを作成する。(2) 作成直後に QR トークン自動発行: `QRAuthService` 経由で `QRToken` を生成。`expires_in_hours` は `staff_type` に応じたデフォルト最大値を使用（temporary=8h, regular/owner=720h。C-02 の有効期限ルール参照）。QR URL はフラグメント方式で role 別: staff 向けは `/s/login/#token={token}`、owner 向けは `/o/login/#token={token}`。`build_qr_url()` の `base_url` に role prefix を含める。**注: 「write は Service 必須」の例外（後述 §1.1）** |
| **操作** | フォーム送信 → スタッフ作成 + QR 発行 → スタッフ詳細画面にリダイレクト。QR コード（URL）が表示される |

#### O-STAFF-DETAIL: スタッフ詳細・無効化

| 項目 | 内容 |
|------|------|
| **URL** | `/o/staff/<id>/` |
| **View** | `owner.views.staff_mgmt.StaffDetailView` |
| **テンプレート** | `owner/staff_detail.html` |
| **表示項目** | 表示名、ロール、種別、状態、作成日、QR コード（画像 or リンク） |
| **データソース** | `Staff.objects.get(pk=id, store=store, is_active=True)` + 最新 QRToken。`is_active=False` の場合は 404（C-02 仕様。無効化済みスタッフは一覧にも詳細にもアクセス不可） |
| **操作** | 「QR 再発行」ボタン → POST → 新しい QR トークン発行 → 表示更新（無効化済みスタッフへの QR 発行は不可。C-02 仕様）。「無効化」ボタン → 確認ダイアログ → POST → `is_active=False` に更新（自分自身の無効化、最後のオーナーの無効化は C-02 のガード条件で拒否） |
| **Alpine.js** | 確認ダイアログの開閉: `x-data="{ showConfirm: false }"` |
| **HTMX** | QR 再発行: `hx-post` → QR 表示部分を差し替え |

### UO-02: 顧客管理

#### O-CUSTOMER-LIST: 顧客一覧

| 項目 | 内容 |
|------|------|
| **URL** | `/o/customers/` |
| **View** | `owner.views.customer.CustomerListView` |
| **テンプレート** | `owner/customer_list.html` |
| **表示** | フィルタバー + テーブル + ページネーション |

**テーブル列:**

| 列 | データソース | ソート | フィルタ |
|----|------------|--------|---------|
| 名前 | `customer.name` | o | 検索（部分一致） |
| セグメント | `customer.segment` → バッジ | - | セグメント選択フィルタ |
| 来店回数 | `customer.visit_count` | o | - |
| 最終来店日 | annotate or Subquery | o | - |
| 未消化タスク | annotate Count | - | - |

**データソース**: `Customer.objects.for_store(store)`。検索: `.filter(name__icontains=q)`。セグメントフィルタ: `.filter(segment=segment)`。ソート: `.order_by(sort_field)`。ページネーション: Django Paginator, 25 件/ページ。

**HTMX**: フィルタ・ソート・ページ切替のいずれも `hx-get` → テーブル本体のみ差し替え。URL パラメータはブラウザ履歴に反映する（`hx-push-url="true"`）。

#### O-CUSTOMER-DETAIL: 顧客詳細

| 項目 | 内容 |
|------|------|
| **URL** | `/o/customers/<id>/` |
| **View** | `owner.views.customer.CustomerDetailView` |
| **テンプレート** | `owner/customer_detail.html` |
| **表示項目** | 全属性（名前, 年齢, 居住エリア, シーシャ歴, LINE ID, メモ, セグメント, 来店回数, 作成日, 更新日）+ 来店履歴テーブル + 未消化タスク一覧 |
| **データソース** | `Customer.objects.for_store(store).get(pk=id)` + `Visit.objects.for_store(store).filter(customer=customer).select_related('staff')` + `HearingTask.objects.for_store(store).filter(customer=customer, status='open')` |
| **操作** | 「編集」ボタン → `/o/customers/<id>/edit/` |

#### O-CUSTOMER-EDIT: 顧客編集

| 項目 | 内容 |
|------|------|
| **URL** | `/o/customers/<id>/edit/` |
| **View** | `owner.views.customer.CustomerEditView` |
| **テンプレート** | `owner/customer_edit.html` |
| **入力** | 全フィールド: 名前（必須）、年齢（任意、数値入力）、居住エリア（任意、テキスト）、シーシャ歴（任意、select）、LINE ID（任意、テキスト）、メモ（任意、textarea） |
| **Form** | `owner.forms.customer.CustomerEditForm` — Django ModelForm |
| **Service** | `CustomerService.update_customer()` → ヒアリング対象項目（age, area, shisha_experience）の変更時は `HearingTaskService.sync_tasks(customer)` を明示呼び出し（C-05a 設計。コア層の CustomerViewSet.perform_update() と同一の責務を UI View でも果たす） |
| **操作** | フォーム送信 → バリデーション → Service 呼び出し → sync_tasks → 成功: 顧客詳細にリダイレクト + トースト |

### UO-03: 来店管理・セグメント設定

#### O-VISIT-LIST: 来店一覧

| 項目 | 内容 |
|------|------|
| **URL** | `/o/visits/` |
| **View** | `owner.views.visit.VisitListView` |
| **テンプレート** | `owner/visit_list.html` |
| **表示** | フィルタバー + テーブル + ページネーション |

**テーブル列:**

| 列 | データソース | ソート | フィルタ |
|----|------------|--------|---------|
| 来店日 | `visit.visited_at` | o（デフォルト DESC） | 日付範囲フィルタ |
| 顧客名 | `visit.customer.name` | o | 顧客名検索 |
| セグメント | `visit.customer.segment` → バッジ | - | セグメント選択 |
| 対応スタッフ | `visit.staff.display_name` | - | スタッフ選択 |
| メモ | `visit.conversation_memo`（先頭 30 文字） | - | - |

**データソース**: `Visit.objects.for_store(store).select_related('customer', 'staff')`。25 件/ページ。

**HTMX**: O-CUSTOMER-LIST と同じパターン（フィルタ・ソート・ページ切替でテーブル差し替え）。

#### O-VISIT-EDIT: 来店編集

| 項目 | 内容 |
|------|------|
| **URL** | `/o/visits/<id>/edit/` |
| **View** | `owner.views.visit.VisitEditView` |
| **テンプレート** | `owner/visit_edit.html` |
| **入力** | 来店日（DateField）、会話メモ（textarea）。顧客・対応スタッフは変更不可（表示のみ） |
| **Service** | `VisitService.update_visit()` — C-04 の `VisitUpdateRequest` に準拠し、更新可能フィールドは `visited_at` と `conversation_memo` のみ |
| **備考** | `customer_id` は immutable（C-04 仕様）。`staff` も更新対象外（C-04 の VisitUpdateRequest に staff フィールドなし）。UI では両方を読み取り専用で表示する |

#### O-VISIT-DELETE: 来店削除確認

| 項目 | 内容 |
|------|------|
| **URL** | `/o/visits/<id>/delete/` |
| **View** | `owner.views.visit.VisitDeleteView` |
| **表示** | 確認ダイアログ（Alpine.js モーダル）: 「この来店記録を削除すると、来店回数とセグメントが再計算されます。削除しますか？」 |
| **Service** | `VisitService.delete_visit()` — 論理削除。`visit_count` と `segment` が自動再計算される |
| **操作** | 「削除」ボタン → POST → 論理削除 → 来店一覧にリダイレクト + トースト |

#### O-SEGMENT-SETTINGS: セグメント閾値設定

| 項目 | 内容 |
|------|------|
| **URL** | `/o/segments/settings/` |
| **View** | `owner.views.segment.SegmentSettingsView` |
| **テンプレート** | `owner/segment_settings.html` |
| **表示** | 現在の閾値テーブル（セグメント名, min_visits, max_visits, display_order）+ 変更フォーム + 影響件数プレビュー |
| **データソース** | `SegmentThreshold.objects.for_store(store).order_by('display_order')` |
| **操作** | 閾値変更 → 「プレビュー」ボタン → HTMX でサーバーに一時計算依頼 → 影響件数表示（「この変更で N 件の顧客のセグメントが変わります」）→ 「確定」ボタン → Service 呼び出し |
| **Service** | (1) 閾値バリデーション: `SegmentThreshold.validate_store_thresholds()` クラスメソッドで整合性検証（C-04 のモデル層検証を利用）。(2) 閾値一括更新: `SegmentThresholdViewSet` の PUT 相当のロジック。(3) 再計算: `SegmentService.bulk_recalculate_segments(store)` を呼び出す。**注: 閾値更新は「write は Service 必須」の例外（後述 §1.1）。再計算は Service 経由** |

**影響プレビューのフロー:**

```
1. オーナーが閾値を変更入力
2. 「プレビュー」ボタン → hx-post="/o/segments/preview/"
3. View: 現在の visit_count × 新閾値で影響件数を計算（DB 更新はしない）
4. HTMX: プレビュー結果を表示
5. 「確定」ボタン → hx-post="/o/segments/apply/"
6. View: SegmentThreshold 一括更新 + SegmentService.bulk_recalculate_segments(store)
7. トースト: 「セグメント閾値を更新しました。N 件の顧客のセグメントが再計算されました」
```

### UO-04: CSV インポート・マッチング管理

#### O-CSV-UPLOAD: CSV アップロード

| 項目 | 内容 |
|------|------|
| **URL** | `/o/imports/upload/` |
| **View** | `owner.views.csv_import.CsvUploadView` |
| **テンプレート** | `owner/csv_upload.html` |
| **表示** | ファイルアップロードフォーム + 過去のインポート履歴一覧 |
| **データソース** | 過去履歴: `CsvImport.objects.for_store(store).order_by('-created_at')[:10]` |
| **操作** | ファイル選択 → 「アップロード」ボタン → POST → `ImportService.upload_csv(store, file, uploaded_by=request.user)` → 成功（status='completed'）: インポート行一覧 `/o/imports/<id>/rows/` にリダイレクト + トースト。失敗（400）: 同画面でエラーメッセージ表示（ヘッダー不正 / 全行不正 等） |
| **備考** | C-06 Stage 1 はアップロード時に同期で CSV パース・バリデーション・CsvImportRow 作成を完了する設計（非同期処理・ポーリングは不要）。アップロード完了 = status='completed' or 400 エラーが即座に返る |

#### O-CSV-ROWS: インポート行一覧

| 項目 | 内容 |
|------|------|
| **URL** | `/o/imports/<id>/rows/` |
| **View** | `owner.views.csv_import.CsvImportRowListView` |
| **テンプレート** | `owner/csv_import_rows.html` |
| **表示** | インポート情報（ファイル名, ステータス, 行数）+ 行テーブル |

**テーブル列:**

| 列 | データソース |
|----|------------|
| 行番号 | `row.row_number` |
| 営業日 | `row.business_date` |
| レシート番号 | `row.receipt_no` |
| ステータス | `row.status` → バッジ（validated / pending_review / confirmed / rejected） |
| マッチ先 | `row.matched_visit` → 顧客名（confirmed の場合） |

**操作**: 「マッチング実行」ボタン → POST → `MatchingService.execute_matching(csv_import)` → マッチング管理画面にリダイレクト

#### O-CSV-MATCHING: マッチング管理

| 項目 | 内容 |
|------|------|
| **URL** | `/o/imports/<id>/matching/` |
| **View** | `owner.views.csv_import.MatchingManageView` |
| **テンプレート** | `owner/csv_import_matching.html` |
| **表示** | pending_review の行一覧。候補は行ごとに遅延ロード（N+1 回避。C-06 仕様に準拠） |
| **データソース** | 行一覧: `CsvImportRow.objects.for_store(store).filter(csv_import=csv_import, status='pending_review')`。候補: 行展開時に HTMX で個別取得（`hx-get="/o/imports/<id>/rows/<row_id>/candidates/"` → candidates API 相当の View が候補を毎回再計算して返す） |
| **操作** | 行クリック → HTMX で候補をその行に遅延ロード。候補選択 → 「確定」ボタン → HTMX PATCH → confirm（`select_for_update` で排他制御）→ 行ステータスが confirmed に更新。「却下」ボタン → HTMX PATCH → reject → 行ステータスが rejected に |

### UO-05: 分析ダッシュボード

#### O-DASHBOARD: 分析ダッシュボード

| 項目 | 内容 |
|------|------|
| **URL** | `/o/dashboard/` |
| **View** | `owner.views.dashboard.DashboardView` |
| **テンプレート** | `owner/dashboard.html` |
| **表示** | 3 つのチャート + 数値サマリー |

**チャート構成:**

| チャート | 種別 | データソース | Chart.js type |
|---------|------|-------------|--------------|
| 日別来客数推移 | 折れ線 | `AnalyticsService.daily_summary(store, date_from, date_to)` | `line` |
| セグメント比率 | 円 | `AnalyticsService.segment_ratio(store, date_from, date_to)` | `doughnut` |
| スタッフ別対応数 | 棒 | `AnalyticsService.staff_summary(store, date_from, date_to)` | `bar` |

**数値サマリー（チャートの上に配置）:**

| 数値 | 計算 |
|------|------|
| 今日の来客数 | `daily_summary` の当日値 |
| 今月の来客数 | `daily_summary` の当月合計 |
| 新規率 | `segment_ratio(store, date_from, date_to)` の new 比率 |
| アクティブ顧客数 | `Customer.objects.for_store(store).count()` |

**期間フィルタ**: デフォルト: 直近 30 日。ドロップダウンで 7 日 / 30 日 / 90 日 を選択。HTMX でチャートデータを再取得。

**Chart.js データ渡し:**

```python
# View
class DashboardView(OwnerRequiredMixin, TemplateView):
    def get_context_data(self, **kwargs):
        store = self.request.user.store
        date_to = date.today()
        date_from = date_to - timedelta(days=30)
        return {
            'daily_data': AnalyticsService.daily_summary(store, date_from, date_to),
            'segment_data': AnalyticsService.segment_ratio(store, date_from, date_to),
            'staff_data': AnalyticsService.staff_summary(store, date_from, date_to),
        }
```

```html
<!-- Template -->
{{ daily_data|json_script:"daily-data" }}
{{ segment_data|json_script:"segment-data" }}
{{ staff_data|json_script:"staff-data" }}
<script>
  const dailyData = JSON.parse(document.getElementById('daily-data').textContent);
  // Chart.js 初期化...
</script>
```

## 7. Cluster / Slice 定義

### 7.1 US-01: ログイン

| 項目 | 内容 |
|------|------|
| **Slice 数** | 1 本 |
| **理由** | ログイン + ログアウトはセットで完結する小スコープ。分割不要 |

#### Slice 1: QR ログイン + ログアウト

**ブランチ説明部**: `us01-staff-login`（実ブランチ名は `feat/<issue番号>-us01-staff-login`。`UI_PIPELINE.md` §2 参照）

**スコープ**: QR ログイン画面、ログアウト処理、base_staff.html（BottomTab 含む）

**対象ファイル**:
- views: `ui/staff/views/auth.py`
- templates: `ui/templates/ui/base.html`, `ui/templates/ui/base_staff.html`, `ui/templates/ui/staff/login.html`
- urls: `ui/staff/urls.py`, `ui/urls.py`
- static: `ui/static/ui/css/` (Tailwind ビルド設定)
- config: `tailwind.config.js`

precondition:
- コア層の C-02 全 Slice が完了済み（`QRAuthService` が動作する）
- コア層の Django プロジェクトに UI app が組み込み可能な状態

postcondition:
- `/s/login/` でQR トークン入力 → ログイン → セッション確立
- `/s/login/#token={token}` で QR リンク経由アクセス → JS が token を読み取り自動ログイン（hash は送信前に `history.replaceState` で除去）
- ログイン後 `/s/customers/` にリダイレクト → stub view が「準備中」を表示する（US-02 Slice 1 で本実装に置き換え）
- `/s/logout/` でセッション破棄 → `/s/login/` にリダイレクト
- `base.html` に HTMX / Alpine.js / Tailwind CSS / Google Fonts の読み込みが含まれる
- `base_staff.html` に Topbar（操作者名表示）+ BottomTab ナビゲーションが含まれる
- 未認証状態で `/s/customers/` にアクセス → `/s/login/` にリダイレクト（stub view に `LoginRequiredMixin` 付与済み）
- 無効トークン → エラーメッセージ表示

**完了条件**: ブラウザで QR ログイン（手動入力 + QR リンク経由の両方）→ `/s/customers/` の stub view が「準備中」を表示（`base_staff.html` 適用、BottomTab + Topbar あり）→ ログアウト → ログイン画面に戻る、が確認できる。未認証で `/s/customers/` → `/s/login/` へリダイレクトされる。QR リンク経由後にブラウザ戻る/再読込で token が再送されないことも検証する。stub view は US-02 Slice 1 で本実装に置き換えられる

### 7.2 US-02: 接客フロー

| 項目 | 内容 |
|------|------|
| **Slice 数** | 2 本 |
| **理由** | 顧客選択（検索 + 新規登録）と接客画面（タスク消化 + メモ + 来店記録）は依存関係がある（選択 → 接客の順序）が、それぞれが十分な実装量を持つ |

#### Slice 1: 顧客選択 + 新規登録

**ブランチ説明部**: `us02-s1-customer-select`（実ブランチ名は `UI_PIPELINE.md` §2 参照）

**スコープ**: 顧客選択画面（最近来た順一覧）、検索モーダル、新規登録モーダル

**対象ファイル**:
- views: `ui/staff/views/customer.py`
- forms: `ui/staff/forms/customer.py`
- templates: `ui/templates/ui/staff/customer_select.html`, `ui/templates/ui/staff/_customer_search_results.html`, `ui/templates/ui/staff/_customer_create_modal.html`
- urls: `ui/staff/urls.py` (追記)

precondition:
- US-01 Slice 1 完了（base_staff.html, BottomTab, 認証基盤が動作）
- コア層 C-03 完了（Customer モデル + Service が動作）
- コア層 C-05a 完了（顧客作成時にタスク生成が動作）

postcondition:
- `/s/customers/` で最近来た順の顧客カード一覧（セグメントバッジ、来店回数、最終来店日）が表示される
- 検索バータップ → モーダル起動 → 文字入力 → インクリメンタル検索結果表示（HTMX、300ms デバウンス）
- 検索結果の顧客タップ → `/s/customers/<id>/session/` にリダイレクト
- 新規登録ボタン → モーダル起動 → 名前入力 → 登録 → `/s/customers/<id>/session/` にリダイレクト
- 顧客作成時に segment='new', visit_count=0 が自動設定される
- 顧客作成直後に `HearingTaskService.generate_tasks(customer)` が呼ばれ、未入力ヒアリング項目の Open タスクが生成される（C-05a 契約）
- BottomTab の「顧客」タブがアクティブ状態

**完了条件**: 顧客検索 → 選択 → 接客画面に遷移（接客画面 View は US-02 Slice 2 で実装。本 Slice ではリダイレクト先 URL の設定を検証）。新規登録 → タスク生成確認 → 接客画面に遷移。

#### Slice 2: 接客画面（タスク・メモ・来店記録）

**ブランチ説明部**: `us02-s2-session`（実ブランチ名は `UI_PIPELINE.md` §2 参照）

**スコープ**: 接客画面（タスク表示・消化、メモ入力、来店記録作成）

**対象ファイル**:
- views: `ui/staff/views/session.py`, `ui/staff/views/visit.py`
- templates: `ui/templates/ui/staff/session.html`, `ui/templates/ui/staff/_zone_*.html`（ゾーンフラグメント群）
- urls: `ui/staff/urls.py` (追記)

precondition:
- US-02 Slice 1 完了（顧客選択 → `/s/customers/<id>/session/` への遷移が動作）
- コア層 C-04 S2 完了（VisitService が動作）
- コア層 C-05a, C-05b 完了（HearingTaskService の auto close + 表示が動作）

postcondition:
- `/s/customers/<id>/session/` で顧客情報 + タスク一覧 + メモ + 来店記録作成ボタン + 直近来店 5 件が 1 画面に表示される
- タスクゾーンタップ → 展開 → チップ選択 → HTMX PATCH → 顧客フィールド更新 + タスク auto close → ゾーンが filled に変化
- メモゾーンタップ → 展開 → テキスト入力 → 「完了」→ Alpine.js 状態として一時保持（即保存しない）
- 「来店記録を作成する」ボタン → HTMX POST → VisitService.create_visit(conversation_memo=memo) → メモが Visit に保存される → トースト表示 → ボタン再利用可能（同日複数来店正当）→ `visitCreated` で顧客ヘッダー・来店履歴を自動更新
- 全タスク消化済みの場合、タスクセクションに「全てのヒアリングが完了しています」表示

**完了条件**: 顧客選択 → 接客画面 → タスク消化 → メモ入力 → 来店記録作成、の一連のフローがブラウザで動作する

### 7.3 US-03: 顧客・来店の簡易管理

| 項目 | 内容 |
|------|------|
| **Slice 数** | 1 本 |
| **理由** | 顧客簡易表示・基本編集・来店履歴の 3 画面はいずれも軽量で、独立した業務フローを持たない補助画面群。まとめて 1 Slice |

#### Slice 1: 顧客簡易表示 + 基本編集 + 来店履歴

**ブランチ説明部**: `us03-customer-detail`（実ブランチ名は `UI_PIPELINE.md` §2 参照）

**スコープ**: 顧客簡易表示、顧客基本編集（ゾーン）、来店履歴一覧

**対象ファイル**:
- views: `ui/staff/views/customer.py` (追記), `ui/staff/views/visit.py` (追記)
- forms: `ui/staff/forms/customer.py` (追記)
- templates: `ui/templates/ui/staff/customer_detail.html`, `ui/templates/ui/staff/customer_edit.html`, `ui/templates/ui/staff/visit_list.html`
- urls: `ui/staff/urls.py` (追記)

precondition:
- US-01 Slice 1 完了（base_staff.html が動作）
- コア層 C-03, C-04 S2 完了
- コア層 C-05a 完了（HearingTaskService.sync_tasks が動作。顧客編集時のタスク同期に必要）

postcondition:
- `/s/customers/<id>/` で顧客の全属性 + セグメントバッジ + 直近来店 5 件が表示される
- `/s/customers/<id>/edit/` でゾーンベースの編集が可能。各ゾーンの変更が hx-patch で即保存される
- ヒアリング対象項目（age, area, shisha_experience）の編集後に `HearingTaskService.sync_tasks()` が呼ばれ、タスクが auto close / 再生成される
- `/s/customers/<id>/visits/` で直近 20 件の来店記録が時系列で表示される

**完了条件**: 顧客詳細閲覧 → 編集 → 保存 → 来店履歴閲覧がブラウザで動作する

### 7.4 US-04: 会計後マッチング

| 項目 | 内容 |
|------|------|
| **Slice 数** | 1 本 |
| **理由** | マッチング画面は 1 画面で候補表示 → 確定/却下が完結する |

#### Slice 1: 会計後マッチング

**ブランチ説明部**: `us04-matching`（実ブランチ名は `UI_PIPELINE.md` §2 参照）

**スコープ**: pending_review 明細一覧、候補遅延ロード、確定（confirm）/却下（reject）

**対象ファイル**:
- views: `ui/staff/views/matching.py`
- templates: `ui/templates/ui/staff/matching.html`, `ui/templates/ui/staff/_matching_candidates.html`
- urls: `ui/staff/urls.py` (追記)

precondition:
- US-01 Slice 1 完了
- コア層 C-06 全 Slice 完了（ImportService, MatchingService が動作）

postcondition:
- `/s/matching/` で当日の `pending_review` CsvImportRow が表示される（`validated` = 候補 0 件の行は表示しない）
- 行タップ → 候補顧客一覧が HTMX で遅延ロードされる（candidates API 相当。毎回再計算）
- 候補タップ → HTMX PATCH → confirm（select_for_update で排他制御）→ 行ステータスが confirmed に更新
- 却下ボタン → HTMX PATCH → reject → 行ステータスが rejected に更新
- pending_review 明細がない場合「マッチ待ちの明細はありません」表示
- BottomTab の「マッチング」タブがアクティブ状態

**完了条件**: pending_review 明細の表示 → 候補遅延ロード → 確定/却下がブラウザで動作する

### 7.5 UO-01: ログイン・スタッフ管理

| 項目 | 内容 |
|------|------|
| **Slice 数** | 2 本 |
| **理由** | ログイン（+ base_owner.html）とスタッフ管理（一覧 + 作成 + 詳細/無効化 + QR 発行）は独立した機能。ログインが先行必須 |

#### Slice 1: オーナーログイン + base_owner.html

**ブランチ説明部**: `uo01-s1-owner-login`（実ブランチ名は `UI_PIPELINE.md` §2 参照）

**スコープ**: ログイン画面、base_owner.html（Sidebar + Header）、OwnerRequiredMixin

**対象ファイル**:
- views: `ui/owner/views/auth.py`
- templates: `ui/templates/ui/base_owner.html`, `ui/templates/ui/owner/login.html`
- urls: `ui/owner/urls.py`, `ui/urls.py` (追記)
- mixins: `ui/mixins.py` (OwnerRequiredMixin)

precondition:
- US-01 Slice 1 完了（base.html, LoginRequiredMixin が存在）
- コア層 C-02 完了

postcondition:
- `/o/login/` でオーナー用ログインが動作する
- `/o/login/#token={token}` で QR リンク経由アクセス → JS が token を読み取り自動ログイン（hash は送信前に `history.replaceState` で除去）
- staff ロールでログイン → エラー表示（オーナー専用）
- `base_owner.html` に Sidebar ナビゲーション + Header（ログインユーザー名）が含まれる
- Chart.js CDN の読み込みが `base_owner.html` に含まれる
- `/o/dashboard/` に `OwnerRequiredMixin` 付き stub view を配置（「準備中」表示。UO-05 Slice 1 で本実装に置き換え）
- 未認証で `/o/dashboard/` → `/o/login/` にリダイレクト（stub view の `OwnerRequiredMixin` が機能）
- staff ロールで `/o/dashboard/` → `/s/customers/` にリダイレクト（stub view の `OwnerRequiredMixin` が機能）

**完了条件**: オーナーとしてログイン（手動入力 + QR リンク経由の両方）→ `/o/dashboard/` の stub view が「準備中」を表示（`base_owner.html` 適用、Sidebar + Header あり）→ staff でログイン → `/s/customers/` にリダイレクト → 未認証で `/o/dashboard/` → `/o/login/` にリダイレクト。QR リンク経由後にブラウザ戻る/再読込で token が再送されないことも検証する。stub view は UO-05 Slice 1 で本実装に置き換えられる

#### Slice 2: スタッフ管理

**ブランチ説明部**: `uo01-s2-staff-mgmt`（実ブランチ名は `UI_PIPELINE.md` §2 参照）

**スコープ**: スタッフ一覧、作成、詳細/無効化、QR 発行

**対象ファイル**:
- views: `ui/owner/views/staff_mgmt.py`
- forms: `ui/owner/forms/staff.py`
- templates: `ui/templates/ui/owner/staff_list.html`, `ui/templates/ui/owner/staff_create.html`, `ui/templates/ui/owner/staff_detail.html`
- urls: `ui/owner/urls.py` (追記)

precondition:
- UO-01 Slice 1 完了（base_owner.html, OwnerRequiredMixin が動作）
- コア層 C-02 完了（Staff CRUD + QRToken 発行が動作）

postcondition:
- `/o/staff/` でスタッフ一覧テーブルが表示される
- `/o/staff/new/` でスタッフ作成 → QR トークン自動発行。発行された QR URL が role に応じて `/s/login/#token=...`（staff/regular/temporary）または `/o/login/#token=...`（owner）を指す
- `/o/staff/<id>/` でスタッフ詳細表示 + QR 表示 + QR 再発行 + 無効化が動作する
- 無効化時に確認ダイアログが表示される
- Sidebar の「スタッフ管理」がアクティブ状態

**完了条件**: スタッフ作成 → QR URL が role 別に正しく生成される → 一覧表示 → 詳細 → QR 再発行 → 無効化がブラウザで動作する

### 7.6 UO-02: 顧客管理

| 項目 | 内容 |
|------|------|
| **Slice 数** | 1 本 |
| **理由** | 一覧 + 詳細 + 編集は典型的な CRUD で分割する理由がない |

#### Slice 1: 顧客一覧 + 詳細 + 編集

**ブランチ説明部**: `uo02-customer-mgmt`（実ブランチ名は `UI_PIPELINE.md` §2 参照）

**スコープ**: 顧客一覧（フィルタ・ソート・ページネーション）、顧客詳細、顧客編集

**対象ファイル**:
- views: `ui/owner/views/customer.py`
- forms: `ui/owner/forms/customer.py`
- templates: `ui/templates/ui/owner/customer_list.html`, `ui/templates/ui/owner/_customer_table.html`, `ui/templates/ui/owner/customer_detail.html`, `ui/templates/ui/owner/customer_edit.html`
- urls: `ui/owner/urls.py` (追記)

precondition:
- UO-01 Slice 1 完了（base_owner.html が動作）
- コア層 C-03 完了（CustomerService が動作）
- コア層 C-05a 完了（HearingTaskService.sync_tasks が動作。顧客編集時のタスク同期に必要）
- コア層 C-05b 完了（タスク表示が顧客詳細に含まれるため）

postcondition:
- `/o/customers/` でフィルタ・ソート・検索・ページネーション付きの顧客一覧テーブルが表示される
- HTMX でフィルタ操作時にテーブル本体のみ差し替え（フルページリロードなし）
- `/o/customers/<id>/` で全属性 + 来店履歴 + 未消化タスクが表示される
- `/o/customers/<id>/edit/` で全フィールド編集 → Service 呼び出し → ヒアリング対象項目変更時は sync_tasks() → 詳細画面にリダイレクト
- 25 件/ページのページネーション

**完了条件**: 顧客一覧のフィルタ・ソート → 詳細閲覧 → 編集 → 保存がブラウザで動作する

### 7.7 UO-03: 来店管理・セグメント設定

| 項目 | 内容 |
|------|------|
| **Slice 数** | 2 本 |
| **理由** | 来店 CRUD とセグメント閾値設定は業務的に独立しており、Service 依存も異なる（VisitService vs SegmentService）。プレビュー + 一括再計算のロジックがある閾値設定は独立 Slice にすべき |

#### Slice 1: 来店一覧 + 編集 + 削除

**ブランチ説明部**: `uo03-s1-visit-mgmt`（実ブランチ名は `UI_PIPELINE.md` §2 参照）

**スコープ**: 来店一覧（フィルタ・ソート）、来店編集、来店削除（確認ダイアログ）

**対象ファイル**:
- views: `ui/owner/views/visit.py`
- forms: `ui/owner/forms/visit.py`
- templates: `ui/templates/ui/owner/visit_list.html`, `ui/templates/ui/owner/_visit_table.html`, `ui/templates/ui/owner/visit_edit.html`
- urls: `ui/owner/urls.py` (追記)

precondition:
- UO-01 Slice 1 完了
- コア層 C-04 S2 完了（VisitService が動作）

postcondition:
- `/o/visits/` でフィルタ・ソート・ページネーション付きの来店一覧テーブルが表示される
- `/o/visits/<id>/edit/` で来店記録を編集できる（customer_id は immutable）
- 削除時に確認ダイアログ表示 → 論理削除 → visit_count とセグメント再計算 → 一覧に戻る

**完了条件**: 来店一覧 → 編集 → 削除がブラウザで動作する

#### Slice 2: セグメント閾値設定

**ブランチ説明部**: `uo03-s2-segment-settings`（実ブランチ名は `UI_PIPELINE.md` §2 参照）

**スコープ**: 閾値一覧表示、変更フォーム、影響プレビュー、確定 + 一括再計算

**対象ファイル**:
- views: `ui/owner/views/segment.py`
- forms: `ui/owner/forms/segment.py`
- templates: `ui/templates/ui/owner/segment_settings.html`, `ui/templates/ui/owner/_segment_preview.html`
- urls: `ui/owner/urls.py` (追記)

precondition:
- UO-01 Slice 1 完了
- コア層 C-04 全 Slice 完了（SegmentService + 閾値 API が動作）

postcondition:
- `/o/segments/settings/` で現在の閾値が表示される
- 閾値変更 → 「プレビュー」→ 影響件数が HTMX で表示される
- 「確定」→ 閾値更新 + 一括再計算 → トースト表示
- セグメント再計算後、顧客一覧のセグメントバッジが更新されている

**完了条件**: 閾値変更 → プレビュー → 確定 → 再計算がブラウザで動作する

### 7.8 UO-04: CSV インポート・マッチング管理

| 項目 | 内容 |
|------|------|
| **Slice 数** | 2 本 |
| **理由** | CSV アップロード + 行一覧（Stage 1）とマッチング管理（Stage 2）はコア層の C-06 Slice 分割と対応する。アップロードが先に動作しないとマッチングに進めない |

#### Slice 1: CSV アップロード + 行一覧

**ブランチ説明部**: `uo04-s1-csv-upload`（実ブランチ名は `UI_PIPELINE.md` §2 参照）

**スコープ**: CSV アップロード（同期処理。成功→行一覧へリダイレクト、失敗→エラー表示）、行一覧

**対象ファイル**:
- views: `ui/owner/views/csv_import.py`
- forms: `ui/owner/forms/csv_import.py`
- templates: `ui/templates/ui/owner/csv_upload.html`, `ui/templates/ui/owner/csv_import_rows.html`
- urls: `ui/owner/urls.py` (追記)

precondition:
- UO-01 Slice 1 完了
- コア層 C-06 S1 完了（ImportService の CSV パース + Stage 1 が動作）

postcondition:
- `/o/imports/upload/` で CSV ファイルをアップロードできる
- アップロード成功（status='completed', row_count >= 0）→ `/o/imports/<id>/rows/` にリダイレクト + トースト（全件重複スキップ時は row_count=0 + 専用トースト）
- アップロード失敗（status='failed': ヘッダー不正 / 全グループ不正）→ 同画面でエラーメッセージ表示
- `/o/imports/<id>/rows/` でインポート行一覧（行番号, 営業日, レシート番号, ステータス）が表示される。failed import でも `/rows/` でエラー詳細を確認可能
- 過去のインポート履歴（直近 10 件）がアップロード画面に表示される。completed は「詳細」リンク、failed は「エラー詳細」リンク

**完了条件**: CSV アップロード → 成功時に行一覧へ遷移（0 件 completed 含む）/ 失敗時にエラー表示。failed import の「エラー詳細」閲覧もブラウザで動作する

#### Slice 2: マッチング管理

**ブランチ説明部**: `uo04-s2-matching-mgmt`（実ブランチ名は `UI_PIPELINE.md` §2 参照）

**スコープ**: マッチング実行トリガー、候補一覧、確定/却下

**対象ファイル**:
- views: `ui/owner/views/csv_import.py` (追記)
- templates: `ui/templates/ui/owner/csv_import_matching.html`, `ui/templates/ui/owner/_matching_row.html`
- urls: `ui/owner/urls.py` (追記)

precondition:
- UO-04 Slice 1 完了（CSV アップロード + 行一覧が動作）
- コア層 C-06 S2 完了（MatchingService が動作）

postcondition:
- 行一覧画面に「マッチング実行」ボタンが表示される
- マッチング実行 → pending_review の行に候補が表示される
- `/o/imports/<id>/matching/` で候補の確定/却下が HTMX で操作できる
- 確定 → 行ステータスが confirmed + matched_visit が設定される
- 却下 → 行ステータスが rejected

**完了条件**: CSV アップロード → マッチング実行 → 候補確定/却下がブラウザで動作する

### 7.9 UO-05: 分析ダッシュボード

| 項目 | 内容 |
|------|------|
| **Slice 数** | 1 本 |
| **理由** | ダッシュボードは 1 画面に 3 チャートを表示するのみ。分割する粒度がない |

#### Slice 1: 分析ダッシュボード

**ブランチ説明部**: `uo05-dashboard`（実ブランチ名は `UI_PIPELINE.md` §2 参照）

**スコープ**: 3 チャート（日別来客推移・セグメント比率・スタッフ別対応数）、数値サマリー、期間フィルタ

**対象ファイル**:
- views: `ui/owner/views/dashboard.py`
- templates: `ui/templates/ui/owner/dashboard.html`
- static: `ui/static/ui/js/charts.js`（Chart.js 初期化コード）
- urls: `ui/owner/urls.py` (追記)

precondition:
- UO-01 Slice 1 完了（base_owner.html に Chart.js CDN が含まれる）
- コア層 C-07 完了（AnalyticsService が動作）

postcondition:
- `/o/dashboard/` で 3 つのチャート（折れ線, 円, 棒）が正しく描画される
- 数値サマリー（今日の来客数、今月の来客数、新規率、アクティブ顧客数）が表示される
- 期間フィルタ（7日/30日/90日）の切替で HTMX でチャートデータが再取得される
- データがない場合（来店記録 0 件）でもエラーにならず、空のグラフ + 「データがありません」表示

**完了条件**: ダッシュボードに 3 チャートが表示され、期間フィルタの切替が動作する

## 8. 実行順序

### Slice 依存グラフ

```
US-01 S1 (Staff Login + base_staff)
  │
  ├── US-02 S1 (顧客選択)
  │     └── US-02 S2 (接客画面)
  │
  ├── US-03 S1 (顧客・来店簡易管理)
  │
  └── US-04 S1 (会計後マッチング)

UO-01 S1 (Owner Login + base_owner) ← US-01 S1 の base.html に依存
  │
  ├── UO-01 S2 (スタッフ管理)
  │
  ├── UO-02 S1 (顧客管理)
  │
  ├── UO-03 S1 (来店管理)
  │     └── UO-03 S2 (セグメント設定)
  │
  ├── UO-04 S1 (CSV アップロード)
  │     └── UO-04 S2 (マッチング管理)
  │
  └── UO-05 S1 (ダッシュボード)
```

### 推奨実行順序

| 順序 | Slice | API 着手条件 | 並列可能 |
|------|-------|-------------|---------|
| **1** | US-01 S1 (Staff Login) | C-02 完了後 | - |
| **2** | UO-01 S1 (Owner Login) | C-02 完了後 | 概念上は US-01 S1 と並列候補だが、base.html 依存のため US-01 S1 完了後に実行（precondition 参照） |
| **3** | US-02 S1 (顧客選択) | C-03, C-05a 完了後 | UO-01 S2 と並列可 |
| **3** | UO-01 S2 (スタッフ管理) | C-02 完了後 | US-02 S1 と並列可 |
| **4** | US-02 S2 (接客画面) | C-04 S2, C-05a, C-05b 完了後 | UO-02 S1, UO-03 S1 と並列可 |
| **4** | UO-02 S1 (顧客管理) | C-03, C-05a, C-05b 完了後 | US-02 S2 と並列可 |
| **4** | UO-03 S1 (来店管理) | C-04 S2 完了後 | US-02 S2, UO-02 S1 と並列可 |
| **5** | US-03 S1 (顧客・来店簡易管理) | C-03, C-04 S2, C-05a 完了後 | UO-03 S2 と並列可 |
| **5** | UO-03 S2 (セグメント設定) | C-04 全 Slice 完了後 | US-03 S1 と並列可 |
| **6** | US-04 S1 (会計後マッチング) | C-06 全 Slice 完了後 | UO-04 S1 と並列可 |
| **6** | UO-04 S1 (CSV アップロード) | C-06 S1 完了後 | US-04 S1 と並列可 |
| **7** | UO-04 S2 (マッチング管理) | C-06 S2 完了後 | UO-05 S1 と並列可 |
| **7** | UO-05 S1 (ダッシュボード) | C-07 完了後 | UO-04 S2 と並列可 |

**合計: 13 Slice**（Staff 5 + Owner 8）。E2E テストは Slice に含めない（D-04 で定義した後続タスク）。

### Closure Audit タイミング

| Cluster | audit タイミング | 検証ポイント |
|---------|----------------|-------------|
| US-01 | Slice 1 完了後（1 Slice のみ） | 認証導線（QR ログイン → セッション確立）、未認証リダイレクト、base_staff.html の描画、BottomTab のリンク定義存在。タブ遷移先は Staff UI 全体 audit で検証 |
| US-02 | Slice 2 完了後 | 顧客選択 → 接客画面の遷移。タスク消化の状態伝搬。generate_tasks → sync_tasks の C-05a 契約 |
| UO-01 | Slice 2 完了後 | `/o/staff/` 直アクセス時の base_owner.html 描画、OwnerRequiredMixin のガード、Sidebar の active state。ログイン着地導線は Owner UI 全体 audit で検証 |
| UO-03 | Slice 2 完了後 | 来店削除 → セグメント再計算の伝搬。閾値変更プレビュー → 確定の整合性 |
| UO-04 | Slice 2 完了後 | CSV アップロード → 行一覧 → マッチング実行 → 確定/却下 の一連フロー |
| **Staff UI 全体** | US-01〜04 全完了後 | ログイン → 顧客選択 → 接客 → 顧客詳細 → マッチング の業務フロー一気通貫。BottomTab 遷移。全タブのアクティブ状態 |
| **Owner UI 全体** | UO-01〜05 全完了後 | Sidebar 全メニューへの遷移。権限ガード。エラー伝搬 |
| **E2E テスト** | 全 Cluster 完了後 | D-04 で定義した 3 クリティカルパス。Staff + Owner の横断フロー。最終リリース判定 |

**注**: Closure Audit の詳細な実施手順・判定ルール・スケジュールは `UI_PIPELINE.md` §3 を参照すること。

## Review Log

- [2026-03-31] 初版作成
- [2026-03-31] Codex レビュー (gpt-5.4 high): 68/100 FAIL。critical 1 + major 6 を修正
  - F-01 (critical): US-04 S-MATCHING の `skip` を削除。C-06 の状態遷移（validated/pending_review/confirmed/rejected）に合わせて再設計。表示対象を `pending_review` のみに修正。reject を追加
  - F-02 (major): US-02 S-SESSION / US-03 のタスク同期を C-05a に合わせ `HearingTaskService.sync_tasks()` の明示呼び出しに修正。US-03 precondition に C-05a 追加
  - F-03 (major): S-CUSTOMER-SELECT の「最近来た順」を `updated_at` から Visit ベースの Subquery annotate に修正
  - F-04 (major): O-STAFF-LIST を C-02 仕様に合わせ `is_active=True` のみ表示に修正。状態列を削除
  - F-05 (major): O-SEGMENT-SETTINGS の Service 名を C-04 の `bulk_recalculate_segments(store)` に修正
  - F-06 (major): O-CSV-MATCHING の候補取得を行ごとの HTMX 遅延ロードに修正（N+1 回避、C-06 準拠）
  - F-07 (major): O-DASHBOARD の `segment_ratio` に `date_from, date_to` パラメータ追加（C-07 は全 API で期間必須）
- [2026-03-31] Codex 再レビュー (gpt-5.4 high): 83/100 FAIL。F-01〜F-07 resolved。新規 3 件を修正
  - F-08 (major): O-CUSTOMER-EDIT に `HearingTaskService.sync_tasks()` 明示呼び出しを追加。UO-02 Slice precondition に C-05a 追加
  - F-09 (major): O-STAFF-DETAIL のデータソースに `is_active=True` ガードを追加。C-02 仕様（inactive = 404）を明記
  - F-10 (moderate): US-04 Slice スコープの「確定/スキップ」を「確定/却下」に統一。完了条件に reject を追加
- [2026-03-31] Codex 3回目レビュー (gpt-5.4 high): 91/100 FAIL。F-08〜F-10 resolved。新規 1 件を修正
  - F-11 (major): O-CSV-UPLOAD からプログレスバー/ポーリングを削除。C-06 Stage 1 は同期処理（upload_csv 完了 = completed or 400）のため非同期 UI は不要。成功→即リダイレクト、失敗→同画面エラー表示に修正
- [2026-03-31] Codex 4回目レビュー (gpt-5.4 high): 96/100 FAIL。F-11 残存 1 件を修正
  - F-11 残存 (moderate): UO-04 Slice 1 スコープの「プログレス表示」文言を削除。同期処理に統一
- [2026-03-31] Codex 5回目レビュー (gpt-5.4 high): 92/100 FAIL。新規 2 件を修正
  - F-12 (major): 接客画面のメモを Customer.memo ではなく Visit.conversation_memo に保存するよう修正。メモは来店記録作成時に一緒に送信する設計に変更
  - F-13 (moderate): 来店記録作成の「重複来店エラー」を削除。C-04 仕様では同日同顧客の複数来店は業務上正当（DB unique 制約なし）
- [2026-03-31] Codex 6回目レビュー (gpt-5.4 high): 97/100 FAIL。F-12 残存矛盾 2 箇所を修正
  - F-12 残存: セクション 3.6 ゾーン設計のメモ行「hx-patch で保存」→ Alpine.js 一時保持に修正。US-02 Slice 2 postcondition「HTMX PATCH → メモ保存」→ Alpine.js 一時保持 + 来店記録作成時に送信に修正
- [2026-03-31] Codex 7回目レビュー (gpt-5.4 high): 99/100 FAIL。新規 1 件を修正
  - F-14 (要件漏れ): O-STAFF-CREATE の Service 欄を具体化。Staff 作成ロジック + QR 発行（expires_in_hours は staff_type 別デフォルト最大値）+ フラグメント方式 URL を明記
- [2026-03-31] Codex 8回目レビュー (gpt-5.4 high): 96/100 FAIL。2 件を修正
  - F-15 (major): S-CUSTOMER-CREATE に C-05a 契約の `HearingTaskService.generate_tasks(customer)` 明示呼び出しを追加。US-02 Slice 1 postcondition にもタスク生成を追記
  - F-16 (moderate): US-01 S1, UO-01 S1, US-02 S1 の完了条件から「仮ページ」表現を排除。実行順序上の過渡状態であることを技術的に説明し、各 Slice の検証範囲を明確化
- [2026-03-31] Codex 9回目レビュー (gpt-5.4 high): 94/100 FAIL。2 件を修正
  - F-17 (major): O-VISIT-EDIT の入力フィールドから「対応スタッフ（select）」を削除。C-04 の VisitUpdateRequest は visited_at と conversation_memo のみ更新可能。staff は読み取り専用表示に変更
  - F-18 (moderate): O-STAFF-CREATE と O-SEGMENT-SETTINGS が「write は Service 必須」原則に違反。§1.1 に例外セクションを追加し、コア層が standalone Service を公開していない 2 操作の根拠と Phase 2 移行計画を明文化
- [2026-03-31] Codex 10回目レビュー (gpt-5.4 high): **100/100 PASS**。全 finding 解消。要 smoke test: HTMX 遷移、Chart.js 描画、confirm/reject UI 操作
