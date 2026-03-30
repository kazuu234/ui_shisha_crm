# AI駆動開発メソドロジー — サブエージェントモデルとレビューゲート

作成日: 2026-03-20
対象読者: AIを活用した開発に関心のある技術者

---

## 1. 概要

本ドキュメントは、AIサブエージェントによる分業開発モデルの全体像を説明する。

### 何を解決するか

AIコーディングエージェントに丸投げすると、以下の問題が起きる。

| 問題 | 具体例 |
|------|--------|
| **実装漏れの不可視化** | stub / skeleton を「完了」と報告し、未実装がどこにあるか分からなくなる |
| **導線の断絶** | ファイル単位では完成しているが、ユーザーの一連の操作が最後まで繋がらない |
| **設定依存の見落とし** | `.env` に値があるだけで「動くはず」と判断し、runtime path が未検証 |
| **品質の後退** | 修正が別の導線を壊していることに誰も気づかない |

これらを構造的に防ぐのが、本メソドロジーの目的である。

---

## 2. アーキテクチャ：4層分業モデル

```
┌──────────────────────────────────────────────────────┐
│              設計層: Opus（Cursor 経由）                │
│  ・プロダクト設計・API 設計                              │
│  ・cluster 分割 + interface 定義                       │
│  ・段階的に出力粒度を上げる（後述）                       │
└────────────────────────┬─────────────────────────────┘
                         │ cluster spec を渡す
                         ▼
              ┌─────────────────────────┐
              │ 設計レビュアー（非常設）    │
              │ gpt-5.4 / xhigh         │
              │ 設計の実現可能性・整合性   │
              └────────────┬────────────┘
                           │ 問題なければ通過
                           ▼
┌──────────────────────────────────────────────────────┐
│           人間 + Codex Main（xhigh）                   │
│  ・dispatch unit への分割の決定                          │
│  ・各 dispatch unit のモデル判定（medium / mini）         │
│  ・dispatch + merge gate + smoke test                  │
└────────┬──────────────────────┬───────────────────────┘
         │ dispatch             │ dispatch
         ▼                     ▼
┌─────────────────┐   ┌─────────────────────────┐
│ Implementation  │   │  Review Subagent        │
│ Subagent        │   │                         │
│                 │   │  ・Scorecard で 100点    │
│ Cursor CLI      │◄──│    になるまで差し戻す     │
│ + Composer 2    │   │  ・gpt-5.4 xhigh        │
│ (subprocess)    │   │  ・コード修正禁止         │
│ コード修正のみ   │   │                         │
└─────────────────┘   └─────────────────────────┘
```

### 各ロールの責務

| ロール | モデル | 責務 | 禁止事項 |
|--------|--------|------|----------|
| **Opus（設計層）** | claude opus | プロダクト設計、cluster 分割、interface 定義 | 実装の直接指示 |
| **設計レビュアー（非常設）** | gpt-5.4 / xhigh | cluster spec の実現可能性・整合性レビュー | コード変更 |
| **人間 + Codex Main** | gpt-5.4 / middle（※[CC ハーネス化提案あり](./PROPOSAL_HARNESS_MODEL.md)） | dispatch unit 分割、dispatch、merge gate、smoke test、バグ報告の記録 | 設計変更（下記参照）、越権行為（下記参照） |
| **Implementation Subagent** | Cursor CLI + Composer 2（subprocess dispatch） | 指定範囲のコード実装、テスト追加 | 指定範囲外の変更 |
| **Review Subagent** | gpt-5.4 / xhigh | Scorecard に基づく採点、pushback、closure audit | コード修正 |

### なぜ Implementation と Review を分けるか

同一エージェントが実装とレビューを兼ねると、自分の実装を正当化するバイアスが生じる。
別エージェントに「100点にならなければ merge しない」という権限を与えることで、
実装側の「完了報告の誇張」を構造的に防ぐ。

