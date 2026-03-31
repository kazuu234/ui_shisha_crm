# UO-04 詳細設計書: CSV インポート + マッチング管理（Owner UI）

> 基本設計書: `docs/design/UI_BASIC_DESIGN.md` §6 UO-04, §7.8
> デザインガイド: `docs/design/UI_DESIGN_GUIDE.md`
> パイプライン: `docs/design/UI_PIPELINE.md` #11, #12
> コア層参照: `docs/reference/cluster/C06_AIRREGI.md`（Slice 1: ImportService, Slice 2: MatchingService）

## 1. 概要

### Cluster 情報

| 項目 | 内容 |
|------|------|
| **Cluster** | UO-04 (CSV インポート・マッチング管理) |
| **Slice 数** | 2 本 |
| **パイプライン順序** | S1: #11 / 13、S2: #12 / 13 |

### Slice 1: CSV アップロード + 行一覧

| 項目 | 内容 |
|------|------|
| **ブランチ説明部** | `uo04-s1-csv-upload` |
| **スコープ** | CSV アップロード画面（同期処理。成功→行一覧リダイレクト、失敗→エラー表示）、インポート行一覧画面、過去インポート履歴（直近 10 件） |

**precondition:**
- UO-01 S1 完了（`base_owner.html`、`OwnerRequiredMixin`、`StoreMixin` が動作）
- コア層 C-06 S1 完了（`ImportService` の CSV パース + Stage 1 が動作）

**postcondition:**
- `/o/imports/upload/` で CSV ファイルをアップロードできる
- アップロード成功（status='completed', row_count > 0）→ `/o/imports/<id>/rows/` にリダイレクト + トースト「CSV をインポートしました（N 件）」
- アップロード成功（status='completed', row_count=0: 全件重複スキップ）→ `/o/imports/<id>/rows/` にリダイレクト + トースト「アップロード完了（0件: 全て重複スキップ）」。行一覧は空テーブル表示（正常系）
- アップロード失敗（ヘッダー不正 / 全行不正）→ 同画面でエラーメッセージ表示（インラインエラー）
- 過去のインポート履歴（直近 10 件）がアップロード画面に表示される（ファイル名、ステータス、行数、日時）
- `/o/imports/<id>/rows/` でインポート行一覧（行番号, 営業日, レシート番号, ステータス, マッチ先顧客名）が表示される
- 行一覧の「マッチング実行」ボタンは Slice 1 では非表示（`{% if matching_enabled %}` で制御。Slice 1 では `matching_enabled=False`）
- Sidebar の「Airレジ連携」がアクティブ状態（`active_sidebar = "imports"`）
- 全 View が `LoginRequiredMixin, OwnerRequiredMixin, StoreMixin` を使用

### Slice 2: マッチング管理

| 項目 | 内容 |
|------|------|
| **ブランチ説明部** | `uo04-s2-matching-mgmt` |
| **スコープ** | マッチング実行トリガー、マッチング管理画面（候補一覧 + 確定/却下） |

**precondition:**
- UO-04 S1 完了（CSV アップロード + 行一覧が動作）
- コア層 C-06 S2 完了（`MatchingService` が動作）

**postcondition:**
- 行一覧画面の「マッチング実行」ボタンを有効化（`matching_enabled=True` に変更）→ POST → `MatchingService.execute_matching(csv_import)` → マッチング管理画面 `/o/imports/<id>/matching/` にリダイレクト + トースト（結果サマリー）
- `/o/imports/<id>/matching/` で `pending_review` の行一覧が表示される
- 各行クリック → HTMX で候補顧客一覧を遅延ロード（N+1 回避。C-06 仕様準拠：候補は毎回再計算、永続化しない）
- 候補選択 → 「確定」ボタン → HTMX PATCH → `MatchingService.confirm_match(row, visit_id)` → confirmed + matched_visit 設定 → 行が一覧から消える
- 「却下」ボタン → HTMX PATCH → `MatchingService.reject_match(row)` → rejected → 行が一覧から消える
- `pending_review` 行がない場合「マッチ待ちの明細はありません」表示
- 確定/却下操作後にトースト表示
- Sidebar の「Airレジ連携」がアクティブ状態（`active_sidebar = "imports"`）
- 全 View が `LoginRequiredMixin, OwnerRequiredMixin, StoreMixin` を使用

## 2. ファイル構成

### Slice 1

```
ui/
├── owner/
│   ├── views/
│   │   └── csv_import.py             # CsvUploadView, CsvImportRowListView
│   ├── forms/
│   │   └── csv_import.py             # CsvUploadForm
│   └── urls.py                       # imports/ 関連 URL を追記
├── templates/ui/
│   └── owner/
│       ├── csv_upload.html           # CSV アップロード画面（フォーム + 過去履歴）
│       └── csv_import_rows.html      # インポート行一覧画面
```

### Slice 2

```
ui/
├── owner/
│   ├── views/
│   │   └── csv_import.py             # MatchingExecuteView, MatchingManageView,
│   │                                 # MatchingCandidatesView, MatchingConfirmView,
│   │                                 # MatchingRejectView を追記
│   ├── forms/
│   │   └── csv_import.py             # MatchingConfirmForm を追記
│   └── urls.py                       # matching/ 関連 URL を追記
├── templates/ui/
│   └── owner/
│       ├── csv_import_matching.html  # マッチング管理画面
│       ├── _matching_row.html        # 行フラグメント（Alpine.js 展開 + HTMX 差し替え用）
│       └── _matching_candidates.html # 候補一覧フラグメント（HTMX 遅延ロード用）
```

**追加するアイコン**: なし（UO-01 S1 で作成済みの `upload.svg` を使用）。

## 3. コア層契約

正式な定義は `docs/reference/cluster/C06_AIRREGI.md` を参照。

**import パスについて**: コア層は別リポジトリ（別 Django app）として管理されている場合がある。本設計書では `from core.services.import_service import ImportService` のような統一的な記法を使用するが、実際の import パスはコア層のパッケージ構造に依存する。実装時にコア層の `__init__.py` や実際のモジュール配置を確認すること。

### CsvImport モデル（UI が参照するフィールド）

| フィールド | 型 | 備考 |
|-----------|-----|------|
| `id` | UUIDField | PK |
| `file_name` | CharField | アップロードファイル名 |
| `status` | CharField (`completed` / `failed`) | インポート結果。completed = 0 件以上正常処理済み（全件重複スキップ含む）。failed = 全グループ不正 |
| `row_count` | PositiveIntegerField | 正常に処理された取引グループ数（= CsvImportRow 件数） |
| `error_message` | JSONField (nullable) | スキップした取引No・元 CSV 行番号・エラー内容の配列。JSON スキーマは下記参照 |
| `uploaded_by` | ForeignKey(Staff) | アップロード実行者 |
| `store` | ForeignKey(Store) | 店舗スコープ |
| `created_at` | DateTimeField | 作成日時 |

**StoreScopedManager**: `CsvImport.objects.for_store(store)` でストアスコープフィルタを適用。

**error_message JSON スキーマ**:

C-06 は `error_message` の具体的な JSON 構造を定義していない。UI テンプレートでの表示に必要な情報（取引No、元 CSV 行番号、エラー内容）に基づき、以下のスキーマを想定する。実装時にコア層と合意すること。

```json
[
  {
    "group_id": 1,
    "receipt_no": "001",
    "lines": [3, 4, 5],
    "error": "来店日のフォーマットが不正です"
  }
]
```

| フィールド | 型 | 備考 |
|-----------|-----|------|
| `group_id` | int | スキップされた取引グループの連番（表示用） |
| `receipt_no` | string | 取引No（CSV の `取引No` フィールド値） |
| `lines` | int[] | 元 CSV の行番号一覧（グループ内の全明細行） |
| `error` | string | エラー内容（日付フォーマット不正、取引No 欠損 等） |

> **注意**: 上記は UI 設計上の想定スキーマである。コア層（C-06 ImportService）の実装時に正式なスキーマを確認し、テンプレートの `{% for err in csv_import.error_message %}` ループを合わせること。

