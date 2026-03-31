# US-01 詳細設計書: Staff Login + base

> 基本設計書: `docs/design/UI_BASIC_DESIGN.md` §5 US-01, §7.1
> デザインガイド: `docs/design/UI_DESIGN_GUIDE.md`
> パイプライン: `docs/design/UI_PIPELINE.md` #1

## 1. 概要

### Slice 情報

| 項目 | 内容 |
|------|------|
| **Cluster** | US-01 (Staff Login) |
| **Slice** | S1（単一 Slice で完結） |
| **パイプライン順序** | #1 / 13 |
| **ブランチ説明部** | `us01-staff-login` |

### スコープ

QR ログイン画面、ログアウト処理、`base.html`（共通基盤）、`base_staff.html`（BottomTab + Topbar）、`/s/customers/` stub view。UI app 全体の土台を構築する。

### precondition

- コア層の C-02 全 Slice が完了済み（`QRAuthService` が動作する）
- コア層の Django プロジェクトに UI app が組み込み可能な状態

### postcondition

- `/s/login/` で QR トークン入力 → ログイン → セッション確立
- `/s/login/#token={token}` で QR リンク経由自動ログイン（hash は `history.replaceState` で除去）
- ログイン後 `/s/customers/` → stub view「準備中」表示（US-02 S1 で本実装に置き換え）
- `/s/logout/` でセッション破棄 → `/s/login/` にリダイレクト
- `base.html` に HTMX / Alpine.js / Tailwind CSS / Google Fonts の読み込み
- `base_staff.html` に Topbar（操作者名表示）+ BottomTab ナビゲーション
- 未認証で `/s/customers/` → `/s/login/` にリダイレクト（stub view に `LoginRequiredMixin`）
- 無効トークン → エラーメッセージ表示

## 2. ファイル構成

```
ui/
├── __init__.py
├── apps.py                          # UiConfig
├── urls.py                          # /s/ → staff.urls, /o/ → owner.urls（UO-01 で追加）
├── mixins.py                        # StaffRequiredMixin, StoreMixin（共通。UO-01 で OwnerRequiredMixin 追加）
├── staff/
│   ├── __init__.py
│   ├── urls.py                      # login, logout, customers stub
│   ├── views/
│   │   ├── __init__.py
│   │   ├── auth.py                  # LoginView, LogoutView
│   │   └── stub.py                  # StubCustomerView
│   └── forms.py                     # QRLoginForm
├── templates/ui/
│   ├── base.html                    # {% load static %} 含む
│   ├── base_staff.html
│   ├── icons/                       # Lucide SVG（US-01 で使う 4 アイコン）
│   │   ├── users.svg
│   │   ├── message-circle.svg
│   │   ├── calendar.svg
│   │   └── link.svg
│   └── staff/
│       ├── login.html
│       └── stub.html
├── static/ui/
│   ├── css/
│   │   ├── input.css                # Tailwind @tailwind directives
│   │   └── output.css               # ビルド済み（git 管理）
│   └── js/
│       └── qr-auto-login.js         # hash 読み取り + 自動 POST
```

**repo root に配置するファイル:**

```
(repo root)/
├── tailwind.config.js               # content パスは ./ui/templates/**/*.html + ./ui/static/ui/js/**/*.js
└── package.json                     # npm run css:watch / css:build
```

## 3. Django app セットアップ

### apps.py

```python
from django.apps import AppConfig

class UiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ui"
    verbose_name = "UI"
```

### settings.py への追加

```python
INSTALLED_APPS = [
    # ... 既存のアプリ ...
    "ui",
]

LOGIN_URL = "/s/login/"
```

### プロジェクト urls.py への追加

```python
urlpatterns = [
    # ... 既存の URL ...
    path("", include("ui.urls")),
]
```

## 4. tailwind.config.js

デザインガイドのトークンを Tailwind のカスタム設定に展開する。

