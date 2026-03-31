# UO-01 詳細設計書: Owner Login + base_owner + スタッフ管理

> 基本設計書: `docs/design/UI_BASIC_DESIGN.md` §6 UO-01, §7.5
> デザインガイド: `docs/design/UI_DESIGN_GUIDE.md`
> パイプライン: `docs/design/UI_PIPELINE.md` #2, #7

## 1. 概要

### Cluster 情報

| 項目 | 内容 |
|------|------|
| **Cluster** | UO-01 (Owner Login + スタッフ管理) |
| **Slice 数** | 2 本 |
| **パイプライン順序** | S1: #2 / 13、S2: #7 / 13 |

### Slice 1: オーナーログイン + base_owner.html

| 項目 | 内容 |
|------|------|
| **ブランチ説明部** | `uo01-s1-owner-login` |
| **スコープ** | ログイン画面、`base_owner.html`（Sidebar + Header）、`OwnerRequiredMixin`、`/o/dashboard/` stub view |

**precondition:**
- US-01 S1 完了（`base.html`、`LoginRequiredMixin`、`ui/mixins.py` が存在）
- コア層 C-02 完了

**postcondition:**
- `/o/login/` でオーナー用ログイン動作（role が owner でなければエラー）
- `/o/login/#token={token}` で QR リンク経由自動ログイン（hash は `history.replaceState` で除去）
- staff ロールでログイン → インラインエラー「オーナー専用です」
- `base_owner.html` に Sidebar ナビゲーション + Header（ログインユーザー名 + ログアウトボタン）
- Chart.js CDN の読み込みが `base_owner.html` に含まれる
- `/o/dashboard/` に `OwnerRequiredMixin` 付き stub view（UO-05 S1 で本実装に置き換え）
- 未認証で `/o/dashboard/` → `/o/login/` にリダイレクト
- staff ロールで `/o/dashboard/` → `/s/customers/` にリダイレクト

### Slice 2: スタッフ管理

| 項目 | 内容 |
|------|------|
| **ブランチ説明部** | `uo01-s2-staff-mgmt` |
| **スコープ** | スタッフ一覧、作成、詳細/無効化、QR 発行 |

**precondition:**
- UO-01 S1 完了（`base_owner.html`、`OwnerRequiredMixin` が動作）
- コア層 C-02 完了（Staff CRUD + QRToken 発行が動作）

**postcondition:**
- `/o/staff/` でスタッフ一覧テーブル表示
- `/o/staff/new/` でスタッフ作成 → QR トークン自動発行（role 別 URL）
- `/o/staff/<id>/` でスタッフ詳細 + QR 表示 + QR 再発行 + 無効化
- 無効化時に確認ダイアログ（Alpine.js）
- Sidebar の「スタッフ管理」がアクティブ状態

## 2. ファイル構成

### Slice 1

```
ui/
├── mixins.py                        # OwnerRequiredMixin を追加（既存の StaffRequiredMixin, StoreMixin と同居）
├── urls.py                          # path("o/", include("ui.owner.urls")) を追記
├── owner/
│   ├── __init__.py
│   ├── urls.py                      # login, logout, dashboard stub
│   ├── views/
│   │   ├── __init__.py
│   │   ├── auth.py                  # OwnerLoginView, OwnerLogoutView
│   │   └── stub.py                  # StubDashboardView
│   └── forms/
│       ├── __init__.py
│       └── auth.py                  # QROwnerLoginForm
├── templates/ui/
│   ├── base_owner.html
│   ├── icons/                       # Sidebar 用アイコン追加
│   │   ├── bar-chart-2.svg
│   │   ├── user-cog.svg
│   │   ├── sliders.svg
│   │   └── upload.svg
│   │   # users.svg, calendar.svg は US-01 で作成済み
│   └── owner/
│       ├── login.html
│       └── stub_dashboard.html
```

### Slice 2

```
ui/owner/
├── views/
│   └── staff_mgmt.py               # StaffListView, StaffCreateView, StaffDetailView
├── forms/
│   └── staff.py                     # StaffCreateForm（基本設計書の配置に準拠）
├── urls.py                          # staff/ 関連 URL を追記
templates/ui/owner/
├── staff_list.html
├── staff_create.html
├── staff_detail.html
└── _qr_section.html              # HTMX フラグメント（QR 再発行で差し替え）
```

