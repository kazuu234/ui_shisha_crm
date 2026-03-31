# UO-05 詳細設計書: 分析ダッシュボード

> 基本設計書: `docs/design/UI_BASIC_DESIGN.md` §6 UO-05, §7.9
> デザインガイド: `docs/design/UI_DESIGN_GUIDE.md`
> パイプライン: `docs/design/UI_PIPELINE.md` #13
> コア層参照: `docs/reference/cluster/C07_ANALYTICS.md`

## 1. 概要

### Slice 情報

| 項目 | 内容 |
|------|------|
| **Cluster** | UO-05 (分析ダッシュボード) |
| **Slice** | S1（単一 Slice で完結） |
| **パイプライン順序** | #13 / 13（最終 Slice） |
| **ブランチ説明部** | `uo05-dashboard` |

### スコープ

分析ダッシュボード画面。3 チャート（日別来客推移・セグメント比率・スタッフ別対応数）、数値サマリー 4 項目、期間フィルタ（7 日/30 日/90 日）。UO-01 S1 で配置した stub view（`StubDashboardView`）を本実装（`DashboardView`）に置き換える。Chart.js v4 を使用し、`json_script` テンプレートタグでデータを渡す。

### precondition

- UO-01 S1 完了（`base_owner.html` に Chart.js CDN `<script src="https://cdn.jsdelivr.net/npm/chart.js@4">` が含まれる。`OwnerRequiredMixin`、`StoreMixin` が動作する。`/o/dashboard/` に `StubDashboardView` が配置済み）
- コア層 C-07 完了（`AnalyticsService` の 3 メソッド `daily_summary`、`segment_ratio`、`staff_summary` が動作する）

### postcondition

- `/o/dashboard/` で 3 つのチャート（折れ線: 日別来客数推移、円: セグメント比率、棒: スタッフ別対応数）が正しく描画される
- 数値サマリー 4 項目（今日の来客数、今月の来客数、新規率、アクティブ顧客数）がチャートの上に表示される
- 期間フィルタ（7 日/30 日/90 日）の切替で HTMX によりチャートデータが再取得される（デフォルト: 30 日）
- データがない場合（来店記録 0 件）でもエラーにならず、空のグラフ + 「データがありません」メッセージが表示される
- Chart.js データは `{{ data|json_script:"id" }}` → JS で `JSON.parse()` の方式で渡される
- Sidebar の「ダッシュボード」がアクティブ状態（`active_sidebar = "dashboard"`）
- 全 View が `LoginRequiredMixin, OwnerRequiredMixin, StoreMixin` を使用
- UO-01 S1 の `StubDashboardView` を `DashboardView` に置き換え（urls.py の更新）

## 2. ファイル構成

```
ui/
├── owner/
│   ├── views/
│   │   ├── dashboard.py              # DashboardView（StubDashboardView を置き換え）
│   │   └── stub.py                   # StubDashboardView を削除（または残して未使用化）
│   └── urls.py                       # StubDashboardView → DashboardView に差し替え
├── static/ui/
│   └── js/
│       └── charts.js                 # Chart.js 初期化コード（3 チャート + 期間フィルタ連携）
├── templates/ui/
│   └── owner/
│       ├── dashboard.html            # ダッシュボード画面（数値サマリー + 3 チャート + 期間フィルタ）
│       ├── _dashboard_charts.html    # HTMX フラグメント（チャートデータ + canvas + json_script）
│       └── stub_dashboard.html       # 削除（DashboardView に置き換え済み）
```

**追加するアイコン**: なし（UO-01 S1 で作成済みの `bar-chart-2.svg` で足りる）。

## 3. コア層契約（C-07 からの引用）

正式な定義は `docs/reference/cluster/C07_ANALYTICS.md` を参照。

**import パスについて**: コア層は別リポジトリ（別 Django app）として管理されている場合がある。本設計書では `from core.services.analytics import AnalyticsService` のような統一的な記法を使用するが、実際の import パスはコア層のパッケージ構造に依存する。実装時にコア層の `__init__.py` や実際のモジュール配置を確認すること。

### AnalyticsService

| メソッド | 引数 | 返り値 | 備考 |
|---------|------|--------|------|
| `daily_summary(store, date_from, date_to)` | `Store, date, date` | `dict` (DailySummaryResponse 形式) | 日別来客数。ゼロ埋めあり |
| `segment_ratio(store, date_from, date_to)` | `Store, date, date` | `dict` (SegmentRatioResponse 形式) | セグメント比率（Visit 単位） |
| `staff_summary(store, date_from, date_to)` | `Store, date, date` | `dict` (StaffSummaryResponse 形式) | スタッフ別対応数 |

