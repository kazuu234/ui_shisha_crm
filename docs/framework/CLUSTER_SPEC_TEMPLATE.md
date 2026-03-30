# Cluster Spec テンプレート

本テンプレートは Opus（設計層）が cluster spec を記述する際のフォーマット。
Codex Main はこのフォーマットで受け取り、dispatch unit 分割と dispatch に使う。

---

## 記述例

```markdown
# Cluster: 顧客管理フロー

## 目的
顧客の登録・来店記録・フレーバー嗜好管理・セッション履歴の閲覧が一連の操作として完結する。

## 他 cluster との依存
- ロイヤルティポイント cluster: customer_id を FK で参照（読み取りのみ）
- LINE連携 cluster: 依存なし（この cluster 完了後に連携を追加）

## Interface 定義
- POST   /api/customers            → CustomerCreateRequest  → CustomerResponse
- GET    /api/customers/:id        → void                   → CustomerResponse
- POST   /api/visits               → VisitCreateRequest     → VisitResponse
- GET    /api/customers/:id/visits → void                   → VisitListResponse

## Slice 分割

### Slice 1: Customer モデル + DB マイグレーション

precondition:
  - DB 接続が確立している

postcondition:
  - customers テーブルが存在し、全カラムの型が正しい
  - status カラムのデフォルト値が 'active' である
  - flavor_preferences カラム（JSONB）が存在する

対象ファイル: models/customer.py, migrations/
モデル推奨: medium（初期段階では模倣元パターンが無いため。安定後に mini 検討可）

### Slice 2: 顧客登録 API

precondition:
  - customers テーブルが存在する（Slice 1 の postcondition）
  - 認証済みユーザーが存在する

postcondition:
  - POST /api/customers で Customer レコードが作成される（status='active'）
  - レスポンスに customer_id, status, created_at が含まれる
  - フレーバー嗜好が初期値として保存される

対象ファイル: api/customers.py, tests/test_customers.py
モデル推奨: medium（バリデーション判断あり）

### Slice 3: 来店記録 API

precondition:
  - Customer が status='active' で存在する（Slice 2 の postcondition と対応）

postcondition:
  - POST /api/visits で Visit レコードが作成される
  - フレーバー嗜好が記録されている
  - session_duration が記録されている
  - 来店日時が記録されている

対象ファイル: api/visits.py, models/visit.py, tests/test_visits.py
モデル推奨: medium（状態遷移ロジックあり）

## Gherkin シナリオ

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

  Scenario: 無効な顧客への来店記録拒否
    Given 無効状態の顧客が存在する
    When ユーザーが来店を記録しようとする
    Then エラーが返される
    And 来店記録は作成されない

## Closure Audit チェックリスト

以下の pre/post 対応を実コードで検証する：

- Slice 1 → 2: テーブル存在 + カラム定義が API 層で正しく利用されているか
- Slice 2 → 3: status='active' の postcondition が来店記録の precondition を満たすか
- Slice 2 → 3: customer_id の存在チェックが来店記録ガードで機能しているか
- Slice 3 内: フレーバー嗜好の postcondition（flavor_preferences が記録されている）が実際に満たされるか

上記 Gherkin シナリオの全 Scenario が実コードの導線で成立することを確認する。
```

---

## テンプレート構造

Opus が cluster spec を書くとき、以下のセクションを含める：

### 必須セクション（段階別）

#### 初期必須（全ての cluster spec に含める）

| セクション | 内容 |
|-----------|------|
| **目的** | この cluster が完了したとき何ができるようになるか |
| **他 cluster との依存** | 読み取り依存・書き込み依存・依存なしを明示 |
| **Interface 定義** | API エンドポイント or 内部 interface の契約 |
| **Design Slice 分割** | 各 design slice の precondition / postcondition / 対象ファイル / モデル推奨 |

#### 安定後に追加（Opus が提供するか、Main が pre/post から導出する）

| セクション | 提供者 | 内容 |
|-----------|--------|------|
| **Gherkin シナリオ** | Opus or Main（導出） | 主要ユーザーフローの Given-When-Then。正常系 + 主要な異常系 |
| **Closure Audit チェックリスト** | Opus or Main（導出） | pre/post の対応表 + シナリオの検証指示 |

Opus が Gherkin / closure checklist を提供しない初期段階では、
Main が pre/post から **derived operational scenarios** として導出する。
これは Opus の設計成果物ではなく、Main の運用成果物として扱う。

### DbC（pre/post）の書き方ルール

- precondition: この design slice の作業を開始するために **真でなければならない** 条件
- postcondition: この design slice が完了したとき **真になっていなければならない** 条件
- **Design slice N の postcondition は design slice N+1 の precondition を満たしていること**
  - 満たしていない場合、設計に穴がある。Opus は修正するか、間に design slice を追加する
- 状態遷移がある場合、「戻れない」条件も postcondition に含める

### Gherkin シナリオの書き方ルール

- 最低限: 正常系 1 + 主要な異常系 2 以上
- Given は **前提となる状態**（DB の状態、認証状態など）
- When は **ユーザーの操作**（API コール、画面操作など）
- Then は **期待される結果**（レスポンス、DB 状態変化、副作用など）
- 書けないシナリオがある場合、その機能の設計が固まっていない。実装に入らない

### Codex Main の使い方

Codex Main はこの cluster spec を受け取り：

1. pre/post の対応を確認する（design slice N.post ⊇ design slice N+1.pre）
2. 対応が取れない場合、ユーザーに報告して Opus に差し戻す
3. design slice を dispatch unit に分割する（必要なら更に細かく分割する）
4. 各 dispatch unit に mini / medium を判定する（Opus の推奨を参考に、厳格基準で判断）
5. Gherkin シナリオを Implementation subagent の acceptance criteria として渡す
6. closure audit 時に、チェックリストをそのまま reviewer に渡す