## 3. コア層契約（C-02 からの引用）

正式な定義は `docs/reference/cluster/C02_AUTH.md` を参照。

### QRAuthService

| メソッド | 引数 | 返り値 | 例外 |
|---------|------|--------|------|
| `authenticate(token)` | `str` | `Staff` | `BusinessError(auth.token_not_found / auth.token_expired / auth.token_used / auth.staff_inactive)` |
| `issue_token(staff, expires_in_hours)` | `Staff, int` | `QRToken` | `BusinessError(auth.staff_inactive / auth.expiry_exceeded)` |

### QRToken モデル（UI が参照するフィールド）

| フィールド | 型 | 備考 |
|-----------|-----|------|
| `token` | CharField (unique) | QR URL に埋め込む秘密値 |
| `expires_at` | DateTimeField | 有効期限 |
| `is_used` | BooleanField | 使用済みフラグ |

### Staff モデル（UI が参照するフィールド）

| フィールド | 型 | 備考 |
|-----------|-----|------|
| `display_name` | CharField | UI 表示名 |
| `role` | CharField (`owner` / `staff`) | 権限判定 |
| `staff_type` | CharField (`owner` / `regular` / `temporary`) | QR 有効期限決定に使用 |
| `store` | ForeignKey(Store) | 店舗スコープ |
| `is_active` | BooleanField | 論理削除。False の場合、一覧・詳細とも 404 |
| `created_at` | DateTimeField | 作成日（auto_now_add） |

### QR URL 生成ルール

| role | QR URL |
|------|--------|
| `staff` | `/s/login/#token={token}` |
| `owner` | `/o/login/#token={token}` |

### QR 有効期限デフォルト

| staff_type | デフォルト最大値 |
|-----------|----------------|
| `temporary` | 8 時間 |
| `regular` | 720 時間（30 日） |
| `owner` | 720 時間（30 日） |

### Staff 無効化のガード条件（C-02）

- 自分自身の無効化は不可
- 店舗内の最後の owner の無効化は不可

## 4. Mixin 定義（Slice 1）

`ui/mixins.py` に `OwnerRequiredMixin` を追加（`StaffRequiredMixin`, `StoreMixin` は US-01 で作成済み）。

```python
# ui/mixins.py に追記

class OwnerRequiredMixin(AccessMixin):
    """role が owner であることを要求する。

    挙動（基本設計書 §3.2 準拠）:
    - 未認証 → /o/login/ へリダイレクト
    - 認証済み + role が owner でない → /s/customers/ へリダイレクト
    """
    login_url = "/o/login/"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.role != "owner":
            return redirect("/s/customers/")
        return super().dispatch(request, *args, **kwargs)
```

## 5. テンプレート

### 5.1 base_owner.html

`base.html` を継承。Sidebar + Header + Content + Modal + Toast の 5 ゾーン構成。

```
{% extends "ui/base.html" %}
{% load static %}

{% block body %}
  <div>  <!-- flex min-h-screen -->

    <!-- Sidebar: 220px 固定幅（デザインガイド準拠） -->
    <aside>
      <!-- ブランド名 -->
      <div>Shisha CRM</div>

      <!-- ナビゲーション -->
      <nav>
        <a href="/o/dashboard/">{% include "ui/icons/bar-chart-2.svg" %} ダッシュボード</a>
        <a href="/o/customers/">{% include "ui/icons/users.svg" %} 顧客管理</a>
        <a href="/o/visits/">{% include "ui/icons/calendar.svg" %} 来店記録</a>
        <a href="/o/staff/">{% include "ui/icons/user-cog.svg" %} スタッフ管理</a>
        <a href="/o/segments/settings/">{% include "ui/icons/sliders.svg" %} セグメント設定</a>
        <a href="/o/imports/upload/">{% include "ui/icons/upload.svg" %} Airレジ連携</a>
        <!-- UO-01 S1 時点: ダッシュボード以外は stub 未設置。リンク先は後続 Slice で実装 -->
        <!-- アクティブ判定: context["active_sidebar"] で切替 -->
      </nav>
    </aside>

    <!-- メインエリア -->
    <div>  <!-- flex-1 flex flex-col -->

      <!-- Header -->
      <header>  <!-- h-[56px] flex items-center justify-between px-6 border-b -->
        <h1>{% block page_title %}{% endblock %}</h1>
        <div>
          <span>{{ request.user.display_name }}</span>
          <form method="post" action="/o/logout/">
            {% csrf_token %}
            <button type="submit">ログアウト</button>
          </form>
        </div>
      </header>

      <!-- Content -->
      <main>  <!-- flex-1 overflow-y-auto p-6 -->
        {% block content %}{% endblock %}
      </main>
    </div>
  </div>

  <!-- Modal: Alpine.js マウントポイント -->
  {% block modal %}{% endblock %}

  <!-- Toast -->
  <div x-data="{ show: false, message: '', type: 'success' }">
    {% block toast %}{% endblock %}
  </div>
{% endblock %}

{% block extra_head %}
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
{% endblock %}
```