### CsvImportRow モデル（UI が参照するフィールド）

| フィールド | 型 | 備考 |
|-----------|-----|------|
| `id` | UUIDField | PK |
| `csv_import` | ForeignKey(CsvImport) | 親 CsvImport |
| `row_number` | PositiveIntegerField | 行番号（表示用） |
| `status` | CharField (`validated` / `pending_review` / `confirmed` / `rejected`) | 行のステータス |
| `business_date` | DateField | 営業日（来店日） |
| `receipt_no` | CharField | 取引No（レシート番号） |
| `normalized_data` | JSONField | 正規化データ。`customer_name`（CSV 顧客名）、`customer_number`（CSV 顧客番号）等を含む |
| `matched_visit` | ForeignKey(Visit, nullable) | 確定済みの来店記録。select_related で customer にアクセス可能 |
| `store` | ForeignKey(Store) | 店舗スコープ |

**StoreScopedManager**: `CsvImportRow.objects.for_store(store)` でストアスコープフィルタを適用。

### ImportService

| メソッド | 引数 | 返り値 | 例外 |
|---------|------|--------|------|
| `upload_csv(store, file, uploaded_by)` | `Store, UploadedFile, Staff` | `CsvImport` | `BusinessError(code='import.invalid_header')`, `BusinessError(code='import.all_groups_invalid')` |

**upload_csv の仕様**:
- CSV ファイルを同期でパース・バリデーション・CsvImportRow 作成する
- 成功: `CsvImport` (status='completed', row_count >= 0) を返す。row_count=0 は全件重複スキップ時に発生しうる（C-06 仕様準拠）
- ヘッダー不正: `BusinessError(code='import.invalid_header')` を raise（CsvImport 未作成）
- 全取引グループ不正: `BusinessError(code='import.all_groups_invalid')` を raise（CsvImport.status='failed'）
- 冪等キー（store_id + business_date + receipt_no）で既存行はスキップ

### MatchingService

| メソッド | 引数 | 返り値 | 例外 |
|---------|------|--------|------|
| `execute_matching(csv_import)` | `CsvImport` | `dict` — `{auto_confirmed_count, pending_review_count, no_candidate_count, already_processed_count}` | `BusinessError(code='import.not_completed')` |
| `get_candidates(row)` | `CsvImportRow` | `list[dict]` — `[{visit_id, customer{id, name}, visited_at, name_match_score}]` | `BusinessError(code='import.candidates_not_available')` |
| `confirm_match(row, visit_id)` | `CsvImportRow, UUID` | `CsvImportRow` (status='confirmed') | `BusinessError` — 下記コード一覧参照 |
| `reject_match(row)` | `CsvImportRow` | `CsvImportRow` (status='rejected') | `BusinessError` — 下記コード一覧参照 |

**execute_matching の仕様**:
- CsvImport の status が 'completed' でない場合は `BusinessError(code='import.not_completed')` を raise
- validated 行のみ処理。pending_review/confirmed/rejected は already_processed_count に加算してスキップ
- 再実行は安全（冪等）
- レスポンスの 4 カウント合計 == CsvImport.row_count（invariant）

**get_candidates の仕様**:
- `pending_review` 以外のステータスで呼ばれた場合は `BusinessError(code='import.candidates_not_available')` を raise
- 候補は毎回再計算（永続化しない）。同一 Store × 同一営業日の Visit から候補を算出
- 候補のソート順: `name_match_score` 降順。顧客名なし or 同スコアの場合は `customer.name` 昇順（五十音順）
- `name_match_score`: CSV の customer_name と CRM Customer.name の部分一致度（0.0〜1.0）。顧客名が CSV にない場合は null

**confirm_match の仕様**:
- `select_for_update` で排他制御。`visit_id` がその時点の候補集合に含まれるか検証
- 同時操作の場合、先行が勝ち、後続は `import.row_conflict` エラー

**reject_match の仕様**:
- `select_for_update` で排他制御。ステータスを `rejected` に更新
- 同時操作の場合、先行が勝ち、後続は `import.row_conflict` エラー

### BusinessError コード一覧（UI が処理するもの）

UI は ImportService / MatchingService を直接呼び出す（コア層 API エンドポイント経由ではない）ため、BusinessError を catch して処理する。

**エラー処理方針（View 種別ごと）**:

- **通常 POST View（CsvUploadView, MatchingExecuteView）**: BusinessError を catch し、フォームエラーまたはトーストで表示する
- **HTMX PATCH View（MatchingConfirmView, MatchingRejectView）**: 全 BusinessError を 422 + `HX-Reswap: none` + トースト（`HX-Trigger: showToast`）で返す。DOM 変更なし、トーストでユーザーにフィードバック
- **HTMX GET View（MatchingCandidatesView）**: `import.candidates_not_available` は UI 上到達しない（pending_review のみ表示するため）防御コード。発生時は `HttpResponseBadRequest("候補を取得できません")` で 400 テキストを返す

| コード | C-06 定義の HTTP | 意味 | UI の対応 |
|--------|-----------------|------|----------|
| `import.invalid_header` | 400 | 必須ヘッダー（取引No, 来店日）欠損 | アップロード画面でインラインエラー表示 |
| `import.all_groups_invalid` | 400 | 全取引グループが不正 | アップロード画面でインラインエラー表示 |
| `import.not_completed` | 400 | status != completed で match 実行 | 防御コード。トースト「マッチングを実行できません」 |
| `import.candidates_not_available` | 400 | `pending_review` 以外で候補取得 | 防御コード。400 テキスト「候補を取得できません」 |
| `import.row_not_pending` | 400 | pending_review 以外で confirm/reject | 422 + トースト「この明細は既に処理されています」 |
| `import.row_already_processed` | 400 | confirmed/rejected 行の再操作 | 422 + トースト「この明細は既に処理されています」 |
| `import.direct_confirm_reject` | 400 | validated 行の直接 confirm/reject | 422 + トースト「この明細はまだマッチング未実行です」 |
| `import.visit_not_in_candidates` | 400 | confirm 時の visit_id が候補集合に不在 | 422 + トースト「選択した候補は無効です。再読み込みしてください」 |
| `import.row_conflict` | 409 | 同時操作の競合 | 422 + トースト「他のユーザーが先に処理しました」 |

**C-06 との整合性**: UI では `pending_review` の行のみマッチング管理画面に表示するため、`import.row_already_processed`、`import.direct_confirm_reject`、`import.candidates_not_available` は通常到達しない。ただし、HTMX 非同期操作のタイミングによっては到達しうるため（例: 行表示中に別端末でステータスが変わった場合）、C-06 が定義する全コードを処理対象に含める。

### ステータスバッジ定義

行一覧・マッチング管理で使用するステータスバッジの色定義。

| ステータス | 日本語ラベル | バッジクラス | 色（デザインガイド準拠） |
|-----------|------------|-------------|----------------------|
| `validated` | 検証済み | `badge-validated` | `--accent-subtle` bg, `--accent` text |
| `pending_review` | レビュー待ち | `badge-pending` | `--warning-subtle` bg, `--warning-dark` text |
| `confirmed` | 確定済み | `badge-confirmed` | `--success-subtle` bg, `--success` text |
| `rejected` | 却下 | `badge-rejected` | `--error-subtle` bg, `--error` text |

## 4. View 定義

### 4.1 CsvUploadView（Slice 1）