```javascript
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./ui/templates/**/*.html",    // repo root からの相対パス
    "./ui/static/ui/js/**/*.js",   // repo root からの相対パス
  ],
  theme: {
    extend: {
      colors: {
        // Base
        "bg-base": "#FAF9F6",
        "bg-surface": "#FFFFFF",
        "bg-surface-alt": "#F3F1ED",
        "bg-inset": "#EBE8E2",
        "border-default": "#E0DCD4",
        "border-strong": "#C8C3BA",
        // Text
        "text-primary": "#1C1917",
        "text-secondary": "#57534E",
        "text-muted": "#A8A29E",
        "text-inverse": "#FAF9F6",
        // Accent (Deep Teal)
        accent: "#2D7D7B",
        "accent-hover": "#246563",
        "accent-active": "#1B4E4D",
        "accent-subtle": "#D4EDEB",
        "accent-light": "#EBF7F6",
        // Semantic
        success: "#4A7C59",
        "success-subtle": "#E4F0E8",
        warning: "#B8860B",
        "warning-dark": "#8B6914",
        "warning-subtle": "#FDF3DC",
        error: "#B91C1C",
        "error-hover": "#991B1B",
        "error-subtle": "#FDE8E8",
      },
      fontFamily: {
        sans: ['"Inter"', '"Noto Sans JP"', "-apple-system", "BlinkMacSystemFont", '"Segoe UI"', "sans-serif"],
        mono: ['"JetBrains Mono"', '"Noto Sans JP"', "monospace"],
      },
      borderRadius: {
        sm: "6px",
        md: "10px",
        lg: "16px",
        full: "9999px",
      },
      boxShadow: {
        sm: "0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06)",
        md: "0 4px 6px rgba(0,0,0,0.07), 0 2px 4px rgba(0,0,0,0.06)",
        lg: "0 10px 15px rgba(0,0,0,0.07), 0 4px 6px rgba(0,0,0,0.05)",
        xl: "0 20px 25px rgba(0,0,0,0.08), 0 10px 10px rgba(0,0,0,0.04)",
      },
      spacing: {
        // 4px grid — デザインガイド準拠
        1: "4px",
        2: "8px",
        3: "12px",
        4: "16px",
        5: "20px",
        6: "24px",
        8: "32px",
        10: "40px",
        12: "48px",
        16: "64px",
      },
    },
  },
  plugins: [],
};
```

### package.json

```json
{
  "private": true,
  "devDependencies": {
    "tailwindcss": "^3.4"
  },
  "scripts": {
    "css:watch": "npx tailwindcss -i ./ui/static/ui/css/input.css -o ./ui/static/ui/css/output.css --watch",
    "css:build": "npx tailwindcss -i ./ui/static/ui/css/input.css -o ./ui/static/ui/css/output.css --minify"
  }
}
```

**Tailwind バージョン**: 3.4.x（v4 ではない。設定ファイル形式が異なるため）。

### Tailwind ビルド

```bash
# 開発時（ファイル変更監視）
npm run css:watch

# CI / verify 用（ワンショット + minify）
npm run css:build
```

`output.css` は git 管理する。`verify.sh` で `npm run css:build` → `git diff --exit-code ui/static/ui/css/output.css` を実行し、ビルド忘れを検出する。

### input.css

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

## 5. テンプレート

### 5.1 base.html

全ページ共通の HTML シェル。`base_staff.html` と `base_owner.html`（UO-01 S1 で作成）の親。

**構造:**

```
{% load static %}
<html lang="ja">
<head>
  charset, viewport
  <title>{% block title %}{% endblock %} | Shisha CRM</title>
  Google Fonts: Inter (400,500,600,700) + Noto Sans JP (400,500,600,700)
  <link rel="stylesheet" href="{% static 'ui/css/output.css' %}">
  {% block extra_head %}{% endblock %}
</head>
<body class="bg-bg-base text-text-primary font-sans">
  {% block body %}{% endblock %}

  <script src="https://unpkg.com/htmx.org@2.0.4"></script>
  <!-- HTMX CSRF 自動付与: 全 hx-post/patch/delete に X-CSRFToken ヘッダを自動追加 -->
  <script>
    document.body.addEventListener("htmx:configRequest", function(evt) {
      evt.detail.headers["X-CSRFToken"] = document.querySelector("[name=csrfmiddlewaretoken]")?.value
        || document.cookie.match(/csrftoken=([^;]+)/)?.[1] || "";
    });
  </script>
  <!-- HTMX 422 swap 許可: バリデーションエラーの HTML フラグメントを描画するため -->
  <script>
    document.body.addEventListener("htmx:beforeSwap", function(evt) {
      if (evt.detail.xhr.status === 422) {
        evt.detail.shouldSwap = true;
        evt.detail.isError = false;
      }
    });
  </script>
  <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.14/dist/cdn.min.js"></script>
  {% block extra_js %}{% endblock %}
</body>
</html>
```