**Sidebar のアクティブ判定:**

```python
# View 側
def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    context["active_sidebar"] = "staff"  # dashboard | customers | visits | staff | segments | imports
    return context
```

テンプレート: `{% if active_sidebar == "staff" %}` でアクティブクラス（`bg-bg-surface-alt text-accent`）を適用。

**Sidebar のリンク状態（UO-01 S1 時点）:**

| メニュー | 状態 | 理由 |
|---------|------|------|
| ダッシュボード | stub view へリンク | UO-01 S1 で stub 配置済み |
| 顧客管理〜Airレジ連携 | リンクはあるが遷移先未実装（404） | 後続 Slice で実装。Owner UI は PC 向けのため aria-disabled ではなくリンクのまま残す（開発者向け導線として有用） |

### 5.2 owner/login.html

`base.html` を直接継承（Sidebar なし）。staff login.html とほぼ同構造。

```
{% extends "ui/base.html" %}
{% load static %}

{% block body %}
  <div>  <!-- min-h-screen flex items-center justify-center -->
    <div>  <!-- max-w-sm, shadow-sm, rounded-md, p-8 -->
      <h1>Shisha CRM — オーナー</h1>

      {% if form.non_field_errors %}
        <div>  <!-- error-subtle, rounded-sm, p-3, mb-4 -->
          {% for error in form.non_field_errors %}
            <p>{{ error }}</p>
          {% endfor %}
        </div>
      {% endif %}

      <form method="post">
        {% csrf_token %}
        <label>QR コード</label>
        {{ form.token }}
        {% if form.token.errors %}
          <p>{{ form.token.errors.0 }}</p>
        {% endif %}
        <button type="submit">ログイン</button>
      </form>
    </div>
  </div>
{% endblock %}

{% block extra_js %}
  <script src="{% static 'ui/js/qr-auto-login.js' %}"></script>
{% endblock %}
```

**注意**: `qr-auto-login.js` は US-01 で作成済み。owner login でもそのまま再利用する（`#token=` の読み取りはパス非依存）。

### 5.3 owner/stub_dashboard.html

```
{% extends "ui/base_owner.html" %}
{% load static %}

{% block page_title %}ダッシュボード{% endblock %}

{% block content %}
  <div>  <!-- text-center, text-text-secondary, py-16 -->
    <p>準備中</p>
    <p>この画面は次のアップデートで利用可能になります</p>
  </div>
{% endblock %}
```

### 5.4 owner/staff_list.html（Slice 2）

```
{% extends "ui/base_owner.html" %}
{% load static %}

{% block page_title %}スタッフ管理{% endblock %}

{% block content %}
  <!-- 新規作成ボタン -->
  <a href="/o/staff/new/">新規スタッフ作成</a>

  <!-- スタッフテーブル -->
  <table>
    <thead>
      <tr>
        <th>表示名</th>
        <th>ロール</th>
        <th>種別</th>
        <th>作成日</th>
      </tr>
    </thead>
    <tbody>
      {% for staff in staff_list %}
        <tr class="cursor-pointer hover:bg-bg-surface-alt" onclick="location.href='/o/staff/{{ staff.id }}/'">
          <td><a href="/o/staff/{{ staff.id }}/" class="stretched-link">{{ staff.display_name }}</a></td>
          <td>{{ staff.get_role_display }}</td>
          <td>{{ staff.get_staff_type_display }}</td>
          <td>{{ staff.created_at|date:"Y/m/d" }}</td>
        </tr>
      {% empty %}
        <tr><td colspan="4">スタッフが登録されていません</td></tr>
      {% endfor %}
    </tbody>
  </table>
{% endblock %}
```

