# 本番環境デプロイ手順書

> **目的**: headless_shisha_crm + UI を本番環境にデプロイし、安全に運用できる状態にする
> **対象**: インフラ担当 / 運用チーム
> **日付**: 2026-04-02
> **前提**: テスト環境での E2E テスト（D-04: 3 フロー 17 テストケース）が全 PASS であること

---

## 1. アーキテクチャ概要

```
                    ┌─────────────┐
                    │   Nginx     │  :443 (HTTPS)
                    │  (reverse   │  :80  (→ 443 redirect)
                    │   proxy)    │
                    └──────┬──────┘
                           │ proxy_pass :8000
                    ┌──────┴──────────────────────────────┐
                    │  gunicorn (WSGI)                     │
                    │  headless_shisha_crm                 │
                    │                                      │
                    │  config/         Django 設定          │
                    │  core/           共通基盤             │
                    │  tenants/        Store/StoreGroup     │
                    │  accounts/       Staff/QRToken        │
                    │  customers/      Customer             │
                    │  visits/         Visit/Segment        │
                    │  tasks/          HearingTask          │
                    │  imports/        CsvImport            │
                    │  analytics/      分析                 │
                    │  ui/ ──→ symlink to ui_shisha_crm/ui/ │
                    │                                      │
                    │  staticfiles/    whitenoise 配信      │
                    └──────────┬───────────────────────────┘
                               │
                        ┌──────┴──────┐
                        │ PostgreSQL  │
                        │ (production)│
                        └─────────────┘
```

### コンポーネント

| コンポーネント | 役割 | 技術 |
|---|---|---|
| リバースプロキシ | TLS 終端・静的ファイルキャッシュ | Nginx |
| WSGI サーバー | Django アプリ実行 | gunicorn |
| Django アプリ | API + UI 統合サーバー | Django 6.0 + DRF 3.17 |
| DB | データ永続化 | PostgreSQL 14+ |
| 静的ファイル | CSS/JS/画像配信 | whitenoise（gunicorn 直接配信） |
| UI アプリ | Django テンプレート + HTMX | symlink 経由で統合 |

---

## 2. 前提条件

| 項目 | 要件 |
|---|---|
| Python | 3.13+ |
| PostgreSQL | 14+（専用サーバーまたはマネージド推奨） |
| Node.js | 18+（Tailwind CSS ビルド用。ビルド後は不要） |
| OS | Linux（RHEL/Rocky/Fedora 系を想定） |
| Nginx | 1.24+ |
| ドメイン | TLS 証明書取得済み（Let's Encrypt 等） |

---

## 3. PostgreSQL セットアップ

### 3.1 データベース・ユーザー作成

```bash
# 本番用の強いパスワードを生成
PROD_DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
echo "DB Password: $PROD_DB_PASSWORD"
# → このパスワードを安全に保管すること

sudo -u postgres psql <<SQL
CREATE USER shisha_prod WITH PASSWORD '${PROD_DB_PASSWORD}';
CREATE DATABASE headless_shisha_crm_prod OWNER shisha_prod;
GRANT ALL PRIVILEGES ON DATABASE headless_shisha_crm_prod TO shisha_prod;

-- 本番推奨設定
ALTER DATABASE headless_shisha_crm_prod SET timezone TO 'Asia/Tokyo';
ALTER DATABASE headless_shisha_crm_prod SET default_transaction_isolation TO 'read committed';
SQL
```

### 3.2 PostgreSQL チューニング（参考値）

`/var/lib/pgsql/data/postgresql.conf`:

```ini
# 接続
max_connections = 100
# メモリ（サーバーRAMの25%目安）
shared_buffers = 256MB
effective_cache_size = 768MB
work_mem = 4MB
maintenance_work_mem = 64MB
# WAL
wal_buffers = 16MB
# ログ
log_min_duration_statement = 1000  # 1秒以上のクエリをログ
```

---

## 4. アプリケーション準備

