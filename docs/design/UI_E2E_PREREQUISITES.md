# UI Design → Headless Design: 結合テストへの要求事項

> **発行元**: UI Design（ui_shisha_crm）
> **宛先**: Headless Design（headless_shisha_crm）
> **日付**: 2026-04-02
> **目的**: Headless 側の結合テスト（テストデプロイ後の API 横断テスト）において、UI 層が依存する振る舞いの検証を要求する

## 背景

UI 層（Django テンプレート + HTMX）はコア層のモデル・サービス・例外を **直接 import** して使用している（同一プロセス内）。REST API 経由ではなく Python レベルの結合である。

現状、両リポジトリとも単体テストは充実しているが、**テストデプロイ環境でのクロス Cluster データフロー検証**（いわゆる結合テスト / E2E テスト）は未実施。

UI 側は Headless 側の結合テスト完了 → Fix 済みを前提として、その後に UI 側の E2E テスト（Playwright）を実施する計画。したがって、Headless 側の結合テストで以下の観点が漏れると、UI 側の E2E で初めてバグが発覚し、切り分けコストが高くなる。

## UI 層が依存するコア層のインターフェース一覧

### サービス

| サービス | メソッド | UI での使用箇所 | 重要度 |
|---------|---------|---------------|--------|
| `QRAuthService` | `authenticate(token)` | Staff/Owner ログイン | Critical |
| `QRAuthService` | `issue_token(staff, expires_in_hours=...)` | Owner: QR 発行（存在すれば委譲、なければ UI 側フォールバック） | Medium |
| `HearingTaskService` | `sync_tasks(customer)` | Staff: 接客画面 / Owner: 顧客編集 | Critical |
| `SegmentService` | `bulk_recalculate_segments(store)` | Owner: セグメント設定確定 | High |
| `SegmentService` | `_determine_segment(visit_count, thresholds)` | Owner: セグメントプレビュー | Medium |
| `ImportService` | `upload_csv(file, store, request=None)` | Owner: CSV アップロード | High |
| `MatchingService` | `run_matching(csv_import, store, request=None)` | Owner: マッチング実行 / Staff: 会計後マッチング | Critical |
| `MatchingService` | `get_candidates(row, store)` | Owner/Staff: 候補一覧表示 | High |
| `MatchingService` | `confirm_row(row, visit_id, store, request=None)` | Owner/Staff: マッチング確定 | High |
| `MatchingService` | `reject_row(row, store, request=None)` | Owner/Staff: マッチング却下 | High |
| `AnalyticsService` | `daily_summary(store, date_from, date_to)` | Owner: ダッシュボード（来店推移チャート） | Medium |
| `AnalyticsService` | `segment_ratio(store, date_from, date_to)` | Owner: ダッシュボード（セグメント分布チャート） | Medium |
| `AnalyticsService` | `staff_summary(store, date_from, date_to)` | Owner: ダッシュボード（スタッフ別対応数チャート） | Medium |

### モデル（直接クエリ）

| モデル | UI での主な使い方 |
|-------|-----------------|
| `Staff` | `Staff.objects.filter(store=..., is_active=True)` でスタッフ一覧・存在チェック |
| `Customer` | `Customer.objects.for_store(store)` で顧客一覧・詳細。`visit_count`, `segment` を読み取り |
| `Visit` | `Visit.objects.for_store(store)` で来店一覧。`form.save()` で更新、`soft_delete()` で論理削除 |
| `SegmentThreshold` | `SegmentThreshold.objects.filter(store=...)` で閾値取得。FormSet で一括更新 |
| `CsvImport` / `CsvImportRow` | import 一覧・行一覧の表示。ステータスフィルタリング |
| `HearingTask` | `HearingTask.objects.filter(customer=..., is_closed=False)` で未完了タスク一覧 |
| `QRToken` | ログイン認証時に `QRAuthService` 経由で参照 |

### 例外

