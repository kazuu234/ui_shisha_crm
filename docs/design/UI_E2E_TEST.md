# UI E2E テスト設計書

> **起源**: 基本設計書 D-04（E2E テスト範囲 → 主要フロー + ログインのみ）
> **前提**: Headless E2E 結合テスト PASS 済み（F-01〜F-08, 46/46 PASS）
> **環境**: `docs/ops/E2E_ENVIRONMENT.md` に従って構築済みであること
> **日付**: 2026-04-02

---

## 1. 方針

### テストの性格

Django TestClient では検証できない **ブラウザ固有の振る舞い** を Playwright で検証する。

| Django TestClient でカバー済み | Playwright で検証（本設計） |
|---|---|
| View の HTTP レスポンス（200, 302, 403, 422） | `location.hash` の読み取り + `history.replaceState` |
| テンプレートの描画内容 | HTMX パーシャル更新の DOM 反映 |
| 権限ガード（リダイレクト/403） | Alpine.js の状態遷移（ゾーン展開/折りたたみ） |
| フォームバリデーション | トースト表示・自動消去 |
| - | Chart.js のキャンバス描画 |

### スコープ

D-04 で定義された **3 クリティカルパス** のみ。「壊れると CRM が使えなくなるパス」に絞る。

| フロー | パス |
|--------|------|
| Flow 1 | スタッフ QR ログイン → セッション確立 |
| Flow 2 | 顧客検索 → 選択 → 接客画面 → タスク消化 → 来店記録作成 |
| Flow 3 | オーナーログイン → ダッシュボード表示 |

### スコープ外

- 全画面の網羅的テスト（TestClient の領域）
- エラー系の E2E テスト（BusinessError ハンドリングは TestClient でカバー済み）
- 複数ブラウザ対応テスト（MVP 外）
- ビジュアルリグレッション（Phase 2 で検討）
- Owner 管理画面の CRUD 操作（TestClient + smoke test でカバー済み）

### ツールチェーン

| ツール | バージョン | 用途 |
|--------|-----------|------|
| Playwright | latest | ブラウザ自動操作 |
| Chromium | Playwright bundled | テスト対象ブラウザ（単一） |
| Django LiveServer | - | 使用しない。テスト環境は手動起動前提 |

---

## 2. テストデータの前提

`docs/ops/E2E_ENVIRONMENT.md` セクション 4 に従い、以下が投入済みであること。

| データ | 内容 | 投入方法 |
|--------|------|---------|
| Store | Default Store | `seed_store` |
| SegmentThreshold | new/repeat/regular の 3 件 | `seed_store` |
| Staff（スタッフ） | E2E Staff (role=staff) | Django shell |
| Staff（オーナー） | E2E Owner (role=owner) | Django shell |
| QRToken（スタッフ用） | 有効期限 24h | Django shell |
| QRToken（オーナー用） | 有効期限 24h | Django shell |
| Customer | E2E Customer (age=None, area=None, shisha_experience=None) | Django shell |

**テストデータの受け渡し**: QRToken の `token` 値と Customer の `pk` は、投入スクリプトの出力を `e2e/fixtures/test-data.ts` に記録する。Playwright テストはこのファイルから読み込む。

---

## 3. ディレクトリ構造

```
ui_shisha_crm/
  e2e/
    flows/
      flow1-staff-login.spec.ts       # Flow 1: QR ログイン
      flow2-staff-session.spec.ts     # Flow 2: 接客フロー
      flow3-owner-dashboard.spec.ts   # Flow 3: ダッシュボード
    fixtures/
      test-data.ts                    # テストデータ定数
    helpers/
      auth.ts                         # ログインヘルパー
  playwright.config.ts
```

---

## 4. テストシナリオ詳細

### Flow 1: スタッフ QR ログイン → セッション確立

**目的**: QR リンク経由の自動ログインが正しく動作し、セッションが確立されること。