### Codex Main の禁止事項：設計をしない、越権しない

Codex Main は **設計判断をしてはならない**。
ユーザー（人間）から設計変更に相当する依頼を受けた場合でも、
自分で設計せず Opus に差し戻す。

> **モデル設定の意図**: Main は gpt-5.4 / **middle** を使用する。
> xhigh では「賢くあろうとしすぎる」結果、設計層の権限に踏み込む越権行為が
> 観測された（cluster 間の共通項の再確認、cluster/slice の再定義の試行など）。
> middle に下げることで過剰な推論を抑制し、手順実行に集中させる。

**越権行為の具体例（絶対にやってはいけないこと）**：

- Opus が定義した cluster 間の共通項を再確認・再分析する
- cluster や design slice の境界を再定義・統合・分割する
- 設計の改善提案を自発的に行う
- design slice の pre/post condition を変更する

設計に該当するもの（Main がやってはいけないこと）：

- API のエンドポイント構成やレスポンス構造の決定
- データモデル（テーブル設計、リレーション）の新設・変更
- cluster の境界変更、新 cluster の追加
- interface 定義の変更
- アーキテクチャ上の方針変更（認証方式、外部サービス連携方式など）

設計に該当しないもの（Main がやって良いこと）：

- design slice の dispatch unit への分割（Opus の cluster spec 内での作業分解）
- mini / medium のモデル判定（dispatch unit 単位）
- dispatch 順序の決定
- バグ報告の受付と `USER_REPORTED_ISSUES.md` / `ACTION_ITEMS.md` への記録
- バグ修正の dispatch unit 化と dispatch（既存設計の範囲内での修正）

バグ報告から設計変更が必要だと判明した場合のフロー：

```
ユーザーがバグ報告
  → Main が USER_REPORTED_ISSUES.md に記録
  → Main が「設計変更が必要か」を判断
     ├── 不要（既存設計内で修正可能）→ 修正 dispatch unit を作って dispatch
     └── 必要 → Opus に差し戻す旨をユーザーに報告
              → ユーザーが Opus（Cursor）で設計を修正
              → 修正された cluster spec を受けて Main が再開
```

### 設計レビュアー（非常設）

Opus が cluster spec を納品したとき、Codex Main とは **別の人格** として
gpt-5.4 / xhigh の設計レビュアーを dispatch できる。

目的: Opus の設計を独立した視点で検証し、実装に入る前に設計上の問題を潰す。

```
Opus → cluster spec を納品
  │
  ▼
設計レビュアー（xhigh、非常設）
  ・cluster 間の依存に矛盾がないか
  ・interface 定義が実装可能か
  ・design slice の粒度が適切か（大きすぎ / 小さすぎ）
  ・見落としている状態遷移やエッジケースがないか
  │
  ├── 問題なし → Main が実装フェーズに入る
  └── 問題あり → ユーザーに報告 → Opus で設計修正
```

設計レビュアーは以下の点で Main / コードレビュアーとは異なる：

| | Main | コードレビュアー | 設計レビュアー |
|---|---|---|---|
| 常設 | ○ | ○ | **×（cluster spec 受領時のみ）** |
| 対象 | dispatch unit の管理と dispatch | コード（diff） | **設計（cluster spec）** |
| 判断権限 | dispatch 順序、モデル選択 | 実装品質のスコアリング | **設計の実現可能性と整合性** |
| コード変更 | ○ | × | **×** |
| 設計変更の提案 | × | × | **○（Opus への差し戻し提案）** |

設計レビュアーは Opus の設計を「信頼するが検証する」ための仕組みであり、
全ての cluster spec に対して必ず dispatch する必要はない。
リスクが高い設計（新しいアーキテクチャパターン、複雑な状態遷移、
複数 cluster にまたがる interface 変更）のときに使う。

### Opus → Codex の分業

Opus は「何を作るか・どう分けるか」を担い、Codex は「どう作るか」を回す。

