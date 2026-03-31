# UI パイプライン定義書

> 基本設計書: `docs/design/UI_BASIC_DESIGN.md` (PASS 100/100)
> 本書は 13 Slice + E2E テストの実行順序・Issue 変換ルール・Closure Audit スケジュールを定義する。
> orchestrator はこの定義に従ってパイプラインを回す。
>
> **本書の status**: 本書自体は orchestrator に渡せる状態。ただしパイプライン実行には各 Slice の Readiness Gate（§5: 詳細設計書が存在し Codex レビュー PASS 済み）を満たす必要がある。詳細設計書（`UI_CLUSTER_*.md`）は Slice 着手の 1 サイクル前に作成する運用であり、全件事前作成は不要。

## 1. 実行方針

### 直列実行

全 Slice を **直列（1 本ずつ順番に）** 実行する。並列実行しない。

**理由**: UI app は単一の Django app (`ui`) として実装される。複数 Slice を並列に進めると migration ファイルの生成順序が競合し、手動での merge が必要になる。直列なら migration 競合ゼロ、デバッグも 1 本に集中できる。

**基本設計書との関係**: `UI_BASIC_DESIGN.md` §8 は並列実行可能な Slice を識別しているが、本書では migration 競合回避のため全 Slice を直列実行とする。Slice 総数（13 + 後続 E2E）および実行順序は本書が優先する。

### パイプライン 1 サイクル

各 Slice について orchestrator が以下のサイクルを 1 回ずつ回す。各ステップは `CLAUDE.md` のワークフロー定義に準拠する。

```
1. 詳細設計書の確認
   - 該当 Slice の詳細設計書が存在し、Codex レビュー PASS 済みであることを確認

2. Issue 作成
   - §4 の Issue テンプレートに従って作成（Slice 着手の直前に 1 件ずつ）

3. branch 作成
   - scripts/start-feature.sh --branch <ブランチ名> --title "<PR タイトル>"

4. Cursor dispatch
   - 指示書を /tmp/instruction.md に作成（詳細設計書の該当 Slice セクション + postcondition）
   - 指示書末尾に Pre-flight Checklist 指示を必ず付与:
     「実装完了後、docs/framework/CURSOR_PREFLIGHT_CHECKLIST.md を読み、
      全項目をセルフチェックすること。違反があれば修正してからコミットすること。」
   - scripts/dispatch-cursor.sh --prompt-file /tmp/instruction.md

5. verify
   - scripts/verify.sh

6. Codex review（Stage 1: Reviewer の責務）
   - REVIEW=$(scripts/request-review.sh)  ← Scorecard 全文を自動埋め込み
   - $REVIEW を mcp__codex__codex に渡す
   - 100/100 のみ PASS。99 点以下は全て FAIL → pushback → 再 dispatch
   - reviewer が runtime 確認できない項目は「要 smoke test」としてマークされる

7. smoke test（Stage 2: orchestrator の責務）
   - Codex review が PASS (100/100) を出した後、orchestrator が「要 smoke test」項目を実行する
   - HTMX 遷移、認証フロー、トースト表示など runtime でのみ確認可能な項目が対象
   - smoke test FAIL → pushback（runtime で発見した問題を指示）→ 再 dispatch
   - smoke test PASS → merge に進む

8. merge
   - scripts/close-feature.sh --reviewer "gpt-5.4 high" --score 100
   - score=100 未満は自動拒否される
   - **merge 条件: Codex review PASS (100/100) + smoke test PASS の両方が必要**
```

FAIL 時は `CLAUDE.md` §5b に従い、PR コメントに findings を投稿して再 dispatch する。3 回 FAIL で escalation。

### Smoke Test 運用ルール

Codex review が PASS (100/100) を出した際、「要 smoke test」としてマークされた項目を orchestrator が runtime で検証する。

**記録場所**: PR コメントに以下のフォーマットで記録する。

```markdown
## Smoke Test Results

| # | 対象 URL | 手順 | 期待結果 | 結果 | 備考 |
|---|---------|------|---------|------|------|
| 1 | /s/login/ | QR コードでログイン | BottomTab 付きホーム画面に遷移 | PASS/FAIL | |
```

**項目 0 件の場合**: Codex review が「要 smoke test」項目をマークしなかった場合、Stage 2 は N/A（= PASS 扱い）とし、そのまま merge に進む。PR コメントに「Smoke test: 該当項目なし — N/A」と記録する。

