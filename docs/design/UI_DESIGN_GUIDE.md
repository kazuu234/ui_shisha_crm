# UI 実装方針書 (Design Guide)

> 企画書: `docs/design/UI_PROPOSAL.md`
> スタイルガイド（実物参照）: `docs/design/assets/styleguide.html`
> 本書は UI 実装者（Cursor / Codex）が従うべきデザイントークン・コンポーネント・インタラクションの定義書である。

## 1. デザインフィロソフィ

### なぜこのデザインか

シーシャバーは暖色の電球に照らされた暗い店内で営業する。スタッフはこの環境でタブレットを操作する。デザインは以下の 3 つの要件を同時に満たす必要がある。

| 要件 | 内容 |
|------|------|
| **視認性** | 暗い店内で画面が自然光源として機能する。ウォームホワイトのベースは眩しすぎず、テキストとのコントラストを確保する |
| **上質感** | 「ハイセンスな作業ツール」としてスタッフが使って誇れるもの。POS 感を排除し、Apple ミニマル × 高級バーの美学を実現する |
| **速度** | 接客しながら操作する。1 項目タッチ 1〜2 回の原則を、ゾーンベースのインタラクションで実現する |

### 2 系統の美学

| UI 系統 | 美学 | キーワード |
|---------|------|-----------|
| **スタッフ UI（タブレット）** | Apple ミニマル × 高級バーの上質感。ウォームホワイト × ディープティール。ゾーンベースの大きなタッチ領域。余白が仕事をするレイアウト | 温かい、洗練、タッチファースト |
| **オーナー UI（PC）** | 事務アプリ的な普通さ。ライト系。情報密度優先。テーブル・フォームの標準的な PC UI | 清潔、効率、情報密度 |

両系統はカラーパレットとタイポグラフィを共有するが、コンポーネントとインタラクションモデルは完全に異なる。

## 2. カラーパレット

### ベースカラー

| Token | 用途 | HEX | 説明 |
|-------|------|-----|------|
| `--bg-base` | ページ背景 | `#FAF9F6` | ウォームホワイト。純白（`#FFF`）ではなくクリーム寄り。暗い店内で眩しすぎない |
| `--bg-surface` | カード・ゾーン背景 | `#FFFFFF` | ベースとの微差で浮き上がりを表現 |
| `--bg-surface-alt` | ヘッダー・選択中の行 | `#F3F1ED` | surface より一段沈んだ面 |
| `--bg-inset` | 窪み・非アクティブ領域 | `#EBE8E2` | 最も沈んだ面 |
| `--border-default` | カード・ゾーン境界 | `#E0DCD4` | 暖色系のボーダー |
| `--border-strong` | ホバー時のボーダー | `#C8C3BA` | より強調されたボーダー |

### テキストカラー

| Token | 用途 | HEX |
|-------|------|-----|
| `--text-primary` | 見出し・本文 | `#1C1917` |
| `--text-secondary` | 補助テキスト・メタ情報 | `#57534E` |
| `--text-muted` | プレースホルダー・ラベル | `#A8A29E` |
| `--text-inverse` | アクセント背景上のテキスト | `#FAF9F6` |

**コントラスト比**:
- `--text-primary` on `--bg-base` = 15.2:1（WCAG AAA）
- `--text-secondary` on `--bg-base` = 6.8:1（WCAG AA）
- `--text-muted` on `--bg-base` = 3.0:1（WCAG AA 不合格）

**`--text-muted` の使用制限**:
- `--text-muted` はコントラスト比が WCAG AA を満たさないため、**情報伝達に必須でないテキストのみ**に使用可
- 使用可: プレースホルダー、ヘルプテキスト、装飾的ラベル
- **使用禁止**: テーブルヘッダー（情報のカテゴリ表示）、ナビゲーションラベル（※disabled 状態を除く — WCAG 2.1 SC 1.4.3 は非アクティブ UI コンポーネントをコントラスト要件の対象外とするため）、エラーメッセージ
- テーブルヘッダー・ナビ非アクティブには `--text-secondary`（6.8:1、WCAG AA 合格）を使うこと
- 12px 以下のテキストには `--text-muted` を使わない（小サイズ × 低コントラストは視認不可。ただし disabled 状態を除く — WCAG 2.1 SC 1.4.3 例外）