| 例外 | 属性 | UI での使い方 |
|------|------|-------------|
| `BusinessError` | `.business_code` | エラーメッセージの出し分け（`ERROR_MESSAGES.get(e.business_code, ...)`） |
| `BusinessError` | `.detail` | フォールバックメッセージとして `str(e)` で表示 |

## 結合テストで検証してほしいデータフロー

以下は **Cluster をまたぐデータの流れ** であり、単体テストでは各 Cluster の内側しか見ていない。結合テストで端から端まで通してほしい。

### F-01: QR 認証 → セッション確立（C-02）

| ステップ | 操作 | 期待 |
|---------|------|------|
| 1 | `QRAuthService.issue_token(staff, expires_in_hours=...)` で token 発行（UI 側にフォールバック実装あり） | `QRToken` レコードが作成される |
| 2 | `QRAuthService.authenticate(token)` で認証 | Staff インスタンスが返る。token が無効化される |
| 3 | 同じ token で再度 `authenticate` | `BusinessError` が発生する（再利用不可） |
| 4 | Owner ロールの Staff で認証 | `staff.role == "owner"` が確認できる |

**UI への影響**: ログインが動かなければ全画面にアクセスできない。

### F-02: 顧客作成 → ヒアリングタスク自動生成（C-03 → C-05a）

| ステップ | 操作 | 期待 |
|---------|------|------|
| 1 | Customer を作成（`age=None, area=None, shisha_experience=None`） | Customer レコード作成 |
| 2 | `HearingTaskService.sync_tasks(customer)` | 3 件の HearingTask が生成される（age, area, experience） |
| 3 | Customer の `age` を更新 → `sync_tasks` 再呼び出し | age タスクが `is_closed=True` になり、残り 2 件 |
| 4 | 全フィールド埋め → `sync_tasks` | 全タスク close。新規タスクなし |

**UI への影響**: 接客画面のタスクゾーン表示、顧客編集後のタスク更新。

### F-03: 来店記録作成 → visit_count 更新 → セグメント再計算（C-04 signal chain）

| ステップ | 操作 | 期待 |
|---------|------|------|
| 1 | Customer の `visit_count` が 0 の状態 | `segment = "new"` |
| 2 | Visit を作成 | signal で `visit_count` が 1 に。`segment` が閾値に応じて更新 |
| 3 | Visit を `soft_delete()` | signal で `visit_count` がデクリメント。`segment` 再計算 |
| 4 | SegmentThreshold を変更 → `bulk_recalculate_segments(store)` | 全顧客の `segment` が新閾値で再計算 |

**UI への影響**: 顧客一覧のセグメントバッジ、セグメント設定画面のプレビュー → 確定フロー。

### F-04: CSV アップロード → マッチング → 確定/却下（C-06 全体）

| ステップ | 操作 | 期待 |
|---------|------|------|
| 1 | `ImportService.upload_csv(file, store)` | `CsvImport` + 複数 `CsvImportRow` 作成。各行 `status="pending"` |
| 2 | `MatchingService.run_matching(csv_import, store)` | 各行に候補が紐づく。`status` が `"matched"` / `"no_match"` 等に更新 |
| 3 | `MatchingService.get_candidates(row, store)` | 候補 Customer リストが返る（スコア付き） |
| 4 | `MatchingService.confirm_row(row, visit_id, store)` | 行の `status="confirmed"`。Customer と Visit が紐づく |
| 5 | `MatchingService.reject_row(row, store)` | 行の `status="rejected"` |
| 6 | 確定された行の Customer の `visit_count` | F-03 の signal chain が動き、visit_count + segment が更新されている |

**UI への影響**: CSV アップロード → 行一覧 → マッチング実行 → 候補表示 → 確定/却下の全画面遷移。F-03 の signal chain と合流する最も複雑なフロー。

### F-05: 分析データ取得（C-07 → C-04, C-03）

