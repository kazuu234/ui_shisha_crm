# ヘッドレスアーキテクチャと分権ガバナンス構想

> 本ドキュメントは、ヘッドレス型プロダクトにおけるUI契約管理・変更ガバナンスの**汎用フレームワーク（抽象）**を定義する。
> 特定プロダクトへの適用（具象）は別ドキュメントで行う。
>
> 関連ドキュメント：
> - [HEADLESS_PRODUCT_DESIGN_GUIDE.md](./HEADLESS_PRODUCT_DESIGN_GUIDE.md) — ヘッドレスXXX自体の構築フレームワーク
> - [HEADLESS_IDM_APPLICATION.md](./HEADLESS_IDM_APPLICATION.md) — 本フレームワークの具象適用例

---

## 1. 背景と問題意識

### 1.1 ヘッドレスXXXの台頭

AI時代において、プロダクトの価値は「画面の美しさ」から「APIの使いやすさ」に移行しつつある。

| 領域 | 従来（UI一体型） | ヘッドレス化 |
|------|------------------|-------------|
| CMS | WordPress | Contentful, Strapi |
| EC | Shopify | Medusa, Saleor |
| 認証 | 自前ログイン画面 | Auth0, Clerk |
| 決済 | 決済画面込み | Stripe |
| 通知 | Webメーラー | SendGrid, Novu |

**UIを持たないことの利点：**
- LLMがAPIを直接操作できる（UIパースのオーバーヘッドなし）
- APIテストで品質を担保しやすい（UIテストの不安定さを排除）
- 複数のUI/フロントエンドを自由に接続可能
- AIによる自動操作・オーケストレーションとの親和性が高い

### 1.2 ヘッドレスにしても結局UIが欲しくなる問題

ヘッドレスAPIを作ると、以下の循環に入る：

```
ヘッドレスAPI完成
  → 管理画面が欲しくなる → UIを作る
  → UIの使い勝手を改善したくなる → UI変更
  → UI変更がAPIとの仕様ズレを引き起こす
  → 仕様ズレがバグ・リグレッションを生む
  → テストが壊れる
  → 繰り返し
```

**この循環を制御する仕組みがなければ、ヘッドレスの利点は半減する。**

---

## 2. UIとAPIの契約管理フレームワーク

### 2.1 3段階のライフサイクル管理

```
     設計時               実装時              変更時
       ↓                   ↓                   ↓
 Capability Gap分析 → UI-API Manifest管理 → Schema Diff Pipeline
 「これ作れる？」      「何に依存？」        「何が壊れる？」
```

### 2.2 設計時：API Capability Contract

APIが「何を提供できるか」を宣言し、UIが「何を必要とするか」を宣言する。
そのギャップを**実装前に検出**する。

```yaml
# api-capabilities.yaml（APIが宣言する）
resources:
  User:
    read:
      fields: [id, name, email, department, role, created_at]
      filters: [department, role, name_contains]
      sort: [name, created_at]
      pagination: cursor
    write:
      create: true
      update:
        allowed_fields: [name, email, department]
        method: PUT
      delete: true
    batch:
      create: false
      update: false
      delete: true
```

```yaml
# ui-requirements.yaml（UIが宣言する）
screens:
  UserListPage:
    requires:
      User:
        read:
          fields: [id, name, email, department]
        write:
          inline_edit:
            fields: [name, department]
            method: PATCH  # ← APIはPUT onlyなのでGap検出
```

**Capability Gap検出ツールにより、実装前にAPI変更の必要性を特定。**

### 2.3 実装時：UI-API Manifest

各UIコンポーネントがどのAPIエンドポイント・フィールドに依存するかを明示的に管理する。

```yaml
# ui-api-manifest.yaml
components:
  UserListPage:
    file: src/pages/UserList.tsx
    depends_on:
      - endpoint: GET /api/users
        fields: [id, name, email, department]
    screenshot_url: /admin/users

  UserDetailPage:
    file: src/pages/UserDetail.tsx
    depends_on:
      - endpoint: GET /api/users/{id}
        fields: [id, name, email, department, manager_id, role]
    screenshot_url: /admin/users/1
```

