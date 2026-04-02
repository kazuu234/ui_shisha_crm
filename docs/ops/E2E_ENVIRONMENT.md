# UI E2E テスト環境準備手順書

> **前提**: headless 側のテストデプロイが完了していること（`headless_shisha_crm/docs/ops/TEST_DEPLOY.md` セクション 1〜5 を実施済み）
> **目的**: headless テスト環境の上に Playwright を追加し、UI E2E テスト（D-04: 3 クリティカルパス）を実行できる状態にする
> **日付**: 2026-04-02

---

## 1. 前提条件の確認

headless 側の `TEST_DEPLOY.md` セクション 5（デプロイ検証チェックリスト）が全 PASS であること。

```bash
# UI ログインページの疎通確認
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/s/login/
# 期待: 200

# Owner ログインページの疎通確認
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/o/login/
# 期待: 200

# 静的ファイル（Tailwind CSS）
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/static/ui/css/output.css
# 期待: 200
```

---

## 2. Playwright インストール

ui_shisha_crm リポジトリ側で作業する。

```bash
cd /var/share/yorusaro/src/ui_shisha_crm

# Node.js 依存（Tailwind 用に既にある場合は確認のみ）
node --version  # 18+ 必須

# Playwright インストール
npm init -y  # package.json がなければ作成
npm install -D @playwright/test

# ブラウザバイナリのインストール（Chromium のみで十分）
npx playwright install chromium
```

---

## 3. Playwright 設定

```bash
# playwright.config.ts を作成
```

設定のポイント:

| 項目 | 値 | 理由 |
|------|-----|------|
| `baseURL` | `http://localhost:8000` | headless 側の gunicorn/runserver |
| `testDir` | `./e2e` | UI リポジトリ内に配置 |
| `projects` | Chromium のみ | MVP では単一ブラウザで十分 |
| `retries` | 0 | flaky test を許容しない |
| `use.trace` | `on-first-retry` | デバッグ用トレース |
| `webServer` | 設定しない | テスト環境は手動起動済み前提 |

---

## 4. テストデータの準備

Playwright E2E はブラウザで実際の画面操作を行うため、DB にテストデータが必要。

### 4.1 基本データ（headless 側で投入済み）

`seed_store` コマンドで以下が存在:
- StoreGroup 1件
- Store 1件（Default Store）
- SegmentThreshold 3件（new/repeat/regular）

### 4.2 E2E 用追加データ

Playwright テスト実行前に、以下のデータを投入する。Django management command または fixture で実装。

```bash
# headless 側で実行
cd /var/share/yorusaro/src/headless_shisha_crm
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)

python manage.py shell -c "
from tenants.models import Store
from accounts.models import Staff, QRToken
from customers.models import Customer
from tasks.models import HearingTask
from tasks.services import HearingTaskService
from django.utils import timezone
from datetime import timedelta

store = Store.objects.first()

# Owner（E2E フロー 3 用）
owner, created = Staff.objects.get_or_create(
    store=store,
    display_name='E2E Owner',
    defaults={'staff_type': 'owner', 'role': 'owner', 'is_active': True},
)
if not created:
    owner.staff_type = 'owner'
    owner.role = 'owner'
    owner.is_active = True
    owner.save(update_fields=['staff_type', 'role', 'is_active'])

# Staff（E2E フロー 1, 2 用）
staff, created = Staff.objects.get_or_create(
    store=store,
    display_name='E2E Staff',
    defaults={'staff_type': 'regular', 'role': 'staff', 'is_active': True},
)
if not created:
    staff.staff_type = 'regular'
    staff.role = 'staff'
    staff.is_active = True
    staff.save(update_fields=['staff_type', 'role', 'is_active'])

# QR Token（ログインテスト用 — Flow 1 用と Flow 2 用の 2 つ）
staff_token_1 = QRToken.objects.create(
    staff=staff,
    token=QRToken.generate_token(),
    expires_at=timezone.now() + timedelta(hours=24),
)
staff_token_2 = QRToken.objects.create(
    staff=staff,
    token=QRToken.generate_token(),
    expires_at=timezone.now() + timedelta(hours=24),
)
owner_token = QRToken.objects.create(
    staff=owner,
    token=QRToken.generate_token(),
    expires_at=timezone.now() + timedelta(hours=24),
)

print(f'Staff token (Flow 1): {staff_token_1.token}')
print(f'Staff token (Flow 2): {staff_token_2.token}')
print(f'Owner token: {owner_token.token}')
print('Save these tokens in e2e/fixtures/test-data.ts (STAFF_TOKEN, STAFF_TOKEN_FLOW2, OWNER_TOKEN).')

# Customer（E2E フロー 2 用）— フィールドをリセットしタスクを再生成
# get_or_create だけでは HearingTask は付かないため generate_tasks が必要。
# 再実行時は age/area/shisha_experience が埋まっているとタスクゾーンが出ないためリセットする。
customer, created = Customer.objects.get_or_create(
    store=store,
    name='E2E Customer',
    defaults={
        'age': None,
        'area': None,
        'shisha_experience': None,
    },
)
if not created:
    customer.age = None
    customer.area = None
    customer.shisha_experience = None
    customer.save(update_fields=['age', 'area', 'shisha_experience'])

# 既存タスクを消してから Open タスクを生成（headless: HearingTaskService に reset_tasks は無い）
HearingTask.objects.filter(customer=customer).delete()
HearingTaskService.generate_tasks(customer, request=None)

print(f'Customer: {customer.pk} (hearing tasks regenerated)')
print('Set CUSTOMER_ID in test-data.ts to the Customer UUID printed above for flow2 link selection.')
"
```

