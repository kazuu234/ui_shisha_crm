# UO-06 詳細設計書: QR コード画像表示 + メール送信

> 基本設計書: `docs/design/UI_BASIC_DESIGN.md` §6 UO-01（スタッフ管理の拡張）
> headless 設計書: `headless_shisha_crm/docs/design/cluster/C09_QR_IMAGE.md`
> デザインガイド: `docs/design/UI_DESIGN_GUIDE.md`

## 1. 概要

### 背景

MVP ではスタッフ詳細画面の QR セクションに URL テキストリンクのみを表示していた（「※ QR 画像生成は Phase 2」）。headless 側で C-09（QR コード画像生成）が完了し、`QRTokenIssueView` のレスポンスに `qr_image`（Base64 Data URI）が追加された。

本 Cluster では以下を実装する:
1. QR コード画像の表示（スタッフ詳細画面）
2. スタッフの email 入力機能（作成・編集）
3. QR コードのメール送信（email 入力済みスタッフのみ）
4. QR コードの印刷対応

### Cluster 情報

| 項目 | 内容 |
|------|------|
| **Cluster** | UO-06 (QR コード画像 + メール送信) |
| **Slice 数** | 2 本 |
| **依存先** | UO-01 S2 完了（スタッフ管理画面が動作）、headless C-09 完了（`qr_image` が API レスポンスに含まれる） |

---

## 2. headless 側との Interface

### 2.1 QR トークン発行 API レスポンス（C-09 で追加済み）

`POST /api/v1/staff/:id/qr-token/` のレスポンス:

```json
{
  "token_id": "uuid",
  "qr_url": "https://example.com/login#token=xxx",
  "qr_image": "data:image/png;base64,iVBORw0KGgoAAAANS...",
  "expires_at": "2026-04-06T10:00:00+09:00"
}
```

UI 側は `_issue_qr_token()` ヘルパーで `QRToken` オブジェクトを直接取得するため、API 経由ではなく **`accounts.qr_image.generate_qr_data_uri()`** を直接呼び出して画像を生成する。

### 2.2 generate_qr_data_uri

```python
# accounts/qr_image.py（headless 側、C-09 で実装済み）
def generate_qr_data_uri(url: str) -> str:
    """URL を QR コード PNG 画像にエンコードし、Base64 Data URI を返す。"""
```

- 入力: URL 文字列（例: `/s/login/#token=xxx`）
- 出力: `data:image/png;base64,...` 形式の Data URI
- 純粋関数（DB アクセスなし）

### 2.3 Staff.email

`Staff(AbstractUser)` から継承された Django 標準フィールド:
- `email = CharField(max_length=254, blank=True)`
- マイグレーション不要（既に DB カラムとして存在）
- headless 側の方針: **任意のまま変更なし**

---

## 3. コア層依存サービス

| サービス / ユーティリティ | メソッド | 用途 |
|---|---|---|
| `accounts.qr_image` | `generate_qr_data_uri(url)` | QR コード画像生成（Data URI） |
| `accounts.models.QRToken` | `generate_token()` / `objects.create()` | トークン発行（既存） |
| `accounts.models.Staff` | `.email` フィールド | メール送信先 |
| `django.core.mail` | `send_mail()` | メール送信 |

---

## 4. Django メール設定

headless 側の `config/settings/` にはメール設定が未定義。以下を追加する必要がある。

### 4.1 production.py への追加（headless 側への申し送り）

```python
# メール送信
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@example.com')
```

### 4.2 テスト / ローカル環境

テスト環境では Django デフォルトの `locmem` バックエンドを使用するため、追加設定不要。`django.core.mail.outbox` でテスト可能。

---

## 5. Slice 分割

### Slice 1: QR 画像表示 + email フィールド追加 + 印刷

| 項目 | 内容 |
|------|------|
| **ブランチ名** | `feat/<issue番号>-uo06-s1-qr-image-display` |
| **スコープ** | QR 画像表示、email フィールド追加（作成・編集）、印刷ボタン |
| **依存** | UO-01 S2、headless C-09 |