#### 2.3.1 Manifestの初期構築手順（Bootstrap）

既存のUIに対してManifestを新規作成する場合の手順：

```
Step 1: 画面棚卸し
  └── 全画面・全コンポーネントの一覧を作成

Step 2: API依存の自動抽出（静的解析）
  └── ソースコードからAPI呼び出し箇所を機械的に抽出
      ├── fetch / axios / API client の呼び出し箇所を検索
      ├── 使用しているレスポンスフィールドを特定
      └── ツール例：AST解析、grep + 正規表現、LLMによるコード解析

Step 3: 自動抽出結果のレビュー
  └── 人間が確認し、以下を補正：
      ├── 動的に構築されるAPI呼び出し（変数展開等）
      ├── 間接的な依存（ストア経由等）
      └── 未使用フィールドの除外

Step 4: スクリーンショットURLの設定
  └── 各コンポーネントに対応する画面URLを記録
      → Schema Diff Pipeline（2.4）のVisual Regression対象

Step 5: CI統合
  └── Manifestとソースコードの乖離を検出するチェックをCIに追加
      → ソースに新しいAPI呼び出しが増えたらManifest更新を要求
```

**初期コストは高いが、一度作れば差分管理に移行できる。**
**Step 2の自動抽出で70-80%はカバーでき、残りを人間が補正する。**

#### 2.3.2 Manifestの維持ルール

```
Manifestの更新タイミング：
  ├── UIコンポーネントの新規追加時 → 新エントリを追加
  ├── UIコンポーネントが新しいAPIを参照した時 → depends_onを更新
  ├── UIコンポーネントの削除時 → エントリを削除
  └── APIエンドポイントの変更時 → 影響するエントリを更新

更新漏れの防止：
  ├── CIでソースコードとManifestの差分を検出（lint）
  ├── PRテンプレートにManifest更新チェックを含める
  └── 定期的な棚卸し（四半期等）で陳腐化を防ぐ
```

### 2.4 変更時：Schema Diff Pipeline

APIスキーマが変更された時、影響するUI画面を自動検出し、Visual Regressionテストを実行する。

```
① oasdiff でAPIスキーマのdiffを検出
  ↓
② ui-api-manifest から影響コンポーネントを特定
  ↓
③ Playwright で対象画面のスクリーンショット取得（Before/After）
  ↓
④ ピクセル比較 + マルチモーダルLLMによる判定
  ↓
⑤ 影響レポート生成 → PRコメントとして投稿
```

**ピクセル比較 =「変わったか」、AI判定 =「正しく変わったか」。両方実行する。**

---

## 3. UI変更のレベル分類とオートレーン

### 3.1 4段階のレベル定義

| Level | 種別 | 例 | API影響 | 出現頻度 |
|-------|------|-----|---------|---------|
| 0 | 純粋な見た目変更 | ボタン色、余白、フォント | なし | 50-60% |
| 1 | 表示データの増減 | 「部署名も表示したい」 | 既存データ有無次第 | 20-25% |
| 2 | 操作の追加・変更 | 「インライン編集したい」 | エンドポイント追加の可能性 | 10-15% |
| 3 | ワークフロー変更 | 「2画面を1画面に統合」 | ビジネスロジック変更の可能性 | 5-10% |

### 3.2 レーン設計

```
UI変更要求
  │
  ▼
┌─────────────┐
│ Level自動判定 │ ← ルールベース + AI のハイブリッド
└──────┬──────┘
       │
       ├── Level 0 ──→ 🟢 即マージ（CIパスすれば）
       │
       ├── Level 1 ──→ 🟢 capability照合
       │                   → Gap無し → 即マージ
       │                   → Gap有り → API拡張タスク自動起票
       │
       ├── Level 2 ──→ 🟡 capability照合 + 影響分析
       │                   → 後方互換なAPI追加で済む → 自動起票 + 自動マージ
       │                   → 既存API変更が必要 → 軽量な人間確認
       │
       └── Level 3 ──→ 🔴 分権判断機構（MAGI）へ
```