## 2. 実行順序

### 順序表（13 Slice）

**ブランチ命名規則**: `feat/<issue番号>-<短い説明>`。CLAUDE.md の Git ルールに準拠する。以下の表の「ブランチ説明部」は Issue 番号を除いた部分を示す。実際のブランチ名は Issue 作成後に `feat/<issue番号>-<ブランチ説明部>` として生成する。

| # | Slice ID | Slice 名 | ブランチ説明部 | コア層 precondition | UI precondition | 詳細設計書 |
|---|----------|----------|--------------|-------------------|----------------|-----------|
| 1 | US-01 S1 | Staff Login + base | `us01-staff-login` | C-02 完了 + Django プロジェクトに UI app 組み込み可能 | なし（最初の Slice） | `UI_CLUSTER_US01.md` |
| 2 | UO-01 S1 | Owner Login + base_owner | `uo01-s1-owner-login` | C-02 完了 | US-01 S1 完了（base.html, LoginRequiredMixin 存在） | `UI_CLUSTER_UO01.md` |
| 3 | US-02 S1 | 顧客選択 + 新規登録 | `us02-s1-customer-select` | C-03, C-05a 完了 | US-01 S1 完了 | `UI_CLUSTER_US02.md` |
| 4 | US-02 S2 | 接客画面 | `us02-s2-session` | C-04 S2, C-05a, C-05b 完了 | US-02 S1 完了 | `UI_CLUSTER_US02.md` |
| 5 | US-03 S1 | 顧客・来店簡易管理 | `us03-customer-detail` | C-03, C-04 S2, C-05a 完了 | US-01 S1 完了 | `UI_CLUSTER_US03.md` |
| 6 | US-04 S1 | 会計後マッチング | `us04-matching` | C-06 全 Slice 完了 | US-01 S1 完了 | `UI_CLUSTER_US04.md` |
| 7 | UO-01 S2 | スタッフ管理 | `uo01-s2-staff-mgmt` | C-02 完了 | UO-01 S1 完了 | `UI_CLUSTER_UO01.md` |
| 8 | UO-02 S1 | 顧客管理 | `uo02-customer-mgmt` | C-03, C-05a, C-05b 完了 | UO-01 S1 完了 | `UI_CLUSTER_UO02.md` |
| 9 | UO-03 S1 | 来店管理 | `uo03-s1-visit-mgmt` | C-04 S2 完了 | UO-01 S1 完了 | `UI_CLUSTER_UO03.md` |
| 10 | UO-03 S2 | セグメント設定 | `uo03-s2-segment-settings` | C-04 全 Slice 完了 | UO-01 S1 完了（基本設計書の precondition 通り。直列実行のため UO-03 S1 も完了済み） | `UI_CLUSTER_UO03.md` |
| 11 | UO-04 S1 | CSV アップロード | `uo04-s1-csv-upload` | C-06 S1 完了 | UO-01 S1 完了 | `UI_CLUSTER_UO04.md` |
| 12 | UO-04 S2 | マッチング管理 | `uo04-s2-matching-mgmt` | C-06 S2 完了（MatchingService 動作） | UO-04 S1 完了 | `UI_CLUSTER_UO04.md` |
| 13 | UO-05 S1 | 分析ダッシュボード | `uo05-dashboard` | C-07 完了 | UO-01 S1 完了 | `UI_CLUSTER_UO05.md` |

**合計: 13 Slice**（Staff 5 + Owner 8）

### 後続タスク: E2E テスト

E2E テストは基本設計書の Slice 定義には含まれない後続タスクである。全 13 Slice 完了後に実施する。

| タスク | ブランチ名 | precondition | 詳細設計書 |
|-------|-----------|-------------|-----------|
| Playwright E2E テスト（3 フロー） | `feat/<issue番号>-ui-e2e-tests` | 全 13 Slice + 全コア層完了 | 別途定義（E2E テスト設計書） |

E2E の 3 フローは基本設計書 D-04 で定義:
1. スタッフ QR ログイン → セッション確立
2. 顧客検索 → 選択 → 接客画面 → タスク消化 → 来店記録作成
3. オーナーログイン → ダッシュボード表示

### 順序の根拠