Opus が出す cluster spec の粒度は段階的に上げる：

- **初期（必須）**: cluster 境界 + interface + design slice 分割案 + 各 design slice の pre/post
- **安定後**: Gherkin シナリオ + closure audit チェックリスト
- **成熟後**: mini-safe タグの付与まで含む

初期から design slice + pre/post を必須とする理由：
pre/post は設計判断であり、Codex Main の権限外である。
Opus が design slice を切れないほど不確実な領域は、そもそも実装に入るべきではない。
design slice を定義できること自体が「設計が十分に固まっている」ことの証拠となる。

### 用語：design slice と dispatch unit

| 用語 | 定義者 | 定義 |
|------|--------|------|
| **design slice** | Opus | pre/post が定義された設計上の作業単位。cluster spec に記載される |
| **dispatch unit** | Codex Main | design slice を実行可能なサイズに分割した dispatch 上の作業単位 |

Codex Main は design slice を **さらに細かい dispatch unit に分割する** ことはできるが、
**新しい design slice を設計する**（pre/post を定義する）ことはできない。
dispatch unit は親 design slice の pre/post の範囲内で行われ、独自の pre/post を持たない。

dispatch unit の完了は設計上の意味を持たず、全 dispatch unit の完了が
親 design slice の postcondition 達成と等価になる。

Gherkin シナリオと closure audit チェックリストは安定後に追加する。
これらは pre/post があれば導出可能なため、初期は Main が
**derived operational scenarios** として導出できる（Main の運用成果物であり、
Opus の設計成果物ではない）。

Opus の出力フォーマットが安定し、乖離が少ないことが確認できてから、
徐々に Opus の出力粒度を上げていく。

### 設計精度を上げる2つの手法

#### Design by Contract（DbC）：事前条件・事後条件の明示

Opus が cluster spec / design slice 定義を書くとき、各 design slice の境界に
**precondition（事前条件）** と **postcondition（事後条件）** を形式的に定義する。

```
Slice A: 顧客登録
  precondition:
    - 認証済みユーザーが存在する
  postcondition:
    - Customer レコードが DB に存在する（status='active'）
    - レスポンスに customer_id が含まれる

Slice B: 来店記録
  precondition:
    - Customer が status='active' で存在する  ← Slice A の postcondition と対応
  postcondition:
    - Visit レコードが DB に存在する
    - フレーバー嗜好が記録されている
    - session_duration が記録されている
```

**Slice A の postcondition と Slice B の precondition が対応しなければ、
設計段階で結合不良が検出できる。** 実装後の closure audit を待つ必要がない。

DbC の効果：

- 仕様の曖昧さを設計段階で炙り出す（postcondition を書こうとした時点で
  「この後何が真であるべきか？」という問いが強制される）
- design slice 間の契約不整合を構造的に防ぐ
- closure audit の層2 で検証すべき接合点が pre/post の対応表から自動的に導出される
- 設計レビュアーの検証観点が明確になる（pre/post の整合性チェック）

#### Executable Specification：Gherkin シナリオによる仕様記述

Opus が cluster spec を書くとき、主要ユーザーフローを
**Given-When-Then 形式の Gherkin シナリオ** で記述する。

```gherkin
Feature: 顧客管理フロー

  Scenario: 顧客の登録
    Given 認証済みユーザーが存在する
    When ユーザーが顧客情報を入力して登録する
    Then 顧客が有効状態で保存される
    And レスポンスに customer_id が含まれる

  Scenario: 来店の記録
    Given 有効な顧客が存在する
    And フレーバー情報が選択されている
    When ユーザーが来店を記録する
    Then 来店記録が保存される
    And フレーバー嗜好が記録される
    And セッション時間が記録される

  Scenario: 来店履歴の閲覧
    Given 有効な顧客が存在する
    And 来店記録が1件以上ある
    When ユーザーが来店履歴を表示する
    Then 来店記録が日時順で表示される
    And 各来店のフレーバー嗜好が表示される

  Scenario: フレーバー嗜好の記録
    Given 有効な顧客が存在する
    When ユーザーがフレーバー嗜好を登録する
    Then フレーバー嗜好が顧客に紐づいて保存される
    And 次回来店時に嗜好が参照できる
```