### 3.3 Level判定の自動化ロジック

```
UI diffを解析
  │
  ├── CSS/スタイルのみ変更？ → Level 0
  │
  ├── 新しいデータフィールド参照あり？
  │     └── api-capabilitiesに存在する？
  │           ├── Yes → Level 1（Gap無し）
  │           └── No  → Level 1（Gap有り）
  │
  ├── 新しいAPI呼び出し（POST/PUT/DELETE）追加？
  │     └── api-capabilitiesに存在する？
  │           ├── Yes → Level 2（既存capability内）
  │           └── No  → Level 2（API拡張必要）
  │
  └── 複数APIの呼び出し順序/依存関係が変化？
      または新しいトランザクション境界が必要？
        └── Yes → Level 3
```

**Level 0〜2の約90%以上がオートレーンで処理可能。**
**人間の判断が必要なのは全体の約3%（Level 3の一部）。**

### 3.4 複合変更の取り扱い（Compound Change Handling）

1つのPRに複数のLevelの変更が混在する場合の扱い：

#### 3.4.1 原則：原子分解してからLevel判定

```
複合変更PR
  │
  ├── Step 1: 変更要求を原子的な単位に分解
  │     └── 「1つの変更 = 1つのLevel判定」になるまで分解
  │
  ├── Step 2: 各原子変更にLevelを判定
  │     └── Level 0が3つ、Level 1が1つ、Level 2が1つ → それぞれ判定
  │
  ├── Step 3: 分離可能性を判断
  │     ├── 独立している → 個別にオートレーンに乗せる
  │     └── 依存関係がある → 最高Levelに統合して1つとして扱う
  │
  └── Step 4: 統合判定（依存ありの場合）
        └── 最高Level のレーンルールを全体に適用
```

#### 3.4.2 分解不能な場合

```
分解不能の基準：
  ├── 変更Aを適用しないと変更Bが意味をなさない → 依存あり
  ├── 変更A・Bが同一画面の同一コンポーネント内 → 通常は依存あり
  └── 変更A・Bが異なる画面 → 通常は独立

分解不能な場合のルール：
  └── 含まれる最高Level で判定する
      例：Level 0 + Level 2 が混在 → Level 2 として処理
```

**「大きなPRを1つ出す」のではなく「小さなPRに分割する」文化を推奨。**
**これはLevel判定の精度だけでなく、レビュー品質とロールバック容易性にも寄与する。**

---

## 4. 分権判断機構（MAGI アーキテクチャ）

### 4.1 着想

エヴァンゲリオンのMAGIシステムに着想を得た分権合議制。
3つの異なる視点を持つ判断者が独立に評価し、多数決で意思決定を行う。

MAGIにおける3つのスーパーコンピュータ（科学者・母・女としての人格）が
それぞれ異なる視点で判断を行うように、
本機構でも**関心の分離された3つの投票者**を配置する。

### 4.2 構成

```
┌─────────────────────────────────────────────┐
│           Level 3 判断パネル（MAGI）          │
│                                             │
│  🧑 人間アーキテクト     1票                  │
│     視点：ビジネス判断・政治判断・暗黙知        │
│                                             │
│  🤖 LLM-A（MELCHIOR）   1票                  │
│     視点：技術的構造整合性                     │
│     評価：API境界設計の一貫性、後方互換性、       │
│          データモデルへの影響                  │
│                                             │
│  🤖 LLM-B（BALTHASAR）  1票                  │
│     視点：リスク分析                          │
│     評価：セキュリティ影響、パフォーマンス影響、  │
│          既存UIの破壊範囲、ロールバック可能性    │
│                                             │
│  合意ルール：2/3 以上で決定                    │
└─────────────────────────────────────────────┘
```

**LLM同士は異なるモデル・異なるプロンプト・異なる評価軸を持たせる。**
同じ視点で2つ回しても意味がない。