```python
# ui/owner/views/csv_import.py

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.views import View

from ui.mixins import OwnerRequiredMixin, StoreMixin
from core.exceptions import BusinessError
from core.services.import_service import ImportService


class CsvUploadView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    """CSV アップロード画面。アップロードフォーム + 過去インポート履歴を表示する。"""
    template_name = "ui/owner/csv_upload.html"
    login_url = "/o/login/"

    def _get_recent_imports(self):
        """過去インポート履歴（直近 10 件）を取得する。"""
        from core.models import CsvImport

        return (
            CsvImport.objects.for_store(self.store)
            .order_by("-created_at")[:10]
        )

    def get(self, request):
        from ui.owner.forms.csv_import import CsvUploadForm

        form = CsvUploadForm()
        return render(request, self.template_name, {
            "form": form,
            "recent_imports": self._get_recent_imports(),
            "active_sidebar": "imports",
        })

    def post(self, request):
        from ui.owner.forms.csv_import import CsvUploadForm

        form = CsvUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {
                "form": form,
                "recent_imports": self._get_recent_imports(),
                "active_sidebar": "imports",
            })

        csv_file = form.cleaned_data["file"]

        try:
            csv_import = ImportService.upload_csv(
                store=self.store,
                file=csv_file,
                uploaded_by=request.user,
            )
        except BusinessError as e:
            # ヘッダー不正 / 全行不正 → 同画面でエラー表示
            form.add_error(None, self._error_message(e))
            return render(request, self.template_name, {
                "form": form,
                "recent_imports": self._get_recent_imports(),
                "active_sidebar": "imports",
            })

        # 成功: 行一覧にリダイレクト + トースト
        if csv_import.row_count == 0:
            # 全件重複スキップ（C-06: row_count=0, status='completed' は正常系）
            toast_message = "アップロード完了（0件: 全て重複スキップ）"
        else:
            toast_message = f"CSV をインポートしました（{csv_import.row_count} 件）"

        request.session["toast"] = {
            "message": toast_message,
            "type": "success",
        }
        return redirect(f"/o/imports/{csv_import.pk}/rows/")

    @staticmethod
    def _error_message(error):
        """BusinessError コードからユーザー向けメッセージを返す。"""
        messages = {
            "import.invalid_header": "CSV のヘッダーが不正です。「取引No」と「来店日」列が必要です。",
            "import.all_groups_invalid": "CSV の全データが不正です。日付フォーマットや取引No を確認してください。",
        }
        return messages.get(error.code, f"インポートに失敗しました: {error.message}")
```

**同期処理**: C-06 Stage 1 は CSV アップロード時に同期で処理が完了する設計。非同期処理・ポーリングは不要。

**トースト表示**: セッションに toast メッセージを保存し、リダイレクト先の行一覧画面で表示する。UO-02 の `CustomerEditView` と同一パターン。

**BusinessError 処理**: `import.invalid_header`（ヘッダー不正）と `import.all_groups_invalid`（全件不正）を catch し、`form.add_error(None, ...)` で non_field_errors としてフォームに表示する。

### 4.2 CsvImportRowListView（Slice 1）

```python
# ui/owner/views/csv_import.py に追記

from django.views.generic import DetailView
from django.shortcuts import get_object_or_404


class CsvImportRowListView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, DetailView):
    """インポート行一覧画面。CsvImport の詳細 + 配下の CsvImportRow 一覧を表示する。"""
    template_name = "ui/owner/csv_import_rows.html"
    context_object_name = "csv_import"
    login_url = "/o/login/"

    def get_object(self):
        from core.models import CsvImport

        return get_object_or_404(
            CsvImport.objects.for_store(self.store),
            pk=self.kwargs["pk"],
        )

    def get_context_data(self, **kwargs):
        from core.models import CsvImportRow

        context = super().get_context_data(**kwargs)
        csv_import = self.object

        rows = (
            CsvImportRow.objects.for_store(self.store)
            .filter(csv_import=csv_import)
            .select_related("matched_visit__customer")
            .order_by("row_number")
        )

        context["rows"] = rows
        context["active_sidebar"] = "imports"
        # Slice 1: matching_enabled=False（マッチング URL 未登録）
        # Slice 2 実装時: この行を True に変更し、マッチング URL を urls.py に追加する
        # 具体的には Slice 2 の対象ファイルに「CsvImportRowListView の matching_enabled を True に変更」を含める
        context["matching_enabled"] = False  # → Slice 2 で True に変更

        # トーストをセッションから取り出し（表示後に削除）
        toast = self.request.session.pop("toast", None)
        if toast:
            context["toast"] = toast

        return context
```

**matching_enabled フラグ**: Slice 1 では `matching_enabled=False` を設定し、テンプレートの `{% if matching_enabled %}` で「マッチング実行」ボタンを非表示にする。Slice 2 で `MatchingExecuteView` の URL が登録された時点で `matching_enabled=True` に変更する。これにより、Slice 1 時点で存在しない URL へのフォーム送信を防止する。

**DetailView の使用**: CsvImport 1 件の詳細 + 配下の行一覧を表示するため、ListView ではなく DetailView を使用し、`get_context_data()` で行一覧をコンテキストに追加する。

**select_related**: `matched_visit__customer` を select_related して、確定済み行のマッチ先顧客名を N+1 なしで取得する。

**行ソート**: `row_number` 昇順。CSV の元の行順を維持する。

### 4.3 MatchingExecuteView（Slice 2）

```python
# ui/owner/views/csv_import.py に追記

from core.services.matching import MatchingService


class MatchingExecuteView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    """マッチング実行トリガー。POST でマッチングを実行し、マッチング管理画面にリダイレクトする。"""
    login_url = "/o/login/"

    def post(self, request, pk):
        from core.models import CsvImport

        csv_import = get_object_or_404(
            CsvImport.objects.for_store(self.store),
            pk=pk,
        )

        try:
            result = MatchingService.execute_matching(csv_import)
        except BusinessError as e:
            # status != completed の場合
            request.session["toast"] = {
                "message": "マッチングを実行できません",
                "type": "error",
            }
            return redirect(f"/o/imports/{csv_import.pk}/rows/")

        # 成功: マッチング管理画面にリダイレクト + 結果サマリートースト
        summary_parts = []
        if result["auto_confirmed_count"] > 0:
            summary_parts.append(f"自動確定 {result['auto_confirmed_count']} 件")
        if result["pending_review_count"] > 0:
            summary_parts.append(f"レビュー待ち {result['pending_review_count']} 件")
        if result["no_candidate_count"] > 0:
            summary_parts.append(f"候補なし {result['no_candidate_count']} 件")
        if result["already_processed_count"] > 0:
            summary_parts.append(f"処理済みスキップ {result['already_processed_count']} 件")

        request.session["toast"] = {
            "message": f"マッチング完了: {', '.join(summary_parts)}" if summary_parts else "マッチング完了: 処理対象なし",
            "type": "success",
        }
        return redirect(f"/o/imports/{csv_import.pk}/matching/")
```

**マッチング結果サマリー**: `execute_matching()` が返す 4 カウントをトーストに表示する。`already_processed_count` は再実行時のスキップ数であり、0 より大きい場合のみ「処理済みスキップ N 件」として表示する。

**GET 不許可**: マッチング実行は副作用のある操作のため POST のみ受け付ける。GET は Django のデフォルトで 405 Method Not Allowed を返す。

### 4.4 MatchingManageView（Slice 2）

```python
# ui/owner/views/csv_import.py に追記


class MatchingManageView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, DetailView):
    """マッチング管理画面。pending_review の行一覧 + 候補の遅延ロード UI を表示する。"""
    template_name = "ui/owner/csv_import_matching.html"
    context_object_name = "csv_import"
    login_url = "/o/login/"

    def get_object(self):
        from core.models import CsvImport

        return get_object_or_404(
            CsvImport.objects.for_store(self.store),
            pk=self.kwargs["pk"],
        )

    def get_context_data(self, **kwargs):
        from core.models import CsvImportRow

        context = super().get_context_data(**kwargs)
        csv_import = self.object

        rows = (
            CsvImportRow.objects.for_store(self.store)
            .filter(csv_import=csv_import, status="pending_review")
            .order_by("row_number")
        )

        # normalized_data から csv_customer_name, csv_customer_number を抽出してテンプレート用に付与
        for row in rows:
            nd = row.normalized_data or {}
            row.csv_customer_name = nd.get("customer_name")
            row.csv_customer_number = nd.get("customer_number")

        context["rows"] = rows
        context["active_sidebar"] = "imports"

        # トーストをセッションから取り出し（表示後に削除）
        toast = self.request.session.pop("toast", None)
        if toast:
            context["toast"] = toast

        return context
```