### アクセントカラー: Deep Teal

ウォームホワイトのベースに対して寒色のコントラストが効く。暖かい空間に涼しいアクセント。

| Token | 用途 | HEX |
|-------|------|-----|
| `--accent` | ボタン・リンク・アクティブ状態 | `#2D7D7B` |
| `--accent-hover` | ホバー状態 | `#246563` |
| `--accent-active` | アクティブ（押下）状態 | `#1B4E4D` |
| `--accent-subtle` | チップ選択背景・フォーカスリング | `#D4EDEB` |
| `--accent-light` | ゾーン展開背景・タスク背景 | `#EBF7F6` |

### セマンティックカラー

| Token | 用途 | HEX |
|-------|------|-----|
| `--success` | 成功・常連バッジ | `#4A7C59` |
| `--success-subtle` | 常連バッジ背景 | `#E4F0E8` |
| `--warning` | 警告・リピートバッジ | `#B8860B` |
| `--warning-dark` | リピートバッジテキスト | `#8B6914` |
| `--warning-subtle` | リピートバッジ背景 | `#FDF3DC` |
| `--error` | エラー・削除 | `#B91C1C` |
| `--error-hover` | Danger ボタンホバー | `#991B1B` |
| `--error-subtle` | エラー背景 | `#FDE8E8` |

### 禁止事項

- 上記以外の色を新規に追加しない。追加が必要な場合は Design Guide の改定を経る
- `opacity` でグレーを作らない。定義済みの `--text-muted` / `--border-default` 等を使う
- アクセントカラーをテキスト背景に使わない（`--accent-light` / `--accent-subtle` を使う）

## 3. タイポグラフィ

### フォント

| Token | フォントスタック | 用途 |
|-------|----------------|------|
| `--font-sans` | `"Inter", "Noto Sans JP", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif` | 全テキスト |
| `--font-mono` | `"JetBrains Mono", "Noto Sans JP", monospace` | コード・トークン表示（管理画面のみ） |

**フォント選定理由:**
- **Inter**: 無料。UI に最適化されたサンセリフ。大きいサイズでも小さいサイズでも破綻しない
- **Noto Sans JP**: 無料。日本語の可読性が高い。Inter とのウェイト感が揃う
- **読み込み**: Google Fonts CDN。ウェイトは 400（Regular）、500（Medium）、600（SemiBold）、700（Bold）の 4 種

### タイプスケール

| レベル | サイズ | ウェイト | 用途 |
|--------|--------|---------|------|
| **H1** | 22px | 700 | ページタイトル（`顧客一覧`） |
| **H2** | 17px | 700 | セクションタイトル（`直近の来店履歴`） |
| **H3** | 15px | 600 | カードタイトル（`ヒアリングタスク`） |
| **Body** | 15px | 400 | 本文 |
| **Small** | 13px | 400 | メタ情報・キャプション |
| **Overline** | 12px | 600 | ラベル（uppercase / letter-spacing: 0.06em） |

### スタッフ UI のフォントサイズ補正

スタッフ UI（タブレット）は全てのテキストを PC より 1 段大きくする。

| レベル | Owner UI (PC) | Staff UI (Tablet) |
|--------|---------------|-------------------|
| H1 | 22px | 22px |
| H2 | 17px | 17px |
| Body | 15px | 16px |
| Input | 15px | 17px |
| Button | 14px | 16〜17px |

### 行間

| コンテキスト | line-height |
|-------------|-------------|
| 見出し | 1.3 |
| 本文 | 1.6 |
| UI ラベル・ボタン | 1.0 |

## 4. スペーシング・レイアウト

### スペーシングスケール（4px グリッド）

| Token | 値 | 主な用途 |
|-------|-----|---------|
| `--space-1` | 4px | アイコンとテキストの隙間 |
| `--space-2` | 8px | バッジの内側余白、チップ間 |
| `--space-3` | 12px | ボタンの内側余白（垂直）、テーブルセル |
| `--space-4` | 16px | カード内側余白、フォームグループ間 |
| `--space-5` | 20px | ゾーンの内側余白 |
| `--space-6` | 24px | セクション間 |
| `--space-8` | 32px | 大きなセクション間 |
| `--space-10` | 40px | ページの外側余白 |
| `--space-12` | 48px | - |
| `--space-16` | 64px | セクショングループ間 |