```
Phase 1: 基盤 ─────────────────────────────
  #1  US-01 S1  base.html + base_staff.html を作成。全 UI の土台
  #2  UO-01 S1  base_owner.html を作成。Owner 側の土台

Phase 2: スタッフ業務コア ─────────────────
  #3  US-02 S1  顧客選択。スタッフの業務入口
  #4  US-02 S2  接客画面。スタッフ業務の核心（タスク消化 + 来店記録）

Phase 3: スタッフ補助 + 統合 ──────────────
  #5  US-03 S1  顧客詳細・編集・来店履歴。補助画面
  #6  US-04 S1  会計後マッチング。C-06 依存の統合機能

  → Staff UI 完了。Staff Closure Audit 実施

Phase 4: オーナー管理 ─────────────────────
  #7  UO-01 S2  スタッフ管理
  #8  UO-02 S1  顧客管理
  #9  UO-03 S1  来店管理
  #10 UO-03 S2  セグメント設定（UO-03 S1 の直後）

Phase 5: オーナー統合 + 分析 ──────────────
  #11 UO-04 S1  CSV アップロード
  #12 UO-04 S2  マッチング管理（UO-04 S1 の直後）
  #13 UO-05 S1  分析ダッシュボード

  → Owner UI 完了。Owner Closure Audit 実施

後続タスク: E2E ─────────────────────────────
  Playwright E2E テスト（3 フロー）

  → 全体 Closure Audit + リリース判定
```

**Staff 業務 Slice を先行させる理由**（Owner 基盤の UO-01 S1 は #2 で早期に作成し、Staff 業務完了後に Owner 管理 Slice に進む）:
- スタッフ UI（タブレット）は日常業務の接客で毎日使う → 先に動くとユーザー価値が早い
- Owner 側は管理画面 → Staff が作ったデータが存在する状態でテストできる
- Owner 基盤（UO-01 S1）を #2 で先行するのは、`base_owner.html` を早期に確立し Owner Slice の precondition を満たすため

## 3. Closure Audit スケジュール

直列実行のため、Closure Audit は **Phase 境界または基盤 cluster 完了時点** で実施する。

**audit slug 規則**: branch 名に使う識別子。日本語・空白を含めない。

| タイミング | audit 対象 | audit slug | トリガー | 検証ポイント |
|-----------|-----------|-----------|---------|-------------|
| #1 完了後 | US-01 | `us01` | US-01 S1 merge 後 | 認証導線（QR ログイン → セッション確立）、未認証リダイレクト、base_staff.html の描画、BottomTab のリンク定義存在。実際のタブ遷移先は stub のため Staff UI 全体 audit で検証 |
| #4 完了後 | US-02 | `us02` | US-02 S2 merge 後 | 顧客選択 → 接客画面の遷移。タスク消化の状態伝搬。generate_tasks → sync_tasks の C-05a 契約 |
| #6 完了後 | Staff UI 全体 | `staff-ui` | US-04 S1 merge 後 | ログイン → 顧客選択 → 接客 → 顧客詳細 → マッチング の業務フロー一気通貫。BottomTab 遷移。全タブのアクティブ状態 |
| #7 完了後 | UO-01 | `uo01` | UO-01 S2 merge 後 | `/o/staff/` 直アクセス時の base_owner.html 描画、OwnerRequiredMixin のガード、Sidebar の active state。`/o/dashboard/` は stub のため Owner UI 全体 audit で検証 |
| #10 完了後 | UO-03 | `uo03` | UO-03 S2 merge 後 | 来店削除 → セグメント再計算の伝搬。閾値変更プレビュー → 確定の整合性 |
| #12 完了後 | UO-04 | `uo04` | UO-04 S2 merge 後 | CSV アップロード → 行一覧 → マッチング実行 → 確定/却下 の一連フロー |
| #13 完了後 | Owner UI 全体 | `owner-ui` | UO-05 S1 merge 後 | Sidebar 全メニューへの遷移。権限ガード。エラー伝搬 |
| E2E 完了後 | E2E 全体 | `e2e` | E2E テスト merge 後 | D-04 で定義した 3 クリティカルパス。Staff + Owner の横断フロー。最終リリース判定 |

### Closure Audit 実施手順

`CLAUDE.md` §5c に準拠する。手順の要約を以下に示す。

1. **audit 用ブランチを作成する**（read-only review。コード変更しない）
   ```bash
   ./scripts/start-feature.sh --branch review/<audit slug>-closure-audit-r1 --title "<audit対象> closure audit"
   ```