### 4.1 ディレクトリ構成

```bash
# アプリ用ディレクトリ
sudo mkdir -p /opt/shisha-crm
sudo chown deploy:deploy /opt/shisha-crm

# ソースコード配置（git clone またはリリースアーカイブ）
cd /opt/shisha-crm
git clone <headless_repo_url> headless_shisha_crm
git clone <ui_repo_url> ui_shisha_crm
```

### 4.2 Python 仮想環境

```bash
cd /opt/shisha-crm/headless_shisha_crm

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn whitenoise
```

### 4.3 UI シンボリックリンク

```bash
# ui/ が ui_shisha_crm/ui/ を指すことを確認
ls -la ui/
# → ui -> /opt/shisha-crm/ui_shisha_crm/ui

# リンクがなければ作成
ln -s /opt/shisha-crm/ui_shisha_crm/ui ./ui
```

### 4.4 Tailwind CSS ビルド

```bash
cd /opt/shisha-crm/ui_shisha_crm
npm install
npx tailwindcss -i ./ui/static/ui/css/input.css -o ./ui/static/ui/css/output.css --minify
```

---

## 5. 本番設定ファイル

### 5.1 production.py 作成

`config/settings/production.py` を作成する:

```python
from .base import *  # noqa: F403

DEBUG = False

# --- データベース ---
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ['POSTGRES_DB'],
        'USER': os.environ['POSTGRES_USER'],
        'PASSWORD': os.environ['POSTGRES_PASSWORD'],
        'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
        'CONN_MAX_AGE': 600,  # コネクションプーリング（10分）
        'CONN_HEALTH_CHECKS': True,
        'OPTIONS': {
            'connect_timeout': 5,
        },
    }
}

# --- セキュリティ ---
ALLOWED_HOSTS = os.environ['ALLOWED_HOSTS'].split(',')
# 例: ALLOWED_HOSTS=shisha-crm.example.com

# HTTPS 必須
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000  # 1年
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Nginx のIPをTRUSTED_PROXY_IPSに設定
TRUSTED_PROXY_IPS = os.environ.get('TRUSTED_PROXY_IPS', '127.0.0.1').split(',')

# QR ログイン POST の Origin 許可
ALLOWED_LOGIN_ORIGINS = os.environ.get('ALLOWED_LOGIN_ORIGINS', '').split(',')
# 例: ALLOWED_LOGIN_ORIGINS=https://shisha-crm.example.com

# --- 静的ファイル ---
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# --- ログ ---
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} {levelname} {name} [{correlation_id}] {message}',
            'style': '{',
            'defaults': {'correlation_id': '-'},
        },
        'json': {
            '()': 'django.utils.log.ServerFormatter',
            'format': '{asctime} {levelname} {name} {message}',
            'style': '{',
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/shisha-crm/app.log',
            'maxBytes': 50 * 1024 * 1024,  # 50MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'error_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/shisha-crm/error.log',
            'maxBytes': 50 * 1024 * 1024,
            'backupCount': 10,
            'formatter': 'verbose',
            'level': 'ERROR',
        },
    },
    'root': {
        'handlers': ['console', 'file', 'error_file'],
        'level': 'INFO',
    },
    'loggers': {
        'django.security': {
            'handlers': ['error_file'],
            'level': 'WARNING',
            'propagate': True,
        },
        'django.request': {
            'handlers': ['error_file'],
            'level': 'ERROR',
            'propagate': True,
        },
    },
}
```

### 5.2 環境変数ファイル