**ルール**: 上記以外の値を使わない。`margin: 7px` のような半端な値は禁止。

### 角丸（Border Radius）

| Token | 値 | 用途 |
|-------|-----|------|
| `--radius-sm` | 6px | ボタン、テキスト入力 |
| `--radius-md` | 10px | カード、ゾーン、ドロップダウン |
| `--radius-lg` | 16px | モーダル、シェル |
| `--radius-full` | 9999px | バッジ、チップ、アバター |

### Elevation（影の階層）

ベタっとしたデザインを防ぐための depth 言語。全てのカード・ゾーンに適切な影を与える。

| レベル | Token | 用途 | 状態 |
|--------|-------|------|------|
| **Level 0** | なし（`border` のみ） | フラット要素、inset | 静止 |
| **Level 1** | `--shadow-sm` | カード、ゾーン、テキスト入力 | 静止 |
| **Level 2** | `--shadow-md` | カードのホバー、ドロップダウン | インタラクション中 |
| **Level 3** | `--shadow-lg` | モーダル、トースト | オーバーレイ |
| **Level 4** | `--shadow-xl` | 検索モーダル（大）| フルスクリーンオーバーレイ |

**ルール**:
- カードは常に `--shadow-sm` 以上を持つ。影なしのカードは禁止（ベタっと問題の防止）
- ホバー時は必ず 1 段上げる（`sm` → `md`）
- ホバー時に `translateY(-1px)` を加え、浮き上がりを表現する
- アクティブ（押下）時は影を下げて「押し込み」を表現する

### スタッフ UI レイアウト

```
┌─────────────────────────────────────┐
│  Topbar: タイトル    操作者名バッジ  │  44px
├─────────────────────────────────────┤
│                                     │
│  Content Area                       │
│  (scrollable)                       │
│                                     │
│  padding: --space-5 (20px)          │
│                                     │
├─────────────────────────────────────┤
│ BottomTab: 顧客|接客|来店記録|マッチング │ 56px
└─────────────────────────────────────┘
```

- Topbar: 固定。ページタイトル + 操作中スタッフ名
- Content: スクロール可能。ゾーンが縦に並ぶ
- Bottom Tab: 固定。アイコン + ラベル

### オーナー UI レイアウト

```
┌──────────┬──────────────────────────┐
│          │                          │
│ Sidebar  │  Content Area            │
│ 220px    │  padding: --space-6      │
│          │                          │
│ Brand    │  H1: ページタイトル       │
│ Nav      │  Table / Form / Cards    │
│          │                          │
│          │                          │
└──────────┴──────────────────────────┘
```

- Sidebar: 固定幅 220px。ブランド名 + ナビゲーション
- Content: スクロール可能

## 5. コンポーネントパターン

> 全コンポーネントの実物は `docs/design/assets/styleguide.html` を参照

### ボタン

| 種別 | クラス | 用途 |
|------|--------|------|
| **Primary** | `.btn-primary` | 主アクション（来店記録作成、登録） |
| **Secondary** | `.btn-secondary` | 副アクション（キャンセル、戻る） |
| **Ghost** | `.btn-ghost` | 補助アクション（もっと見る、リンク的） |
| **Danger** | `.btn-danger` | 破壊的アクション（削除） |

**タッチサイズ**: スタッフ UI のボタンは `min-height: 48px`（`.btn-lg`）。44px 以下のタッチターゲットは禁止。

### インタラクティブ要素の状態定義

全てのインタラクティブ要素は以下の状態を定義すること。未定義の状態があってはならない。