### 4.3 テストデータの管理方針

| 方針 | 詳細 |
|------|------|
| **テストごとにリセットしない** | E2E は 3 フローのみ。フロー間の副作用は許容する（フロー 2 で作成した来店記録がフロー 3 のダッシュボードに表示される） |
| **全リセットが必要な場合** | `python manage.py flush --noinput && python manage.py seed_store` + 上記データ再投入 |
| **Token の有効期限** | 24 時間。テスト実行のたびに再発行が必要な場合がある |

---

## 5. ディレクトリ構造

```
ui_shisha_crm/
  e2e/                         # Playwright テストディレクトリ
    flows/
      flow1-staff-login.spec.ts      # フロー 1: スタッフ QR ログイン
      flow2-staff-session.spec.ts    # フロー 2: 顧客検索→接客→タスク消化→来店記録
      flow3-owner-dashboard.spec.ts  # フロー 3: オーナーログイン→ダッシュボード
    fixtures/
      test-data.ts             # テストデータ（token, customer ID 等）
    helpers/
      auth.ts                  # ログインヘルパー
  playwright.config.ts
  package.json
```

---

## 6. D-04 の 3 フローと URL マッピング

### フロー 1: スタッフ QR ログイン → セッション確立

| ステップ | URL | 操作 | 検証 |
|---------|-----|------|------|
| 1 | `/s/login/` | ページ表示 | ログインフォームが表示される |
| 2 | `/s/login/#token={token}` | QR リンク経由アクセス | JS が hash から token を読み取り自動 POST |
| 3 | `/s/customers/` | リダイレクト先 | 顧客選択画面が表示される。`history.replaceState` で hash が除去されている |
| 4 | ブラウザの戻る | 戻る操作 | token が再送されない |

**TestClient では検証不可な理由**: `location.hash` の読み取り、`history.replaceState`、JS の自動 POST はサーバーサイドテストでは再現できない。

### フロー 2: 顧客検索 → 選択 → 接客画面 → タスク消化 → 来店記録作成

| ステップ | URL | 操作 | 検証 |
|---------|-----|------|------|
| 1 | `/s/customers/` | 検索バーに顧客名入力 | HTMX で検索結果が部分更新される |
| 2 | `/s/customers/search/?q=E2E` | HTMX レスポンス | 顧客カードが表示される |
| 3 | `/s/customers/{id}/session/` | 顧客カードをクリック | 接客画面に遷移。タスクゾーンが表示される |
| 4 | 接客画面内 | タスクの「回答」ボタンをクリック | ゾーンが編集モードに展開（Alpine.js） |
| 5 | 接客画面内 | フィールド入力 → 保存 | HTMX でゾーン更新。タスクが消化される |
| 6 | `/s/visits/create/` | 「来店記録を作成」ボタン | 来店記録作成 → トースト表示 |

**TestClient では検証不可な理由**: HTMX パーシャル更新の DOM 反映、Alpine.js の状態遷移（ゾーン展開/折りたたみ）、トースト表示。

### フロー 3: オーナーログイン → ダッシュボード表示

| ステップ | URL | 操作 | 検証 |
|---------|-----|------|------|
| 1 | `/o/login/#token={token}` | QR リンク経由アクセス | 自動ログイン |
| 2 | `/o/dashboard/` | リダイレクト先 | ダッシュボード画面が表示される |
| 3 | ダッシュボード | 画面描画完了を待つ | Chart.js の 3 チャートが描画される（canvas 要素が存在） |
| 4 | ダッシュボード | 期間フィルタを変更 | HTMX でチャート領域が更新される |

**TestClient では検証不可な理由**: Chart.js のキャンバス描画、HTMX による期間フィルタ切り替えの部分更新。

---

## 7. テスト実行

```bash
cd /var/share/yorusaro/src/ui_shisha_crm

# 全 E2E テスト実行
npx playwright test

# 特定フロー
npx playwright test e2e/flows/flow1-staff-login.spec.ts

# headed モード（ブラウザを表示して実行）
npx playwright test --headed

# デバッグモード
npx playwright test --debug

# テストレポート表示
npx playwright show-report
```

---

## 8. CI 統合（将来）

MVP では手動実行。将来的に GitHub Actions に組み込む場合の考慮事項:

- headless サーバーの起動を `webServer` 設定で自動化
- テストデータの投入を fixture script で自動化
- Chromium のキャッシュを GitHub Actions のキャッシュ機能で保持

---

## 9. トラブルシューティング

| 症状 | 原因 | 対処 |
|------|------|------|
| `browserType.launch: Executable doesn't exist` | Chromium 未インストール | `npx playwright install chromium` |
| ログイン画面でリダイレクトループ | CSRF cookie の Secure=True | staging.py で `CSRF_COOKIE_SECURE = False` を確認 |
| QR リンクでログインできない | Token 期限切れ | Token を再発行（セクション 4.2） |
| HTMX の部分更新が反映されない | 静的ファイルが古い | Tailwind CSS を再ビルド（`TEST_DEPLOY.md` セクション 3.4） |
| `page.goto: net::ERR_CONNECTION_REFUSED` | サーバー未起動 | `TEST_DEPLOY.md` セクション 4 でサーバーを起動 |
| Chart.js が描画されない | JS が読み込まれていない | `collectstatic` を再実行 |

---

## Review Log

- [2026-04-02] 初版作成
- [2026-04-02] Issue #30 R12: E2E Customer のヒアリングフィールドリセット + `HearingTask` 削除後 `HearingTaskService.generate_tasks`（headless `tasks.services`）。Flow 2 の検索結果クリックを `CUSTOMER_ID` 指定に合わせて手順書に追記。