**注意**: Django テンプレートの `{% load %}` タグは継承されない。`{% static %}` を使う各テンプレートで個別に `{% load static %}` を宣言すること。`base.html`、`base_staff.html`、`login.html` それぞれに記述が必要。

**読み込み順序:**
1. CSS（Google Fonts → Tailwind）
2. Body コンテンツ
3. JS（HTMX → Alpine.js → extra_js）

### 5.2 base_staff.html

`base.html` を継承。Topbar + Content + BottomTab + Toast の 4 ゾーン構成。

**構造:**

```
{% extends "ui/base.html" %}
{% load static %}

{% block body %}
  <!-- Topbar: 44px 固定 -->
  <header>
    {% block page_title %}{% endblock %}
    <span>{{ request.user.display_name }}</span>  <!-- 操作者名バッジ -->
    <!-- ログアウトボタン -->
    <form method="post" action="/s/logout/">
      {% csrf_token %}
      <button type="submit">ログアウト</button>
    </form>
  </header>

  <!-- Content: スクロール可能領域、padding: 20px -->
  <main>
    {% block content %}{% endblock %}
  </main>

  <!-- BottomTab: 56px 固定 -->
  <nav>
    <!-- 顧客タブ: 唯一のアクティブリンク（US-01 時点） -->
    <a href="/s/customers/">{% include "ui/icons/users.svg" %} 顧客</a>

    <!-- 以下 3 タブは US-01 時点で遷移先未実装 → aria-disabled + 非活性スタイル -->
    <button disabled aria-disabled="true">{% include "ui/icons/message-circle.svg" %} 接客</button>
    <button disabled aria-disabled="true">{% include "ui/icons/calendar.svg" %} 来店記録</button>
    <button disabled aria-disabled="true">{% include "ui/icons/link.svg" %} マッチング</button>
    <!-- 各タブは対応 Slice 完了時に <a> リンクに置き換え -->
  </nav>

  <!-- Toast: Alpine.js 制御 -->
  <div x-data="{ show: false, message: '', type: 'success' }">
    {% block toast %}{% endblock %}
  </div>
{% endblock %}
```

**BottomTab のアクティブ判定:**

テンプレートコンテキストに `active_tab` 変数を渡す。各 View で設定。

```python
# View 側
def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    context["active_tab"] = "customers"  # customers | session | visits | matching
    return context
```

テンプレート側で `{% if active_tab == "customers" %}` でアクティブクラスを切替。

**レイアウトの CSS 方針:**
- 全体は `min-h-screen flex flex-col`
- Topbar: `h-[44px] flex items-center px-5`
- Content: `flex-1 overflow-y-auto p-5`
- BottomTab: `h-[56px] flex items-center justify-around border-t border-border-default`

### 5.3 staff/login.html

`base.html` を直接継承（BottomTab なし）。

**構造:**

```
{% extends "ui/base.html" %}
{% load static %}

{% block body %}
  <!-- 中央寄せコンテナ -->
  <div>  <!-- min-h-screen flex items-center justify-center -->

    <!-- ログインカード -->
    <div>  <!-- max-w-sm, shadow-sm, rounded-md, p-8 -->

      <!-- ブランドロゴ -->
      <h1>Shisha CRM</h1>

      <!-- エラーメッセージ（条件付き表示） -->
      {% if form.non_field_errors %}
        <div>  <!-- error-subtle 背景, error テキスト, rounded-sm, p-3, mb-4 -->
          {% for error in form.non_field_errors %}
            <p>{{ error }}</p>
          {% endfor %}
        </div>
      {% endif %}

      <!-- ログインフォーム -->
      <form method="post">
        {% csrf_token %}

        <!-- QR トークン入力 -->
        <label>QR コード</label>
        {{ form.token }}
        <!-- input: w-full, border border-border-default, rounded-sm, p-3, text-[17px] -->
        {% if form.token.errors %}
          <p>{{ form.token.errors.0 }}</p>
        {% endif %}

        <!-- ログインボタン -->
        <button type="submit">ログイン</button>
          <!-- accent 背景, text-inverse, rounded-sm, w-full, py-3, mt-4 -->
      </form>
    </div>
  </div>
{% endblock %}

{% block extra_js %}
  <script src="{% static 'ui/js/qr-auto-login.js' %}"></script>
{% endblock %}
```