**pending_review のみ表示**: マッチング管理画面では `pending_review` の行のみ表示する。`validated`（候補 0 件）、`confirmed`（確定済み）、`rejected`（却下済み）は表示しない。

**csv_customer_name / csv_customer_number の付与**: US-04 と同一パターン。`normalized_data` は JSONField であり、テンプレートから直接 dict キーにアクセスするのは可読性が低い。View で `row.csv_customer_name`、`row.csv_customer_number` としてプロパティ的に付与する。`customer_number` は C-06 仕様で手動レビューの参考情報として表示する。

### 4.5 MatchingCandidatesView（Slice 2）

```python
# ui/owner/views/csv_import.py に追記

from django.http import HttpResponseBadRequest


class MatchingCandidatesView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    """HTMX GET: 候補一覧を遅延ロードする。"""
    login_url = "/o/login/"

    def get(self, request, pk, row_id):
        from core.models import CsvImportRow

        row = get_object_or_404(
            CsvImportRow.objects.for_store(self.store).filter(csv_import_id=pk),
            pk=row_id,
        )

        try:
            raw_candidates = MatchingService.get_candidates(row)
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

        return render(request, "ui/owner/_matching_candidates.html", {
            "candidates": candidates,
            "csv_import_id": str(pk),
            "row_id": str(row.pk),
        })
```

**候補の毎回再計算**: `MatchingService.get_candidates(row)` は候補を永続化せず毎回再計算する（C-06 設計に準拠）。展開のたびに最新の候補が表示されるため、Visit の追加・更新・削除が反映される。

**候補データの flat 化**: C-06 の `get_candidates()` はネストされた dict を返す。テンプレートでの可読性と明示性のため View で flat 化する（US-04 と同一パターン）。

**csv_import_id のスコープ**: `CsvImportRow` の取得時に `csv_import_id=pk` でフィルタし、他の CsvImport に属する行へのアクセスを防止する。

### 4.6 MatchingConfirmView（Slice 2）

```python
# ui/owner/views/csv_import.py に追記

from django.http import HttpResponse, QueryDict


ERROR_MESSAGES = {
    "import.row_not_pending": "この明細は既に処理されています",
    "import.row_already_processed": "この明細は既に処理されています",
    "import.direct_confirm_reject": "この明細はまだマッチング未実行です",
    "import.visit_not_in_candidates": "選択した候補は無効です。再読み込みしてください",
    "import.row_conflict": "他のユーザーが先に処理しました",
}


class MatchingConfirmView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    """HTMX PATCH: 候補を確定する。"""
    login_url = "/o/login/"

    def patch(self, request, pk, row_id):
        from core.models import CsvImportRow
        from ui.owner.forms.csv_import import MatchingConfirmForm

        row = get_object_or_404(
            CsvImportRow.objects.for_store(self.store).filter(csv_import_id=pk),
            pk=row_id,
        )

        # PATCH body を手動パース（Django は PATCH を request.POST にパースしない）
        data = QueryDict(request.body)
        form = MatchingConfirmForm(data)

        if not form.is_valid():
            return HttpResponseBadRequest("無効なリクエストです")

        visit_id = form.cleaned_data["visit_id"]

        try:
            MatchingService.confirm_match(row, visit_id)
        except BusinessError as e:
            # エラーメッセージをトーストで表示し、行はそのまま残す
            message = ERROR_MESSAGES.get(e.code, "確定に失敗しました")
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

**confirm 成功時の挙動**: 空の HTML を返し、`hx-swap="outerHTML"` により行要素が DOM から消える。トースト「確定しました」を表示する。

**エラー時の挙動**: 422 + `HX-Reswap: none` で DOM を変更せず、トーストでエラーメッセージを表示する。`base.html` の `htmx:beforeSwap` が 422 を swap 許可しているが、`HX-Reswap: none` で上書きして DOM 変更を抑止する。

**PATCH body パース**: US-04 と同じく `QueryDict(request.body)` で手動パースする。

### 4.7 MatchingRejectView（Slice 2）

```python
# ui/owner/views/csv_import.py に追記


class MatchingRejectView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    """HTMX PATCH: 明細を却下する。"""
    login_url = "/o/login/"

    def patch(self, request, pk, row_id):
        from core.models import CsvImportRow

        row = get_object_or_404(
            CsvImportRow.objects.for_store(self.store).filter(csv_import_id=pk),
            pk=row_id,
        )

        try:
            MatchingService.reject_match(row)
        except BusinessError as e:
            message = ERROR_MESSAGES.get(e.code, "却下に失敗しました")
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

## 5. Form 定義

### 5.1 CsvUploadForm（Slice 1）

```python
# ui/owner/forms/csv_import.py

from django import forms


class CsvUploadForm(forms.Form):
    file = forms.FileField(
        label="CSV ファイル",
        help_text="Airレジの「会計明細CSV」をアップロードしてください",
    )

    def clean_file(self):
        """ファイル拡張子とサイズの基本チェック。"""
        f = self.cleaned_data.get("file")
        if f:
            if not f.name.endswith(".csv"):
                raise forms.ValidationError("CSV ファイルを選択してください")
            # 最大ファイルサイズ: 10MB
            if f.size > 10 * 1024 * 1024:
                raise forms.ValidationError("ファイルサイズは 10MB 以下にしてください")
        return f
```

**バリデーション範囲**: Form は拡張子とファイルサイズの基本チェックのみ。CSV の中身（ヘッダー検証・行検証）は `ImportService.upload_csv()` が担う。責務分離のため、Form で CSV パースを行わない。

### 5.2 MatchingConfirmForm（Slice 2）

```python
# ui/owner/forms/csv_import.py に追記


class MatchingConfirmForm(forms.Form):
    visit_id = forms.UUIDField()
```

**シンプルな理由**: confirm 操作のバリデーション（visit_id が候補集合に含まれるか）は `MatchingService.confirm_match()` が担う。Form はリクエストボディの型チェックのみ。US-04 と同一パターン。

## 6. テンプレート

### 6.1 owner/csv_upload.html（Slice 1）

```
{% extends "ui/base_owner.html" %}
{% load static %}

{% block page_title %}Airレジ連携{% endblock %}

{% block content %}
  <!-- CSV アップロードフォーム -->
  <section>  <!-- bg-bg-surface, shadow-sm, rounded-md, p-6, mb-6 -->
    <h2>CSV アップロード</h2>

    <form method="post" enctype="multipart/form-data">
      {% csrf_token %}

      <!-- non_field_errors（BusinessError のエラーメッセージ） -->
      {% if form.non_field_errors %}
        <div>  <!-- bg-error-subtle, text-error, p-4, rounded-md, mb-4 -->
          {% for error in form.non_field_errors %}
            <p>{{ error }}</p>
          {% endfor %}
        </div>
      {% endif %}

      <div>  <!-- mb-4 -->
        <label for="{{ form.file.id_for_label }}">{{ form.file.label }}</label>
        {{ form.file }}
        {% if form.file.help_text %}
          <p>  <!-- text-text-secondary, text-sm, mt-1 -->
            {{ form.file.help_text }}
          </p>
        {% endif %}
        {% if form.file.errors %}
          <p class="text-error">{{ form.file.errors.0 }}</p>
        {% endif %}
      </div>

      <button type="submit" class="btn-primary">アップロード</button>
    </form>
  </section>

  <!-- 過去のインポート履歴 -->
  <section>  <!-- bg-bg-surface, shadow-sm, rounded-md, p-6 -->
    <h2>インポート履歴</h2>

    {% if recent_imports %}
      <table>
        <thead>
          <tr>
            <th>ファイル名</th>
            <th>ステータス</th>
            <th>行数</th>
            <th>日時</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {% for imp in recent_imports %}
            <tr>
              <td>{{ imp.file_name }}</td>
              <td>
                {% if imp.status == "completed" %}
                  <span class="badge-confirmed">完了</span>
                {% elif imp.status == "failed" %}
                  <span class="badge-rejected">失敗</span>
                {% endif %}
              </td>
              <td>{{ imp.row_count }} 件</td>
              <td>{{ imp.created_at|date:"Y/m/d H:i" }}</td>
              <td>
                {% if imp.status == "completed" %}
                  <a href="/o/imports/{{ imp.pk }}/rows/" class="text-accent text-sm">詳細</a>
                {% elif imp.status == "failed" %}
                  <a href="/o/imports/{{ imp.pk }}/rows/" class="text-accent text-sm">エラー詳細</a>
                {% endif %}
              </td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    {% else %}
      <p class="text-text-secondary">インポート履歴はありません</p>
    {% endif %}
  </section>
{% endblock %}
```