2. **Codex に closure audit を手動プロンプトで依頼する**（`request-review.sh` は使わない）
   - **Locked spec baseline**: main の commit hash + 設計書パス一覧
   - **Acceptance criteria**: `REVIEW_SCORECARD.md` で 100/100 採点
   - **層1（回帰確認）**: 各 Slice の postcondition が main 上で維持されているか
   - **層2（結合面チェック）**: 上記スケジュール表の「検証ポイント」列を接合点チェックリストとしてそのまま列挙する
   - **Non-goals**: コード修正、docs の書き換え、merge
   - **出力フォーマット**: Verdict / Score / Findings / Gate Check / Next smallest slice

3. **結果の処理**
   - **PASS (100/100)**: audit 完了。audit PR を close し、main に戻って local/remote branch を削除して終了（merge 不要、read-only のため）
   - **FAIL**: findings から最小 fix slice を切り、通常パイプライン（§1 サイクル）で修正 → 修正 merge 後に再 audit。audit ブランチは再 audit まで残す

### Closure Audit の判定ルール

- **PASS**: findings なし → 次の Slice に進む
- **FAIL**: findings あり → fix slice を切って通常パイプラインで修正 → 修正 merge 後に再 audit
- fix slice は Issue を作成してから通常パイプラインで修正する。ブランチ名は CLAUDE.md の Git ルールに従い `fix/<issue番号>-<audit slug>-closure` (例: `fix/42-us02-closure`, `fix/55-staff-ui-closure`)

### 省略する Closure Audit

以下の Cluster は **単一 Slice** であり、Slice 単体の review (100/100) で品質が担保されるため、個別の Closure Audit は省略する。全体 audit（Staff UI 全体 / Owner UI 全体）でカバーする。

- US-03（1 Slice）
- US-04（1 Slice）
- UO-02（1 Slice）
- UO-05（1 Slice）

**注意**: US-01 も単一 Slice だが、全 UI の土台（base.html, base_staff.html, 認証基盤）を含むため個別の Closure Audit を実施する（基本設計書 §8 の定義通り）。

## 4. Issue 変換ルール

各 Slice について orchestrator が Issue を作成する際のテンプレート。

### Issue テンプレート

```markdown
## [UI] <Cluster名> - <Slice名>

### パイプライン順序
#<順序番号> / 13

### ブランチ名
`feat/<この Issue の番号>-<ブランチ説明部>`（§2 順序表のブランチ説明部を使用）

### 詳細設計書
`docs/design/<詳細設計書ファイル名>` の Slice <番号> セクション

### Cluster / Slice 定義
- **Cluster**: <Cluster ID> (<Cluster名>)
- **Slice**: <Slice番号> (<Slice名>)
- **Slice 数**: 単一 Slice で完結 / <N> Slice 中の <M> 本目

### precondition
- コア層: <コア層 precondition>
- UI: <UI precondition>

### postcondition
<基本設計書の postcondition をそのまま転記>

### 完了条件
<基本設計書の完了条件をそのまま転記>

### 実装指示
詳細設計書 `docs/design/<ファイル名>` の Slice <番号> セクションに従って実装すること。

### テスト要件
各 View について以下のカテゴリのテストを Django TestClient で実装すること:
- [ ] **full-page GET**: 正常系レスポンス（200）とテンプレート確認
- [ ] **権限ガード**: 未認証 → ログインページへリダイレクト、権限不足 → Slice 仕様に従いリダイレクトまたは 403
- [ ] **HTMX fragment**: `HX-Request` ヘッダ付きリクエストで partial レスポンス確認（該当する場合）
- [ ] **write 成功/エラー**: POST/PATCH の正常系とバリデーションエラー（該当する場合）

具体的なテストケースは詳細設計書の各 Slice セクションに記載される。

**Browser smoke test 必須ケース**（Django TestClient では検証不可な項目。該当 Slice で Codex review の「要 smoke test」に含める）:
- US-01 S1 / UO-01 S1: `/s/login/#token=...` `/o/login/#token=...` で自動ログイン、`history.replaceState` 後の URL に hash が残らない、戻る/再読込で token 再送されない

### Pre-flight Checklist
実装完了後、PR を出す前に `docs/framework/CURSOR_PREFLIGHT_CHECKLIST.md` を読み、
全項目をセルフチェックすること。違反があれば修正してからコミットすること。

### レビュー基準
`docs/framework/REVIEW_SCORECARD.md` で 100/100 のみ PASS。