### 5.5 owner/staff_create.html（Slice 2）

```
{% extends "ui/base_owner.html" %}
{% load static %}

{% block page_title %}スタッフ作成{% endblock %}

{% block content %}
  <form method="post">
    {% csrf_token %}

    <!-- 表示名 -->
    <label>{{ form.display_name.label }}</label>
    {{ form.display_name }}
    {% if form.display_name.errors %}<p>{{ form.display_name.errors.0 }}</p>{% endif %}

    <!-- ロール -->
    <label>{{ form.role.label }}</label>
    {{ form.role }}

    <!-- 種別 -->
    <label>{{ form.staff_type.label }}</label>
    {{ form.staff_type }}

    <button type="submit">作成</button>
    <a href="/o/staff/">キャンセル</a>
  </form>
{% endblock %}
```

### 5.6 owner/staff_detail.html（Slice 2）

```
{% extends "ui/base_owner.html" %}
{% load static %}

{% block page_title %}{{ staff.display_name }}{% endblock %}

{% block content %}
  <!-- エラーメッセージ（無効化ガード失敗時） -->
  {% if error %}
    <div>  <!-- error-subtle 背景, error テキスト, rounded-sm, p-3, mb-4 -->
      <p>{{ error }}</p>
    </div>
  {% endif %}

  <!-- 基本情報 -->
  <dl>
    <dt>表示名</dt><dd>{{ staff.display_name }}</dd>
    <dt>ロール</dt><dd>{{ staff.get_role_display }}</dd>
    <dt>種別</dt><dd>{{ staff.get_staff_type_display }}</dd>
    <dt>作成日</dt><dd>{{ staff.created_at|date:"Y/m/d H:i" }}</dd>
  </dl>

  <!-- QR コード表示 -->
  <section id="qr-section">
    {% include "ui/owner/_qr_section.html" %}
  </section>

  <!-- 無効化 -->
  <div x-data="{ showConfirm: false }">
    <button @click="showConfirm = true">このスタッフを無効化</button>

    <!-- 確認ダイアログ -->
    <div x-show="showConfirm" x-transition>
      <p>{{ staff.display_name }} を無効化しますか？この操作は元に戻せません。</p>
      <form method="post" action="/o/staff/{{ staff.id }}/deactivate/">
        {% csrf_token %}
        <button type="submit">無効化する</button>
        <button type="button" @click="showConfirm = false">キャンセル</button>
      </form>
    </div>
  </div>
{% endblock %}
```

### 5.7 owner/_qr_section.html（HTMX フラグメント）

```
<h2>QR コード</h2>
{% if latest_qr_token %}
  <p>URL: <a href="{{ qr_url }}" target="_blank" class="text-accent underline">{{ qr_url }}</a></p>
  <p>有効期限: {{ latest_qr_token.expires_at|date:"Y/m/d H:i" }}</p>
  <p class="text-text-muted text-sm">※ QR 画像生成は Phase 2。MVP ではリンクをコピーして利用</p>
{% else %}
  <p>QR トークンがありません</p>
{% endif %}

<button hx-post="/o/staff/{{ staff.id }}/qr-issue/"
        hx-target="#qr-section"
        hx-swap="innerHTML">
  QR 再発行
</button>
```

### 5.8 HTMX CSRF 設定（base.html への追加）

UO-01 S2 で HTMX POST（QR 再発行）を使用するため、`base.html` に CSRF トークン自動付与を追加する。US-01 設計書への波及修正。

`base.html` の HTMX script 読み込み直後に以下を追加:

```html
<script>
  document.body.addEventListener("htmx:configRequest", function(evt) {
    evt.detail.headers["X-CSRFToken"] = document.querySelector("[name=csrfmiddlewaretoken]")?.value
      || document.cookie.match(/csrftoken=([^;]+)/)?.[1] || "";
  });
</script>
```