Gherkin シナリオは3つの役割を同時に果たす：

1. **設計の仕様書** — Opus が意図した振る舞いの正確な記述
2. **Implementation の acceptance criteria** — dispatch unit の完了条件そのもの
3. **結合テストのシナリオ** — 人間が結合テスト時にそのまま使えるチェックリスト

自然言語の「顧客管理ができること」は曖昧だが、
Given-When-Then で書くと入力状態・操作・期待出力を必ず明示させることになる。
**書けないということは、設計が固まっていないということ。**

#### 2つの手法の関係

DbC と Gherkin は相補的に機能する：

- **DbC（pre/post）** は design slice 間の **契約の整合性** を保証する（構造面）
- **Gherkin** は **ユーザーから見た振る舞い** を保証する（振る舞い面）

```
DbC:     Slice A.post ⊇ Slice B.pre  →  契約が繋がっている
Gherkin: Given → When → Then          →  ユーザーの導線が繋がっている
```

Opus の cluster spec には DbC（pre/post）を必ず含める。
Gherkin シナリオは Opus が提供する場合はそのまま使い、
提供されない初期段階では Main が pre/post から derived operational scenarios として導出する。

Codex Main は dispatch unit 分割時に pre/post の対応を確認し、
Implementation subagent には Gherkin シナリオ（Opus 提供 or Main 導出）を
acceptance criteria として渡す。

---

## 3. 2つのワークフロー：レビュー先行 vs 実装先行

プロジェクトの状態によって、gated workflow の回し方が異なる。

### 3.1 レビュー先行ワークフロー（既存コードの改善時）

壊れた・品質の低いコードが既にある場合に使う。
`stripe_billing_tickets_production` の Phase 1 がこのパターンだった。

```
既存コードがある（品質に問題あり）
  │
  ▼
Review Subagent が既存コードを監査・採点
  │
  ▼
指摘事項を元に人間が最小修正単位を決定
  │
  ▼
Implementation Subagent が修正
  │
  ▼
Review Subagent が再採点
  │
  ├── FAIL → pushback → 修正 → 再レビュー
  └── PASS (100/100) → Main smoke test → merge
```

**使うべき場面**: 既存コードの改善・リファクタリング・外部レビュー指摘対応

### 3.2 実装先行ワークフロー（新規開発時）← 本プロジェクトで使用

設計が先にあり、ゼロから作る場合に使う。
**本プロジェクト（headless_shisha_crm）はこちら。**

```
人間が設計に基づいて最小実装単位を決定
  │
  ▼
Implementation Subagent が実装
  │
  ▼
Review Subagent が Scorecard で採点
  │
  ├── FAIL → Implementation に pushback（修正指示付き）
  │            └── 修正後、再度 Review へ
  │
  └── PASS (100/100) → Main smoke test → merge
```

**使うべき場面**: 新規開発・設計済み機能の追加実装

### 3.3 なぜ本プロジェクトは実装先行か

`stripe_billing_tickets_production` では、gpt-5.4 mini による並列実装で以下が起きた：

- main からの指示が不十分なまま並列実行された
- reviewer からのフィードバックループが無かった
- 小型モデルに skill や十分なコンテキストを与えなかった
- 結果として導線の断絶・stub 放置・設定未検証が多発した

このため、**既にあるコードをまずレビューして問題を洗い出す**レビュー先行が必要だった。

本プロジェクトは新規であり、壊れたコードが存在しない。
設計ドキュメントを先に作り、そこから design slice → dispatch unit に分割して実装する。
したがって **実装先行ワークフローが適切**である。