### DailySummaryResponse 構造

```json
{
  "period": {"from": "2026-03-01", "to": "2026-03-31"},
  "daily": [
    {"date": "2026-03-01", "total_visits": 5, "new_visits": 2, "repeat_visits": 2, "regular_visits": 1}
  ]
}
```

### SegmentRatioResponse 構造

```json
{
  "period": {"from": "2026-03-01", "to": "2026-03-31"},
  "total_visits": 150,
  "segments": [
    {"segment": "new", "visit_count": 50, "ratio": 0.333},
    {"segment": "repeat", "visit_count": 60, "ratio": 0.400},
    {"segment": "regular", "visit_count": 40, "ratio": 0.267}
  ]
}
```

### StaffSummaryResponse 構造

```json
{
  "period": {"from": "2026-03-01", "to": "2026-03-31"},
  "staff": [
    {"staff_id": "...", "display_name": "田中", "total_visits": 30}
  ]
}
```

### Customer モデル（数値サマリーで参照）

| フィールド | 型 | 備考 |
|-----------|-----|------|
| `store` | ForeignKey(Store) | 店舗スコープ |

**StoreScopedManager**: `Customer.objects.for_store(store).count()` でアクティブ顧客数を取得。

### セグメント定義の注意（C-07 仕様）

分析値は「現在の顧客セグメント（`Customer.segment`）」で集計される。来店時点のセグメント履歴は保持しない。顧客のセグメントが変更されると、過去期間のレポート結果も変動する。これは MVP の仕様であり不具合ではない。

## 4. View 定義

### 4.1 DashboardView

```python
# ui/owner/views/dashboard.py

from datetime import date, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from ui.mixins import OwnerRequiredMixin, StoreMixin
from core.services.analytics import AnalyticsService
from customers.models import Customer

# 期間フィルタの選択肢（値: 日数）
PERIOD_CHOICES = {
    "7": 7,
    "30": 30,
    "90": 90,
}
DEFAULT_PERIOD = "30"


class DashboardView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, TemplateView):
    template_name = "ui/owner/dashboard.html"
    login_url = "/o/login/"

    def get_period(self):
        """リクエストパラメータから期間（日数）を取得する。
        不正値はデフォルト（30日）にフォールバック。
        """
        period_key = self.request.GET.get("period", DEFAULT_PERIOD).strip()
        if period_key not in PERIOD_CHOICES:
            period_key = DEFAULT_PERIOD
        return period_key, PERIOD_CHOICES[period_key]

    def get_template_names(self):
        # HTMX リクエスト時はチャートフラグメントのみ返す
        if self.request.headers.get("HX-Request") == "true":
            return ["ui/owner/_dashboard_charts.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        store = self.store

        period_key, days = self.get_period()
        date_to = date.today()
        date_from = date_to - timedelta(days=days - 1)

        # C-07 AnalyticsService 呼び出し
        daily_data = AnalyticsService.daily_summary(store, date_from, date_to)
        segment_data = AnalyticsService.segment_ratio(store, date_from, date_to)
        staff_data = AnalyticsService.staff_summary(store, date_from, date_to)

        # 数値サマリー算出
        today_str = date_to.isoformat()
        today_visits = 0
        for day in daily_data.get("daily", []):
            if day.get("date") == today_str:
                today_visits = day.get("total_visits", 0)
                break

        # 今月の来客数: 月初〜当日の daily_summary を別途取得して合計
        # （期間フィルタとは独立。7日フィルタでも当月全体を表示する）
        month_start = date_to.replace(day=1)
        if month_start < date_from:
            # 期間フィルタの範囲外（月初がフィルタ開始日より前）の場合、別途取得
            month_daily = AnalyticsService.daily_summary(store, month_start, date_to)
        else:
            month_daily = daily_data
        month_visits = 0
        for day in month_daily.get("daily", []):
            day_date = day.get("date", "")
            if day_date >= month_start.isoformat():
                month_visits += day.get("total_visits", 0)

        # 新規率: segment_ratio の new の ratio
        new_ratio = 0.0
        for seg in segment_data.get("segments", []):
            if seg.get("segment") == "new":
                new_ratio = seg.get("ratio", 0.0)
                break

        # アクティブ顧客数（StoreScopedManager 使用）
        active_customer_count = Customer.objects.for_store(store).count()

        # データ有無判定（空状態表示に使用）
        total_visits = segment_data.get("total_visits", 0)
        has_data = total_visits > 0

        # Chart.js 用データ整形
        # 折れ線チャート: labels = 日付配列、datasets = total_visits 配列
        chart_daily = {
            "labels": [d["date"] for d in daily_data.get("daily", [])],
            "datasets": [{
                "label": "来客数",
                "data": [d["total_visits"] for d in daily_data.get("daily", [])],
            }],
        }

        # 円チャート: labels = セグメント名、data = visit_count
        segment_labels_map = {"new": "新規", "repeat": "リピート", "regular": "常連"}
        chart_segment = {
            "labels": [
                segment_labels_map.get(s["segment"], s["segment"])
                for s in segment_data.get("segments", [])
            ],
            "datasets": [{
                "data": [s["visit_count"] for s in segment_data.get("segments", [])],
            }],
        }

        # 棒チャート: labels = スタッフ名、data = total_visits
        chart_staff = {
            "labels": [s["display_name"] for s in staff_data.get("staff", [])],
            "datasets": [{
                "label": "対応数",
                "data": [s["total_visits"] for s in staff_data.get("staff", [])],
            }],
        }

        context.update({
            "active_sidebar": "dashboard",
            "current_period": period_key,
            "period_choices": [
                ("7", "7日"),
                ("30", "30日"),
                ("90", "90日"),
            ],
            # 数値サマリー
            "today_visits": today_visits,
            "month_visits": month_visits,
            "new_ratio": round(new_ratio * 100, 1),
            "active_customer_count": active_customer_count,
            # Chart.js データ（json_script で渡す）
            "chart_daily": chart_daily,
            "chart_segment": chart_segment,
            "chart_staff": chart_staff,
            # 空状態判定
            "has_data": has_data,
        })
        return context
```