**precondition:**
- UO-01 S2 完了（スタッフ管理画面が動作）
- headless C-09 完了（`accounts.qr_image.generate_qr_data_uri()` が利用可能）
- `qrcode>=8.0`, `Pillow>=10.0` が headless 側の requirements.txt に追加済み

**postcondition:**

#### View 変更

- `StaffCreateView.post()`: `Staff.objects.create_user()` に `email=form.cleaned_data["email"]` を渡す
- `StaffDetailView.get()`: コンテキストに `qr_image` を追加する
  - `latest_qr` が存在する場合: `generate_qr_data_uri(qr_url)` を呼び出し、結果を `qr_image` としてテンプレートに渡す
  - `latest_qr` が存在しない場合: `qr_image = None`
- `StaffQRIssueView.post()`: 同様に `qr_image` をコンテキストに追加する
- 新規 `StaffEditView`（GET / POST）:
  - `GET /o/staff/<uuid:pk>/edit/`: 編集フォームを表示（`display_name`, `email`, `role`, `staff_type`）
  - `POST`: `staff.display_name`, `staff.email` を更新して `staff.save(update_fields=[...])` → staff-detail にリダイレクト
  - `role` と `staff_type` は表示のみ（編集不可）。変更するとトークン有効期限の整合性が崩れるため
  - Owner 以外はアクセス不可（`OwnerRequiredMixin`）

#### Form 変更

- `StaffCreateForm`: `email` フィールドを追加
  - `forms.EmailField(label="メールアドレス", required=False, max_length=254)`
  - `widget=forms.EmailInput(attrs={"placeholder": "example@example.com", ...})`
- 新規 `StaffEditForm`:
  - `display_name`: `CharField(max_length=100)`
  - `email`: `EmailField(required=False, max_length=254)`

#### Template 変更

- `_qr_section.html`:
  - 「※ QR 画像生成は Phase 2」の注記を削除
  - `{% if qr_image %}` で `<img src="{{ qr_image }}" alt="QR コード" class="w-48 h-48">` を表示
  - URL テキストリンクは画像の下に維持（コピー用途）
  - 「印刷」ボタンを追加: `onclick="window.print()"` で QR 画像を印刷
- `staff_detail.html`:
  - 基本情報セクションに「メールアドレス」行を追加（`staff.email` が空なら「未設定」）
  - 「編集」ボタンを追加（`staff-edit` へのリンク）
- 新規 `staff_edit.html`: スタッフ編集フォーム（display_name, email）
- 印刷用 CSS: `@media print` で QR セクション以外を非表示にするスタイル

#### URL 追加

- `path("staff/<uuid:pk>/edit/", StaffEditView.as_view(), name="staff-edit")`

#### テスト

- `StaffDetailView` が `qr_image` をコンテキストに含むこと
- `qr_image` が `data:image/png;base64,` で始まること
- `_qr_section.html` に `<img` タグが含まれること
- 「Phase 2」注記が消えていること
- `StaffCreateForm` に email フィールドがあること
- email 付きでスタッフ作成 → `staff.email` に保存されること
- email なしでスタッフ作成 → `staff.email == ""` で正常作成されること
- `StaffEditView` GET: 編集フォームが表示されること
- `StaffEditView` POST: display_name, email が更新されること
- `StaffEditView` POST: 不正な email → バリデーションエラー
- 印刷ボタンが表示されること

#### 対象ファイル

- `ui/owner/views/staff_mgmt.py` — StaffDetailView, StaffQRIssueView, StaffCreateView 変更 + StaffEditView 新規
- `ui/owner/forms/staff.py` — StaffCreateForm 変更 + StaffEditForm 新規
- `ui/owner/urls.py` — staff-edit URL 追加
- `ui/templates/ui/owner/_qr_section.html` — QR 画像表示 + 印刷ボタン
- `ui/templates/ui/owner/staff_detail.html` — email 表示 + 編集ボタン
- `ui/templates/ui/owner/staff_edit.html` — 新規
- `ui/templates/ui/owner/staff_create.html` — email フィールド追加
- `ui/static/ui/css/input.css` — `@media print` スタイル追加（必要に応じて）
- `ui/tests/test_owner_staff.py` — テスト追加