### Merge ゲート（2 段階）
- **Stage 1**: Codex review PASS (100/100)。「要 smoke test」項目がマークされる
- **Stage 2**: orchestrator が「要 smoke test」項目を runtime で検証。PASS で merge、FAIL で pushback

### Closure Audit
<該当する場合> この Slice 完了後に <audit 対象> の Closure Audit を実施する。
<該当しない場合> この Slice 単体での Closure Audit はなし。
```

### Issue 作成タイミング

**Slice 着手の直前に 1 件ずつ作成する**。まとめて 13 件作らない。

理由: 前の Slice の結果（fix slice の追加、設計修正）が後続 Slice の precondition に影響する可能性がある。

## 5. 詳細設計書の対応表

| 詳細設計書 | 含む Slice | パイプライン順序 |
|-----------|-----------|----------------|
| `UI_CLUSTER_US01.md` | US-01 S1 | #1 |
| `UI_CLUSTER_UO01.md` | UO-01 S1, UO-01 S2 | #2, #7 |
| `UI_CLUSTER_US02.md` | US-02 S1, US-02 S2 | #3, #4 |
| `UI_CLUSTER_US03.md` | US-03 S1 | #5 |
| `UI_CLUSTER_US04.md` | US-04 S1 | #6 |
| `UI_CLUSTER_UO02.md` | UO-02 S1 | #8 |
| `UI_CLUSTER_UO03.md` | UO-03 S1, UO-03 S2 | #9, #10 |
| `UI_CLUSTER_UO04.md` | UO-04 S1, UO-04 S2 | #11, #12 |
| `UI_CLUSTER_UO05.md` | UO-05 S1 | #13 |

### 詳細設計書の作成順序

パイプラインの実行順序に合わせて、**必要になる直前に作成する**。

**Readiness Gate**: 各 Slice のパイプラインサイクル Step 1 で「詳細設計書が存在し、Codex レビュー PASS 済み」であることを確認する。この条件を満たさない限り、その Slice の Issue 作成以降のステップには進まない。詳細設計書は Slice 着手の 1 サイクル前に作成・レビューを完了させること。

| 作成順序 | 詳細設計書 | 必要になるタイミング |
|---------|-----------|-------------------|
| 1 | `UI_CLUSTER_US01.md` | #1 着手前 |
| 2 | `UI_CLUSTER_UO01.md` | #2 着手前（UO-01 S2 は #7 だが、S1 と一緒に設計する） |
| 3 | `UI_CLUSTER_US02.md` | #3 着手前 |
| 4 | `UI_CLUSTER_US03.md` | #5 着手前 |
| 5 | `UI_CLUSTER_US04.md` | #6 着手前 |
| 6 | `UI_CLUSTER_UO02.md` | #8 着手前 |
| 7 | `UI_CLUSTER_UO03.md` | #9 着手前 |
| 8 | `UI_CLUSTER_UO04.md` | #11 着手前 |
| 9 | `UI_CLUSTER_UO05.md` | #13 着手前 |

## 6. コア層の前提条件

UI パイプラインを開始するには、コア層の Cluster が完了している必要がある。

### 最低限の開始条件

UI パイプライン #1（US-01 S1）を開始するには:
- **C-02 全 Slice 完了**（QRAuthService, StaffViewSet, QRToken）
- **Django プロジェクトに UI app が組み込み可能な状態**

基本設計書の US-01 S1 precondition は上記 2 項目を記載している。C-01 は C-02 の暗黙的前提（C-02 の precondition に C-01 各 Slice の完了が含まれる）のため、C-02 完了を確認すれば C-01 も完了していることが保証される。

### Slice ごとのコア層依存

以下は基本設計書の各 Slice precondition の **要約** である。正式な precondition 原文は `UI_BASIC_DESIGN.md` §7 の各 Slice 定義を参照すること。C-01 は全コア層 Cluster の暗黙的前提のため個別に記載しない。

| UI Slice | コア層 precondition（基本設計書の記載通り） | 最も遅い依存 |
|----------|--------------------------------------------|----|
| #1 US-01 S1 | C-02 完了 + Django プロジェクトに UI app 組み込み可能 | C-02 |
| #2 UO-01 S1 | C-02 完了 | C-02 |
| #3 US-02 S1 | C-03, C-05a 完了 | C-05a |
| #4 US-02 S2 | C-04 S2, C-05a, C-05b 完了 | C-05b |
| #5 US-03 S1 | C-03, C-04 S2, C-05a 完了 | C-05a |
| #6 US-04 S1 | C-06 全 Slice 完了 | C-06 |
| #7 UO-01 S2 | C-02 完了 | C-02 |
| #8 UO-02 S1 | C-03, C-05a, C-05b 完了 | C-05b |
| #9 UO-03 S1 | C-04 S2 完了 | C-04 S2 |
| #10 UO-03 S2 | C-04 全 Slice 完了 | C-04 |
| #11 UO-04 S1 | C-06 S1 完了 | C-06 S1 |
| #12 UO-04 S2 | C-06 S2 完了（MatchingService 動作） | C-06 S2 |
| #13 UO-05 S1 | C-07 完了 | C-07 |
| E2E | 全コア層完了 | C-07 |

**注意**: コア層が未完了の Slice に到達した場合、パイプラインを **停止** して design に報告する。コア層の完了を待ってから再開する。

## 7. リスクと対策

| リスク | 影響 | 対策 |
|-------|------|------|
| コア層の Cluster が UI 着手時に未完了 | パイプライン停止 | コア層パイプラインの進捗を事前確認。#1, #2 は C-02 完了のみが条件なので早期着手可 |
| Slice 間で migration 競合 | ビルド失敗 | 直列実行で回避済み |
| Closure Audit で大きな設計欠陥発見 | 手戻り | 詳細設計書の Codex レビューで事前検出。fix slice は最小範囲に限定 |
| 詳細設計書の作成が Slice 着手に間に合わない | パイプライン待ち | 詳細設計書は Slice 着手の 1 サイクル前に作成開始する |
| migration の rollback が必要になる | データ不整合 | UI Slice は原則 migration を作らない（モデルはコア層で定義済み）。必要な場合は詳細設計書で明示し、reversible であること・`migrate` / `migrate <previous>` の往復確認を verify に含めること |

## Review Log

- [2026-03-31] 初版作成
- [2026-03-31] Codex レビュー (gpt-5.4 high): 82/100 FAIL。5 件を修正
  - F-01 (high): US-01 Closure Audit を省略リストから復帰。基本設計書 §8 の定義通り #1 完了後に実施
  - F-02 (high): E2E を Slice から分離。正式 Slice は 13 本、E2E は後続タスクとして別セクションに記載
  - F-03 (medium): UO-03 S2 の UI precondition を基本設計書に合わせ UO-01 S1 完了に修正（直列実行のため UO-03 S1 は自然に完了済み）
  - F-04 (medium): 開始条件から C-01 を削除。基本設計書の precondition は C-02 のみ（C-01 は C-02 の暗黙的前提）
  - F-05 (medium): パイプラインサイクルに CLAUDE.md の必須手順（Pre-flight Checklist, request-review.sh, close-feature.sh --score 100）を明記。Issue テンプレートにも追加
- [2026-03-31] Codex 2回目レビュー (gpt-5.4 high): 94/100 FAIL。2 件を修正
  - F-06 (medium): precondition の転記ずれ修正。US-01 S1 に「Django プロジェクトに UI app 組み込み可能」追加、UO-01 S1 に「LoginRequiredMixin 存在」追加、UO-04 S2 を「C-06 S2 完了」に修正（基本設計書の原文通り）
  - F-07 (medium): パイプラインサイクルに smoke test gate（Stage 2）を追加。merge 条件を「Codex review PASS + smoke test PASS」の 2 段階ゲートとして明記
- [2026-03-31] Codex 3回目レビュー (gpt-5.4 high): 96/100 FAIL。2 件を修正
  - F-08 (medium): Issue テンプレートに Merge ゲート（2 段階）セクションを追加。Stage 1（review 100/100）+ Stage 2（smoke test）を明記
  - F-09 (low): 開始条件の説明文を修正。US-01 S1 precondition が 2 項目（C-02 完了 + Django プロジェクト組み込み可能）であることを正確に記載
- [2026-03-31] Codex 4回目レビュー (gpt-5.4 high): 98/100 FAIL。1 件を修正
  - F-10 (low): コア層依存テーブルの見出しを「そのまま転記」から「要約」に修正。正式な precondition 原文は基本設計書 §7 を参照する旨を明記
- [2026-03-31] Codex 5回目レビュー (gpt-5.4 high): 84/100 CONDITIONAL。4 件を修正
  - F-11 (high): §1 に基本設計書との関係を明記。基本設計 §8 は並列可能性を識別、本書は実装判断として直列を選択。Slice 総数・実行順序は本書が優先する旨を追記
  - F-12 (medium): §3 に Closure Audit 実施手順を追加。CLAUDE.md §5c 準拠のブランチ命名、locked spec baseline、層1/層2 監査観点、手動プロンプト構築、結果処理を明記
  - F-13 (medium): Issue テンプレートにテスト要件セクションを追加。full-page GET / 権限ガード / HTMX fragment / write 成功・エラーの 4 カテゴリを定義
  - F-14 (medium): Smoke Test 運用ルールを §1 に追加。PR コメントへの記録フォーマット、項目 0 件時の skip ルールを定義
- [2026-03-31] Codex 6回目レビュー (gpt-5.4 high): 86/100 CONDITIONAL。4 件を修正
  - F-15 (high): `scripts/_common.sh` の WORKDIR と DEFAULT_BRANCH を ui_shisha_crm / main に修正（フレームワークコピー時の修正漏れ）
  - F-16 (medium): テスト要件の権限ガードを「403」から「Slice 仕様に従いリダイレクトまたは 403」に修正。基本設計の StaffRequiredMixin / OwnerRequiredMixin はリダイレクト動作
  - F-17 (medium): §3 の見出しを「Phase 境界または基盤 cluster 完了時点で実施」に修正
  - F-18 (low): Smoke Test の URL 例を `/staff/login/` → `/s/login/` に修正（基本設計の URL 体系に準拠）
- [2026-03-31] Codex 7回目レビュー (gpt-5.4 high): 86/100 CONDITIONAL。4 件を修正
  - F-19 (medium): `UI_BASIC_DESIGN.md` の Slice 総数を「14 Slice（Owner 9）」→「13 Slice（Owner 8）」に修正。E2E は Slice に含めない旨を明記
  - F-20 (medium): `CLAUDE.md` §5c の `master` 表記を `main` に統一（2箇所）
  - F-21 (medium): fix branch 命名を `fix/<issue番号>-<audit対象>-closure` に変更。CLAUDE.md の Git ルール `fix/<issue番号>-<説明>` と整合
  - F-22 (low): Closure Audit PASS 時の手順に「audit PR を close、local/remote branch を削除」を追記。FAIL 時は再 audit まで audit ブランチを残す旨を明記
- [2026-03-31] Codex 8回目レビュー (gpt-5.4 high): 84/100 CONDITIONAL。3 件を修正
  - F-23 (high): §5 に Readiness Gate を明記。詳細設計書が存在し Codex レビュー PASS 済みでない限り Issue 作成以降に進まない旨を追記
  - F-24 (medium): `dispatch-cursor.sh` の env bootstrap を修正。別プロジェクト（stripe_billing_*）参照を削除し、WORKDIR の .env のみを読む形に統一
  - F-25 (medium): §7 に migration ポリシーを追加。UI Slice は原則 migration を作らない。必要時は詳細設計書で明示、reversible + 往復確認を verify に含める
- [2026-03-31] Codex 9回目レビュー (gpt-5.4 high): 84/100 CONDITIONAL。4 件を修正
  - F-26 (high): ブランチ名を固定値から生成規則に変更。`feat/<issue番号>-<ブランチ説明部>` 形式で CLAUDE.md の Git ルールと整合。順序表のヘッダを「ブランチ説明部」に変更、Issue テンプレート・E2E も同規則に統一
  - F-27 (high): US-01 Closure Audit（#1 完了後）の検証ポイントを縮小。認証導線・未認証リダイレクト・base_staff 描画・BottomTab リンク定義存在に限定。タブ遷移先は Staff UI 全体 audit へ移動
  - F-28 (high): UO-01 Closure Audit（#7 完了後）の検証ポイントを修正。`/o/staff/` 直アクセス時の描画・OwnerRequiredMixin・Sidebar active state に限定。ログイン着地導線は Owner UI 全体 audit へ移動
  - F-29 (medium): smoke test 0 件時を「Stage 2 は N/A = PASS 扱い」と明文化。merge 条件との矛盾を解消
- [2026-03-31] Codex 10回目レビュー (gpt-5.4 high): 86/100 CONDITIONAL。2 件を修正
  - F-30 (high): 冒頭に本書の status を明記。本書自体は orchestrator に渡せる状態、パイプライン実行は Readiness Gate（§5）で制御、詳細設計書は着手直前に作成する運用
  - F-31 (medium): `UI_BASIC_DESIGN.md` の固定ブランチ名 13 箇所を「ブランチ説明部」に変更（実ブランチ名は UI_PIPELINE.md §2 参照）。Closure Audit テーブルの検証ポイントをパイプライン定義書と同期
- [2026-03-31] Codex 11回目レビュー (gpt-5.4 high): 88/100 CONDITIONAL。2 件を修正
  - F-32 (medium): `UI_BASIC_DESIGN.md` §8 の推奨実行順序テーブルの precondition 転記ずれ修正。US-02 S2 に C-05a 追加、US-03 S1 に C-05a 追加、UO-04 S2 を C-06 S2 完了に修正
  - F-33 (medium): QR ログインの role 別 URL ルーティングを基本設計書に追記。staff は `/s/login/#token={token}`、owner は `/o/login/#token={token}`。ログインページの JS が `location.hash` から token を読み取り自動 POST する仕様を S-LOGIN / O-LOGIN に追加。O-STAFF-CREATE の QR URL 生成も role 別に明確化