### 4.3 判定マトリクス

| 人間 | LLM-A | LLM-B | 結果 | 備考 |
|------|-------|-------|------|------|
| ✅ | ✅ | ✅ | ✅ 即承認 | 全会一致 |
| ✅ | ✅ | ❌ | ✅ 承認 | リスク懸念をnoteに記録 |
| ✅ | ❌ | ✅ | ✅ 承認 | 構造懸念をnoteに記録 |
| ❌ | ✅ | ✅ | ⚠️ 承認 | 人間の懸念をログ、要フォローアップ |
| ✅ | ❌ | ❌ | ❌ 却下 | 人間だけYesは危険信号 |
| ❌ | ✅ | ❌ | ❌ 却下 | - |
| ❌ | ❌ | ✅ | ❌ 却下 | - |
| ❌ | ❌ | ❌ | ❌ 却下 | 全会一致で却下 |

### 4.4 Override機構

```
通常フロー：    2/3 多数決で自動処理
人間override：  理由を書けば拒否権を行使可能
安全弁：        override頻度が月に3回を超えたら判断基準の再校正を実施
```

- **人間✅ LLM❌❌**の場合：自動却下 + 「本当にやりますか？override理由を記述してください」
- **人間❌ LLM✅✅**の場合：承認するが、実装後のレビューポイントを自動設置

### 4.5 投票独立性の保証（Sealed Vote + Delphi法）

分権判断の品質は、各投票者の**独立性**に依存する。
投票中に他の判断者の結果が見えると、以下の汚染（Vote Contamination）が発生する：

- **アンカリングバイアス**: LLM-Aの結果を見たLLM-Bが引きずられる
- **忖度（Sycophancy）**: 人間の判断を見たLLMが迎合する
- **同調圧力**: LLM2票の結果を見た人間がラバースタンプ化する

**見えた瞬間に「独立した3票」が「追従した3票」に劣化する。**

#### 4.5.1 Sealed Vote（封印投票）プロトコル

```
Phase 1: 独立評価（相互不可視・並列実行）
┌──────────┐  ┌──────────┐  ┌──────────┐
│ MELCHIOR │  │ BALTHASAR│  │  人間    │
│ 評価中... │  │ 評価中... │  │ 評価中... │
│（他の結果 │  │（他の結果 │  │（他の結果 │
│ 見えない）│  │ 見えない）│  │ 見えない）│
└────┬─────┘  └────┬─────┘  └────┬─────┘
     │sealed       │sealed       │sealed
     ▼             ▼             ▼
┌─────────────────────────────────────────┐
│         Sealed Vote Storage              │
│  全員の投票が揃うまで開封しない            │
└────────────────┬────────────────────────┘
                 │ 全票揃った
                 ▼
Phase 2: 一斉開封 + 集計
┌─────────────────────────────────────────┐
│  MELCHIOR:  approve (confidence: 0.87)   │
│  BALTHASAR: reject  (confidence: 0.72)   │
│  人間:      approve                      │
│  ─────────────────────                   │
│  Result: approved (2/3)                  │
└─────────────────────────────────────────┘
```

**全投票者が提出完了するまで、いかなる中間結果も他の投票者に開示しない。**

#### 4.5.2 実装例

```python
import asyncio
from dataclasses import dataclass

@dataclass
class SealedVote:
    voter_id: str
    vote: str          # "approve" | "reject"
    reasoning: str
    confidence: float
    timestamp: str

async def magi_decision(change_request: dict) -> dict:
    """
    3つの投票を並列・独立に実行し、
    全票が揃ってから一斉開封する。
    """

    # Phase 1: 独立評価（並列実行、相互不可視）
    melchior_task = asyncio.create_task(
        evaluate_structure(change_request)    # LLM-A: 構造分析
    )
    balthasar_task = asyncio.create_task(
        evaluate_risk(change_request)         # LLM-B: リスク分析
    )
    human_task = asyncio.create_task(
        collect_human_vote(change_request)    # 人間: UI入力待ち
    )

    # 全票が揃うまで待機（途中結果は共有しない）
    votes = await asyncio.gather(
        melchior_task, balthasar_task, human_task
    )

    # Phase 2: 一斉開封 + 集計
    result = tally_votes(votes)

    # Phase 3: 開封後の相互参照（ここで初めて他の判断が見える）
    result["cross_review"] = generate_cross_review(votes)

    return result
```