#### 完了条件

- スタッフ詳細画面に QR コード画像が表示される
- QR 再発行後も画像が更新される
- スタッフ作成時に email を入力できる
- スタッフ編集画面で display_name, email を変更できる
- 印刷ボタンで QR コード画像が印刷できる
- `pytest` 全テスト PASS

---

### Slice 2: QR コードメール送信

| 項目 | 内容 |
|------|------|
| **ブランチ名** | `feat/<issue番号>-uo06-s2-qr-email` |
| **スコープ** | QR コードのメール送信機能 |
| **依存** | UO-06 S1 完了（QR 画像表示 + email フィールドが動作） |

**precondition:**
- UO-06 S1 完了（QR 画像表示、StaffEditView、email フィールドが動作）
- Django メール設定が存在する（テスト環境では `locmem` で動作）

**postcondition:**

#### View 追加

- 新規 `StaffQREmailView`（POST のみ、HTMX）:
  - URL: `POST /o/staff/<uuid:pk>/qr-email/`
  - 処理:
    1. `staff.email` が空 → 400 エラーレスポンス（HTMX フラグメント）
    2. 最新の `QRToken` を取得（なければ新規発行）
    3. QR URL を構築 + `generate_qr_data_uri()` で画像生成
    4. `django.core.mail.EmailMessage` でメール送信:
       - 件名: `【シーシャ CRM】QR ログインコード`
       - 本文: テキスト（QR URL + 有効期限）
       - HTML 本文: QR 画像をインライン表示（`<img src="cid:qr-code">`）+ QR URL + 有効期限
       - QR 画像を PNG 添付（Content-ID: `qr-code`）
    5. 送信成功 → 成功メッセージの HTMX フラグメントを返す
    6. 送信失敗 → エラーメッセージの HTMX フラグメントを返す
  - `OwnerRequiredMixin` で保護
  - Store スコープチェック

#### Template 変更

- `_qr_section.html`:
  - メール送信ボタンを追加（`staff.email` が空の場合は `disabled`）
  - `hx-post="{% url 'owner:staff-qr-email' staff.pk %}"` で HTMX POST
  - `hx-target="#qr-email-status"` でステータスメッセージ表示
  - email 未設定時のツールチップ/メッセージ: 「メールアドレスが未設定です。スタッフ編集から設定してください」
- 新規 `_qr_email_status.html`: 送信結果フラグメント（成功 / 失敗メッセージ）

#### URL 追加

- `path("staff/<uuid:pk>/qr-email/", StaffQREmailView.as_view(), name="staff-qr-email")`

#### テスト

- email 入力済みスタッフ → メール送信成功（`django.core.mail.outbox` で検証）
- 送信されたメールの件名・宛先・本文を検証
- 送信されたメールに QR URL が含まれること
- email 未設定スタッフ → 400 エラーレスポンス
- QR トークンがない場合 → 新規発行してから送信
- HTMX レスポンス（成功メッセージ / エラーメッセージ）の検証
- email 未設定時の送信ボタン disabled 検証

#### 対象ファイル

- `ui/owner/views/staff_mgmt.py` — StaffQREmailView 新規
- `ui/owner/urls.py` — staff-qr-email URL 追加
- `ui/templates/ui/owner/_qr_section.html` — メール送信ボタン追加
- `ui/templates/ui/owner/_qr_email_status.html` — 新規（HTMX フラグメント）
- `ui/tests/test_owner_staff.py` — テスト追加

#### 完了条件

- email 入力済みスタッフの詳細画面で「QR をメール送信」ボタンが表示される
- ボタンクリックでメールが送信される（テスト環境では `outbox` で検証）
- email 未設定スタッフでは送信ボタンが非活性
- `pytest` 全テスト PASS