**期間フィルタのホワイトリスト制御**: ユーザー入力の `period` パラメータは `PERIOD_CHOICES` に定義された値のみ許可し、未知の値はデフォルト（30 日）にフォールバックする。

**date_from の算出**: `date_to - timedelta(days=days - 1)` で当日を含む `days` 日間を指定する。例: 7 日間 = 今日を含む過去 7 日（today - 6 日 〜 today）。C-07 の `daily_summary` はゼロ埋めにより期間内の全日付を返すため、欠損は発生しない。

**HTMX リクエスト判定**: `HX-Request` ヘッダーの有無で返すテンプレートを切り替える。期間フィルタの変更は `hx-get` で `_dashboard_charts.html` フラグメント（数値サマリー + チャート canvas + json_script）のみを返す。

**数値サマリーの算出**:
- `today_visits`: `daily_data` の配列から当日の `total_visits` を検索。当日がない場合（フィルタ期間が過去のみの場合）は 0。
- `month_visits`: 月初（`date_to.replace(day=1)`）〜当日の `daily_summary` を取得して `total_visits` を合計。期間フィルタとは独立して常に当月全体を表示する（基本設計書 §6 O-DASHBOARD 準拠: 「`daily_summary` の当月合計」）。期間フィルタの範囲が月初より後の場合（例: 7 日フィルタで月末）、月初〜当日の `daily_summary` を別途取得する。
- `new_ratio`: `segment_data` の `segments` 配列から `segment == "new"` の `ratio` を取得。
- `active_customer_count`: `Customer.objects.for_store(store).count()` で取得。期間フィルタとは独立した値（常に最新の全顧客数）。

**空状態判定**: `segment_data.total_visits == 0` で判定。0 の場合でも canvas は常に描画し、Chart.js に空データ（ゼロ埋め配列）を渡して空のグラフを表示する。加えて「データがありません」メッセージを半透明オーバーレイで canvas 上に重ねて表示する（基本設計書 §7.9 postcondition「空のグラフ + 『データがありません』表示」に準拠）。

**Chart.js 用データ整形**: View 側で Chart.js の `labels` / `datasets` 構造に整形してからテンプレートに渡す。テンプレートでは `json_script` で JSON 化し、`charts.js` で `JSON.parse()` → `new Chart()` に渡すだけの薄い処理とする。セグメント名の日本語ラベル解決も View 側で行い、テンプレート・JS に翻訳ロジックを持たせない。

## 5. テンプレート

### 5.1 owner/dashboard.html