- [2026-03-31] Codex 12回目レビュー (gpt-5.4 high): 89/100 CONDITIONAL。2 件を修正
  - F-34 (medium): QR リンク自動ログインを Slice の postcondition / 完了条件に反映。US-01 S1・UO-01 S1 に QR リンク経由自動ログインと token 再送防止の検証を追加。UO-01 S2 に role 別 QR URL 生成の検証を追加
  - F-35 (medium): `location.hash` 読み取り後に `history.replaceState` で hash を除去する要件を S-LOGIN / O-LOGIN に追記。戻る/再読込で token 再送されない仕様を明確化
- [2026-03-31] Codex 13回目レビュー (gpt-5.4 high): 86/100 CONDITIONAL。3 件を修正
  - F-36 (medium): UO-01 S1 完了条件に「過渡状態」の但し書きを追加。`/s/customers/` リダイレクト先は US-02 S1 で実装されるため、ロール分岐設定自体を検証対象とする
  - F-37 (medium): `UI_BASIC_DESIGN.md` §8 の UO-01 S1 並列可能欄を修正。「概念上は並列候補だが base.html 依存のため US-01 S1 完了後に実行」と注記
  - F-38 (medium): Issue テンプレートに Browser smoke test 必須ケースを追加。QR hash 自動ログイン・replaceState・token 再送防止は Django TestClient で検証不可のため smoke test 対象
