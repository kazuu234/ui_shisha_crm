# Review Scorecard

作成日: 2026-03-20

## 目的

このファイルは、subagent review を行うときの採点基準です。
review subagent はこの基準で採点し、`100点` を出せるまで implementation subagent に差し戻します。

review subagent の推奨モデル設定:

- model: `gpt-5.4`
- reasoning effort: `xhigh`

## 結論

- merge には `PASS (100/100)` + Main の smoke test 完了 の **両方** が必要
- reviewer はコードと証跡を評価して PASS/FAIL を判定する（reviewer の責務）
- Main は smoke test で runtime 動作を確認する（Main の責務）
- reviewer が runtime 確認できない項目は `要 smoke test` としてマークし、
  **その項目を理由に減点しない**（Main の smoke test で担保する）
- 未確認、stub、未接続、未完了、open finding が1つでもあれば `100点` は付けない
  （ただし `要 smoke test` マーク項目は除く）
- review は、その dispatch unit 開始時に固定した仕様基準に対して行う

## 仕様基準の扱い

review subagent は、常に「その dispatch unit の開始時点で main agent が固定した仕様基準」に対して採点する。

原則:

- 進行中 dispatch unit の review 基準は途中で自動更新しない
- 実装中に設計書やガイドが更新されても、その差分は次の dispatch unit で扱う
- 途中で新仕様を今の dispatch unit に含めるなら、main agent が acceptance criteria を再定義し、dispatch log に基準変更を明記してから再開する

このルールにより、reviewer が「着手後に追加された仕様」で後出し減点することを防ぐ。

## 必須ゲート（Stage 1: Reviewer の責務）

次のどれか1つでも満たしていなければ、review score は最大 `99点` に制限する。
reviewer がコードと証跡から判定できる項目のみ。

1. 指示された実装範囲が未完了
2. stub / skeleton / TODO / placeholder が実利用経路に残っている
3. review 時点で unresolved finding が残っている
4. 最終報告が実装状態を誤認させる表現になっている
5. 指示範囲外の変更が review 未承認のまま混入している
6. 既存機能を壊している可能性が高い変更が unresolved のまま残っている

## Smoke Test ゲート（Stage 2: Main の責務）

以下は reviewer ではなく Main が smoke test で確認する。
reviewer はこれらを `要 smoke test` としてマークし、**減点しない**。

1. user/admin/operator の end-to-end 導線が実際に通るか
2. runtime で使うはずの provider / DB alias / 設定経路が実際に使われるか
3. reviewer が `要 smoke test` としてマークしたその他の項目

## 採点項目

合計 `100点`

### 1. 指示範囲の完了度: 30点

観点:

- 与えたタスク範囲を全部終えているか
- `途中まで` を `完了` と報告していないか
- 関連する上流導線まで接続されているか
- 関連する下流導線まで接続されているか

減点例:

- エンドポイントはあるが、そこへ到達する導線がない
- ボタンだけあるが遷移先未接続
- API はあるが POST 後の処理が未実装
- 管理画面はあるが実データで開けない

### 2. 機能的完全性: 20点

観点:

- ユーザーまたは管理者が実際に目的を達成できるか
- 主要正常系が最後まで通るか
- 主要な異常系が破綻しないか
- 要件に反する穴がないか

ここでいう主要な異常系:

- バリデーションエラー
- 権限不足
- 対象データなし
- 期限切れ
- 無効トークン
- 二重実行

### 3. 要件網羅性: 15点

観点:

- 仕様書（プロダクト固有の設計ドキュメント）に照らして不足がないか

ただし、ここで照合する対象は `最新の全資料` ではなく、`その dispatch unit でロックされた仕様基準` である。

減点例:

- 仕様変更が設計にはあるがコードへ未反映
- ガイドに反する簡易実装
- 外部レビューで指摘済みの観点が取りこぼされている

### 4. 品質・堅牢性: 15点

観点:

- エラー処理
- 境界条件
- 外部連携（DB / API / LINE通知 / ジョブ等）の扱い
- misleading な内部状態依存がないか
- 既存機能を壊していないか
- 指示範囲外の不要なリファクタが混ざっていないか

減点例:

- config があるだけで runtime path 未確認
- env を読んでいるが実際には使っていない
- 共有 service の変更で既存導線が壊れる
- 指示範囲外の変更が混ざって review コストと回帰リスクを増やしている

### 5. テスト・検証の妥当性: 10点

観点:

- 変更に見合った test、または手動検証 / smoke check の証跡があるか
- 重要導線を route / API レベルで確認しているか
- 単体テストだけで誤魔化していないか

運用メモ:

- タスクに test 追加まで含まれている場合は、自動 test を強く要求する
- タスクに test 追加が含まれていない場合でも、最低限の手動検証や request-level 検証の証跡は要求する

### 6. 報告の正確性: 10点

観点:

- 実装済み/未実装/未検証の区別が正しいか
- 完了報告が誇張されていないか
- 未完を done と書いていないか

## review subagent の出力フォーマット

review subagent は最低でも次を返す。

### Verdict

- `PASS` または `FAIL`

### Score

- `/100`

### Findings

- severity 順
- file/path 明記
- 要件漏れか、品質問題か、統合漏れかを区別

### Gate Check

- 必須ゲートを全部満たしたか
- reviewer が自分で確認できたこと / 確認不能だったことを区別すること

### Pushback

- implementation subagent に返すべき修正指示

## 100点の条件（Stage 1 で reviewer が判定する範囲）

`100点` は次を全部満たした時だけ。

- 指示範囲が完全に終わっている
- open finding がない
- stub / TODO / placeholder が実経路にない
- 要件漏れがない
- 既存導線を壊していない（コード上の判断）
- 指示範囲外の不要変更がない
- 報告に誇張がない
- runtime 確認が必要な項目は `要 smoke test` でマークされている

注: end-to-end 導線の **実際の動作確認** は Stage 2（Main の smoke test）で行う。
reviewer はコードレベルで導線が接続されているかを確認し、
runtime での検証が必要な項目は `要 smoke test` とマークする。

## 実務上の運用

- review subagent が `100点` 以外を出したら、implementation subagent に差し戻す
- main agent は review コメントをそのまま渡すのではなく、次の最小修正単位に切って返す
- main agent は `100点` が出ても、merge 前に自分で最終 smoke test を行う
- review subagent が runtime 確認を行えない場合、その項目は `要 smoke test` とマークする
  - `要 smoke test` 項目は reviewer の減点対象外（Main の smoke test で担保する）
  - Main は merge 前に `要 smoke test` 項目を全て実行し、PASS/FAIL を判定する
  - smoke test で FAIL なら merge しない（review score とは独立した gate）

## Merge の2段階ゲート

```
reviewer: コード + 証跡を評価 → PASS (100/100) or FAIL
  │
  ├── FAIL → pushback → 再実装 → 再レビュー
  │
  └── PASS (100/100)
        │
        ▼
Main: 「要 smoke test」項目を実行 → runtime PASS or FAIL
  │
  ├── FAIL → pushback（runtime で発見した問題を指示）
  │
  └── PASS → merge
```