```
{% extends "ui/base_owner.html" %}
{% load static %}

{% block page_title %}ダッシュボード{% endblock %}

{% block content %}
  <!-- 期間フィルタ -->
  <div class="flex items-center justify-end mb-6">
    <select name="period"
            hx-get="/o/dashboard/"
            hx-target="#dashboard-charts"
            hx-indicator="#dashboard-loading"
            hx-push-url="true">
      {% for value, label in period_choices %}
        <option value="{{ value }}" {% if value == current_period %}selected{% endif %}>{{ label }}</option>
      {% endfor %}
    </select>
  </div>

  <!-- チャートエリア（HTMX 差し替え対象） -->
  <div id="dashboard-charts">
    {% include "ui/owner/_dashboard_charts.html" %}
  </div>

  <!-- ローディング表示 -->
  <div id="dashboard-loading" class="htmx-indicator">
    <div class="text-center py-8 text-text-secondary">読み込み中...</div>
  </div>
{% endblock %}

{% block extra_js %}
  <script src="{% static 'ui/js/charts.js' %}"></script>
{% endblock %}
```

**設計方針**: `dashboard.html` は期間フィルタと HTMX ターゲットの骨格のみを担う。数値サマリー + チャート canvas + json_script は全て `_dashboard_charts.html` フラグメントに含め、`#dashboard-charts` ごと HTMX 差し替えする。これにより期間フィルタ切替時に数値サマリーとチャートデータが同時に更新される。

**`charts.js` の読み込み**: `{% block extra_js %}` で `charts.js` を読み込む。Chart.js CDN は `base_owner.html` の `{% block extra_head %}` で既に読み込み済み（UO-01 S1 で配置）。

### 5.2 owner/_dashboard_charts.html（HTMX フラグメント）

数値サマリー + 3 チャート canvas + json_script を含む。HTMX 差し替え時はこのフラグメント全体が `#dashboard-charts` に差し込まれる。

```
{% load static %}

<!-- 数値サマリー -->
<div class="grid grid-cols-4 gap-4 mb-8">
  <div class="bg-surface rounded-md p-4 border border-border-default">
    <p class="text-text-secondary text-sm">今日の来客数</p>
    <p class="text-2xl font-bold">{{ today_visits }}</p>
  </div>
  <div class="bg-surface rounded-md p-4 border border-border-default">
    <p class="text-text-secondary text-sm">今月の来客数</p>
    <p class="text-2xl font-bold">{{ month_visits }}</p>
  </div>
  <div class="bg-surface rounded-md p-4 border border-border-default">
    <p class="text-text-secondary text-sm">新規率</p>
    <p class="text-2xl font-bold">{{ new_ratio|floatformat:1 }}%</p>
  </div>
  <div class="bg-surface rounded-md p-4 border border-border-default">
    <p class="text-text-secondary text-sm">アクティブ顧客数</p>
    <p class="text-2xl font-bold">{{ active_customer_count }}</p>
  </div>
</div>

<!-- 3 チャート -->
<div class="grid grid-cols-2 gap-6">

  <!-- 日別来客数推移（折れ線） — 2 カラム幅 -->
  <div class="col-span-2 bg-surface rounded-md p-4 border border-border-default relative">
    <h3 class="text-lg font-semibold mb-4">日別来客数推移</h3>
    <canvas id="chart-daily" height="200"></canvas>
    {% if not has_data %}
      <div class="absolute inset-0 flex items-center justify-center bg-surface/80 text-text-secondary">
        <p>データがありません</p>
      </div>
    {% endif %}
  </div>

  <!-- セグメント比率（円） -->
  <div class="bg-surface rounded-md p-4 border border-border-default relative">
    <h3 class="text-lg font-semibold mb-4">セグメント比率</h3>
    <canvas id="chart-segment" height="200"></canvas>
    {% if not has_data %}
      <div class="absolute inset-0 flex items-center justify-center bg-surface/80 text-text-secondary">
        <p>データがありません</p>
      </div>
    {% endif %}
  </div>

  <!-- スタッフ別対応数（棒） -->
  <div class="bg-surface rounded-md p-4 border border-border-default relative">
    <h3 class="text-lg font-semibold mb-4">スタッフ別対応数</h3>
    <canvas id="chart-staff" height="200"></canvas>
    {% if not has_data %}
      <div class="absolute inset-0 flex items-center justify-center bg-surface/80 text-text-secondary">
        <p>データがありません</p>
      </div>
    {% endif %}
  </div>

</div>

<!-- Chart.js データ（json_script で安全に渡す） -->
{{ chart_daily|json_script:"daily-data" }}
{{ chart_segment|json_script:"segment-data" }}
{{ chart_staff|json_script:"staff-data" }}

<!-- HTMX 差し替え後にチャートを再描画するためのインラインスクリプト -->
<script>
  // HTMX フラグメント差し替え後に実行される
  // charts.js の initCharts() が定義されていれば呼び出す
  // has_data が false でも canvas は存在するため、空のグラフとして描画する
  if (typeof initCharts === "function") {
    initCharts();
  }
</script>
```