```bash
# /opt/shisha-crm/.env（root:deploy 0640 で保護）
cat > /opt/shisha-crm/.env <<'ENV'
DJANGO_SETTINGS_MODULE=config.settings.production
DJANGO_SECRET_KEY=<ここに 50 文字以上のランダム文字列>
POSTGRES_DB=headless_shisha_crm_prod
POSTGRES_USER=shisha_prod
POSTGRES_PASSWORD=<セクション 3.1 で生成したパスワード>
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
ALLOWED_HOSTS=shisha-crm.example.com
ALLOWED_LOGIN_ORIGINS=https://shisha-crm.example.com
TRUSTED_PROXY_IPS=127.0.0.1
ENV

# SECRET_KEY の生成
python3 -c "import secrets; print(secrets.token_urlsafe(50))"

# パーミッション制限
chmod 640 /opt/shisha-crm/.env
chown root:deploy /opt/shisha-crm/.env
```

**重要**: `.env` ファイルは git に含めない。本番シークレットはバージョン管理しない。

### 5.3 ログディレクトリ

```bash
sudo mkdir -p /var/log/shisha-crm
sudo chown deploy:deploy /var/log/shisha-crm
```

---

## 6. マイグレーション + 初期データ

```bash
cd /opt/shisha-crm/headless_shisha_crm
source .venv/bin/activate
export $(grep -v '^#' /opt/shisha-crm/.env | xargs)

# Django システムチェック
python manage.py check --deploy
# → セキュリティ警告がないことを確認

# マイグレーション
python manage.py migrate

# 初期データ投入（StoreGroup + Store + SegmentThreshold x3）
python manage.py seed_store

# 静的ファイル収集
python manage.py collectstatic --noinput
```

---

## 7. gunicorn 設定

### 7.1 gunicorn 設定ファイル

`/opt/shisha-crm/gunicorn.conf.py`:

```python
import multiprocessing

# サーバーソケット
bind = '127.0.0.1:8000'  # Nginx からのみアクセス

# ワーカー
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = 'gthread'
threads = 2
worker_connections = 1000

# タイムアウト
timeout = 30
graceful_timeout = 30
keepalive = 5

# プロセス管理
max_requests = 1000        # メモリリーク対策
max_requests_jitter = 50   # 一斉再起動を防止
preload_app = True

# ログ
accesslog = '/var/log/shisha-crm/gunicorn-access.log'
errorlog = '/var/log/shisha-crm/gunicorn-error.log'
loglevel = 'info'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# セキュリティ
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# PID
pidfile = '/run/shisha-crm/gunicorn.pid'
```

### 7.2 systemd サービス

`/etc/systemd/system/shisha-crm.service`:

```ini
[Unit]
Description=Shisha CRM (gunicorn)
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=notify
User=deploy
Group=deploy
RuntimeDirectory=shisha-crm
WorkingDirectory=/opt/shisha-crm/headless_shisha_crm
EnvironmentFile=/opt/shisha-crm/.env
ExecStart=/opt/shisha-crm/headless_shisha_crm/.venv/bin/gunicorn \
    config.wsgi:application \
    --config /opt/shisha-crm/gunicorn.conf.py
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=30
Restart=on-failure
RestartSec=5

# セキュリティ強化
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/var/log/shisha-crm /run/shisha-crm
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

```bash
# サービス有効化・起動
sudo systemctl daemon-reload
sudo systemctl enable shisha-crm
sudo systemctl start shisha-crm
sudo systemctl status shisha-crm
```

---

## 8. Nginx 設定

### 8.1 Nginx 設定ファイル

`/etc/nginx/conf.d/shisha-crm.conf`:

```nginx
upstream shisha_crm {
    server 127.0.0.1:8000;
}