**検証する「TestClient では不可能な」振る舞い**:
- `location.hash` からの token 読み取り（`qr-auto-login.js`）
- `history.replaceState` による hash 除去
- JS による form 自動 submit

#### テストケース

| # | テスト名 | 手順 | 検証（assertion） |
|---|---------|------|-------------------|
| 1 | `test_qr_link_auto_login` | `/s/login/#token={staff_token}` にアクセス | (a) `/s/customers/` にリダイレクトされる (b) URL に `#token=` が残っていない (c) 顧客選択画面のコンテンツが表示される |
| 2 | `test_hash_removed_after_login` | Flow 1-1 の後、現在の URL を取得 | `location.hash` が空である |
| 3 | `test_back_button_no_resubmit` | Flow 1-1 の後、ブラウザの「戻る」を実行 | (a) token が再送されない（ログインフォームに戻るか、既にログイン済みで `/s/customers/` にリダイレクト） (b) エラーメッセージ「既に使用されています」が表示されない |
| 4 | `test_session_persists` | Flow 1-1 の後、`/s/customers/` に直接アクセス | ログインページにリダイレクトされない（セッション維持） |
| 5 | `test_unauthenticated_redirect` | ログインしていない状態で `/s/customers/` にアクセス | `/s/login/` にリダイレクトされる |

#### 実装イメージ

```typescript
// flow1-staff-login.spec.ts

import { test, expect } from '@playwright/test';
import { STAFF_TOKEN } from '../fixtures/test-data';

test('QR link auto login', async ({ page }) => {
  await page.goto(`/s/login/#token=${STAFF_TOKEN}`);

  // 自動 POST → リダイレクト → 顧客選択画面
  await page.waitForURL('/s/customers/');
  await expect(page).toHaveURL('/s/customers/');

  // hash が除去されている
  const url = page.url();
  expect(url).not.toContain('#token=');

  // 顧客選択画面のコンテンツ
  await expect(page.locator('input[name="q"]')).toBeVisible();
});

test('back button does not resubmit token', async ({ page }) => {
  await page.goto(`/s/login/#token=${STAFF_TOKEN}`);
  await page.waitForURL('/s/customers/');

  await page.goBack();

  // ログイン済みなので /s/customers/ にリダイレクトされるか、
  // ログインページが表示されるが「既に使用」エラーは出ない
  const errorText = page.locator('text=既に使用されています');
  await expect(errorText).not.toBeVisible();
});
```

### Flow 2: 顧客検索 → 選択 → 接客画面 → タスク消化 → 来店記録作成

**目的**: スタッフの主要業務フロー全体が一気通貫で動作すること。

**前提**: Flow 1 でログイン済み（`helpers/auth.ts` のログインヘルパーを使用）。

**検証する「TestClient では不可能な」振る舞い**:
- HTMX 検索（`hx-get` による部分更新）
- 接客画面のタスクゾーン展開/折りたたみ（Alpine.js `x-show`）
- フィールド更新の HTMX 送信 → ゾーン再描画
- 来店記録作成の HTMX POST → トースト表示（`showToast` イベント）
- 来店記録作成後の recent visits 更新（`visitCreated` イベントによる HTMX リフレッシュ）

#### テストケース

| # | テスト名 | 手順 | 検証（assertion） |
|---|---------|------|-------------------|
| 1 | `test_customer_search_htmx` | `/s/customers/` で検索バーに「E2E」入力 | HTMX で検索結果が部分更新される。「E2E Customer」のカードが表示される |
| 2 | `test_navigate_to_session` | 顧客カードをクリック | `/s/customers/{id}/session/` に遷移。接客画面が表示される |
| 3 | `test_task_zone_visible` | 接客画面表示 | タスクゾーンに未消化タスクが表示される（age, area, shisha_experience の 3 件） |
| 4 | `test_task_zone_expand` | タスクの「回答する」ボタンをクリック | Alpine.js でゾーンが展開モードに切り替わる。入力フォームが表示される |
| 5 | `test_task_field_update` | age ゾーンで「20代」を選択 → 保存 | (a) HTMX でゾーンが再描画される (b) 保存された値が表示される (c) age タスクが消化される（タスク数が 2 に減る） |
| 6 | `test_visit_create_with_toast` | 「来店記録を作成」ボタンをクリック | (a) HTMX POST 成功 (b) トースト「来店記録を作成しました」が表示される (c) トーストが一定時間後に消える |
| 7 | `test_recent_visits_updated` | Flow 2-6 の後 | 接客画面の「最近の来店」セクションに今日の来店記録が表示される |

#### 実装イメージ

```typescript
// flow2-staff-session.spec.ts