**数値サマリーのレイアウト**: 4 カラムグリッドで横並び配置。各カードは `bg-surface` + `border-border-default` でデザインガイド準拠。

**新規率の表示**: `{{ new_ratio|floatformat:1 }}%` で小数点 1 桁表示。C-07 の `segment_ratio` は `ratio` を 0.0〜1.0 の小数で返すため、View 側で `round(new_ratio * 100, 1)` としてパーセント値に変換してからテンプレートに渡す。テンプレートでは `%` を付けるだけの薄い処理となる。

**チャートレイアウト**: 2 カラムグリッド。日別来客数推移は全幅（`col-span-2`）、セグメント比率とスタッフ別対応数は 1 カラムずつ並列配置。

**空状態**: `has_data == False` の場合でも canvas は常に描画する。Chart.js に空データ（ゼロ埋め配列）を渡して空のグラフを表示し、その上に半透明オーバーレイ（`bg-surface/80`）で「データがありません」メッセージを重ねる。canvas が存在することで Chart.js の初期化エラーを防止し、基本設計書の「空のグラフ + 『データがありません』」の仕様に準拠する。

**HTMX 差し替え後の再描画**: フラグメント内にインラインスクリプトを配置し、`initCharts()` を呼び出す。HTMX は差し替えた HTML 内の `<script>` タグを実行するため、期間フィルタ切替後に新しいデータでチャートが再描画される。

### 5.3 static/ui/js/charts.js

```javascript
// Chart.js 初期化コード
// base_owner.html で Chart.js CDN が読み込み済みの前提

// チャートインスタンスの参照（再描画時に破棄するため保持）
let dailyChart = null;
let segmentChart = null;
let staffChart = null;

// デザインガイド（UI_DESIGN_GUIDE.md §2）準拠のカラー定義
const COLORS = {
  accent: "#2D7D7B",        // --accent（折れ線・棒チャートのメイン色）
  accentLight: "rgba(45, 125, 123, 0.1)",  // 折れ線チャートの fill（--accent の 10% 不透明度）
  new: "#2D7D7B",           // 新規セグメント（--accent）
  repeat: "#B8860B",        // リピートセグメント（--warning）
  regular: "#4A7C59",       // 常連セグメント（--success）
  textPrimary: "#1C1917",   // --text-primary
  textSecondary: "#57534E", // --text-secondary
  borderDefault: "#E0DCD4", // --border-default（グリッド線）
};

function initCharts() {
  // 既存チャートを破棄（HTMX 差し替え後の再描画で二重生成を防止）
  if (dailyChart) { dailyChart.destroy(); dailyChart = null; }
  if (segmentChart) { segmentChart.destroy(); segmentChart = null; }
  if (staffChart) { staffChart.destroy(); staffChart = null; }

  // json_script からデータを取得
  const dailyEl = document.getElementById("daily-data");
  const segmentEl = document.getElementById("segment-data");
  const staffEl = document.getElementById("staff-data");

  // json_script 要素が存在しない場合は何もしない（テンプレートエラー時のフォールバック）
  if (!dailyEl || !segmentEl || !staffEl) return;

  const dailyData = JSON.parse(dailyEl.textContent);
  const segmentData = JSON.parse(segmentEl.textContent);
  const staffData = JSON.parse(staffEl.textContent);

  // 日別来客数推移（折れ線）
  const dailyCanvas = document.getElementById("chart-daily");
  if (dailyCanvas) {
    dailyChart = new Chart(dailyCanvas, {
      type: "line",
      data: {
        labels: dailyData.labels,
        datasets: [{
          label: dailyData.datasets[0].label,
          data: dailyData.datasets[0].data,
          borderColor: COLORS.accent,
          backgroundColor: COLORS.accentLight,
          fill: true,
          tension: 0.3,
          pointRadius: 2,
          pointHoverRadius: 5,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
        },
        scales: {
          x: {
            grid: { color: COLORS.borderDefault },
            ticks: { color: COLORS.textSecondary, maxTicksLimit: 10 },
          },
          y: {
            beginAtZero: true,
            grid: { color: COLORS.borderDefault },
            ticks: {
              color: COLORS.textSecondary,
              precision: 0,  // 整数のみ表示
            },
          },
        },
      },
    });
  }

  // セグメント比率（ドーナツ）
  const segmentCanvas = document.getElementById("chart-segment");
  if (segmentCanvas) {
    segmentChart = new Chart(segmentCanvas, {
      type: "doughnut",
      data: {
        labels: segmentData.labels,
        datasets: [{
          data: segmentData.datasets[0].data,
          backgroundColor: [COLORS.new, COLORS.repeat, COLORS.regular],
          borderWidth: 0,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "bottom",
            labels: { color: COLORS.textPrimary },
          },
        },
      },
    });
  }

  // スタッフ別対応数（棒）
  const staffCanvas = document.getElementById("chart-staff");
  if (staffCanvas) {
    staffChart = new Chart(staffCanvas, {
      type: "bar",
      data: {
        labels: staffData.labels,
        datasets: [{
          label: staffData.datasets[0].label,
          data: staffData.datasets[0].data,
          backgroundColor: COLORS.accent,
          borderRadius: 4,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: COLORS.textPrimary },
          },
          y: {
            beginAtZero: true,
            grid: { color: COLORS.borderDefault },
            ticks: {
              color: COLORS.textSecondary,
              precision: 0,  // 整数のみ表示
            },
          },
        },
      },
    });
  }
}

// 初回読み込み時に実行
document.addEventListener("DOMContentLoaded", initCharts);
```