# HTTP → HTTPS リダイレクト
server {
    listen 80;
    server_name shisha-crm.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name shisha-crm.example.com;

    # --- TLS 設定 ---
    ssl_certificate     /etc/letsencrypt/live/shisha-crm.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/shisha-crm.example.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache   shared:SSL:10m;
    ssl_session_timeout 10m;

    # --- セキュリティヘッダー ---
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;

    # --- クライアント制限 ---
    client_max_body_size 10M;  # CSV アップロード上限

    # --- プロキシ設定 ---
    location / {
        proxy_pass http://shisha_crm;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;

        # タイムアウト
        proxy_connect_timeout 30s;
        proxy_read_timeout 30s;
        proxy_send_timeout 30s;
    }

    # --- 静的ファイル（Nginx で直接配信する場合） ---
    # whitenoise を使用する場合はこのブロックは不要。
    # パフォーマンスを重視する場合は whitenoise を無効化して Nginx 配信に切り替える。
    #
    # location /static/ {
    #     alias /opt/shisha-crm/headless_shisha_crm/staticfiles/;
    #     expires 1y;
    #     add_header Cache-Control "public, immutable";
    # }

    # --- ヘルスチェック（ALB/LB 用） ---
    location = /api/v1/health/ {
        proxy_pass http://shisha_crm;
        proxy_set_header Host $host;
        access_log off;
    }
}
```

```bash
# 設定テスト・起動
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl restart nginx
```

### 8.2 TLS 証明書（Let's Encrypt）

```bash
# certbot インストール（RHEL/Rocky 系）
sudo dnf install certbot python3-certbot-nginx

# 証明書取得
sudo certbot --nginx -d shisha-crm.example.com

# 自動更新確認
sudo certbot renew --dry-run
```

---

## 9. デプロイ検証チェックリスト

デプロイ後、以下を **順番に** 確認する。

### 9.1 プロセス正常性

```bash
# gunicorn 起動確認
sudo systemctl status shisha-crm
# → Active: active (running)

# ワーカープロセス確認
ps aux | grep gunicorn
# → master + worker プロセスが起動していること

# Nginx 起動確認
sudo systemctl status nginx
# → Active: active (running)
```

### 9.2 ネットワーク疎通

```bash
# ローカルからの gunicorn 直接アクセス
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/api/v1/health/
# 期待: 200

# HTTPS 経由（外部から）
curl -s https://shisha-crm.example.com/api/v1/health/ | python3 -m json.tool
# 期待: {"status": "ok"}

# HTTP → HTTPS リダイレクト
curl -s -o /dev/null -w "%{http_code}" http://shisha-crm.example.com/
# 期待: 301
```

### 9.3 DB 正常性

```bash
cd /opt/shisha-crm/headless_shisha_crm
source .venv/bin/activate
export $(grep -v '^#' /opt/shisha-crm/.env | xargs)

# Django チェック（本番セキュリティ含む）
python manage.py check --deploy

# マイグレーション状態
python manage.py showmigrations | grep "\[ \]"
# 期待: 出力なし（全マイグレーション適用済み）

# seed_store 確認
python manage.py shell -c "
from tenants.models import Store
from visits.models import SegmentThreshold
store = Store.objects.first()
print(f'Store: {store.name}')
print(f'Thresholds: {SegmentThreshold.objects.filter(store=store).count()} 件')
"
# 期待: Store: <店舗名>, Thresholds: 3 件
```

### 9.4 UI 正常性

```bash
# Staff ログインページ
curl -s -o /dev/null -w "%{http_code}" https://shisha-crm.example.com/s/login/
# 期待: 200

# Owner ログインページ
curl -s -o /dev/null -w "%{http_code}" https://shisha-crm.example.com/o/login/
# 期待: 200

# 静的ファイル（Tailwind CSS）
curl -s -o /dev/null -w "%{http_code}" https://shisha-crm.example.com/static/ui/css/output.css
# 期待: 200
```

### 9.5 セキュリティ確認

```bash
# HSTS ヘッダー
curl -sI https://shisha-crm.example.com/ | grep -i strict-transport
# 期待: strict-transport-security: max-age=31536000; includeSubDomains; preload

# X-Frame-Options
curl -sI https://shisha-crm.example.com/ | grep -i x-frame
# 期待: x-frame-options: DENY

# Cookie Secure フラグ（ログイン後のレスポンスで確認）
# sessionid と csrftoken に Secure フラグが付いていること
```

---

## 10. 運用手順

### 10.1 アプリケーション更新（通常デプロイ）

```bash
cd /opt/shisha-crm/headless_shisha_crm
source .venv/bin/activate
export $(grep -v '^#' /opt/shisha-crm/.env | xargs)