**enctype**: ファイルアップロードのため `multipart/form-data` を指定する。

**インポート履歴のリンク**: `completed` は「詳細」リンクで行一覧を表示。`failed` は「エラー詳細」リンクで `/rows/` に遷移し、`error_message` JSON を整形表示する（行データは 0 件だがエラー情報は `CsvImport.error_message` に保存されている）。

### 6.2 owner/csv_import_rows.html（Slice 1）

```
{% extends "ui/base_owner.html" %}
{% load static %}

{% block page_title %}インポート詳細{% endblock %}

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
  <!-- インポート情報ヘッダー -->
  <section>  <!-- bg-bg-surface, shadow-sm, rounded-md, p-6, mb-6 -->
    <div>  <!-- flex items-center justify-between -->
      <div>
        <h2>{{ csv_import.file_name }}</h2>
        <p>  <!-- text-text-secondary, text-sm -->
          {% if csv_import.status == "completed" %}
            <span class="badge-confirmed">完了</span>
          {% elif csv_import.status == "failed" %}
            <span class="badge-rejected">失敗</span>
          {% endif %}
          {{ csv_import.created_at|date:"Y/m/d H:i" }} ・ {{ csv_import.row_count }} 件
        </p>
      </div>

      <!-- マッチング実行ボタン（Slice 1: matching_enabled=False で非表示、Slice 2: True で表示） -->
      {% if matching_enabled %}
        <form method="post" action="/o/imports/{{ csv_import.pk }}/matching/execute/">
          {% csrf_token %}
          <button type="submit" class="btn-primary">マッチング実行</button>
        </form>
      {% endif %}
    </div>

    <!-- エラー情報（status に応じて文言を分岐） -->
    {% if csv_import.error_message %}
      <div>  <!-- bg-warning-subtle, text-warning-dark, p-4, rounded-md, mt-4 -->
        {% if csv_import.status == "failed" %}
          <p>全件不正のためインポートに失敗しました:</p>
        {% else %}
          <p>一部の取引データがスキップされました:</p>
        {% endif %}
        <ul>  <!-- list-disc, ml-4, mt-2, text-sm -->
          {% for err in csv_import.error_message %}
            <li>取引No {{ err.receipt_no }}（CSV {{ err.lines|join:", " }} 行目）: {{ err.error }}</li>
          {% endfor %}
        </ul>
      </div>
    {% endif %}
  </section>

  <!-- 行一覧テーブル -->
  <section>  <!-- bg-bg-surface, shadow-sm, rounded-md -->
    <table>
      <thead>
        <tr>
          <th>行番号</th>
          <th>営業日</th>
          <th>レシート番号</th>
          <th>ステータス</th>
          <th>マッチ先</th>
        </tr>
      </thead>
      <tbody>
        {% for row in rows %}
          <tr>
            <td>{{ row.row_number }}</td>
            <td>{{ row.business_date|date:"Y/m/d" }}</td>
            <td>{{ row.receipt_no }}</td>
            <td>
              {% if row.status == "validated" %}
                <span class="badge-validated">検証済み</span>
              {% elif row.status == "pending_review" %}
                <span class="badge-pending">レビュー待ち</span>
              {% elif row.status == "confirmed" %}
                <span class="badge-confirmed">確定済み</span>
              {% elif row.status == "rejected" %}
                <span class="badge-rejected">却下</span>
              {% endif %}
            </td>
            <td>
              {% if row.matched_visit %}
                {{ row.matched_visit.customer.name }}
              {% else %}
                <span class="text-text-muted">-</span>
              {% endif %}
            </td>
          </tr>
        {% empty %}
          <tr>
            <td colspan="5">インポートデータがありません</td>
          </tr>
        {% endfor %}
      </tbody>
    </table>
  </section>

  <!-- アップロード画面に戻るリンク -->
  <div>  <!-- mt-4 -->
    <a href="/o/imports/upload/" class="text-accent text-sm">← アップロード画面に戻る</a>
  </div>
{% endblock %}
```

**マッチ先の表示**: `select_related("matched_visit__customer")` で取得済みの顧客名を表示する。`confirmed` ステータスの行のみ `matched_visit` が設定されている。

**エラー情報**: `csv_import.error_message` は JSON 配列（スキップされた取引の詳細）。部分失敗時（一部の取引がスキップされたが status='completed'）に警告として表示する。

**マッチング実行ボタン**: `{% if matching_enabled %}` で制御する。Slice 1 では `matching_enabled=False` のためボタンは非表示。Slice 2 で `matching_enabled=True` に変更し、ボタンを表示する。Slice 1 時点で存在しない URL へのフォーム送信を防止する。

### 6.3 owner/csv_import_matching.html（Slice 2）

```
{% extends "ui/base_owner.html" %}
{% load static %}

{% block page_title %}マッチング管理{% endblock %}

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
  <!-- インポート情報ヘッダー -->
  <div>  <!-- mb-6 -->
    <h2>{{ csv_import.file_name }} - マッチング</h2>
    <p>  <!-- text-text-secondary, text-sm -->
      レビュー待ち: {{ rows|length }} 件
    </p>
  </div>

  <!-- pending_review 行一覧 -->
  <div>  <!-- bg-bg-surface, shadow-sm, rounded-md -->
    {% for row in rows %}
      {% include "ui/owner/_matching_row.html" with row=row %}
    {% empty %}
      <div>  <!-- text-center, text-text-secondary, py-8, px-5 -->
        <p>マッチ待ちの明細はありません</p>
      </div>
    {% endfor %}
  </div>

  <!-- ナビゲーション -->
  <div>  <!-- mt-4, flex gap-4 -->
    <a href="/o/imports/{{ csv_import.pk }}/rows/" class="text-accent text-sm">← 行一覧に戻る</a>
    <a href="/o/imports/upload/" class="text-accent text-sm">アップロード画面に戻る</a>
  </div>
{% endblock %}
```

### 6.4 owner/_matching_row.html（Slice 2）

行フラグメント。Alpine.js で展開/折りたたみを制御し、展開時に HTMX で候補を遅延ロードする。