import { test, expect } from '@playwright/test';
import { staffLogin } from '../helpers/auth';
import { CUSTOMER_NAME, CUSTOMER_ID } from '../fixtures/test-data';

test.beforeEach(async ({ page }) => {
  await staffLogin(page);
});

test('customer search via HTMX', async ({ page }) => {
  const searchInput = page.locator('input[name="q"]');
  await searchInput.fill('E2E');

  // HTMX debounce 後に検索結果が部分更新される
  await expect(page.locator(`text=${CUSTOMER_NAME}`)).toBeVisible({ timeout: 3000 });
});

test('task zone expand and field update', async ({ page }) => {
  await page.goto(`/s/customers/${CUSTOMER_ID}/session/`);

  // タスクゾーンが表示される
  const taskZone = page.locator('[data-field="age"]');
  await expect(taskZone).toBeVisible();

  // 「回答する」をクリック → ゾーン展開
  await taskZone.locator('button:has-text("回答")').click();

  // 入力フォームが表示される（Alpine.js 状態遷移）
  const select = taskZone.locator('select, input');
  await expect(select).toBeVisible();

  // 値を選択して保存
  await select.first().selectOption({ label: '20代' });
  await taskZone.locator('button:has-text("保存")').click();

  // HTMX でゾーンが再描画される
  await expect(taskZone.locator('text=20代')).toBeVisible({ timeout: 3000 });
});

test('visit create shows toast', async ({ page }) => {
  await page.goto(`/s/customers/${CUSTOMER_ID}/session/`);

  await page.locator('button:has-text("来店記録を作成")').click();

  // トースト表示
  const toast = page.locator('[role="alert"], .toast');
  await expect(toast).toContainText('来店記録を作成しました', { timeout: 3000 });
});
```

### Flow 3: オーナーログイン → ダッシュボード表示

**目的**: オーナーの QR ログインとダッシュボード画面の初期表示が動作すること。

**前提**: Flow 2 で来店記録が作成済み（ダッシュボードにデータが表示される）。

**検証する「TestClient では不可能な」振る舞い**:
- Owner 用 QR リンク経由の自動ログイン（`qr-auto-login.js` の Owner 版）
- Chart.js キャンバスの描画（`<canvas>` 要素の存在 + 描画完了）
- 期間フィルタの HTMX 切り替え（`hx-get` による部分更新）

#### テストケース

| # | テスト名 | 手順 | 検証（assertion） |
|---|---------|------|-------------------|
| 1 | `test_owner_qr_login` | `/o/login/#token={owner_token}` にアクセス | (a) `/o/dashboard/` にリダイレクトされる (b) URL に `#token=` が残っていない |
| 2 | `test_dashboard_charts_rendered` | ダッシュボード画面表示 | (a) 3 つの `<canvas>` 要素が存在する (b) 各 canvas に幅と高さがある（描画済み） |
| 3 | `test_dashboard_kpi_cards` | ダッシュボード画面表示 | KPI カード（今月の来客数、新規率等）が表示される |
| 4 | `test_period_filter_htmx` | 期間フィルタを「7日」から「30日」に変更 | HTMX でチャート領域が再描画される。canvas 要素が更新される |
| 5 | `test_sidebar_navigation` | Sidebar の「顧客管理」をクリック | `/o/customers/` に遷移する |