| 状態 | Button Primary | Button Secondary | Button Danger | Button Ghost |
|------|---------------|-----------------|--------------|-------------|
| **default** | `--accent` bg, `--text-inverse` text, `--shadow-sm` | `--bg-surface` bg, `--border-default` border, `--shadow-sm` | `--error` bg, `--text-inverse` text, `--shadow-sm` | transparent bg, `--accent` text |
| **hover** | `--accent-hover` bg, `--shadow-md`, `translateY(-1px)` | `--bg-surface-alt` bg, `--border-strong`, `--shadow-md`, `translateY(-1px)` | `--error-hover` bg, `--shadow-md`, `translateY(-1px)` | `--accent-light` bg |
| **active** | `--accent-active` bg, shadow なし, `translateY(0)` | `--bg-inset` bg, shadow なし, `translateY(0)` | `--error-hover` bg, shadow なし, `translateY(0)` | `--accent-subtle` bg |
| **focus-visible** | `--accent` bg + 3px `--accent-subtle` リング | 同 default + 3px `--accent-subtle` リング | `--error` bg + 3px `--error-subtle` リング | 3px `--accent-subtle` リング |
| **disabled** | `--bg-inset` bg, `--text-muted` text, shadow なし, `cursor: not-allowed` | 同左 | 同左 | `--text-muted` text, `cursor: not-allowed` |
| **loading** | default と同じ外観 + スピナーアイコン表示 + `pointer-events: none` | 同左 | 同左 | 同左 |

| 状態 | Chip | Zone | Tab | Sidebar Item |
|------|------|------|-----|-------------|
| **default** | `--bg-surface` bg, `--border-default` border | `--bg-surface` bg, `--shadow-sm` | `--text-secondary` text | `--text-secondary` text |
| **hover** | `--accent-light` bg, `--accent` border | `--shadow-md` | `--text-primary` text | `--text-primary` text, `--bg-surface-alt` bg |
| **active/selected** | `--accent` bg, `--text-inverse` text | `--accent-light` bg | `--accent` text | `--accent` text, `--accent-light` bg |
| **focus-visible** | 3px `--accent-subtle` リング | 3px `--accent-subtle` リング | 3px `--accent-subtle` リング | 3px `--accent-subtle` リング |
| **disabled** | `--bg-inset` bg, `--text-muted` text | `--bg-inset` bg, `--text-muted` text | `--text-muted` text, `cursor: not-allowed`（opacity 不使用。WCAG 2.1 SC 1.4.3 により非アクティブ UI は contrast 要件対象外） | `--text-muted` text, `cursor: not-allowed`（同左） |
| **loading** | N/A（選択 UI のためローディングなし） | スケルトンローダー表示 | N/A | N/A |

**注**: Chip / Tab / Sidebar Item は loading 状態を持たない（ユーザー操作に対する即時応答のみ）。Zone は非同期データ取得中にスケルトンローダーを表示する場合がある。

### カード

全てのカードに `--shadow-sm` を与える。ホバー可能なカードには `:hover` で `--shadow-md` + `translateY(-1px)`。

### ゾーン（スタッフ UI 専用）

スタッフ UI ではフォーム入力をゾーンベースで行う。**従来の `<input>` / `<textarea>` を画面上にそのまま配置しない。**

| ゾーン状態 | 外観 | 説明 |
|-----------|------|------|
| **Collapsed (empty)** | ラベル + 「タップして入力」+ chevron | 未入力。タップで展開 |
| **Collapsed (filled)** | ラベル + 値 + chevron | 入力済み。タップで再編集 |
| **Expanded (selection)** | ラベル + チップ群がインライン展開 | 選択肢がその場に出現。1 タップで選択 → 自動で collapse |
| **Expanded (text)** | ラベル + テキストエリア + 「完了」ボタン | その場にテキストエリアが展開。他のゾーンは見えたまま |

### ゾーングループ

関連するゾーンを 1 枚のカードにまとめる。各ゾーンは独立して展開/折りたたみ。

### インタラクションモデル（スタッフ UI）

| 入力タイプ | 方式 | 理由 |
|-----------|------|------|
| 顧客検索 | **モーダル** | 結果一覧に全画面のスペースが必要 |
| 新規顧客の名前入力 | **モーダル** | キーボード入力に集中する場面 |
| 選択入力（4〜5 択） | **インライン展開** | チップがその場に出現。文脈が途切れない |
| テキスト入力（メモ） | **インライン展開** | 他の情報（タスク・顧客情報）を見ながら書ける |
| アクション（記録作成） | **フル幅ボタン** | 単一アクション。大きなタップ領域 |

### バッジ

顧客セグメントの視覚表現。