- [2026-03-31] Codex 14回目レビュー (gpt-5.4 high): 82/100 CONDITIONAL。4 件を修正
  - F-39 (high): US-01 S1 の `/s/customers/` 過渡状態を解消。`LoginRequiredMixin` 付き guarded stub view を US-01 S1 で配置、「準備中」表示。未認証リダイレクトが検証可能に。US-02 S1 で本実装に置き換え
  - F-40 (high): UO-01 S1 の `/o/dashboard/` を同様に guarded stub view（`OwnerRequiredMixin` 付き）で解消。未認証リダイレクト・staff ロール分岐が検証可能に。UO-05 S1 で本実装に置き換え
  - F-41 (medium): Closure Audit テーブルに audit slug 列を追加（`us01`, `us02`, `staff-ui`, `uo01`, `uo03`, `uo04`, `owner-ui`, `e2e`）。branch 名は `review/<audit slug>-closure-audit-r1` で固定
  - F-42 (medium): 順序の根拠を「Staff 側を先に全部完了」→「Staff 業務 Slice を先行、Owner 基盤 UO-01 S1 は #2 で早期作成」に修正。UO-01 S1 を先行する理由を追記
- [2026-03-31] Codex 15回目レビュー (gpt-5.4 high): 89/100 CONDITIONAL。1 件を修正
  - F-43 (medium): fix branch 命名の `<audit対象>` を `<audit slug>` に統一。例も slug ベースに修正
- [2026-03-31] Codex 16回目レビュー (gpt-5.4 high): 89/100 CONDITIONAL。1 件を修正
  - F-44 (medium): `CLAUDE.md` §5c の closure audit branch 規則を `review/<audit slug>-closure-audit-r1` に統一。パイプライン定義書との二重定義を解消
- [2026-03-31] Codex 17回目レビュー (gpt-5.4 high): **100/100 PASS**
