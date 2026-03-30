# Cursor Pre-flight Checklist

> Codex レビューの findings を蓄積し、Cursor が同じ失敗を繰り返さないためのチェックリスト。
> orchestrator は **毎回の dispatch 指示書にこのファイルのパスを含める**こと。

---

## 使い方

1. orchestrator が Cursor に dispatch する際、指示書の末尾に以下を追加する：
   ```
   ## Pre-flight Checklist
   実装完了後、PR を出す前に `docs/framework/CURSOR_PREFLIGHT_CHECKLIST.md` を読み、
   全項目をセルフチェックすること。違反があれば修正してからコミットすること。
   ```
2. 新しい finding パターンが発見されたら、本ファイルに追記する（design の責務）
3. Codex レビューが 1 発 PASS した Slice のパターンはポジティブ事例として記録する

---

## チェックリスト

### 1. テストの網羅性（最頻出 — 6/17 findings）

- [ ] **設計書の Gherkin シナリオに 1:1 対応するテストがあるか**
  - 設計書に `Scenario:` が 10 個あればテストも 10+ 個必要
  - 「動くから OK」ではなく「設計書のシナリオが全部カバーされているか」
- [ ] **postcondition の全項目にテストがあるか**
  - postcondition に「〜が動作する」と書かれていれば、それを検証するテストが必要
  - 特に「エラーレスポンス」セクションの各エラーコードに対するテスト
- [ ] **エッジケースのテストがあるか**
  - 並行リクエスト（select_for_update 系）
  - 未捕捉例外時の挙動
  - 空入力・境界値
  - 既に処理済みのリソースへの再操作

> **実例**: C01-S3 で `request_in_progress`, `stale recovery`, `同一キー別パス→409` のテストが欠落して 5 ラウンドかかった

### 2. 設計書との完全一致（4/17 findings）

- [ ] **フィールド型が設計書と一致しているか**
  - 設計書が `JSONField` なら `JSONField`。理由があっても勝手に `TextField` に変えない
  - 変更が必要な場合は設計の問題なので、実装側で判断せず停止して報告する
- [ ] **レスポンスのフィールド名が設計書と一致しているか**
  - `role` と `staff_type` は別物。設計書の Interface 定義を文字通りに実装する
- [ ] **設計書の「明示シナリオ」を全て実装したか**
  - 設計書の Gherkin に「Scenario: 同一キーを別エンドポイントに再利用すると 409」と書いてあれば、それは仕様であり、実装+テストが必須

> **実例**: C02-S1 で `staff_type` をそのまま返したが、設計は `role` (owner/staff) を要求していた

### 3. トランザクション・統合設計（3/17 findings）

- [ ] **設計書に「transaction.atomic()」「SAVEPOINT」と書いてあれば、その通りに実装したか**
  - 特に AuditLogger の SAVEPOINT 設計: 外側 atomic + 内側 atomic(savepoint) のネスト構造
- [ ] **Middleware ↔ ViewSet ↔ Service の接続が実際に動作するか**
  - Middleware が `request.xxx` にセットする値を、下流が `getattr(request, 'xxx', None)` で取得できるか
  - signal が `apps.py` の `ready()` で正しく登録されているか
- [ ] **未捕捉例外時のフォールバックがあるか**
  - `try/finally` で metrics・ログが記録されるか
  - 例外が握りつぶされていないか

> **実例**: C01-S2 で AuditLogger.log() が SAVEPOINT として動作しておらず、業務処理と同一トランザクションになっていなかった

### 4. scope 厳守（3/17 findings）

- [ ] **変更ファイルが設計書の「対象ファイル」に列挙されたものだけか**
  - 列挙外のファイルを変更した場合、その変更が本当に必要か再確認
  - 「ついでにリファクタ」は禁止。次の Slice でやるべき
- [ ] **設定ファイル（base.py 等）の変更が最小限か**
  - 自分の Slice で追加する設定のみ。既存設定の位置変更やコメント追加は scope 外
- [ ] **conftest.py の変更に理由コメントがあるか**
  - fixture の追加・削除にはコメントで理由を明記する

> **実例**: C01-S4 で base.py に TRUSTED_PROXY_IPS の位置変更が混入して減点

### 5. stub/placeholder の撲滅（1/17 findings）

- [ ] **空ファイル・空クラス・TODO コメントが実利用経路に残っていないか**
  - `test_utils.py` が空、`pass` だけの関数、`# TODO: implement` — 全て NG
  - 不要なら削除する。必要なら実装する
- [ ] **`pass` だけのテストメソッドがないか**

> **実例**: C01-S1 で `core/test_utils.py` が placeholder のまま残っていた

### 6. バリデーション・ドメインロジックの防御的実装（4 findings — C04-S3 で発見）

- [ ] **入力バリデーションで型チェックをしているか**
  - DRF の Serializer は `IntegerField` でも JSON の `true/false` を int として通す（Python の `isinstance(True, int) == True`）
  - **明示的に `isinstance(value, bool)` で弾く**か、`not isinstance(value, int) or isinstance(value, bool)` でガードする
  - 必須キーの存在チェック、min > max の逆転チェックも忘れずに