| セグメント | クラス | 背景 | テキスト |
|-----------|--------|------|---------|
| 新規 | `.badge-new` | `--accent-subtle` | `--accent` |
| リピート | `.badge-repeat` | `--warning-subtle` | `--warning-dark` |
| 常連 | `.badge-regular` | `--success-subtle` | `--success` |

### テーブル（オーナー UI 専用）

- ヘッダー: `--bg-surface-alt` 背景。Overline スタイル（12px / 600 / uppercase）。テキストは `--text-secondary`（`--text-muted` はコントラスト不足のため禁止）
- 行ホバー: `--accent-light` 背景
- 行区切り: `--border-default`

**テーブルの追加パターン:**

| パターン | 外観・振る舞い |
|---------|--------------|
| **ソート** | ヘッダーをクリックでソート。アクティブ列に `--accent` 色の矢印アイコン（▲/▼）。非アクティブ列は `--text-muted` の矢印 |
| **フィルタ** | テーブル上部にフィルタバー。選択中のフィルタは `--accent-subtle` bg のチップで表示。クリアボタン付き |
| **空状態** | テーブル領域に `--text-secondary` のメッセージ（例: 「顧客がまだ登録されていません」）。イラストは使わずテキストのみ |
| **ローディング** | テーブル領域にスケルトンローダー（`--bg-surface-alt` の矩形がパルスアニメーション） |
| **ページネーション** | テーブル下部。「前へ」「次へ」ボタン（Secondary スタイル）+ 現在ページ表示 |

### 確認ダイアログ（オーナー UI）

破壊的操作（論理削除、一括再計算等）の前に表示する確認ダイアログ。

| 要素 | 外観 |
|------|------|
| オーバーレイ | 半透明黒（`rgba(28,25,23, 0.4)`）|
| ダイアログ本体 | `--bg-surface` bg, `--shadow-xl`, `--radius-lg`, max-width 480px |
| タイトル | H2 スタイル |
| 本文 | Body スタイル。操作内容と影響範囲を明記 |
| アクション | 右寄せ。Secondary（キャンセル）+ Danger（実行）|

### プログレス表示（オーナー UI）

CSV インポート・一括再計算等の非同期処理。

| 要素 | 外観 |
|------|------|
| プログレスバー | `--bg-inset` bg のトラック内に `--accent` bg のバー。高さ 8px, `--radius-full` |
| ステータステキスト | Body スタイル。「処理中: 24 / 100 件」のように件数表示 |
| 完了時 | プログレスバーが `--success` に変化。トーストで通知 |
| エラー時 | プログレスバーが `--error` に変化。エラー詳細をテーブルで表示 |

### トースト

操作完了のフィードバック。画面下部に 3 秒表示 → 自動消去。

| 種別 | 色 |
|------|-----|
| 成功 | `--success` 背景 |
| エラー | `--error` 背景 |
| 情報 | `--accent` 背景 |

### フォーム（オーナー UI）

オーナー UI では従来のフォーム入力（ラベル + input）を使う。ゾーンパターンは PC では不要。

| 状態 | 外観 |
|------|------|
| 通常 | `--border-default` ボーダー |
| ホバー | `--border-strong` ボーダー |
| フォーカス | `--accent` ボーダー + `--accent-subtle` リング（3px） |
| エラー | `--error` ボーダー + `--error-subtle` リング |

## 6. CSS フレームワーク選定

### 決定: Tailwind CSS（daisyUI 不使用）

| 項目 | 内容 |
|------|------|
| **フレームワーク** | Tailwind CSS v3+ |
| **コンポーネントライブラリ** | 不使用（daisyUI / Headless UI 等を使わない）。自前で Tailwind ユーティリティを組む |
| **ビルド** | `npx tailwindcss` で CSS をビルド。webpack / Vite は使わない |
| **設定ファイル** | `tailwind.config.js` に本書のデザイントークンを全て定義する |

### なぜ Tailwind か

| 理由 | 詳細 |
|------|------|
| **トークン一元管理** | `tailwind.config.js` にカラー・スペーシング・影・角丸を定義。Cursor への指示は「config に従え」で完結する |
| **既製コンポーネントの排除** | Bootstrap / daisyUI のデフォルトスタイルが混入しない。ウォームホワイト × ティールの独自美学を汚さない |
| **Depth の強制** | Shadow / hover 状態を config で定義し、`shadow-sm` 等のユーティリティとして適用。「影をつけ忘れる」を防ぐ |
| **AI との相性** | Cursor は Tailwind のユーティリティクラスを正確に生成できる。config がルールブックになる |