これにより `hx-post` / `hx-patch` / `hx-delete` で個別に CSRF トークンを渡す必要がなくなる。`base_owner.html` / `base_staff.html` にはログアウト form（`{% csrf_token %}`）が常に存在するため、`csrfmiddlewaretoken` は取得可能。

## 6. View 定義

### Slice 1

#### 6.1 QROwnerLoginForm

```python
# ui/owner/forms/auth.py

from django import forms

class QROwnerLoginForm(forms.Form):
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

#### 6.2 OwnerLoginView

```python
# ui/owner/views/auth.py

from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from django.views import View

from core.exceptions import BusinessError
from core.services.auth import QRAuthService
from ui.owner.forms.auth import QROwnerLoginForm

ERROR_MESSAGES = {
    "auth.token_not_found": "QR コードが無効です",
    "auth.token_expired": "QR コードの有効期限が切れています",
    "auth.token_used": "この QR コードは既に使用されています",
    "auth.staff_inactive": "このアカウントは無効化されています",
}

class OwnerLoginView(View):
    template_name = "ui/owner/login.html"

    def get(self, request):
        if request.user.is_authenticated and request.user.role == "owner":
            return redirect("/o/dashboard/")
        return render(request, self.template_name, {"form": QROwnerLoginForm()})

    def post(self, request):
        form = QROwnerLoginForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        token = form.cleaned_data["token"]
        # role を事前チェック（トークン消費前）
        # QRToken から staff を取得して role を確認し、owner でなければトークンを消費せずに拒否する
        from accounts.models import QRToken as QRTokenModel
        try:
            qr_token = QRTokenModel.objects.select_related("staff").get(token=token)
        except QRTokenModel.DoesNotExist:
            form.add_error(None, ERROR_MESSAGES["auth.token_not_found"])
            return render(request, self.template_name, {"form": form})

        if qr_token.staff.role != "owner":
            form.add_error(None, "オーナー専用です。スタッフ用 QR コードではログインできません")
            return render(request, self.template_name, {"form": form})

        # role が owner であることを確認後、トークンを消費して認証
        try:
            staff = QRAuthService.authenticate(token)
        except BusinessError as e:
            form.add_error(None, ERROR_MESSAGES.get(e.code, "認証に失敗しました"))
            return render(request, self.template_name, {"form": form})

        login(request, staff, backend="django.contrib.auth.backends.ModelBackend")
        return redirect("/o/dashboard/")
```

**認証済みユーザーの GET:**
- role が owner → `/o/dashboard/` にリダイレクト
- role が owner でない → ログインフォームを表示（re-login を許可）

#### 6.3 OwnerLogoutView

```python
class OwnerLogoutView(View):
    def post(self, request):
        logout(request)
        return redirect("/o/login/")
```

#### 6.4 StubDashboardView

```python
# ui/owner/views/stub.py

from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from ui.mixins import OwnerRequiredMixin, StoreMixin

class StubDashboardView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, TemplateView):
    template_name = "ui/owner/stub_dashboard.html"
    login_url = "/o/login/"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_sidebar"] = "dashboard"
        return context
```

### Slice 2

#### 6.5 StaffCreateForm

```python
# ui/owner/forms/staff.py

from django import forms

class StaffCreateForm(forms.Form):
    display_name = forms.CharField(
        max_length=150,
        error_messages={"required": "表示名を入力してください"},
    )
    role = forms.ChoiceField(
        choices=[("staff", "スタッフ"), ("owner", "オーナー")],
    )
    staff_type = forms.ChoiceField(
        choices=[("regular", "レギュラー"), ("temporary", "テンポラリー"), ("owner", "オーナー")],
    )
```

#### 6.6 StaffListView

```python
# ui/owner/views/staff_mgmt.py

from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from ui.mixins import OwnerRequiredMixin, StoreMixin

class StaffListView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, ListView):
    template_name = "ui/owner/staff_list.html"
    context_object_name = "staff_list"
    login_url = "/o/login/"

    # ページネーションなし: 1 店舗あたりのスタッフ数は数名〜数十名のため全件表示。
    # 基本設計の 25 件/ページルールの例外。
    def get_queryset(self):
        return Staff.objects.filter(store=self.store, is_active=True).order_by("display_name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_sidebar"] = "staff"
        return context