- [ ] **設計書に「モデル層バリデーション」と書いてあれば、Serializer だけでなく Model.save() にも実装したか**
  - Serializer バリデーションは API 経由のみ。admin/shell/signal 経由のデータは素通りする
  - 設計書に `validate_store_thresholds()` クラスメソッドとあれば、それは Model 層の実装を意味する
- [ ] **バッチ処理で「中間状態」を考慮しているか**
  - 複数レコードをループで更新する場合、途中の状態で整合性チェックが走ると失敗する
  - `get_or_create` は内部で `save()` を呼ぶ — カスタム `save()` にバリデーションがあると中間状態で発火する
  - **対策**: ループ中は `validate_integrity=False` 等でバリデーションを抑制し、ループ後に一括検証
- [ ] **初期状態・不完全データでクラッシュしないか**
  - `seed_store` 未実行、マイグレーション直後、テストの fixture 不足 — データが 0 件や不完全な状態でもエラーにならないか
  - 特に `bulk_recalculate` のような一括処理は、前提データが揃っていない場合に安全に no-op すること

> **実例**: C04-S3 で `get_or_create` が内部 `save()` を呼び、バッチ更新中の中間状態でモデル層バリデーションが発火してエラー。`isinstance(True, int) == True` で bool が int バリデーションを通過。閾値 3 件未満の初期状態で `bulk_recalculate` がクラッシュ

---

## ポジティブ事例（1 発 PASS したパターン）

### C03-S1 Customer モデル — 0 fix, 0 review rounds
- シンプルなモデル定義のみ
- 対象ファイルが 3 つだけ（models.py, migrations/, tests/）
- scope が明確で余計な変更なし

### C04-S1 Visit モデル — 0 fix, 0 review rounds
### C04-S2 来店 CRUD — 1 fix のみ
### C05a-S2 タスクサービス — 1 fix のみ
- チェックリスト導入後の Slice
- 1 fix は transaction.atomic() の追加のみ（チェックリスト項目 3 に該当）

**教訓**: scope が小さく、設計書と 1:1 で実装できる Slice は失敗しにくい。チェックリスト導入後は API 実装系も 1 fix で収束する傾向

---

## Finding ログ（時系列）

| 日付 | Slice | Round | Score | カテゴリ | 概要 |
|------|-------|-------|-------|---------|------|
| 2026-03-29 | C01-S1 | R1 | 86 | 統合漏れ | create_superuser の REQUIRED_FIELDS 不整合 |
| 2026-03-29 | C01-S1 | R1 | 86 | stub残留 | core/test_utils.py が placeholder |
| 2026-03-29 | C01-S2 | R1 | 69 | 統合漏れ | SAVEPOINT 設計が未実装 |
| 2026-03-29 | C01-S3 | R1 | 80 | テスト不足 | ViewSet の @idempotency_exempt、リプレイヘッダー |
| 2026-03-29 | C01-S3 | R5 | 85 | 設計逸脱 | response_body を JSONField→TextField に勝手変更 |
| 2026-03-29 | C01-S3 | R5 | 85 | テスト不足 | 別パス再利用409、異ユーザー同キーのテスト欠落 |
| 2026-03-29 | C01-S4 | R1 | 86 | テスト不足 | RequestLoggingMiddleware テスト欠落 |
| 2026-03-29 | C01-S4 | R1 | 86 | scope外 | base.py に不要な差分混入 |
| 2026-03-29 | C01-S4 | R2 | 94 | 統合漏れ | 未捕捉例外時に metrics/ログ未記録 |
| 2026-03-29 | C03-S1 | R1 | 100 | — | 1発PASS |
| 2026-03-29 | C02-S1 | R1 | 80 | 設計逸脱 | staff_type を role として返却 |
| 2026-03-29 | C02-S1 | R1 | 80 | テスト不足 | CSRF テスト欠落 |
| 2026-03-30 | C04-S3 | R1 | — | バリデーション不足 | 型チェックなし（bool が int 通過）、必須キー未チェック、min>max 未チェック |
| 2026-03-30 | C04-S3 | R2 | — | 要件漏れ | 設計書の validate_store_thresholds() がモデル層に未実装 |
| 2026-03-30 | C04-S3 | R3 | — | エッジケース | bulk_recalculate が閾値 <3 件でクラッシュ |
| 2026-03-30 | C04-S3 | R4 | — | ORM の罠 | get_or_create の暗黙 save() でバッチ中間状態にバリデーション発火 |

---

## メンテナンス

- **追記タイミング**: Codex レビューで新しいパターンの finding が出るたびに追記
- **追記者**: design（設計専任）が分析して追記する。orchestrator は finding ログのみ追記してよい
- **棚卸し**: 5 Slice ごとに傾向を再分析し、チェックリストの優先順位を見直す

## Review Log

- [2026-03-29] v1 — PR#57〜#62 の findings から初版作成（12 findings 分析）
- [2026-03-30] v2 — C04-S3 の 4 fix を分析し「6. バリデーション・ドメインロジック」カテゴリ追加。bool/int の罠、バッチ中間状態、初期データ不足の 3 パターン