**チャート破棄**: `initCharts()` の先頭で既存チャートを `destroy()` する。HTMX 差し替え後にフラグメント内のインラインスクリプトが `initCharts()` を呼ぶため、二重生成を防止する。

**Chart.js type**: 基本設計書 §6 O-DASHBOARD で「円」と記載されているが、`doughnut` を使用する。Chart.js の `doughnut` は `pie` の中央が空いたバリアントであり、セグメント比率の表示には `doughnut` がより適している（中央にサマリー数値を表示できる余地がある）。基本設計書の「円」は `doughnut` を含む広義の用法として解釈する。

**カラーの決定**: デザインガイドのカラーパレット（`--accent`、`--warning`、`--success`）を直接 JS 定数として定義。CSS 変数の `getComputedStyle` による動的取得は不要（カラーは静的であり、テーマ切替の予定もない）。

**レスポンシブ**: `responsive: true` + `maintainAspectRatio: false` で親コンテナの幅に追従。canvas の `height` はテンプレート側で固定。

**Y 軸の整数表示**: `ticks.precision: 0` で来客数・対応数が整数のみ表示されるようにする。

## 6. URL 設定

### ui/owner/urls.py（変更）

```python
# 変更前（UO-01 S1 で配置済み）:
# from ui.owner.views.stub import StubDashboardView
# path("dashboard/", StubDashboardView.as_view(), name="dashboard"),

# 変更後（UO-05 S1 で置き換え）:
from ui.owner.views.dashboard import DashboardView

path("dashboard/", DashboardView.as_view(), name="dashboard"),
```

**StubDashboardView の処理**: `stub.py` から `StubDashboardView` のクラスは削除する。`stub_dashboard.html` テンプレートも削除する。URL 名 `name="dashboard"` は維持する。

## 7. テストケース

### 7.1 Django TestClient