```

#### 6.7 StaffCreateView

```python
from django.shortcuts import redirect, render
from django.views import View
from core.services.auth import QRAuthService

# QR 有効期限デフォルト（C-02 仕様）
QR_EXPIRY_HOURS = {
    "temporary": 8,
    "regular": 720,
    "owner": 720,
}

class StaffCreateView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    template_name = "ui/owner/staff_create.html"
    login_url = "/o/login/"

    def get(self, request):
        return render(request, self.template_name, {
            "form": StaffCreateForm(),
            "active_sidebar": "staff",
        })

    def post(self, request):
        form = StaffCreateForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {
                "form": form,
                "active_sidebar": "staff",
            })

        # スタッフ作成（§1.1 例外: Service ではなく ORM 直接）
        # コア基本設計: username は UUID 自動生成（Staff モデルの save() で設定される）
        staff = Staff(
            display_name=form.cleaned_data["display_name"],
            role=form.cleaned_data["role"],
            staff_type=form.cleaned_data["staff_type"],
            store=self.store,
        )
        staff.set_unusable_password()
        staff.save()

        # QR トークン自動発行
        expires_hours = QR_EXPIRY_HOURS[staff.staff_type]
        qr_token = QRAuthService.issue_token(staff, expires_in_hours=expires_hours)

        return redirect(f"/o/staff/{staff.pk}/")
```

**注意**: スタッフ作成は「write は Service 必須」の例外（基本設計書 §1.1）。`StaffViewSet.perform_create()` 相当のロジックを再現。

#### 6.8 StaffDetailView

```python
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.http import HttpResponseNotAllowed

class StaffDetailView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    template_name = "ui/owner/staff_detail.html"
    login_url = "/o/login/"

    def get_staff(self):
        return get_object_or_404(Staff, pk=self.kwargs["pk"], store=self.store, is_active=True)

    def get(self, request, pk):
        staff = self.get_staff()
        latest_qr = QRToken.objects.filter(staff=staff).order_by("-created_at").first()
        qr_url = self._build_qr_url(staff, latest_qr) if latest_qr else None

        return render(request, self.template_name, {
            "staff": staff,
            "latest_qr_token": latest_qr,
            "qr_url": qr_url,
            "active_sidebar": "staff",
        })

    @staticmethod
    def _build_qr_url(staff, qr_token):
        prefix = "/o/login/" if staff.role == "owner" else "/s/login/"
        return f"{prefix}#token={qr_token.token}"
```

#### 6.9 QR 再発行（HTMX）

```python
# staff_mgmt.py に追加

class StaffQRIssueView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    """HTMX POST: QR 再発行 → QR セクション HTML フラグメントを返す"""
    login_url = "/o/login/"

    def post(self, request, pk):
        staff = get_object_or_404(Staff, pk=pk, store=self.store, is_active=True)
        expires_hours = QR_EXPIRY_HOURS[staff.staff_type]
        qr_token = QRAuthService.issue_token(staff, expires_in_hours=expires_hours)
        qr_url = StaffDetailView._build_qr_url(staff, qr_token)

        return render(request, "ui/owner/_qr_section.html", {
            "latest_qr_token": qr_token,
            "qr_url": qr_url,
            "staff": staff,
        })
```

フラグメントテンプレート `_qr_section.html` は QR 表示部分のみ。

#### 6.10 スタッフ無効化

```python
class StaffDeactivateView(LoginRequiredMixin, OwnerRequiredMixin, StoreMixin, View):
    login_url = "/o/login/"

    def post(self, request, pk):
        staff = get_object_or_404(Staff, pk=pk, store=self.store, is_active=True)

        # ガード条件（C-02 仕様）
        def _render_detail_with_error(error_msg):
            latest_qr = QRToken.objects.filter(staff=staff).order_by("-created_at").first()
            qr_url = StaffDetailView._build_qr_url(staff, latest_qr) if latest_qr else None
            return render(request, "ui/owner/staff_detail.html", {
                "staff": staff, "latest_qr_token": latest_qr, "qr_url": qr_url,
                "error": error_msg, "active_sidebar": "staff",
            })

        if staff.pk == request.user.pk:
            return _render_detail_with_error("自分自身を無効化することはできません")

        owner_count = Staff.objects.filter(store=self.store, role="owner", is_active=True).count()
        if staff.role == "owner" and owner_count <= 1:
            return _render_detail_with_error("最後のオーナーは無効化できません")

        staff.is_active = False
        staff.save(update_fields=["is_active"])
        return redirect("/o/staff/")