# 1. ソース更新
git pull origin main

# 2. UI ソース更新
cd /opt/shisha-crm/ui_shisha_crm
git pull origin main

# 3. 依存更新（変更がある場合）
cd /opt/shisha-crm/headless_shisha_crm
pip install -r requirements.txt

# 4. Tailwind CSS リビルド（UI テンプレートに変更がある場合）
cd /opt/shisha-crm/ui_shisha_crm
npx tailwindcss -i ./ui/static/ui/css/input.css -o ./ui/static/ui/css/output.css --minify

# 5. マイグレーション（スキーマ変更がある場合）
cd /opt/shisha-crm/headless_shisha_crm
python manage.py migrate

# 6. 静的ファイル再収集
python manage.py collectstatic --noinput

# 7. gunicorn グレースフルリスタート
sudo systemctl reload shisha-crm

# 8. 検証（セクション9のチェックリスト）
curl -s https://shisha-crm.example.com/api/v1/health/ | python3 -m json.tool
```

### 10.2 ロールバック

```bash
cd /opt/shisha-crm/headless_shisha_crm

# 1. 前のコミットに戻す
git log --oneline -5  # 戻すべきコミットを確認
git checkout <前のコミットハッシュ>

# 2. UI も同様に戻す（必要な場合）
cd /opt/shisha-crm/ui_shisha_crm
git checkout <前のコミットハッシュ>

# 3. マイグレーションのロールバック（スキーマ変更があった場合）
cd /opt/shisha-crm/headless_shisha_crm
python manage.py migrate <app_name> <前のマイグレーション番号>

# 4. 静的ファイル再収集
python manage.py collectstatic --noinput

# 5. gunicorn リスタート
sudo systemctl restart shisha-crm

# 6. 検証
curl -s https://shisha-crm.example.com/api/v1/health/ | python3 -m json.tool
```

### 10.3 ログ確認

```bash
# アプリケーションログ
tail -f /var/log/shisha-crm/app.log

# エラーログ
tail -f /var/log/shisha-crm/error.log

# gunicorn アクセスログ
tail -f /var/log/shisha-crm/gunicorn-access.log

# Nginx アクセスログ
tail -f /var/log/nginx/access.log

# systemd ジャーナル
journalctl -u shisha-crm -f
```

### 10.4 データベースバックアップ

```bash
# 日次バックアップスクリプト例（cron で実行）
BACKUP_DIR=/opt/shisha-crm/backups
mkdir -p $BACKUP_DIR

pg_dump -U shisha_prod -h localhost headless_shisha_crm_prod \
  | gzip > $BACKUP_DIR/shisha_crm_$(date +%Y%m%d_%H%M%S).sql.gz

# 7日以上前のバックアップを削除
find $BACKUP_DIR -name "*.sql.gz" -mtime +7 -delete
```

cron 設定例:
```bash
# /etc/cron.d/shisha-crm-backup
0 3 * * * deploy /opt/shisha-crm/scripts/backup.sh
```

### 10.5 リストア

```bash
# バックアップからのリストア
gunzip -c /opt/shisha-crm/backups/shisha_crm_YYYYMMDD_HHMMSS.sql.gz \
  | psql -U shisha_prod -h localhost headless_shisha_crm_prod
```

---

## 11. 監視

### 11.1 ヘルスチェック（最低限）

外部監視ツール（UptimeRobot 等）で以下を定期的に確認:

| エンドポイント | 間隔 | 期待 |
|---|---|---|
| `https://shisha-crm.example.com/api/v1/health/` | 1分 | `{"status": "ok"}` |
| `https://shisha-crm.example.com/s/login/` | 5分 | HTTP 200 |

### 11.2 ディスク・プロセス監視