---

## 6. 画面遷移

```
スタッフ一覧 (/o/staff/)
  │
  ├── [新規作成] → スタッフ作成 (/o/staff/new/)
  │                   └── POST → スタッフ詳細にリダイレクト
  │
  └── [行クリック] → スタッフ詳細 (/o/staff/<pk>/)
                       │
                       ├── [編集] → スタッフ編集 (/o/staff/<pk>/edit/)  ★新規
                       │              └── POST → スタッフ詳細にリダイレクト
                       │
                       ├── [QR 再発行] → HTMX POST (/o/staff/<pk>/qr-issue/)
                       │                  └── _qr_section.html 更新（画像付き）
                       │
                       ├── [QR メール送信] → HTMX POST (/o/staff/<pk>/qr-email/)  ★新規
                       │                      └── _qr_email_status.html 表示
                       │
                       ├── [印刷] → window.print()  ★新規
                       │
                       └── [無効化] → POST (/o/staff/<pk>/deactivate/)
```

---

## 7. Gherkin シナリオ

```gherkin
Feature: QR コード画像表示

  Scenario: スタッフ詳細画面に QR コード画像が表示される
    Given オーナーとしてログインしている
    And QR トークンが発行済みのスタッフが存在する
    When スタッフ詳細画面を開く
    Then QR コード画像が表示される
    And QR URL がテキストリンクとして表示される
    And 有効期限が表示される
    And 「Phase 2」注記が表示されない

  Scenario: QR 再発行で画像が更新される
    Given スタッフ詳細画面を表示している
    When 「QR 再発行」ボタンをクリックする
    Then QR セクションが HTMX で更新される
    And 新しい QR コード画像が表示される

  Scenario: 印刷ボタンで QR コードを印刷
    Given スタッフ詳細画面を表示している
    When 「印刷」ボタンをクリックする
    Then ブラウザの印刷ダイアログが表示される

Feature: スタッフ email 管理

  Scenario: スタッフ作成時に email を入力
    Given オーナーとしてログインしている
    When スタッフ作成フォームで表示名と email を入力して送信する
    Then スタッフが作成され email が保存される

  Scenario: スタッフ作成時に email を省略
    Given オーナーとしてログインしている
    When スタッフ作成フォームで表示名のみ入力して送信する
    Then スタッフが作成され email は空で保存される

  Scenario: スタッフ編集で email を変更
    Given オーナーとしてログインしている
    And email 未設定のスタッフが存在する
    When スタッフ編集画面で email を入力して保存する
    Then スタッフの email が更新される

Feature: QR コードメール送信

  Scenario: email 入力済みスタッフに QR コードを送信
    Given オーナーとしてログインしている
    And email が設定されたスタッフのスタッフ詳細画面を表示している
    When 「QR をメール送信」ボタンをクリックする
    Then メールが送信される
    And 成功メッセージが表示される

  Scenario: email 未設定スタッフでは送信ボタンが非活性
    Given オーナーとしてログインしている
    And email が未設定のスタッフのスタッフ詳細画面を表示している
    Then 「QR をメール送信」ボタンが非活性で表示される
    And 「メールアドレスが未設定です」のメッセージが表示される
```

---

## 8. Closure Audit チェックリスト

- S1 → S2 の接合: `_qr_section.html` の `qr_image` / `staff.email` がメール送信 View で正しく利用されるか
- `generate_qr_data_uri` の import が UI View で正しく解決されるか（headless 側 `accounts.qr_image` への依存）
- email フィールドの保存/読み取りが `StaffCreateView` / `StaffEditView` / `StaffDetailView` で一貫しているか
- HTMX の `hx-target` が QR 再発行とメール送信で競合しないか（`#qr-section` vs `#qr-email-status`）
- メール送信失敗時に画面が壊れないか（HTMX フラグメントでエラー表示）
- 印刷スタイルが他画面に影響しないか（`@media print` のスコープ）

---

## Review Log

- [2026-04-05] 初版作成