| # | テスト | 検証内容 |
|---|--------|---------|
| 1 | `test_dashboard_owner` | owner で GET `/o/dashboard/` → 200、チャート canvas あり |
| 2 | `test_dashboard_unauthenticated` | 未認証 → 302 `/o/login/` |
| 3 | `test_dashboard_staff_redirect` | staff で GET → 302 `/s/customers/` |
| 4 | `test_dashboard_default_period` | パラメータなし → `current_period == "30"` |
| 5 | `test_dashboard_period_7` | `?period=7` → `current_period == "7"`、date_from が today - 6 日 |
| 6 | `test_dashboard_period_90` | `?period=90` → `current_period == "90"` |
| 7 | `test_dashboard_period_invalid` | `?period=999` → デフォルト（30 日）にフォールバック |
| 8 | `test_dashboard_htmx_fragment` | `HX-Request: true` ヘッダー付き → `_dashboard_charts.html` フラグメントのみ返却 |
| 9 | `test_dashboard_summary_today_visits` | 今日の来客記録あり → `today_visits` が正しい値 |
| 10 | `test_dashboard_summary_month_visits` | 当月の来客記録あり → `month_visits` が正しい合計値 |
| 11 | `test_dashboard_summary_new_ratio` | new セグメント来客あり → `new_ratio` がパーセント値（100 倍済み）で正しい |
| 12 | `test_dashboard_summary_active_customers` | 顧客 N 件 → `active_customer_count == N` |
| 13 | `test_dashboard_empty_state` | 来店記録 0 件 → `has_data == False`、エラーなし（200 応答） |
| 14 | `test_dashboard_chart_data_daily` | `chart_daily` に `labels` と `datasets` が含まれる |
| 15 | `test_dashboard_chart_data_segment` | `chart_segment` に日本語ラベル（新規/リピート/常連）が含まれる |
| 16 | `test_dashboard_chart_data_staff` | `chart_staff` に `display_name` が含まれる |
| 17 | `test_dashboard_store_scope` | 他店舗のデータが context に含まれない |
| 18 | `test_dashboard_json_script_rendered` | レスポンス HTML に `id="daily-data"` / `id="segment-data"` / `id="staff-data"` の script タグが含まれる |
| 19 | `test_dashboard_sidebar_active` | `/o/dashboard/` で `active_sidebar == "dashboard"` |
| 20 | `test_dashboard_stub_removed` | `/o/dashboard/` が `DashboardView` を使用（`StubDashboardView` でない） |
| 21 | `test_dashboard_daily_zero_fill` | 7 日間で来店がない日がある場合、`chart_daily.labels` に全日付が含まれ、`chart_daily.datasets[0].data` の該当日が 0 |
| 22 | `test_dashboard_month_visits_independent` | `?period=7` でも `month_visits` が月初〜当日の合計（7 日分ではなく当月全体） |
| 23 | `test_dashboard_canvas_always_rendered` | `has_data == False` でもレスポンス HTML に `id="chart-daily"` / `id="chart-segment"` / `id="chart-staff"` の canvas タグが含まれる |

### 7.2 Browser smoke test

| # | 対象 URL | 手順 | 期待結果 |
|---|---------|------|---------|
| 1 | `/o/dashboard/` | ダッシュボード表示 | 数値サマリー 4 項目 + 3 チャートが描画される |
| 2 | `/o/dashboard/` | 期間フィルタを「7日」に変更 | HTMX でチャートエリアのみ差し替え（フルページリロードなし）。数値サマリーも更新される |
| 3 | `/o/dashboard/` | 期間フィルタを「90日」に変更 | HTMX でチャートデータが再取得され、90 日分のデータで再描画 |
| 4 | `/o/dashboard/` | 来店記録 0 件の状態で表示 | エラーなし。「データがありません」メッセージがチャート領域に表示 |
| 5 | `/o/dashboard/` | Sidebar の「ダッシュボード」がアクティブ | アクティブスタイル（bg-bg-surface-alt text-accent）が適用 |
| 6 | `/o/dashboard/` | 期間フィルタ切替中のローディング表示 | HTMX リクエスト中に「読み込み中...」が表示される |
| 7 | `/o/dashboard/` | ブラウザリロード後に期間フィルタの状態維持 | `hx-push-url` により URL パラメータが更新され、リロード後も同じ期間が表示される |

## 8. Gherkin シナリオ

```gherkin
Feature: Owner 分析ダッシュボード

  Scenario: ダッシュボードの初期表示
    Given オーナーとしてログインしている
    And 店舗に直近 30 日間の来店記録がある
    When `/o/dashboard/` にアクセスする
    Then 数値サマリー 4 項目（今日の来客数、今月の来客数、新規率、アクティブ顧客数）が表示される
    And 日別来客数推移の折れ線チャートが描画される
    And セグメント比率のドーナツチャートが描画される
    And スタッフ別対応数の棒チャートが描画される

  Scenario: 期間フィルタで 7 日に切替
    Given ダッシュボードが表示されている（デフォルト: 30 日）
    When 期間フィルタで「7日」を選択する
    Then HTMX でチャートエリアのみ差し替えられる
    And チャートデータが直近 7 日間のデータに更新される
    And 今日の来客数・新規率は 7 日間のデータに基づいて更新される
    And 今月の来客数・アクティブ顧客数は期間フィルタの影響を受けない（常に当月全体 / 全顧客数）
    And ブラウザ URL に `?period=7` が反映される

  Scenario: 期間フィルタで 90 日に切替
    Given ダッシュボードが表示されている
    When 期間フィルタで「90日」を選択する
    Then チャートデータが直近 90 日間のデータに更新される

  Scenario: データがない場合の空状態表示
    Given 店舗に来店記録が 0 件である
    When `/o/dashboard/` にアクセスする
    Then エラーにならず 200 応答が返される
    And チャート領域に「データがありません」メッセージが表示される
    And 数値サマリーは 0 で表示される（今日の来客数: 0、今月の来客数: 0、新規率: 0.0%、アクティブ顧客数は顧客数に依存）

  Scenario: 不正な期間パラメータ
    Given オーナーとしてログインしている
    When `?period=999` でダッシュボードにアクセスする
    Then デフォルト（30 日）で表示される（エラーにならない）

  Scenario: 未認証でのアクセス
    Given ログインしていない
    When `/o/dashboard/` にアクセスする
    Then `/o/login/` にリダイレクトされる

  Scenario: スタッフでのアクセス
    Given staff ロールでログインしている
    When `/o/dashboard/` にアクセスする
    Then `/s/customers/` にリダイレクトされる

  Scenario: 他店舗のデータが混入しない
    Given Store A に来店記録 5 件がある
    And Store B に来店記録 3 件がある
    And Store A のオーナーとしてログインしている
    When ダッシュボードにアクセスする
    Then Store A のデータのみが集計される
    And Store B のデータは含まれない

  Scenario: stub view の置き換え確認
    Given UO-05 S1 が完了している
    When `/o/dashboard/` にアクセスする
    Then DashboardView が応答する（StubDashboardView の「準備中」メッセージは表示されない）
    And 3 チャートが描画される
```