**エラーメッセージ:**

| エラー | メッセージ |
|--------|----------|
| 無効なトークン | 「QR コードが無効です」 |
| 期限切れ | 「QR コードの有効期限が切れています」 |
| 使用済み | 「この QR コードは既に使用されています」 |

### 5.4 staff/stub.html

`base_staff.html` を継承。`/s/customers/` の仮実装。US-02 S1 で置き換え。

**構造:**

```
{% extends "ui/base_staff.html" %}

{% block page_title %}顧客{% endblock %}

{% block content %}
  <div>  <!-- text-center, text-text-secondary, py-16 -->
    <p>準備中</p>
    <p>この画面は次のアップデートで利用可能になります</p>
  </div>
{% endblock %}
```

## 6. View 定義

### 6.0 コア層契約（C-02 からの引用）

View が依存するコア層の API 契約を以下に示す。正式な定義は `docs/reference/cluster/C02_AUTH.md` を参照。

**`QRAuthService.authenticate(token: str) -> Staff`**

| 結果 | 挙動 |
|------|------|
| 成功 | `Staff` インスタンスを返す。`QRToken.is_used = True` に更新済み |
| token 不存在 | `BusinessError(code="auth.token_not_found")` |
| token 期限切れ | `BusinessError(code="auth.token_expired")` |
| token 使用済み | `BusinessError(code="auth.token_used")` |
| staff 無効 | `BusinessError(code="auth.staff_inactive")` |

**`Staff` モデル（UI が参照するフィールド）**

| フィールド | 型 | 備考 |
|-----------|-----|------|
| `display_name` | CharField | UI 表示用の名前 |
| `role` | CharField (`owner` / `staff`) | 権限判定に使用 |
| `store` | ForeignKey(Store) | 店舗スコープ |
| `is_active` | BooleanField | 論理削除フラグ |

**注意**: `Staff` は `AbstractUser` を継承（`AUTH_USER_MODEL = 'accounts.Staff'`）。`django.contrib.auth.login(request, staff)` でセッション確立可能。ただし `backend` 引数の明示指定が必要:

```python
login(request, staff, backend="django.contrib.auth.backends.ModelBackend")
```

`AUTHENTICATION_BACKENDS` が 1 件のみの場合は省略可能だが、明示指定を推奨する（将来の backend 追加時の破綻防止）。

### 6.1 QRLoginForm

```python
# ui/staff/forms.py

from django import forms

class QRLoginForm(forms.Form):
    token = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            "placeholder": "QR コードを入力",
            "autocomplete": "off",
            "autofocus": True,
        }),
        error_messages={"required": "QR コードを入力してください"},
    )
```

### 6.2 LoginView

```python
# ui/staff/views/auth.py

from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from django.views import View

from core.exceptions import BusinessError
from core.services.auth import QRAuthService
from ui.staff.forms import QRLoginForm

class LoginView(View):
    """QR トークンログイン。GET でフォーム表示、POST で認証。"""
    template_name = "ui/staff/login.html"

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("/s/customers/")
        return render(request, self.template_name, {"form": QRLoginForm()})

    def post(self, request):
        form = QRLoginForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        token = form.cleaned_data["token"]
        try:
            staff = QRAuthService.authenticate(token)
        except BusinessError as e:
            form.add_error(None, ERROR_MESSAGES.get(e.code, "認証に失敗しました"))
            return render(request, self.template_name, {"form": form})

        login(request, staff, backend="django.contrib.auth.backends.ModelBackend")
        return redirect("/s/customers/")
```