```

## 7. URL 設定

### ui/urls.py（追記）

```python
# 既存の staff include に追加
urlpatterns = [
    path("s/", include("ui.staff.urls", namespace="staff")),
    path("o/", include("ui.owner.urls", namespace="owner")),  # UO-01 S1 で追加
]
```

### ui/owner/urls.py

```python
from django.urls import path
from ui.owner.views.auth import OwnerLoginView, OwnerLogoutView
from ui.owner.views.stub import StubDashboardView
from ui.owner.views.staff_mgmt import (
    StaffListView, StaffCreateView, StaffDetailView,
    StaffQRIssueView, StaffDeactivateView,
)

app_name = "owner"

urlpatterns = [
    # Slice 1: ログイン + dashboard stub
    path("login/", OwnerLoginView.as_view(), name="login"),
    path("logout/", OwnerLogoutView.as_view(), name="logout"),
    path("dashboard/", StubDashboardView.as_view(), name="dashboard"),

    # Slice 2: スタッフ管理
    path("staff/", StaffListView.as_view(), name="staff-list"),
    path("staff/new/", StaffCreateView.as_view(), name="staff-create"),
    path("staff/<uuid:pk>/", StaffDetailView.as_view(), name="staff-detail"),
    path("staff/<uuid:pk>/qr-issue/", StaffQRIssueView.as_view(), name="staff-qr-issue"),
    path("staff/<uuid:pk>/deactivate/", StaffDeactivateView.as_view(), name="staff-deactivate"),
]
```

## 8. テストケース

### 8.1 Slice 1: Django TestClient

| # | テスト | 検証内容 |
|---|--------|---------|
| 1 | `test_owner_login_get` | GET `/o/login/` → 200 |
| 2 | `test_owner_login_valid_token` | POST valid owner token → 302 `/o/dashboard/`。セッション確立。QRToken.is_used == True |
| 3 | `test_owner_login_staff_token` | POST valid staff token → 200、「オーナー専用です」エラー。**QRToken.is_used == False**（トークン未消費） |
| 4 | `test_owner_login_invalid_token` | POST invalid → 200、エラーメッセージ |
| 5 | `test_owner_login_expired_token` | POST expired → 200、期限切れエラー |
| 6 | `test_owner_login_used_token` | POST used → 200、使用済みエラー |
| 7 | `test_owner_login_redirect_if_authenticated` | owner で GET `/o/login/` → 302 `/o/dashboard/` |
| 8 | `test_owner_login_show_form_if_staff` | staff で GET `/o/login/` → 200（re-login 許可） |
| 9 | `test_owner_logout` | POST `/o/logout/` → 302 `/o/login/`、セッション破棄 |
| 10 | `test_dashboard_stub_owner` | owner で GET `/o/dashboard/` → 200、stub 表示 |
| 11 | `test_dashboard_stub_unauthenticated` | 未認証で GET `/o/dashboard/` → 302 `/o/login/` |
| 12 | `test_dashboard_stub_staff_redirect` | staff で GET `/o/dashboard/` → 302 `/s/customers/` |
| 13 | `test_sidebar_links` | レスポンスに Sidebar 6 メニューのリンクが含まれる |
| 14 | `test_header_logout_form` | レスポンスに `action="/o/logout/"` の POST form が含まれる |

### 8.2 Slice 2: Django TestClient

| # | テスト | 検証内容 |
|---|--------|---------|
| 15 | `test_staff_list` | owner で GET `/o/staff/` → 200、active staff のみ表示 |
| 16 | `test_staff_list_unauthenticated` | 未認証 → 302 `/o/login/` |
| 17 | `test_staff_list_staff_redirect` | staff で GET → 302 `/s/customers/` |
| 18 | `test_staff_create_get` | GET `/o/staff/new/` → 200 |
| 19 | `test_staff_create_post` | POST valid → スタッフ作成 + QRToken 発行 + 302 詳細画面 |
| 20 | `test_staff_create_invalid` | POST empty display_name → 200、エラー |
| 21 | `test_staff_create_qr_url_role` | staff role で作成 → QR URL が `/s/login/#token=...`。owner role → `/o/login/#token=...` |
| 22 | `test_staff_detail` | GET `/o/staff/<id>/` → 200、基本情報 + QR 表示 |
| 23 | `test_staff_detail_inactive_404` | is_active=False のスタッフ → 404 |
| 24 | `test_qr_reissue` | POST `/o/staff/<id>/qr-issue/` → 新しい QRToken 発行、HTML フラグメント返却 |
| 25 | `test_deactivate` | POST `/o/staff/<id>/deactivate/` → is_active=False + 302 一覧 |
| 26 | `test_deactivate_self` | 自分自身の無効化 → エラー |
| 27 | `test_deactivate_last_owner` | 最後の owner → エラー |
| 28 | `test_sidebar_active_staff` | `/o/staff/` で active_sidebar == "staff" |
| 29 | `test_staff_list_has_detail_links` | 一覧レスポンスに各スタッフの `/o/staff/<id>/` リンクが含まれる |
| 30 | `test_qr_url_displayed_as_link` | 詳細画面で QR URL が `<a href=...>` リンクとして表示される |