#### 実装イメージ

```typescript
// flow3-owner-dashboard.spec.ts

import { test, expect } from '@playwright/test';
import { OWNER_TOKEN } from '../fixtures/test-data';

test('owner QR login to dashboard', async ({ page }) => {
  await page.goto(`/o/login/#token=${OWNER_TOKEN}`);

  await page.waitForURL('/o/dashboard/');
  await expect(page).toHaveURL('/o/dashboard/');

  const url = page.url();
  expect(url).not.toContain('#token=');
});

test('dashboard charts are rendered', async ({ page }) => {
  await page.goto(`/o/login/#token=${OWNER_TOKEN}`);
  await page.waitForURL('/o/dashboard/');

  // 3 つの canvas 要素が存在する
  const canvases = page.locator('canvas');
  await expect(canvases).toHaveCount(3);

  // 各 canvas が描画済み（幅 > 0）
  for (let i = 0; i < 3; i++) {
    const canvas = canvases.nth(i);
    const box = await canvas.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeGreaterThan(0);
    expect(box!.height).toBeGreaterThan(0);
  }
});

test('period filter updates charts via HTMX', async ({ page }) => {
  await page.goto(`/o/login/#token=${OWNER_TOKEN}`);
  await page.waitForURL('/o/dashboard/');

  // 期間フィルタを変更
  const filter = page.locator('select[name="period"], [data-period]');
  await filter.first().click();
  // 30日を選択（実装に応じて調整）

  // HTMX で部分更新 → canvas が再描画される
  await page.waitForResponse(resp => resp.url().includes('/o/dashboard/'));
  const canvases = page.locator('canvas');
  await expect(canvases).toHaveCount(3);
});
```

---

## 5. ログインヘルパー

Flow 2 以降ではログイン済み状態が前提。`helpers/auth.ts` でヘルパーを提供する。

```typescript
// e2e/helpers/auth.ts

import { Page } from '@playwright/test';
import { STAFF_TOKEN, OWNER_TOKEN } from '../fixtures/test-data';

export async function staffLogin(page: Page): Promise<void> {
  await page.goto(`/s/login/#token=${STAFF_TOKEN}`);
  await page.waitForURL('/s/customers/');
}

export async function ownerLogin(page: Page): Promise<void> {
  await page.goto(`/o/login/#token=${OWNER_TOKEN}`);
  await page.waitForURL('/o/dashboard/');
}
```

**注意**: QR Token は一度使うと無効化される。テスト間で同じ token を使い回せない。テスト実行前にフロー数分の token を発行するか、テストの `beforeAll` で API 経由で token を発行する仕組みが必要。

### Token 管理戦略

| 戦略 | 採用 | 理由 |
|------|------|------|
| A: テスト前に一括発行 | **採用** | シンプル。3 フロー分 + 予備で 5 個程度を事前発行 |
| B: `beforeAll` で Django shell 経由発行 | 不採用 | Playwright から Django shell を呼ぶのは複雑 |
| C: API 経由で発行 | 不採用 | token 発行 API は外部公開されていない |

テスト実行手順:
1. Django shell で token を必要数（5個）発行
2. `e2e/fixtures/test-data.ts` に記録
3. `npx playwright test` 実行

---

## 6. Playwright 設定

```typescript
// playwright.config.ts