```
{% load static %}

<div id="matching-row-{{ row.id }}"
     x-data="{ open: false }"
     class="border-b border-border-default last:border-b-0">

  <!-- 行ヘッダー（クリックで展開。展開のたびに候補を再取得する） -->
  <div @click="open = !open; if (open) { $nextTick(() => htmx.trigger($refs.candidateArea, 'loadCandidates')) }"
       class="py-3 px-5 cursor-pointer hover:bg-accent-light">
    <div>  <!-- flex items-center justify-between -->
      <div>
        <span>{{ row.business_date|date:"n/j" }}</span>  <!-- font-medium -->
        <span>No.{{ row.receipt_no }}</span>  <!-- text-text-secondary, text-sm, ml-2 -->
        <span>行{{ row.row_number }}</span>  <!-- text-text-muted, text-xs, ml-2 -->
      </div>
      <span x-text="open ? '▾' : '▸'"></span>  <!-- text-text-muted -->
    </div>
    {% if row.csv_customer_name or row.csv_customer_number %}
      <p>  <!-- text-text-secondary, text-sm, mt-1 -->
        {% if row.csv_customer_name %}CSV 顧客名: {{ row.csv_customer_name }}{% endif %}
        {% if row.csv_customer_number %}
          <span class="ml-2">顧客番号: {{ row.csv_customer_number }}</span>
        {% endif %}
      </p>
    {% endif %}
  </div>

  <!-- 候補エリア（展開時に HTMX で遅延ロード） -->
  <div x-show="open" x-transition x-ref="candidateArea"
       hx-get="/o/imports/{{ row.csv_import_id }}/rows/{{ row.id }}/candidates/"
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

**遅延ロードのトリガー**: 行を展開するたびに `htmx.trigger()` でカスタムイベント `loadCandidates` を発火し、候補一覧を HTMX GET で再取得する。C-06 の設計に従い、候補は毎回再計算される（永続化しない）。展開のたびに最新の候補が表示されるため、Visit の追加・更新・削除が反映される。US-04 と同一パターン。

**行ヘッダーの情報**: 営業日、レシート番号、行番号、CSV 顧客名、CSV 顧客番号を表示する。オーナー UI では行番号も表示する（スタッフ UI の US-04 よりも詳細な情報を提供する）。`customer_number` は C-06 仕様に基づき、手動レビュー時の参考情報として表示する。

### 6.5 owner/_matching_candidates.html（Slice 2）

候補一覧フラグメント。HTMX GET の応答として返される。

```
{% load static %}

{% if candidates %}
  <div>  <!-- divide-y divide-border-default -->
    {% for candidate in candidates %}
      <div>  <!-- py-2, flex items-center justify-between -->
        <div>
          <span>{{ candidate.customer_name }}</span>  <!-- font-medium -->
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
          hx-patch="/o/imports/{{ csv_import_id }}/rows/{{ row_id }}/confirm/"
          hx-vals='{"visit_id": "{{ candidate.visit_id }}"}'
          hx-target="#matching-row-{{ row_id }}"
          hx-swap="outerHTML"
          class="btn-sm text-accent font-medium">
          確定
        </button>
      </div>
    {% endfor %}
  </div>

  <!-- 却下ボタン -->
  <div>  <!-- mt-3, pt-3, border-t border-border-default -->
    <button
      hx-patch="/o/imports/{{ csv_import_id }}/rows/{{ row_id }}/reject/"
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
      hx-patch="/o/imports/{{ csv_import_id }}/rows/{{ row_id }}/reject/"
      hx-target="#matching-row-{{ row_id }}"
      hx-swap="outerHTML"
      class="text-sm text-error font-medium">
      この明細を却下
    </button>
  </div>
{% endif %}
```

**confirm の HTMX ターゲット**: `hx-target="#matching-row-{{ row_id }}"` で行全体を差し替える。confirm/reject 成功後は空の HTML を返し、行が消える（一覧から除去）。US-04 と同一パターン。

**reject ボタンの配置**: 候補一覧の下に配置する。候補が 0 件の場合でも却下操作は可能とする（オペレーターがマッチング不要と判断した場合）。

**確定ボタンの hx-vals**: `visit_id` を JSON で送信する。CSRF トークンは `base.html` の `htmx:configRequest` イベントハンドラで自動付与される。

## 7. URL 設定

### ui/owner/urls.py（追記部分）

#### Slice 1 で追加する URL

```python
from ui.owner.views.csv_import import CsvUploadView, CsvImportRowListView

urlpatterns = [
    # ... UO-01, UO-02, UO-03 の既存 URL ...

    # UO-04 S1: CSV アップロード
    path("imports/upload/", CsvUploadView.as_view(), name="csv-upload"),

    # UO-04 S1: インポート行一覧
    path("imports/<uuid:pk>/rows/", CsvImportRowListView.as_view(), name="csv-import-rows"),
]
```

#### Slice 2 で追加する URL

```python
from ui.owner.views.csv_import import (
    MatchingExecuteView,
    MatchingManageView,
    MatchingCandidatesView,
    MatchingConfirmView,
    MatchingRejectView,
)