---

## 4. Cluster Closure Audit：design slice 間の結合検証

cluster 内の全 **design slice** の postcondition が達成されたあと（= 全 dispatch unit が
100/100 + smoke test PASS で merge 済み）、**design slice 間の結合面が正しいか**を
検証する専用の read-only レビューを実施する。

```
design slice A (postcondition 達成) ─┐
design slice B (postcondition 達成) ─┤── cluster closure audit
design slice C (postcondition 達成) ─┘        │
                                              ├── 層1: 各 design slice の回帰確認
                                              └── 層2: design slice 間の結合面チェック
```

### 層1: 個別 design slice の回帰確認

- 各 design slice の postcondition が default branch (`master`) 上で維持されているか
- 仕様に対するカバレッジ漏れがないか

### 層2: design slice 間の結合面チェック

- design slice A の出力が design slice B の入力として正しく消費されるか
- design slice 間で共有する状態遷移が矛盾しないか
- design slice A で追加した guard が design slice B の導線を壊していないか
- design slice 間のデータ受け渡し契約（pre/post の対応）が維持されているか

### 教訓：なぜ層2 を明示する必要があるか

`stripe_billing_tickets_production` の closure audit では、
reviewer に「end-to-end で確認」とだけ指示していた。
結果として reviewer は層1（個別の仕様カバレッジ）を見たが、
層2（design slice 間の接合点の検証）は構造的に抜けていた。

**「end-to-end で確認」は指示として不十分。**
closure audit の dispatch には、**どの design slice 間のどの接合点を見るか**を
明示的に列挙する。

詳細は [GIT_WORKFLOW_GUIDANCE.md](./GIT_WORKFLOW_GUIDANCE.md) の
「Cluster と Closure Audit」セクションを参照。

---

## 5. 速度改善戦略

### 方針

Implementation Subagent は Cursor CLI + Composer 2（subprocess dispatch）を使用する。
Composer 2 は CursorBench 61.3 のコード専用モデルであり、
トークン単価が Codex medium の約 1/6 でありながら実装品質が高い。

cluster 並列は現時点では導入しない（共有インフラ競合・cross-cluster 統合の
未解決課題があるため）。

### Pushback エスカレーションルール

同一 dispatch unit に対して pushback が **3回** に達した場合：

```
pushback 1回目 → 通常の修正指示
pushback 2回目 → 修正指示 + 根本原因の特定を要求
pushback 3回目（3-strike）→ 実装ループ停止 → エスカレーション
```

3-strike 時のアクション：

1. **実装ループを停止する**（4回目の pushback は行わない）
2. **原因を分類する**：
   - **(a) 指示の曖昧さ** → Main が dispatch 指示を書き直して再 dispatch
   - **(b) 設計の不備** → Opus にフラグして設計修正を依頼（spec rebaseline）
   - **(c) モデル能力の限界** → mini → medium、medium → xhigh に昇格して再 dispatch
3. **SUBAGENT_DISPATCH_LOG.md に 3-strike の記録と原因分類を残す**

### Spec Rebaseline プロトコル

進行中の dispatch unit で設計変更が必要と判明した場合：

1. Main は **現在の dispatch unit を中断** する（merge しない）
2. 変更理由を `ACTION_ITEMS.md` に記録し、ユーザーに Opus-level 修正を依頼
3. Opus が修正した cluster spec を受領したら、**影響を受ける design slice の pre/post を更新**
4. 更新された pre/post に基づき、中断していた dispatch unit を再計画する
5. SUBAGENT_DISPATCH_LOG.md に「spec rebaseline: [理由]」を記録する

原則として **進行中の dispatch unit の仕様基準を途中で変えない**。
spec rebaseline が必要な場合は、明示的に中断 → 再計画のサイクルを回す。

### Implementation Subagent：Cursor CLI + Composer 2（正式採用）