import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,  // フロー間に副作用あり（Flow 2 の来店記録が Flow 3 に影響）
  retries: 0,            // flaky test を許容しない
  workers: 1,            // 直列実行
  reporter: 'html',

  use: {
    baseURL: 'http://localhost:8000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
});
```

**`fullyParallel: false` + `workers: 1`** の理由:
- Flow 2 で作成した来店記録が Flow 3 のダッシュボードに表示される
- Token は使い捨てのため、並列実行すると競合する
- 3 フローのみなので直列でも実行時間は問題ない

---

## 7. Cluster / Slice 定義

### Cluster: UI E2E テスト

**Slice 1 本。理由**: テストコードのみの新規追加。プロダクションコードの変更なし。3 フロー間に依存関係があるが、全て 1 つの Slice で実装する。

| 項目 | 内容 |
|------|------|
| **ブランチ名** | `feat/<issue番号>-ui-e2e-tests` |
| **スコープ** | Playwright テスト + 設定ファイルの新規追加のみ |
| **依存** | 全 13 Slice merge 済み + Issue #27 fix 済み + headless E2E PASS |
| **対象ファイル（新規作成）** | `playwright.config.ts`, `e2e/flows/*.spec.ts`, `e2e/fixtures/test-data.ts`, `e2e/helpers/auth.ts` |
| **対象ファイル（変更）** | `package.json`（Playwright 依存追加） |
| **プロダクションコード変更** | なし |

### 完了条件

1. `npx playwright test` が全テスト PASS
2. Flow 1: QR リンク自動ログイン + hash 除去 + 戻るボタン安全性
3. Flow 2: 顧客検索（HTMX）→ 接客画面遷移 → タスクゾーン展開（Alpine.js）→ フィールド更新（HTMX）→ 来店記録作成 + トースト表示
4. Flow 3: オーナー QR ログイン → ダッシュボード表示 → Chart.js 描画確認 → 期間フィルタ切り替え（HTMX）
5. 既存の Django テストに影響がないこと（`pytest ui/tests/` が引き続き PASS）

### テストトレース表

| D-04 定義 | Flow | テストファイル | テスト名 |
|-----------|------|--------------|---------|
| (1) スタッフ QR ログイン → セッション確立 | Flow 1 | `flow1-staff-login.spec.ts` | `test_qr_link_auto_login`, `test_hash_removed_after_login`, `test_back_button_no_resubmit`, `test_session_persists`, `test_unauthenticated_redirect` |
| (2) 顧客検索 → 選択 → 接客 → タスク消化 → 来店記録 | Flow 2 | `flow2-staff-session.spec.ts` | `test_customer_search_htmx`, `test_navigate_to_session`, `test_task_zone_visible`, `test_task_zone_expand`, `test_task_field_update`, `test_visit_create_with_toast`, `test_recent_visits_updated` |
| (3) オーナーログイン → ダッシュボード表示 | Flow 3 | `flow3-owner-dashboard.spec.ts` | `test_owner_qr_login`, `test_dashboard_charts_rendered`, `test_dashboard_kpi_cards`, `test_period_filter_htmx`, `test_sidebar_navigation` |

**合計: 17 テストケース**（Flow 1: 5, Flow 2: 7, Flow 3: 5）

---

## 8. 注意事項

### HTMX の待機

HTMX リクエストは非同期。Playwright の assertion には `timeout` を指定して、HTMX レスポンスの反映を待つ。

```typescript
// NG: 即座に assertion → HTMX 反映前で失敗
await expect(page.locator('text=E2E Customer')).toBeVisible();

// OK: timeout で待機
await expect(page.locator('text=E2E Customer')).toBeVisible({ timeout: 3000 });
```

### Alpine.js の状態遷移

Alpine.js の `x-show` / `x-if` は DOM 上に要素が存在するが非表示の場合がある。`toBeVisible()` で表示状態を確認する。

### Token の使い捨て

QR Token は認証成功で `is_used=True` に更新され、再利用不可。各テストで新しい token が必要。テスト実行前に十分な数の token を発行しておくこと。

### テスト実行順序

`playwright.config.ts` で `fullyParallel: false` + `workers: 1` に設定済み。テストファイル名のプレフィックス（`flow1-`, `flow2-`, `flow3-`）でアルファベット順に実行される。

---

## Review Log

- [2026-04-02] 初版作成 — D-04 の 3 クリティカルパスを 17 テストケースに展開