```bash
# ディスク使用率（ログ肥大化の検出）
df -h /var/log/shisha-crm/

# gunicorn ワーカー数
ps aux | grep -c "[g]unicorn"

# PostgreSQL 接続数
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity WHERE datname = 'headless_shisha_crm_prod';"
```

---

## 12. セキュリティチェックリスト

デプロイ完了後に確認する。

| # | 項目 | 確認方法 | 期待 |
|---|------|---------|------|
| 1 | `DEBUG = False` | `python manage.py shell -c "from django.conf import settings; print(settings.DEBUG)"` | `False` |
| 2 | `SECRET_KEY` がデフォルト値でない | `.env` を確認 | `dev-insecure-change-me` でないこと |
| 3 | `ALLOWED_HOSTS` が `*` でない | `python manage.py shell -c "from django.conf import settings; print(settings.ALLOWED_HOSTS)"` | ドメイン名のリスト |
| 4 | `SESSION_COOKIE_SECURE = True` | 同上 | `True` |
| 5 | `CSRF_COOKIE_SECURE = True` | 同上 | `True` |
| 6 | `SECURE_SSL_REDIRECT = True` | 同上 | `True` |
| 7 | `.env` のパーミッション | `ls -la /opt/shisha-crm/.env` | `640` (root:deploy) |
| 8 | PostgreSQL パスワード強度 | 32文字以上のランダム文字列 | テスト用パスワードでないこと |
| 9 | HTTPS 強制 | `curl -I http://...` | 301 → https |
| 10 | `check --deploy` クリーン | `python manage.py check --deploy` | 警告なし |

---

## 13. テスト環境との差分まとめ

| 項目 | テスト環境 (staging.py) | 本番環境 (production.py) |
|------|----------------------|------------------------|
| `DEBUG` | `False` | `False` |
| `ALLOWED_HOSTS` | `['*']` | ドメイン名のみ |
| `SESSION_COOKIE_SECURE` | `False` | `True` |
| `CSRF_COOKIE_SECURE` | `False` | `True` |
| `SECURE_SSL_REDIRECT` | なし | `True` |
| `SECURE_HSTS_*` | なし | 有効 |
| DB 接続 | デフォルトクレデンシャル | 強いパスワード + `CONN_MAX_AGE` |
| ログ | コンソールのみ | ファイル + コンソール（ローテーション付き） |
| フロントエンド | Nginx なし（gunicorn 直接） | Nginx リバースプロキシ + TLS |
| バックアップ | なし | 日次 pg_dump |

---

## 14. トラブルシューティング

| 症状 | 原因 | 対処 |
|------|------|------|
| `502 Bad Gateway` | gunicorn 未起動 | `sudo systemctl start shisha-crm` |
| `CSRF verification failed` | `ALLOWED_LOGIN_ORIGINS` に HTTPS URL が未設定 | `.env` に `ALLOWED_LOGIN_ORIGINS=https://ドメイン` |
| QR ログインできない | Cookie Secure=True だが HTTP | HTTPS を使う / Nginx の `X-Forwarded-Proto` 設定を確認 |
| 静的ファイル 404 | `collectstatic` 未実行 | `python manage.py collectstatic --noinput` |
| `DisallowedHost` | `ALLOWED_HOSTS` にドメイン未設定 | `.env` を修正 |
| gunicorn ワーカーが OOM Killed | `max_requests` 未設定 | `gunicorn.conf.py` に `max_requests = 1000` |
| `connection refused` (DB) | PostgreSQL 未起動 / 認証エラー | `pg_isready` で確認。`pg_hba.conf` を確認 |
| Tailwind CSS が適用されない | CSS 未ビルド or collectstatic 未実行 | セクション 4.4 → 6 を再実行 |
| ログファイルが肥大化 | ローテーション未設定 | `gunicorn.conf.py` の `RotatingFileHandler` を確認 |

---

## Review Log

- [2026-04-02] 初版作成