**ポイント：`asyncio.gather` で並列実行し、途中結果を共有しない構造を強制する。**

#### 4.5.3 意見が割れた場合：Delphi法による再投票

Sealed Voteで1ラウンド目を行った後、**意見が割れた場合のみ**2ラウンド目を実施する。

```
Round 1: Sealed Vote（相互不可視）
  → 全会一致 → 即決定。Round 2 不要。
  → 意見が割れた（2:1 or 1:1:棄権）→ Round 2 へ

Round 2: Open Deliberation（相互可視）
  → 全員の Round 1 の reasoning を公開
  → 各投票者は他の意見を見た上で再投票
  → ただし「Round 1からの変更理由」の記述を必須とする
  → 変更理由なしの追従は無効票として扱う

Round 2 でも割れた → 最終判定ルール適用（2/3多数決）
```

**Round 1で独立判断の純度を保ち、Round 2で相互の視点を取り入れた再考を許す。**
これは専門家合議の手法として確立されたDelphi法そのもの。

#### 4.5.4 人間側UIのブロッキング設計

人間の投票UIにも、投票前にLLMの結果が見えない設計が必須。

```
❌ ダメなUI（LLM結果が見えている）：
┌──────────────────────────────────┐
│ MELCHIOR: approve ✅              │ ← 見えちゃってる
│ BALTHASAR: reject ❌              │ ← 見えちゃってる
│                                  │
│ あなたの判断: [ approve ] [ reject]│ ← 影響される
└──────────────────────────────────┘

✅ 正しいUI（投票確定まで非公開）：
┌──────────────────────────────────┐
│ 変更内容：〇〇〇〇               │
│ AI分析結果：🔒 投票後に開示        │
│                                  │
│ あなたの判断: [ approve ] [ reject]│
│ 理由: [________________]         │
│                                  │
│        [ 投票を確定する ]          │
└──────────────────────────────────┘

投票確定後（一斉開封）：
┌──────────────────────────────────┐
│ 🔓 全投票結果                     │
│ MELCHIOR:  approve (構造的に問題なし) │
│ BALTHASAR: reject  (ロールバック懸念) │
│ あなた:    approve (UX優先度が高い)   │
│                                  │
│ 結果: approved (2/3)              │
│ 注意: BALTHASARの懸念をフォローアップ │
└──────────────────────────────────┘
```

### 4.6 監査証跡

```json
{
  "decision_id": "ARCH-2026-0342",
  "change": "ユーザー作成と権限設定の1画面統合",
  "level": 3,
  "protocol": {
    "round_1": {
      "method": "sealed_vote",
      "all_votes_sealed_at": "2026-03-19T14:32:00Z",
      "unsealed_at": "2026-03-19T14:32:01Z"
    },
    "round_2": null
  },
  "votes": {
    "melchior": {
      "vote": "approve",
      "reasoning": "BFF層での吸収が可能。既存API互換性を維持。",
      "confidence": 0.87,
      "submitted_at": "2026-03-19T14:31:45Z"
    },
    "balthasar": {
      "vote": "reject",
      "reasoning": "権限設定のアトミック性が保証できない。部分失敗時のロールバック未定義。",
      "confidence": 0.72,
      "submitted_at": "2026-03-19T14:31:47Z"
    },
    "human": {
      "vote": "approve",
      "reasoning": "UX改善の優先度が高い。部分失敗はフェーズ2で対応。",
      "submitted_at": "2026-03-19T14:32:00Z"
    }
  },
  "result": "approved",
  "dissenting_notes": "BALTHASAR: 部分失敗リスクを指摘",
  "follow_up_tasks": ["TASK-1234: 複合操作のロールバック機構実装"],
  "integrity": {
    "vote_isolation_verified": true,
    "no_intermediate_disclosure": true
  }
}
```