urlpatterns = [
    # ... 既存 URL + Slice 1 URL ...

    # UO-04 S2: マッチング実行（POST のみ）
    path("imports/<uuid:pk>/matching/execute/", MatchingExecuteView.as_view(), name="matching-execute"),

    # UO-04 S2: マッチング管理画面
    path("imports/<uuid:pk>/matching/", MatchingManageView.as_view(), name="matching-manage"),

    # UO-04 S2: 候補遅延ロード（HTMX GET）
    path("imports/<uuid:pk>/rows/<uuid:row_id>/candidates/", MatchingCandidatesView.as_view(), name="matching-candidates"),

    # UO-04 S2: 候補確定（HTMX PATCH）
    path("imports/<uuid:pk>/rows/<uuid:row_id>/confirm/", MatchingConfirmView.as_view(), name="matching-confirm"),

    # UO-04 S2: 明細却下（HTMX PATCH）
    path("imports/<uuid:pk>/rows/<uuid:row_id>/reject/", MatchingRejectView.as_view(), name="matching-reject"),
]
```

**URL パスの設計意図**:
- `/o/imports/upload/`: CSV アップロード画面
- `/o/imports/<id>/rows/`: インポート行一覧
- `/o/imports/<id>/matching/execute/`: マッチング実行（POST のみ）
- `/o/imports/<id>/matching/`: マッチング管理画面
- `/o/imports/<id>/rows/<row_id>/candidates/`: 候補遅延ロード（HTMX GET）
- `/o/imports/<id>/rows/<row_id>/confirm/`: 候補確定（HTMX PATCH）
- `/o/imports/<id>/rows/<row_id>/reject/`: 明細却下（HTMX PATCH）

**コア層 API エンドポイントとの関係**: コア層は `/api/v1/imports/csv/...` を提供する。UI は Service 層を直接呼び出すため、コア層の API エンドポイントは使用しない。URL パスはオーナー UI の慣例（`/o/` プレフィックス）に従う。

## 8. テストケース

### 8.1 Django TestClient — Slice 1

#### CSV アップロード画面

| # | テスト | 検証内容 |
|---|--------|---------|
| 1 | `test_csv_upload_get` | GET `/o/imports/upload/` → 200。`csv_upload.html` 使用 |
| 2 | `test_csv_upload_requires_auth` | 未認証で GET → 302 `/o/login/` |
| 3 | `test_csv_upload_requires_owner` | staff ロールで GET → 302 `/s/customers/` |
| 4 | `test_csv_upload_active_sidebar` | context に `active_sidebar == "imports"` |
| 5 | `test_csv_upload_shows_form` | レスポンスにファイル入力フィールドとアップロードボタンが含まれる |
| 6 | `test_csv_upload_shows_recent_imports` | 過去インポート履歴が表示される（直近 10 件） |
| 7 | `test_csv_upload_recent_imports_limit_10` | 11 件のインポートがある場合、最新 10 件のみ表示される |
| 8 | `test_csv_upload_recent_imports_order` | インポート履歴が `created_at` 降順で表示される |
| 9 | `test_csv_upload_recent_imports_store_scope` | 他店舗のインポートは表示されない |
| 10 | `test_csv_upload_post_success` | 正常 CSV → 302 `/o/imports/<id>/rows/`。セッションに toast。CsvImport 作成 |
| 11 | `test_csv_upload_post_invalid_header` | ヘッダー不正 CSV → 200（同画面再表示）。non_field_errors にエラーメッセージ |
| 12 | `test_csv_upload_post_all_groups_invalid` | 全件不正 CSV → 200（同画面再表示）。non_field_errors にエラーメッセージ |
| 13 | `test_csv_upload_post_no_file` | ファイル未選択 → 200（同画面再表示）。form.file.errors にエラー |
| 14 | `test_csv_upload_post_non_csv` | .txt ファイル → 200（同画面再表示）。form.file.errors にエラー |
| 15 | `test_csv_upload_post_oversized` | 10MB 超ファイル → 200（同画面再表示）。form.file.errors にエラー |
| 16 | `test_csv_upload_toast_message` | アップロード成功後のトーストに行数が含まれる |
| 16a | `test_csv_upload_post_all_duplicates` | 全件重複スキップ CSV（row_count=0, status='completed'）→ 302 `/o/imports/<id>/rows/`。トースト「アップロード完了（0件: 全て重複スキップ）」 |
| 16b | `test_csv_upload_all_duplicates_redirect_to_rows` | 全件重複スキップ後のリダイレクト先で行一覧が空テーブル（「インポートデータがありません」）表示される |
| 16c | `test_csv_upload_failed_import_in_history` | 失敗したインポート（status='failed'）がインポート履歴に `badge-rejected`（失敗）バッジ付きで表示される |

#### インポート行一覧画面

| # | テスト | 検証内容 |
|---|--------|---------|
| 17 | `test_csv_import_rows_get` | GET `/o/imports/<id>/rows/` → 200。`csv_import_rows.html` 使用 |
| 18 | `test_csv_import_rows_requires_auth` | 未認証で GET → 302 `/o/login/` |
| 19 | `test_csv_import_rows_requires_owner` | staff ロールで GET → 302 `/s/customers/` |
| 20 | `test_csv_import_rows_store_scope` | 他店舗の CsvImport → 404 |
| 21 | `test_csv_import_rows_nonexistent` | 存在しない CsvImport → 404 |
| 22 | `test_csv_import_rows_active_sidebar` | context に `active_sidebar == "imports"` |
| 23 | `test_csv_import_rows_displays_columns` | テーブルに行番号、営業日、レシート番号、ステータス、マッチ先が表示される |
| 24 | `test_csv_import_rows_order_by_row_number` | 行が `row_number` 昇順で表示される |
| 25 | `test_csv_import_rows_status_badge` | 各ステータスに対応するバッジクラスが表示される |
| 26 | `test_csv_import_rows_matched_visit_customer_name` | confirmed 行にマッチ先の顧客名が表示される |
| 27 | `test_csv_import_rows_no_match_dash` | 未確定行のマッチ先列に「-」が表示される |
| 28 | `test_csv_import_rows_matching_button_hidden_slice1` | Slice 1（`matching_enabled=False`）では「マッチング実行」ボタンが表示されない |
| 29 | `test_csv_import_rows_toast_display` | セッションに toast がある場合、トーストが表示される |
| 30 | `test_csv_import_rows_error_message_display` | `csv_import.error_message` がある場合、スキップ情報が表示される |
| 31 | `test_csv_import_rows_empty` | 行が 0 件の場合「インポートデータがありません」が表示される |
| 31a | `test_csv_import_rows_header_status_badge` | インポート情報ヘッダーに `csv_import.status` のバッジ（完了 = `badge-confirmed`、失敗 = `badge-rejected`）が表示される |
| 31b | `test_csv_import_rows_header_filename` | インポート情報ヘッダーに `csv_import.file_name` が表示される |

### 8.2 Django TestClient — Slice 2

#### マッチング実行

| # | テスト | 検証内容 |
|---|--------|---------|
| 32 | `test_matching_execute_post` | POST `/o/imports/<id>/matching/execute/` → 302 `/o/imports/<id>/matching/`。セッションに toast |
| 33 | `test_matching_execute_requires_auth` | 未認証で POST → 302 `/o/login/` |
| 34 | `test_matching_execute_requires_owner` | staff ロールで POST → 302 `/s/customers/` |
| 35 | `test_matching_execute_store_scope` | 他店舗の CsvImport → 404 |
| 36 | `test_matching_execute_nonexistent` | 存在しない CsvImport → 404 |
| 37 | `test_matching_execute_get_not_allowed` | GET → 405 Method Not Allowed |
| 38 | `test_matching_execute_not_completed` | status != completed の CsvImport → 302（行一覧に戻る）+ エラートースト |
| 39 | `test_matching_execute_toast_summary` | トーストに自動確定数、レビュー待ち数、候補なし数のサマリーが含まれる |
| 40 | `test_matching_execute_idempotent` | 2 回目の実行 → 302 + トーストに「処理済みスキップ N 件」が含まれる（already_processed_count > 0） |
| 40a | `test_csv_import_rows_matching_button_visible_slice2` | Slice 2（`matching_enabled=True`）では「マッチング実行」ボタンが表示される |

#### マッチング管理画面

| # | テスト | 検証内容 |
|---|--------|---------|
| 41 | `test_matching_manage_get` | GET `/o/imports/<id>/matching/` → 200。`csv_import_matching.html` 使用 |
| 42 | `test_matching_manage_requires_auth` | 未認証で GET → 302 `/o/login/` |
| 43 | `test_matching_manage_requires_owner` | staff ロールで GET → 302 `/s/customers/` |
| 44 | `test_matching_manage_store_scope` | 他店舗の CsvImport → 404 |
| 45 | `test_matching_manage_active_sidebar` | context に `active_sidebar == "imports"` |
| 46 | `test_matching_manage_shows_pending_review_only` | `pending_review` の行のみ表示。`validated`, `confirmed`, `rejected` は表示されない |
| 47 | `test_matching_manage_empty_message` | `pending_review` 行が 0 件の場合「マッチ待ちの明細はありません」が表示される |
| 48 | `test_matching_manage_displays_receipt_no` | レスポンスにレシート番号が含まれる |
| 49 | `test_matching_manage_displays_csv_customer_name` | CSV 顧客名がある行で、顧客名が表示される |
| 50 | `test_matching_manage_no_csv_customer_name` | CSV 顧客名がない行で、顧客名セクションが表示されない |
| 50a | `test_matching_manage_displays_csv_customer_number` | CSV 顧客番号がある行で、顧客番号が表示される |
| 50b | `test_matching_manage_no_csv_customer_number` | CSV 顧客名も顧客番号もない行で、顧客情報セクションが表示されない |
| 51 | `test_matching_manage_order_by_row_number` | 行が `row_number` 昇順で表示される |
| 52 | `test_matching_manage_toast_display` | セッションに toast がある場合、トーストが表示される |

#### 候補遅延ロード

| # | テスト | 検証内容 |
|---|--------|---------|
| 53 | `test_candidates_get` | GET `/o/imports/<id>/rows/<row_id>/candidates/` → 200。`_matching_candidates.html` 使用 |
| 54 | `test_candidates_requires_auth` | 未認証で GET → 302 `/o/login/` |
| 55 | `test_candidates_requires_owner` | staff ロールで GET → 302 `/s/customers/` |
| 56 | `test_candidates_store_scope` | 他店舗の row_id → 404 |
| 57 | `test_candidates_nonexistent_row` | 存在しない row_id → 404 |
| 58 | `test_candidates_wrong_import` | 別の CsvImport の row_id → 404 |
| 59 | `test_candidates_displays_customer_name` | 候補の顧客名が表示される |
| 60 | `test_candidates_displays_visited_at` | 候補の来店日が表示される |
| 61 | `test_candidates_displays_match_score` | `name_match_score` が 1.0 の候補に「完全一致」、0.5 の候補に「部分一致」が表示される |
| 62 | `test_candidates_not_pending_review_validated` | `validated` ステータスの行で GET → 400。レスポンス本文に「候補を取得できません」を含む。`HX-Trigger` ヘッダーが付与されない |
| 62a | `test_candidates_not_pending_review_confirmed` | `confirmed` ステータスの行で GET → 400。レスポンス本文に「候補を取得できません」を含む。`HX-Trigger` ヘッダーが付与されない |
| 62b | `test_candidates_not_pending_review_rejected` | `rejected` ステータスの行で GET → 400。レスポンス本文に「候補を取得できません」を含む。`HX-Trigger` ヘッダーが付与されない |
| 63 | `test_candidates_has_confirm_button` | 各候補に確定ボタン（`hx-patch` 付き）が含まれる |
| 64 | `test_candidates_has_reject_button` | 却下ボタンが含まれる |
| 65 | `test_candidates_empty` | 候補 0 件の場合、「候補が見つかりませんでした」メッセージと却下ボタンが表示される |
| 66 | `test_candidates_sort_order` | 候補が `name_match_score` 降順で表示される |
| 67 | `test_candidates_flat_mapping` | View が C-06 のネスト構造をテンプレート用に flat 化していることを検証 |

#### 候補確定（confirm）

| # | テスト | 検証内容 |
|---|--------|---------|
| 68 | `test_confirm_patch` | PATCH with visit_id → 200。行が confirmed に遷移 |
| 69 | `test_confirm_requires_auth` | 未認証で PATCH → 302 `/o/login/` |
| 70 | `test_confirm_requires_owner` | staff ロールで PATCH → 302 `/s/customers/` |
| 71 | `test_confirm_store_scope` | 他店舗の row_id → 404 |
| 72 | `test_confirm_nonexistent_row` | 存在しない row_id → 404 |
| 73 | `test_confirm_wrong_import` | 別の CsvImport の row_id → 404 |
| 74 | `test_confirm_invalid_visit_id` | PATCH with visit_id="invalid" → 400 「無効なリクエストです」 |
| 75 | `test_confirm_missing_visit_id` | PATCH without visit_id → 400 「無効なリクエストです」 |
| 76 | `test_confirm_visit_not_in_candidates` | MatchingService が `import.visit_not_in_candidates` → 422 + トースト |
| 77 | `test_confirm_row_not_pending` | MatchingService が `import.row_not_pending` → 422 + トースト |
| 78 | `test_confirm_row_already_processed` | MatchingService が `import.row_already_processed` → 422 + トースト |
| 79 | `test_confirm_row_conflict` | MatchingService が `import.row_conflict` → 422 + トースト |
| 79a | `test_confirm_direct_confirm_reject` | MatchingService が `import.direct_confirm_reject` → 422 + トースト「この明細はまだマッチング未実行です」 |
| 80 | `test_confirm_success_empty_response` | 成功時のレスポンスボディが空（行が DOM から消える） |
| 81 | `test_confirm_success_toast` | 成功時に `HX-Trigger` ヘッダーで「確定しました」トーストが発火 |
| 82 | `test_confirm_error_reswap_none` | エラー時に `HX-Reswap: none` ヘッダーが付与される |

#### 明細却下（reject）

| # | テスト | 検証内容 |
|---|--------|---------|
| 83 | `test_reject_patch` | PATCH → 200。行が rejected に遷移 |
| 84 | `test_reject_requires_auth` | 未認証で PATCH → 302 `/o/login/` |
| 85 | `test_reject_requires_owner` | staff ロールで PATCH → 302 `/s/customers/` |
| 86 | `test_reject_store_scope` | 他店舗の row_id → 404 |
| 87 | `test_reject_nonexistent_row` | 存在しない row_id → 404 |
| 88 | `test_reject_wrong_import` | 別の CsvImport の row_id → 404 |
| 89 | `test_reject_row_not_pending` | MatchingService が `import.row_not_pending` → 422 + トースト |
| 90 | `test_reject_row_conflict` | MatchingService が `import.row_conflict` → 422 + トースト |
| 90a | `test_reject_row_already_processed` | MatchingService が `import.row_already_processed` → 422 + トースト「この明細は既に処理されています」 |
| 90b | `test_reject_direct_confirm_reject` | MatchingService が `import.direct_confirm_reject` → 422 + トースト「この明細はまだマッチング未実行です」 |
| 91 | `test_reject_success_empty_response` | 成功時のレスポンスボディが空 |
| 92 | `test_reject_success_toast` | 成功時に `HX-Trigger` ヘッダーで「却下しました」トーストが発火 |
| 93 | `test_reject_error_reswap_none` | エラー時に `HX-Reswap: none` ヘッダーが付与される |
| 94 | `test_reject_no_body_required` | リクエストボディなしで PATCH → 正常に reject される |

## 9. 設計パターン準拠チェックリスト

本設計書が従う共通パターン（UO-01〜UO-03 で確立済み）の一覧。

| # | パターン | 適用箇所 | 準拠状況 |
|---|---------|---------|---------|
| 1 | Mixin 順序: `LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, {View/DetailView}` | 全 View | 準拠 |
| 2 | `active_sidebar = "imports"` をコンテキストに含める | 全 View | 準拠 |
| 3 | `login_url = "/o/login/"` を全 View に設定 | 全 View | 準拠 |
| 4 | Store スコープ: `objects.for_store(self.store)` で他店舗アクセス防止 | 全 View | 準拠 |
| 5 | トースト: セッション経由でメッセージを渡し、リダイレクト先で表示・消去 | CsvUploadView, MatchingExecuteView | 準拠 |
| 6 | HTMX エラー: 422 + `HX-Reswap: none` + `HX-Trigger: showToast` | MatchingConfirmView, MatchingRejectView | 準拠 |
| 7 | HTMX confirm/reject 成功: 空レスポンス + `hx-swap="outerHTML"` で行消去 | MatchingConfirmView, MatchingRejectView | 準拠 |
| 8 | PATCH body パース: `QueryDict(request.body)` | MatchingConfirmView | 準拠 |
| 9 | BusinessError 処理: catch してユーザー向けメッセージに変換 | 全 write View | 準拠 |
| 10 | 候補遅延ロード: Alpine.js 展開 + HTMX カスタムイベント | _matching_row.html | 準拠 |
| 11 | 候補 flat 化: C-06 のネスト構造を View で展開 | MatchingCandidatesView | 準拠 |

## Review Log

- [2026-03-31] 初版作成
- [2026-03-31] Codex レビュー 1回目 (gpt-5.4): FAIL。6 件を修正
  - F-01 (critical): `row_count=0` の completed 処理を追加。C-06 は全件重複スキップ時に `row_count=0, status='completed'` を返す。トースト「アップロード完了（0件: 全て重複スキップ）」を表示し、行一覧（空テーブル）にリダイレクト。postcondition と View コードを更新
  - F-02 (high): Slice 1 で「マッチング実行」ボタンを非表示に変更。`{% if matching_enabled %}` で制御し、Slice 1 では `matching_enabled=False`、Slice 2 で `True` に切り替え。存在しない URL へのフォーム送信を防止
  - F-03 (high): 行一覧ヘッダーに `csv_import.status` バッジ（完了/失敗）を追加。`csv_import.file_name` は既存だが、ステータスバッジが欠落していた
  - F-04 (high): `error_message` の JSON スキーマを定義。`[{group_id, receipt_no, lines, error}]` 構造を想定し、テンプレートの表示ロジックを合わせた。コア層との合意が必要な旨を注記
  - F-05 (medium): マッチング行表示に `customer_number` を追加。C-06 仕様で手動レビュー参考情報として `normalized_data.customer_number` を表示。View、テンプレート、CsvImportRow モデルフィールド表を更新
  - F-06 (medium): テストケース 8 件追加（#16a, #16b, #16c, #28 修正, #31a, #31b, #40a, #50a, #50b）。0件アップロード、失敗インポート履歴バッジ、Slice 1 ボタン非表示、ヘッダーバッジ、顧客番号表示を網羅
- [2026-04-01] Codex レビュー 2回目: 84/100 CONDITIONAL。3 件を修正
  - F-07 (high): Slice 2 で matching_enabled=True に変更する指示を明記
  - F-08 (medium): CsvImport.status の completed 定義を「0件以上正常処理済み」に修正
  - F-09 (medium): failed import にも「エラー詳細」リンクを追加。error_message を /rows/ で表示
- [2026-04-01] Codex レビュー 3回目: 88/100 CONDITIONAL。2 件を修正
  - F-10 (medium): /rows/ テンプレートの error_message 表示を csv_import.status で分岐。failed=「全件不正」、completed=「一部スキップ」
  - F-11 (medium): UI_BASIC_DESIGN.md の UO-04 postcondition を更新。completed=0件以上、failed の「エラー詳細」導線を追記