| ステップ | 操作 | 期待 |
|---------|------|------|
| 1 | 複数の Visit を異なる日付で作成 | データが蓄積される |
| 2 | `AnalyticsService.daily_summary(store, date_from, date_to)` | 日別来客数 dict が返る。ゼロ埋めあり |
| 3 | `AnalyticsService.segment_ratio(store, date_from, date_to)` | セグメント比率 dict が返る（ratio は 0.0〜1.0） |
| 4 | `AnalyticsService.staff_summary(store, date_from, date_to)` | スタッフ別対応数 dict が返る |
| 5 | Visit を削除（`soft_delete`）後にステップ 2〜4 を再取得 | 削除分が反映されている |

**UI への影響**: ダッシュボードの 3 チャート（来店推移・セグメント分布・スタッフ別対応数）の正確性。UI は `get_dashboard_data` のような集約メソッドではなく、3 メソッドを個別に呼び出している。

### F-06: `soft_delete` の一貫性（横断）

| 確認対象 | 期待 |
|---------|------|
| `Visit.soft_delete()` 後に `Visit.objects.for_store(store)` | 論理削除された Visit が **含まれない** |
| `Staff` の `is_active=False` 設定後 | `Staff.objects.filter(is_active=True)` から **除外される** |
| 論理削除 Visit の `visit_count` 反映 | signal が正しく発火し、カウントが減る |

**UI への影響**: 一覧画面に削除済みデータが表示されないこと。全一覧画面に影響。

### F-07: `BusinessError` の属性一貫性（横断）

| 確認対象 | 期待 |
|---------|------|
| 全サービスが送出する `BusinessError` | `.business_code` が文字列で存在する |
| 同上 | `.detail` が人間可読なメッセージで存在する |
| 同上 | `str(e)` がフォールバック表示に使える |

**UI への影響**: UI は `e.business_code` でエラーメッセージを出し分けている。属性名が違うと `AttributeError` で 500 になる（Issue #21 の再設計で発覚した実例あり）。

### F-08: Store スコープの分離（横断）

| 確認対象 | 期待 |
|---------|------|
| Store A の Customer が Store B のクエリに **出ない** | `Customer.objects.for_store(store_b)` で 0 件 |
| Store A の Visit が Store B に **出ない** | 同上 |
| `ImportService.upload_csv(file, store_a)` の結果が Store B に **出ない** | 同上 |
| `AnalyticsService.daily_summary(store_b, ...)` 等 3 メソッド | Store A のデータが **含まれない** |

**UI への影響**: マルチテナント分離。オーナーが他店舗のデータを見れたら致命的。

## 検証してほしくない（スコープ外）こと

- 各モデルのフィールドバリデーション（単体テストの領域）
- API エンドポイントのレスポンス形式（UI は REST API を使わず、Python 直接呼び出し）
- パフォーマンス・負荷テスト（MVP スコープ外）
- Django Admin の動作

## 結合テスト結果として UI 側が必要とする情報

Headless 側の結合テスト完了時に、以下を共有してほしい:

1. **テスト結果サマリ**: F-01〜F-08 の各フローの PASS/FAIL
2. **Fix があった場合の変更一覧**: どのサービス/モデルの振る舞いが変わったか
3. **API 契約の変更**: メソッドシグネチャ、返り値の型、例外の属性に変更があれば詳細
4. **既知の制約**: 「この操作は○○の条件でないと動かない」等、UI 実装に影響する注意事項

## Review Log

- [2026-04-02] 初版作成
- [2026-04-02] Headless Design からの指摘を受けて修正（v2）
  - MatchingService: `run_matching(csv_import)` → `run_matching(csv_import, store, request=None)`, `confirm_row(row, customer)` → `confirm_row(row, visit_id, store, request=None)`, `reject_row(row)` → `reject_row(row, store, request=None)`
  - AnalyticsService: `get_dashboard_data(store, period)` は存在しない。`daily_summary`, `segment_ratio`, `staff_summary` の 3 メソッド個別呼び出しに修正
  - QRAuthService: `issue_qr_token(staff)` → `issue_token(staff, expires_in_hours=...)`。UI 側はフォールバック実装あり（サービスメソッドが存在しない場合は `QRToken.objects.create()` で直接発行）
  - F-04, F-05 のシナリオステップを正しいシグネチャに更新