**「なぜこの判断をしたか」が3つの視点から完全に記録される。SOX監査レベルのトレーサビリティ。**

---

## 5. OSSガバナンスとの類似性

この分権モデルは、OSSコミュニティが30年かけて有機的に進化させてきたパターンと本質的に同じ構造を持つ。

### 5.1 対応関係

| OSSの仕組み | 本構想での対応物 |
|-------------|----------------|
| Linux Kernelのサブシステムメンテナ | LLM-A（専門領域レビュー） |
| 上位メンテナ / BDFL | 人間アーキテクト（最終判断 + 拒否権） |
| Apache PMC投票（+1/-1） | 3票制の多数決 |
| -1拒否権に理由記述必須 | Override時の理由記述必須 |
| CI/Bot の自動チェック | Level 0〜2のオートレーン |
| CODEOWNERS | UI-API Manifestによる責任分離 |
| Rust RFCの複数チームレビュー | LLM-A / LLM-B の関心分離 |

### 5.2 OSSとの決定的な違い

OSSの課題：
- メンテナは無償ボランティア → レビューアー不足 → PRが放置
- 特定の人に判断が集中 → バーンアウト、バス係数1

LLM分権モデル：
- LLMは24/365、疲れない、コスト数セント
- 人間は「本当に人間にしかできない判断」だけに集中
- 大規模OSSでしか成立しなかったガバナンスが、小規模チームでも実現可能に

---

## 6. 本番インシデントからのフィードバックループ

### 6.1 インシデント起因の校正サイクル

本番でUI-API起因のインシデントが発生した場合、フレームワーク自体を校正する：

```
本番インシデント発生
  │
  ├── Step 1: 原因分類
  │     ├── Manifestの欠落/陳腐化 → Manifest更新 + CI強化
  │     ├── Level判定の誤り → 判定ロジック改善
  │     ├── MAGI判断の誤り → 判断基準の再校正
  │     └── Schema Diff Pipelineの検出漏れ → パイプライン改善
  │
  ├── Step 2: 根本原因の記録
  │     └── インシデントレポートに以下を記録：
  │         ├── 本来検出されるべきだったポイント
  │         ├── なぜ検出されなかったか
  │         └── 再発防止のためのフレームワーク改善案
  │
  ├── Step 3: フレームワーク改善の実施
  │     ├── Level判定ルールの追加・修正
  │     ├── Manifest CIチェックの強化
  │     ├── MAGI プロンプトの調整
  │     └── 必要に応じてオートレーンの閾値見直し
  │
  └── Step 4: 改善の検証
        └── 過去のインシデント事例を新ルールで再判定
            → 正しく検出されることを確認（回帰テスト的）
```

### 6.2 数値仮説のフィードバック

本ドキュメント中の数値（Level分布の出現頻度等）は**設計目標（仮説）**である。
実測値は以下のサイクルで校正する：

```
仮説（例：Level 0 = 50-60%）
  → 具象プロダクトで3ヶ月間計測
  → 実測値を集計（例：実測 Level 0 = 42%）
  → 乖離が大きい場合：
      ├── 仮説の数値を更新
      ├── Level判定ロジックの精度を検証
      └── 必要ならLevel定義自体を見直し
```

### 6.3 Override頻度に基づく校正

```
Override月間閾値（初期値: 3回）
  │
  ├── 閾値以下 → 正常運転
  │
  └── 閾値超過 → 校正フロー開始
        ├── Override事例の共通パターン分析
        ├── Level判定 or MAGI判定の改善候補を抽出
        ├── 改善案を適用
        └── 翌月のOverride頻度を観測 → 効果検証
```

---

## 7. まとめ：全体構想の構造