Implementation Subagent は **Cursor CLI + Composer 2** を使う。
2026-03-23 に検証完了、正式採用。

Composer 2 は Cursor が開発したコード専用モデルで、
CursorBench 61.3（Opus 4.6 超え）、トークン単価は medium の約 1/6。
Cursor CLI のヘッドレスモードで subprocess として直接起動し、ファイル + git diff でメッセージングする。
worktree で Main の checkout と分離する。監視は `tail -f` でログファイルを確認。

> 注: 当初 tmux send-key 方式を採用したが、セッション消失の不安定さがあり subprocess 直接起動に変更した。

通信方式・dispatch スクリプト・ディレクトリ構造の詳細:
[PROPOSAL_COMPOSER2_IMPLEMENTATION.md](./PROPOSAL_COMPOSER2_IMPLEMENTATION.md)

### 並列化について（将来検討事項）

以下は現時点では導入しない。品質安定を確認してから段階的に検討する：

- cluster 間の並列実装（共有インフラ競合、cross-cluster 統合の課題が未解決）
- Core / UI の並列開発（API 契約の安定後に検討。スタブ品質の問題がある）

---

## 6. 教訓（stripe_billing_tickets_production から）

### やってはいけなかったこと

1. **速度と並列化を優先しすぎた** — 各 PR が自分のモジュールだけ見て、全体の最終導線を誰も責任を持って見ていない状態が生まれた
2. **指示がファイル責務中心でユーザー完了条件中心でなかった** — モジュール単位で割り振ったが、ユーザーの一連の導線に対する owner を置かなかった
3. **post-merge の実確認が不足** — コードレビューと test はやったが、実際に動かす確認が不十分だった
4. **設定依存を「設定済みなら動くはず」と雑に扱った** — `.env` に値があるだけで runtime path 未確認
5. **dispatch 前に指示文のログを残していなかった** — 曖昧な指示を自分でも検知できなかった
6. **小型モデルに十分なコンテキスト・skill を与えなかった** — gpt-5.4 mini は指示の理解・遵守が不十分で、main の意図と乖離した実装を量産した
7. **closure audit で design slice 間の結合面を明示的に検証していなかった** — 「end-to-end で確認」とだけ指示し、reviewer は個別 design slice のカバレッジしか見なかった
8. **速度改善策を一度に複数導入した** — 並列化 + 小型モデル + 不十分な指示を同時に変えたため、問題発生時にどの変更が原因か切り分けられなかった

### 改善策（本プロジェクトで適用）

1. Implementation subagent は原則 `gpt-5.4 / medium`。mini は厳格基準を満たす dispatch unit にのみ限定適用
2. dispatch 前に、送る指示文を docs に保存する
3. 指示は「担当ファイル」だけでなく「ユーザー完了条件」を必ず含める
4. 各 dispatch unit の最後に、main 側で主要導線の smoke test を行う
5. 設定依存機能は、設定値の有無ではなく「実際にその provider が使われたか」で確認する
6. 新規開発では実装先行ワークフローを使い、実装してからレビューに回す
7. closure audit では design slice 間の結合面チェックリストを acceptance criteria に明示する
8. 速度改善は一度に1つだけ変数を変えて効果を検証する（mini 限定採用から開始）

---

## 7. 関連ドキュメント

- [REVIEW_SCORECARD.md](./REVIEW_SCORECARD.md) — 100点レビュー基準
- [GIT_WORKFLOW_GUIDANCE.md](./GIT_WORKFLOW_GUIDANCE.md) — gated workflow ルール
- [SUBAGENT_DISPATCH_LOG.md](./state/SUBAGENT_DISPATCH_LOG.md) — dispatch 記録
- [CURRENT_WORK_STATUS.md](./state/CURRENT_WORK_STATUS.md) — 進捗台帳
- [SESSION_RESTART_GUIDE.md](./SESSION_RESTART_GUIDE.md) — セッション再開手順