**エラーメッセージマッピング:**

```python
ERROR_MESSAGES = {
    "auth.token_not_found": "QR コードが無効です",
    "auth.token_expired": "QR コードの有効期限が切れています",
    "auth.token_used": "この QR コードは既に使用されています",
    "auth.staff_inactive": "このアカウントは無効化されています",
}
```

**認証済みユーザーのアクセス:**
- GET: `/s/customers/` にリダイレクト（ログイン画面を表示しない）

### 6.2 LogoutView

```python
class LogoutView(View):
    """POST のみ受付。セッション破棄してログイン画面にリダイレクト。"""

    def post(self, request):
        logout(request)
        return redirect("/s/login/")
```

**GET は受け付けない**: CSRF 対策。ログアウトは POST のみ。

### 6.3 StubCustomerView

```python
# ui/staff/views/stub.py

class StubCustomerView(LoginRequiredMixin, StaffRequiredMixin, StoreMixin, TemplateView):
    """US-02 S1 で本実装に置き換える仮 View。"""
    template_name = "ui/staff/stub.html"
    login_url = "/s/login/"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "customers"
        return context
```

## 7. QR hash 自動ログイン JS

`ui/static/ui/js/qr-auto-login.js`

```javascript
/**
 * QR リンク経由ログイン
 * URL: /s/login/#token={token}
 *
 * 動作:
 * 1. location.hash から token を読み取る
 * 2. history.replaceState で hash を除去（戻る/再読込で再送防止）
 * 3. input[name="token"] にセット
 * 4. フォームを自動 POST
 */
document.addEventListener("DOMContentLoaded", function () {
  const hash = location.hash;
  if (!hash || !hash.startsWith("#token=")) return;

  const token = decodeURIComponent(hash.substring("#token=".length));
  if (!token) return;

  // hash 除去（再読込/戻るで再送されない）
  history.replaceState(null, "", location.pathname + location.search);

  // フォームにセットして自動送信
  const input = document.querySelector('input[name="token"]');
  const form = input?.closest("form");
  if (input && form) {
    input.value = token;
    form.submit();
  }
});
```

**仕様:**
- `#token=` プレフィックスがない場合は何もしない（手動入力モード）
- `decodeURIComponent` で URL エンコードされた token に対応
- `history.replaceState` は `submit()` 前に実行（ブラウザ履歴に hash を残さない）

## 8. URL 設定

### ui/urls.py（2 段 include のハブ）

```python
from django.urls import path, include

app_name = "ui"

urlpatterns = [
    path("s/", include("ui.staff.urls", namespace="staff")),
    # path("o/", include("ui.owner.urls", namespace="owner")),  # UO-01 S1 で追加
]
```

プロジェクト urls.py は `path("", include("ui.urls"))` で接続。結果: `/s/login/`, `/s/logout/`, `/s/customers/`。

### ui/staff/urls.py

```python
from django.urls import path
from ui.staff.views.auth import LoginView, LogoutView
from ui.staff.views.stub import StubCustomerView

app_name = "staff"

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("customers/", StubCustomerView.as_view(), name="customers"),
]
```

## 9. Mixin 定義

`ui/mixins.py`（`ui/staff/` ではなく `ui/` 直下。UO-01 で `OwnerRequiredMixin` を同ファイルに追加する）

### StaffRequiredMixin

```python
# ui/mixins.py

from django.contrib.auth import logout
from django.contrib.auth.mixins import AccessMixin
from django.shortcuts import redirect

class StaffRequiredMixin(AccessMixin):
    """role が staff または owner であることを要求する。

    挙動:
    - 未認証 → handle_no_permission()（LOGIN_URL へリダイレクト）
    - 認証済みだが role が staff/owner でない → /s/login/ へリダイレクト（異常系: ログアウトさせる）
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.role not in ("staff", "owner"):
            logout(request)
            return redirect("/s/login/")
        return super().dispatch(request, *args, **kwargs)
```

**権限制御の契約:**