### ベタっと問題の防止策

Tailwind でベタっとしたデザインになる原因と対策:

| 原因 | 対策 |
|------|------|
| 影をつけない | **ルール**: 全てのカード・ゾーンに `shadow-sm` 以上を必須とする |
| ホバー状態がない | **ルール**: インタラクティブ要素には必ず `hover:` / `active:` を定義する |
| 色がフラット | **ルール**: ベース・サーフェス・ボーダーの 3 層を使い分ける。単色の面を避ける |
| 角丸が不統一 | **ルール**: `--radius-sm/md/lg/full` のみ使用。任意の値は禁止 |
| 余白が不統一 | **ルール**: `--space-*` のスケールのみ使用。任意の px 値は禁止 |

### tailwind.config.js のベース

```javascript
// tailwind.config.js（抜粋）
module.exports = {
  content: ['./ui/templates/**/*.html', './ui/static/ui/js/**/*.js'],
  theme: {
    extend: {
      colors: {
        base:    '#FAF9F6',
        surface: { DEFAULT: '#FFFFFF', alt: '#F3F1ED' },
        inset:   '#EBE8E2',
        border:  { DEFAULT: '#E0DCD4', strong: '#C8C3BA' },
        text:    { primary: '#1C1917', secondary: '#57534E', muted: '#A8A29E', inverse: '#FAF9F6' },
        accent:  { DEFAULT: '#2D7D7B', hover: '#246563', active: '#1B4E4D', subtle: '#D4EDEB', light: '#EBF7F6' },
        success: { DEFAULT: '#4A7C59', subtle: '#E4F0E8' },
        warning: { DEFAULT: '#B8860B', dark: '#8B6914', subtle: '#FDF3DC' },
        error:   { DEFAULT: '#B91C1C', hover: '#991B1B', subtle: '#FDE8E8' },
      },
      fontFamily: {
        sans: ['"Inter"', '"Noto Sans JP"', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'sans-serif'],
      },
      borderRadius: {
        sm: '6px', md: '10px', lg: '16px', full: '9999px',
      },
      boxShadow: {
        sm: '0 1px 3px rgba(28,25,23,0.06), 0 1px 2px rgba(28,25,23,0.04)',
        md: '0 4px 12px rgba(28,25,23,0.08), 0 2px 4px rgba(28,25,23,0.04)',
        lg: '0 12px 32px rgba(28,25,23,0.10), 0 4px 8px rgba(28,25,23,0.04)',
        xl: '0 20px 48px rgba(28,25,23,0.14), 0 8px 16px rgba(28,25,23,0.06)',
      },
      spacing: {
        1: '4px', 2: '8px', 3: '12px', 4: '16px', 5: '20px',
        6: '24px', 8: '32px', 10: '40px', 12: '48px', 16: '64px',
      },
    },
  },
}
```

## 7. アイコン・イラスト方針

### アイコンセット

| 項目 | 選定 |
|------|------|
| **ライブラリ** | Lucide Icons（旧 Feather Icons の後継。MIT ライセンス、無料） |
| **スタイル** | 線画（stroke）。ブランドの線画の犬と統一感を持たせる |
| **サイズ** | ナビゲーション: 22px、インライン: 18px、小アイコン: 16px |
| **太さ** | `stroke-width: 2`（Lucide のデフォルト） |
| **色** | 現在の文脈の text カラーに従う（`currentColor`） |

### 利用方法

SVG をインラインで埋め込む。アイコンフォントは使わない。

```html
<!-- Django テンプレートでの利用 -->
{% include "ui/icons/search.svg" %}
```

### イラスト

MVP ではイラストは使用しない。エンプティステート（データなし）のメッセージはテキストのみ。

## 8. 付属アセット一覧

| ファイル | 内容 | 用途 |
|---------|------|------|
| `docs/design/assets/styleguide.html` | HTML+CSS スタイルガイド。ブラウザで開いて全コンポーネント・レイアウトを確認できる | Cursor への視覚的リファレンス。デザインレビューの基準 |