## 9. Closure Audit チェックリスト

- UO-01 S1 → UO-05 S1: `base_owner.html` の Chart.js CDN 読み込みが `DashboardView` で正しく利用されるか
- UO-01 S1 → UO-05 S1: Sidebar「ダッシュボード」リンク `/o/dashboard/` が `DashboardView` で応答するか（stub からの置き換え）
- UO-05 postcondition「3 チャート描画」: `json_script` で渡された JSON が `charts.js` で正しくパースされ、Chart.js のインスタンスが生成されるか
- UO-05 postcondition「期間フィルタ」: `hx-get` による HTMX リクエストで `_dashboard_charts.html` フラグメントが返り、チャートが再描画されるか
- UO-05 postcondition「空状態」: 来店記録 0 件で canvas が常時描画され、データがない場合はオーバーレイ「データがありません」が表示されるか（JS エラーが発生しないこと）
- UO-05 postcondition「Store スコープ」: `AnalyticsService` の呼び出しに `store` が渡され、`Customer.objects.for_store(store)` が使用されているか
- UO-05 postcondition「Sidebar アクティブ」: `active_sidebar = "dashboard"` が設定されているか
- UO-05 postcondition「stub 置き換え」: `StubDashboardView` が削除され、`DashboardView` に完全に置き換えられているか
- C-07 → UO-05: `AnalyticsService` の 3 メソッドの返り値構造が View のデータ整形ロジックと整合するか

## Review Log

- [2026-03-31] 初版作成
- [2026-03-31] Codex レビュー 1回目 (gpt-5.4): 82/100 FAIL。4 件を修正
  - F-01 (high): 空状態の仕様を基本設計書に準拠させた。canvas を常に描画し、空データでグラフ描画 + オーバーレイ「データがありません」表示に変更。テンプレートの `{% if has_data %}` 条件分岐を削除し、canvas は無条件で出力
  - F-02 (high): `今月の来客数` を期間フィルタとは独立に月初〜当日の `daily_summary` を別途取得して合計する方式に変更。基本設計書の「`daily_summary` の当月合計」に準拠
  - F-03 (medium): `charts.js` のカラー定義をデザインガイド（`UI_DESIGN_GUIDE.md` §2）の値に修正。`--accent: #2D7D7B`、`--warning: #B8860B`、`--success: #4A7C59`
  - F-04 (medium): テストケースに「欠損日ゼロ埋めがチャート系列に反映される」検証（#21）、「月来客数の期間フィルタ独立性」検証（#22）、「空状態でも canvas が描画される」検証（#23）を追加
- [2026-03-31] Codex レビュー 2回目 (gpt-5.4): 4 件を修正
  - F-05 (high): Gherkin「期間フィルタで 7 日に切替」シナリオで、today_visits・new_ratio のみ期間フィルタで更新され、month_visits・active_customer_count は影響を受けないことを明記
  - F-06 (medium): Closure Audit「空状態」の記述を F-01 修正後の仕様（canvas 常時描画 + オーバーレイ表示）に整合させた
  - F-07 (medium): テンプレートの CSS クラスを HTML コメントから実際の class 属性に移動
  - F-08 (low): charts.js カラー説明の `--warning-dark` を `--warning` に修正