| 状態 | 挙動 | 根拠 |
|------|------|------|
| 未認証 | `LOGIN_URL` (`/s/login/`) へリダイレクト | `LoginRequiredMixin` + `handle_no_permission()` |
| 認証済み + role 不正 | `logout()` + `/s/login/` へリダイレクト | role 不正はスタッフ UI への異常アクセス。セッション破棄してログイン画面に戻す。自己リダイレクトループを回避 |
| 認証済み + role 正常 | 通常処理 | — |

### StoreMixin

```python
class StoreMixin:
    """self.store と context["store"] をセットする。"""

    def dispatch(self, request, *args, **kwargs):
        self.store = request.user.store
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["store"] = self.store
        return context
```

**Mixin の適用順序**: `LoginRequiredMixin, StaffRequiredMixin, StoreMixin` の順。`StoreMixin` は `request.user.store` の存在が前提のため、認証チェック後に配置する。

## 10. テストケース

### 10.1 Django TestClient

| # | テスト | 検証内容 |
|---|--------|---------|
| 1 | `test_login_page_get` | GET `/s/login/` → 200、`login.html` 使用 |
| 2 | `test_login_valid_token` | POST `/s/login/` with valid token → 302 `/s/customers/`。セッション確立（`_auth_user_id` 存在）。後続 GET `/s/customers/` が 200。`QRToken.is_used == True` |
| 3 | `test_login_invalid_token` | POST `/s/login/` with invalid token → 200、エラーメッセージ表示 |
| 4 | `test_login_expired_token` | POST with expired token → 200、期限切れエラー |
| 5 | `test_login_empty_token` | POST with empty token → 200、エラーメッセージ |
| 6 | `test_login_redirect_if_authenticated` | 認証済みで GET `/s/login/` → 302 `/s/customers/` |
| 7 | `test_logout_post` | POST `/s/logout/` → 302 `/s/login/`、セッション破棄 |
| 8 | `test_logout_get_not_allowed` | GET `/s/logout/` → 405 |
| 9 | `test_stub_requires_auth` | 未認証で GET `/s/customers/` → 302 `/s/login/` |
| 10 | `test_stub_authenticated` | 認証済みで GET `/s/customers/` → 200、`stub.html` 使用 |
| 11 | `test_stub_active_tab` | context に `active_tab == "customers"` |
| 12 | `test_base_staff_topbar` | レスポンスに `request.user.display_name` が含まれる |
| 13 | `test_base_staff_bottomtab` | レスポンスに BottomTab のアクティブリンク（顧客）+ 非活性ボタン 3 つが含まれる |
| 14 | `test_login_used_token` | POST with used token → 200、「既に使用されています」エラー |
| 15 | `test_login_inactive_staff` | POST with inactive staff token → 200、「無効化されています」エラー |
| 16 | `test_stub_rejects_non_staff_role` | role が staff/owner でないユーザーで GET `/s/customers/` → logout + 302 `/s/login/`（StaffRequiredMixin） |
| 17 | `test_bottomtab_disabled_tabs` | レスポンスに `aria-disabled="true"` の button が 3 つ含まれる（接客/来店記録/マッチング） |
| 18 | `test_topbar_logout_form` | レスポンスに `action="/s/logout/"` の POST form と `csrfmiddlewaretoken` が含まれる |

### 10.2 Browser smoke test（Codex review で「要 smoke test」指定）

| # | 対象 URL | 手順 | 期待結果 |
|---|---------|------|---------|
| 1 | `/s/login/#token={valid}` | QR リンク経由でアクセス | 自動ログイン → `/s/customers/` に遷移 |
| 2 | (ブラウザ) | #1 の後、URL バーを確認 | `/s/customers/` が表示されており、URL に `#token=` が残っていない |
| 3 | (ブラウザ) | #1 の後、ブラウザ戻る → 再読込 | token の自動 POST が再発しない（hash が replaceState で除去済みのため） |
| 4 | `/s/login/#token={invalid}` | 無効 token で QR リンク経由アクセス | 自動 POST → エラーメッセージ「QR コードが無効です」表示 |
| 5 | `/s/customers/` | 認証済みでアクセス | stub view「準備中」+ Topbar（操作者名）+ BottomTab 表示 |
| 6 | `/s/customers/` | BottomTab の非活性タブをタップ | 何も起きない（disabled button） |

## Review Log