### styleguide.html の構成

| セクション | 内容 |
|-----------|------|
| Color Palette | 全色の HEX 付きスウォッチ |
| Typography | H1〜Overline の日本語サンプル |
| Elevation | 影の 4 段階の実物比較 |
| Buttons | Primary / Secondary / Ghost / Danger。標準サイズとタッチサイズ |
| Form Elements | テキスト入力（Owner UI）、Selection Chips |
| Badges | 新規 / リピート / 常連 |
| Toast | 成功 / エラー / 情報 |
| Zone Input Pattern | ゾーンの全状態（collapsed / filled / expanded）。インライン展開の選択・テキスト入力 |
| Search Modal | 検索モーダルの実物デモ（クリックで開く） |
| Interaction Model Summary | モーダル vs インラインの使い分け表 |
| Staff UI Layout | タブレットの全画面デモ。ハイブリッドインタラクション |
| Owner UI Layout | PC のサイドバー + テーブルのデモ |
| Design Token Reference | 全トークンの一覧表 |

## Review Log

- [2026-03-31] 初版作成
- [2026-03-31] Codex レビュー (gpt-5.4 high): 71/100 FAIL。F-01〜F-06 修正
  - F-01 (major): `--warning-dark`, `--error-hover` をトークンに追加。styleguide.html のハードコード色を全てトークン参照に置換
  - F-02 (major): 全インタラクティブ要素の状態定義表を追加（default/hover/active/focus-visible/disabled/loading）
  - F-03 (major): styleguide.html のスペーシング逸脱を修正（badge padding, border-width, tab gap）
  - F-04 (major): `--text-muted` のコントラスト不足を明記し使用制限ルールを追加。テーブルヘッダーを `--text-secondary` に変更
  - F-05 (minor): タブ名称を UI_PROPOSAL.md と統一（顧客/接客/来店記録/マッチング）
  - F-06 (major): オーナー UI のソート/フィルタ/空状態/ローディング/確認ダイアログ/プログレス表示を追加
- [2026-03-31] Codex 2回目レビュー (gpt-5.4 high): 79/100 FAIL。F-01/02/04/05 残留 + F-07〜09 新規。修正
  - F-01 残留: styleguide.html に `--warning-dark`, `--error-hover` のスウォッチ追加
  - F-02 残留: Chip/Zone/Tab/Sidebar に loading 行追加（N/A 明記）と注釈
  - F-04 残留: タブデフォルト色を `--text-secondary` に修正。サイズを 12px に修正。overline ラベルも `--text-secondary` に統一
  - F-05 残留: レイアウト図の `MC` を `マッチング` に修正
  - F-07 (major): tailwind.config.js に `warning.dark`, `error.hover` を追加
  - F-08 (major): Danger button active を `--error-hover` に修正
  - F-09 (minor): F-01 残留と統合して対応済み
- [2026-03-31] Codex 3回目レビュー (gpt-5.4 high): 92/100 FAIL。残1件修正
  - F-10 (major): styleguide.html に `.btn-danger:active` を追加
- [2026-04-01] orchestrator 再設計依頼 (Issue #1): Tab/Sidebar disabled 状態の仕様矛盾を修正
  - §2 `--text-muted` 使用制限: ナビゲーションラベル禁止に「disabled 状態を除く（WCAG 2.1 SC 1.4.3 による例外）」を追記
  - §5 状態定義表: Tab/Sidebar Item disabled から `opacity: 0.5` を削除し `cursor: not-allowed` に変更
  - 根拠: WCAG 2.1 SC 1.4.3 は非アクティブ UI コンポーネントをコントラスト要件の対象外としており、`--text-muted`（3.0:1）は disabled 状態に使用可。`opacity` 併用は §2 禁止事項違反かつコントラスト低下を招くため削除
- [2026-04-01] orchestrator 再設計依頼 2回目 (Issue #1): 12px ルールに disabled 例外を追記漏れ
  - §2 12px ルール: 「12px 以下のテキストには `--text-muted` を使わない」に「ただし disabled 状態を除く（WCAG 2.1 SC 1.4.3 例外）」を追記
  - 前回修正でナビラベル禁止には例外を入れたが、同じ WCAG 根拠で適用すべき 12px ルールへの反映が漏れていた