### 8.3 Browser smoke test

| # | 対象 URL | 手順 | 期待結果 |
|---|---------|------|---------|
| 1 | `/o/login/#token={owner}` | QR リンク経由 | 自動ログイン → `/o/dashboard/` stub 表示 |
| 2 | (ブラウザ) | #1 の後 URL 確認 | hash なし |
| 3 | `/o/staff/new/` | スタッフ作成 | 詳細画面に遷移、QR URL 表示 |
| 4 | `/o/staff/<id>/` | QR 再発行ボタン | HTMX で QR セクション更新（ページ遷移なし） |
| 5 | `/o/staff/<id>/` | 無効化ボタン | Alpine.js 確認ダイアログ表示 → 確定 → 一覧に戻る |

## Review Log

- [2026-03-31] 初版作成
- [2026-03-31] Codex レビュー (gpt-5.4 high): 64/100 FAIL。8 件を修正
  - F-01 (critical): OwnerLoginView で role を事前チェック（QRToken 読み取り → role 確認 → authenticate）。staff token でトークン消費されない設計に変更
  - F-02 (high): QR 再発行の HTMX target `#qr-section` を staff_detail.html に追加。_qr_section.html フラグメントを新設・ファイル構成に追加
  - F-03 (high): 無効化ガード失敗時の再描画で latest_qr_token / qr_url を正しく渡す。テンプレートにエラー表示領域を追加
  - F-04 (high): Staff 作成を `Staff() + set_unusable_password() + save()` に変更。コア仕様の username UUID 自動生成に準拠
  - F-05 (medium): `date_joined` → `created_at` に統一（コア基本設計準拠）
  - F-06 (medium): スタッフ一覧はページネーション不要（1 店舗数名〜数十名）と明記
  - F-07 (medium): forms ファイル配置を `ui/owner/forms/auth.py` + `ui/owner/forms/staff.py` に変更（基本設計書準拠）
  - F-08 (low): Sidebar 幅を 240px → 220px に修正（デザインガイド準拠）
- [2026-03-31] Codex 2回目レビュー (gpt-5.4 high): 84/100 CONDITIONAL。3 件を修正
  - F-09 (high): HTMX CSRF 設定を追加。base.html に htmx:configRequest イベントで X-CSRFToken 自動付与
  - F-10 (high): スタッフ一覧の行クリック導線を具体化。stretched-link + onclick で詳細画面に遷移。テスト追加
  - F-11 (medium): QR 表示を `<a>` リンク形式に確定。QR 画像は Phase 2 と明記。テスト追加
- [2026-03-31] Codex 3回目レビュー (gpt-5.4 high): 89/100 CONDITIONAL。1 件を修正
  - F-12 (medium): US-01 の base.html に HTMX CSRF 自動付与（htmx:configRequest）を反映。共通基盤仕様の波及漏れ解消
- [2026-03-31] Codex 4回目レビュー (gpt-5.4 high): **93/100 PASS**