- [2026-03-31] 初版作成
- [2026-03-31] Codex レビュー (gpt-5.4 high): 58/100 FAIL。10 件を修正
  - F-01 (high): URL 二重定義を解消。プロジェクト urls.py → ui/urls.py → staff/urls.py の 2 段 include に統一
  - F-02 (high): Mixin を `ui/staff/mixins.py` → `ui/mixins.py` に移動。UO-01 で OwnerRequiredMixin を同ファイルに追加する前提
  - F-03 (high): StaffRequiredMixin の権限不足時の挙動を修正。未認証→LOGIN_URL、role不正→logout()+/s/login/（自己ループ回避。基本設計書 §3.2 も同期更新済み）
  - F-04 (high): QRLoginForm を新設。LoginView を Form ベースに書き直し。BusinessError → form.add_error() で正規化
  - F-05 (high): BottomTab の未実装 3 タブを `<button disabled aria-disabled="true">` に変更。404 回避
  - F-06 (medium): アイコン SVG ファイル（users/message-circle/calendar/link）をファイル構成に追加
  - F-07 (medium): `{% load static %}` の記述要件を base.html と login.html に明記
  - F-08 (medium): コア層契約セクション（§6.0）を新設。QRAuthService.authenticate() の返り値・例外・Staff モデルフィールドを引用
  - F-09 (medium): テスト 4 件追加（used token、inactive staff、non-staff role 拒否、disabled tabs）。smoke test 2 件追加（無効 hash token、disabled tab タップ）
  - F-10 (medium): package.json を追加（Tailwind 3.4.x）。css:build コマンド + verify 手順を明記
- [2026-03-31] Codex 2回目レビュー (gpt-5.4 high): 84/100 CONDITIONAL。6 件を修正
  - F-11 (high): {% load static %} は継承されない旨を訂正。base.html / base_staff.html / login.html 各テンプレートに個別宣言
  - F-12 (high): base_staff.html の Topbar にログアウトボタン（POST form）を追加
  - F-13 (high): StaffRequiredMixin の role 不正時を logout() + /s/login/ リダイレクトに変更。自己ループ回避
  - F-14 (high): login() に backend 引数を明示指定。AUTHENTICATION_BACKENDS 前提を明記
  - F-15 (medium): smoke test #2,#3 を「hash 残存なし + token 再送なし」の検証観点に修正
  - F-16 (medium): test_login_valid_token でセッション確立（_auth_user_id）+ QRToken.is_used + 後続 GET 200 まで検証
- [2026-03-31] Codex 3回目レビュー (gpt-5.4 high): 84/100 CONDITIONAL。5 件を修正
  - F-17 (high): StaffRequiredMixin の変更を基本設計書 §3.2 に反映（role不正→logout()+/s/login/）
  - F-18 (high): tailwind.config.js / package.json を repo root 配置に修正。content パスを ./ui/ 相対に統一
  - F-19 (medium): 基本設計書の base_staff.html 構造にログアウトボタンを追記
  - F-20 (medium): test_topbar_logout_form を追加（action="/s/logout/" + csrfmiddlewaretoken 存在確認）
  - F-21 (low): Review Log F-03 の記述を現行仕様（logout()+/s/login/）に修正
- [2026-03-31] Codex 4回目レビュー (gpt-5.4 high): 88/100 CONDITIONAL。2 件を修正
  - F-22 (medium): StaffRequiredMixin に `from django.contrib.auth import logout` の import を追加
  - F-23 (medium): UI_DESIGN_GUIDE.md の tailwind.config.js content に JS パスを追加
- [2026-03-31] Codex 5回目レビュー (gpt-5.4 high): 84/100 CONDITIONAL。3 件を修正
  - F-24 (medium): StubCustomerView に StoreMixin を追加（基本設計書 §3.2 の全業務 View に適用ルール準拠）
  - F-25 (medium): LoginView / LogoutView の import を完全化（redirect, render, logout, BusinessError, QRAuthService）
  - F-26 (low): ファイル構成の tailwind.config.js コメントに JS パスを追記（本文設定例と整合）
- [2026-03-31] Codex 6回目レビュー (gpt-5.4 high): **92/100 PASS**