```
ヘッドレスXXXを作る
  ↓
UIが欲しくなる
  ↓
UIとAPIの仕様ズレが発生する ← ここが核心課題
  ↓
4つの仕組みで制御する：

  ① 設計フレームワーク化
     → API Capability Contract + UI Requirements の宣言的管理
     → 設計時点でGapを検出

  ② 変更影響の自動検出
     → Schema Diff Pipeline（oasdiff + manifest + Playwright + LLM判定）
     → 変更時にUI影響を自動追跡

  ③ 変更内容のレベル分類 + 分権判断機構（MAGI）
     → Level 0〜2: オートレーンで全自動処理（全体の90%以上）
     → Level 3: 人間1票 + LLM2票の合議制で判断
     → Override機構 + 監査証跡で安全性と透明性を確保

  ④ 本番インシデントからのフィードバック
     → インシデント原因の分類 → フレームワーク自体の校正
     → 数値仮説の実測フィードバック
     → Override頻度に基づく判断基準の自動校正
```

---

## 8. 設計方針

### 8.1 本ドキュメントの位置づけ

本ドキュメントは**フレームワーク（抽象）**を定義するものであり、
具体プロダクトへの適用（具象）は別ドキュメントで行う。

```
本ドキュメント（抽象）           適用ドキュメント（具象）
  interface / abstract class  →  concrete class
  ─────────────────────────      ─────────────────────────
  Capability Contract 仕様    →  IDMリソースのCRUD定義
  Level分類ルール             →  IDM管理画面のLevel判定
  MAGIプロトコル              →  IDMアーキテクチャ判断
  コスト・ROI                 →  具象側の責務
```

- **適用例：** [HEADLESS_IDM_APPLICATION.md](./HEADLESS_IDM_APPLICATION.md)

### 8.2 異常系に対する基本方針

異常系は「起きないようにする」のではなく「起きても戻せる」ことを保証する。

```
安全性の担保：
  ├── コード → git revert で可逆
  ├── API → バージョニングで旧版維持
  ├── Manifest → git管理で履歴保持
  └── MAGI判断 → 監査証跡 + ロールバック可能

LLMの独立性が不完全でも：
  → 判断が間違っていたら revert する
  → revert 事象を学習データとして判断基準を校正する
  → つまり「異常系の可逆性」がLLM独立性問題のフェールセーフ
```

### 8.3 数値目標について

本ドキュメント中の数値（Level分布の出現頻度等）は**設計目標（仮説）**である。
実測値は具象プロダクトで計測し、フィードバックループで校正する。

```
仮説設定 → 1プロダクトで適用 → 実測 → 仮説を補正 → 再適用
```

---

## 9. 今後の検討事項

- [ ] Capability Contract のスキーマ仕様の詳細設計
- [ ] Level自動判定エンジンのプロトタイプ実装
- [ ] Level判定の前段に「変更要求の原子分解」ステップを追加
- [ ] MAGI判断パネルのプロンプト設計（MELCHIOR / BALTHASAR の役割定義）
- [ ] Sealed Voteプロトコルの実装（投票独立性の技術的保証）
- [ ] Delphi法 Round 2 の「変更理由なし追従 = 無効票」判定ロジック
- [ ] 人間側投票UIのブロッキング設計（LLM結果の事前非公開）
- [ ] Override頻度に基づく判断基準の自動再校正アルゴリズム
- [ ] Manifest と実コードの乖離検出CI（静的解析との突合）
- [ ] Manifest 初期構築の半自動化ツール（AST解析 + LLM補正）
- [ ] 複合変更の自動分解ロジックのプロトタイプ
- [ ] インシデント → フレームワーク校正の記録テンプレート
- [ ] 複数UIチームの並行変更時のManifest排他制御・競合解決プロトコル
- [ ] Figmaプラグインとの連携（UIデザイン時にUI Requirementsを半自動生成）

---

> **本構想の本質：**
> OSSコミュニティが30年かけて体得した「分権ガバナンス」の知恵を、
> LLMの力でフレームワーク化し、小規模チームでも運用可能にする。
> 「UIを作らない」が最強のUI戦略になる時代に、
> 「UIを安全に作り続ける」ための仕組みを確立する。
