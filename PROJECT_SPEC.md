# Discord Butler Bot — 工程實作規格書

> 文件版本：v2.0
> 最後更新：2026-05-07
> 文件狀態：Canonical implementation spec & engineering prompt
> 主要讀者：負責撰寫程式碼的 AI / 人類工程師、專案維護者

---

## 0. 給工程 AI 的執行 prompt

### 0.1 你的任務

你是負責實作 Discord Butler Bot 的工程師。你**只需要讀本文件**就能完成 MVP 的所有實作。本文件是專案的單一權威 spec —— 不要尋找或引用其他規格文件（之前的 `discord_butler_bot_spec.md` 與 `DEPLOYMENT.md` 已合併進本文件並刪除）。

### 0.2 絕對不能做的事

- 把任何 secret（DISCORD_TOKEN、GEMINI_API_KEY、DB password、SSH key）commit 進 git
- 在程式碼或測試 fixture 中寫死 API key
- 跳過 Alembic migration 直接改 production DB
- 用 mock 假裝測過真實外部 API（mock 是 CI 隔離手段，不能宣稱 mock 通過 = 真實 API 通過）
- 在 CI 中呼叫真實 Discord、Gemini、巴哈、KKTIX、Tixcraft API
- 引入未列在 §5 技術選型的核心 dependency（小工具如 click 等可加，但 ORM/scheduler/LLM SDK 等核心不可換）
- 為了避過錯誤就跳過 hook（如 `git commit --no-verify`）
- 在 PR / commit 訊息暴露任何 secret 片段
- 用 `linux/amd64` build production image —— 必須 `linux/arm64`
- 在 `src/butler/` 下建立名為 `discord/` 的 subpackage（會與第三方 `discord` 套件 import 衝突）

### 0.3 撰寫順序（嚴格依此順序）

依照 §23 milestone 順序逐個完成。每個 milestone 都必須 pass DoD 才能進入下一個。Milestone 之間不要跨 scope（例如 M3 不要寫 M4 的 LLM 程式碼）。

優先順序：

1. **M0 骨架**：`pyproject.toml`、`uv.lock`、`Dockerfile`、`docker-compose.yml`、`docker-compose.dev.yml`、`.env.example`、CI workflow、`src/butler/` package 樹、ruff/mypy/pytest 設定
2. **M1 Discord lifecycle + `/ping` + health endpoints**
3. **M2 OCI 部署 + GitHub Actions deploy**（提前部署，先驗證環境）
4. **M3 動畫訂閱**
5. **M4 LLM (`/ask` + `/summary`)**
6. **M5 票券訂閱**
7. **M6 Observability**

### 0.4 何時該停下來問 user

- spec 中沒寫的破壞性決策（drop 既有 table、改 schema 不相容、改變 DB driver）
- 外部 API 行為與 spec 描述不符（例如 Gemini API 改版、巴哈動畫瘋網頁結構大改）
- 套件相依性衝突無法用 spec 列出的版本解決
- DoD 中某項驗證項目本機無法重現

不需要問的事（直接做）：

- 補充註解、文件、type hint
- 寫測試
- 修 lint / format 錯誤
- spec 中未列出但對 service 行為無影響的小工具函式

### 0.5 Quality bar

- 每個 service function 應可單元測試（依賴注入 / 不直接 instantiate clients）
- Cogs 不直接寫 SQL / 不直接呼叫 httpx
- 業務邏輯放 `services/`，資料存取放 `repositories/`，外部呼叫放 `crawlers/` 與 `services/llm.py`
- 所有 async function 有清楚 timeout 邊界
- Error log 要帶 `guild_id`、`channel_id`、`user_id`、`command/job` context，**不要 log secret**
- 對 user 的錯誤訊息要短、清楚、可行動

---

## 1. 專案概述

### 1.1 名稱與定位

**Discord Butler Bot** — 一個服務於小型朋友群組的 Discord 多功能管家 bot，整合動畫更新通知、票券開賣監控、LLM 問答與群組摘要，部署在 Oracle Cloud ARM 免費資源上。

### 1.2 設計目標

| 目標 | 描述 |
|---|---|
| 真實使用 | 朋友群組會持續使用，能驅動長期迭代 |
| 技術廣度 | 在單一專案中涵蓋 Backend / DB / Cache / Scheduler / Crawler / LLM / Container / CI/CD / Observability |
| 可維運 | 自架在 OCI Always Free，能用一份 docker-compose 還原至任意 cloud |
| 私人 | 單一 Discord guild，朋友信任度高，不需企業級 RBAC |

### 1.3 角色

| 角色 | 描述 | 權限 |
|---|---|---|
| Owner | 部署與維護者 | 設定環境、看 logs/metrics、處理告警、調整功能 |
| Admin | 受信任朋友或 Discord guild admin | 管理訂閱、觸發狀態檢查、協助排錯 |
| Member | 一般群組成員 | 使用 `/ping`、`/ask`、`/summary`、訂閱動畫與票券通知 |

### 1.4 規模假設

- 單一 Discord guild
- 3-20 人
- 少於 20 個文字 channel
- 每月訊息量 < 10,000 則
- 同時互動量低，簡單 rate limit 即可

### 1.5 明確不做

- 多 server SaaS / 上架公開 bot marketplace
- 商業金流或付費方案
- 完整企業級 RBAC
- MVP 不做：Web 管理面板、語音轉文字、翻譯助手、YOLO 圖像辨識（M7+ 才考慮）

---

## 2. MVP 功能規格

### 2.1 Slash command 總覽

| 功能 | 指令 | 完成於 |
|---|---|---|
| 健康檢查 | `/ping` | M1 |
| 管理診斷 | `/admin status` | M2 |
| 動畫訂閱 | `/anime subscribe`、`/anime list`、`/anime unsubscribe` | M3 |
| LLM 問答 | `/ask` | M4 |
| 群組摘要 | `/summary` | M4 |
| 票券監控 | `/ticket subscribe`、`/ticket list`、`/ticket unsubscribe` | M5 |

### 2.2 `/ping`

目的：確認 bot 存活、Discord gateway 延遲與基本版本資訊。

行為：

- 回覆 gateway latency
- 回覆 app version 或 git sha
- 回覆可設為 ephemeral 避免洗頻

範例：

```text
Pong. gateway=42ms, app=v0.1.0, ready=true
```

### 2.3 `/anime`

```text
/anime subscribe keyword:<作品名> channel:<可選，預設目前 channel>
/anime list
/anime unsubscribe anime:<已訂閱作品>
```

行為：

- `subscribe`：呼叫 animead crawler search → 多結果用 select menu 讓使用者選 → 寫入 `anime_subscriptions`，**`last_episode_no` 與 `last_episode_external_id` 初始化為當下最新集數**（避免第一次訂閱就推送舊集數）
- 每 30 分鐘 scheduler 檢查更新（`ANIME_CHECK_INTERVAL_MINUTES`）
- 新集數寫入 `external_events` + `notification_deliveries`，再送 Discord
- 同一 subscription 對同一 episode 只通知一次（靠 `notification_deliveries.uq_notification_delivery`）

錯誤處理：

- 找不到作品 → 「找不到符合的動畫，請換關鍵字」
- crawler timeout → 「來源暫時無法連線，稍後再試」+ 寫 `crawler_runs.status=failed`
- Discord 發送失敗 → `notification_deliveries.status=failed` 並保留錯誤訊息供排查

### 2.4 `/ask`

```text
/ask question:<問題>
```

行為：

- 立即 `defer`（避免 Discord 3 秒 interaction timeout）
- 檢查 per-user daily rate limit（Redis）
- 呼叫 Gemini API（model 由 `GEMINI_MODEL`）
- 回覆超過 Discord 訊息上限（2000 字）時切多則 follow-up
- 寫 `llm_usage` + `command_invocations`

限制：

- `question` 長度上限 2,000 字
- timeout 60 秒（`GEMINI_TIMEOUT_SECONDS`）
- LLM retry 最多 2 次，只 retry timeout / 429 / 5xx
- 不把 secret、`.env` 內容送進 prompt

### 2.5 `/summary`

```text
/summary count:<10-200，預設 50>
```

行為：

- **需要 Discord Message Content privileged intent**
- 讀取目前 channel 最近 N 則訊息
- 排除 bot 自己、system message、空訊息
- 整理成 prompt（作者顯示名、時間、內容）
- 呼叫 LLM，產出條列：重點摘要、決策/結論、待辦事項、需要回覆的問題
- 寫 `llm_usage`

安全與隱私：

- 僅在 guild 內可用，DM 不可
- 預設公開到 channel；若群組覺得敏感可改 ephemeral 或 admin-only
- 若未啟用 Message Content intent，**明確錯誤訊息**提醒去 Developer Portal 開啟

### 2.6 `/ticket`

```text
/ticket subscribe keyword:<關鍵字> source:<kktix|tixcraft|all> channel:<可選>
/ticket list
/ticket unsubscribe subscription:<訂閱項目>
```

行為：

- `keyword` 做 trim、lowercase、全形空白正規化後存入 `keyword_normalized`
- `source=all` 在查詢時擴展多個 source（不建多筆 subscription）
- 每 5-15 分鐘檢查（`TICKET_CHECK_INTERVAL_MINUTES`，預設 10 分）
- 比對新活動的 title、description、artist 欄位
- 通知含活動名稱、來源、開賣時間、活動時間、URL

注意：

- 票券網站改版機率高 → crawler 必須有 fixture tests
- 尊重 robots.txt、低頻率、明確 user-agent，**不做侵入式繞過**

### 2.7 `/admin status`

```text
/admin status
```

回覆：

- app version / git sha
- DB ready
- Redis ready
- scheduler running jobs
- 最近一次 anime/ticket crawler 結果
- 最近 24 小時錯誤數

權限：

- 僅 Owner、Discord guild admin、或 `DISCORD_ADMIN_ROLE_ID` 指定 role 可用

---

## 3. 非功能性需求

| 類別 | 需求 |
|---|---|
| 可用性 | Bot crash 後由 Docker `restart: unless-stopped` 自動重啟 |
| 可觀測性 | MVP：JSON logs、health endpoints、command/crawler/LLM DB 記錄；M6+：Prometheus/Grafana/Loki |
| 成本控制 | LLM per-user rate limit、可設定每日上限、記錄 token usage |
| 安全 | Secrets 不進 git；正式 `.env` 權限 600；SSH password login 關閉；deploy key 獨立 |
| 效能 | 小群組規模下單一 bot container 足夠；爬蟲與 LLM 使用 async I/O |
| 可維護性 | Crawler 模組化；HTML parsing 有 fixtures；migration 可重跑 |
| 可還原性 | PostgreSQL 每日備份保留 30 天；`.env` 與 deploy key 存密碼管理器；目標 RTO < 1 小時 |

---

## 4. 系統架構

### 4.1 Runtime 架構

```text
Discord Server
  │
  │ Gateway / Interactions
  ▼
bot container (Python 3.12, linux/arm64)
  ├─ discord.py app_commands
  ├─ APScheduler AsyncIOScheduler
  ├─ FastAPI health endpoints (uvicorn as asyncio task)
  ├─ crawler adapters (httpx async)
  ├─ LLM service (google-genai)
  ├─ SQLAlchemy 2.x async + asyncpg
  └─ redis-py asyncio
       │
       ├──────── PostgreSQL 16 (source of truth)
       └──────── Redis 7 (cache / lock / rate limit)

M6+：
Cloudflare Tunnel → bot:8000
Prometheus → /metrics
Grafana / Loki + Promtail
```

### 4.2 Python process 啟動順序

1. 讀取設定（pydantic-settings），初始化 logging
2. 建立 DB engine、Redis client
3. 確認 Alembic migration 已是 head（由 entrypoint.sh `alembic upgrade head` 完成）
4. 啟動 FastAPI health server（uvicorn 作為 asyncio task）
5. 啟動 scheduler，但 job 等 ready 後才真正執行
6. 登入 Discord，sync guild-scoped slash commands

### 4.3 關閉順序

1. 停止接受新 scheduler jobs
2. 關閉 Discord client
3. 關閉 FastAPI server
4. dispose DB engine
5. close Redis connection

### 4.4 互動指令資料流

```text
User slash command
  → discord.py command handler (cog)
  → validate input / permissions / rate limit
  → service layer
  → DB / Redis / external API
  → Discord interaction response
  → command_invocations + structured log
```

### 4.5 排程通知資料流

```text
APScheduler job
  → acquire Redis lock (SET NX EX)
  → load enabled subscriptions from PostgreSQL
  → crawler fetch/parse
  → upsert external_events
  → insert notification_deliveries (skip if exists by unique constraint)
  → send Discord message
  → update delivery status (sent / failed) + subscription cursor
  → release Redis lock
```

---

## 5. 技術選型

| 類別 | 選擇 | 備註 |
|---|---|---|
| Python | 3.12 | async I/O |
| Package manager | `uv` | 速度快，適合 Docker build；維持 lockfile |
| Discord framework | `discord.py` 2.x | slash commands / app_commands |
| Web framework | FastAPI + Uvicorn | health/ready/version；M6 metrics |
| DB | PostgreSQL 16 | 使用 `postgres:16-alpine`（multi-arch） |
| ORM | SQLAlchemy 2.x async + Alembic | migration 必備 |
| DB driver | asyncpg | 搭配 SQLAlchemy async |
| Redis | Redis 7 + redis-py asyncio | rate limit / cache / lock |
| Scheduler | APScheduler `AsyncIOScheduler` | MVP 足夠，不引 Celery |
| HTTP client | httpx async | 統一 timeout/retry/user-agent |
| HTML parser | BeautifulSoup4 或 selectolax | crawler fixtures 解析 |
| LLM | Google Gen AI Python SDK (`google-genai`) | MVP 主要使用 Gemini |
| Config | pydantic-settings | type-safe env parsing |
| Logging | structlog | JSON log 到 stdout |
| Tests | pytest、pytest-asyncio、respx | mock HTTP / async services |
| Lint/format | ruff | lint + format 一站式 |
| Type check | mypy | services/core 嚴格；cogs 必要時放寬 |
| Container | Docker + Docker Compose | dev / prod compose 分離 |
| CI/CD | GitHub Actions + GHCR | build linux/arm64，SSH 部署 |

---

## 6. 專案結構

```text
DiscordGuildKeeper/
├─ PROJECT_SPEC.md            ← 本文件（單一權威 spec）
├─ README.md                  ← 給 user 看的快速入門
├─ pyproject.toml
├─ uv.lock
├─ Dockerfile
├─ docker-compose.yml         ← production
├─ docker-compose.dev.yml     ← 本機開發（hot reload、暴露 port）
├─ .env.example
├─ .dockerignore
├─ .gitignore
├─ alembic.ini
├─ migrations/
│  ├─ env.py
│  └─ versions/
├─ scripts/
│  ├─ entrypoint.sh
│  └─ backup.sh
├─ .github/
│  └─ workflows/
│     ├─ ci.yml
│     └─ deploy.yml
├─ src/
│  └─ butler/
│     ├─ __init__.py
│     ├─ main.py              ← Python entry point
│     ├─ core/
│     │  ├─ __init__.py
│     │  ├─ config.py         ← pydantic-settings
│     │  ├─ db.py             ← SQLAlchemy engine/session
│     │  ├─ redis_client.py
│     │  ├─ logging.py        ← structlog 設定
│     │  ├─ scheduler.py      ← APScheduler 包裝
│     │  └─ version.py        ← git sha / app version
│     ├─ bot/                 ← Discord-related code (注意：「bot」名稱不與 discord 套件衝突)
│     │  ├─ __init__.py
│     │  ├─ client.py         ← discord.Client 實例與 lifecycle
│     │  ├─ permissions.py    ← admin role check helpers
│     │  └─ cogs/
│     │     ├─ __init__.py
│     │     ├─ ping.py
│     │     ├─ anime.py
│     │     ├─ ai.py          ← /ask + /summary
│     │     ├─ tickets.py
│     │     └─ admin.py
│     ├─ api/                 ← FastAPI
│     │  ├─ __init__.py
│     │  ├─ app.py            ← FastAPI app 建立
│     │  ├─ health.py         ← /healthz, /readyz, /version
│     │  └─ metrics.py        ← /metrics（M6+）
│     ├─ crawlers/
│     │  ├─ __init__.py
│     │  ├─ base.py           ← interface + dataclass
│     │  ├─ animead.py        ← 巴哈動畫瘋
│     │  ├─ kktix.py
│     │  └─ tixcraft.py       ← 拓元
│     ├─ models/              ← SQLAlchemy ORM
│     │  ├─ __init__.py
│     │  ├─ base.py
│     │  ├─ discord_entities.py
│     │  ├─ subscriptions.py
│     │  ├─ events.py
│     │  ├─ usage.py
│     │  └─ crawler.py
│     ├─ repositories/        ← 資料存取層
│     │  ├─ __init__.py
│     │  ├─ subscriptions.py
│     │  ├─ events.py
│     │  └─ usage.py
│     └─ services/            ← 業務邏輯
│        ├─ __init__.py
│        ├─ anime.py
│        ├─ tickets.py
│        ├─ llm.py            ← Gemini provider
│        ├─ summary.py
│        ├─ notification.py
│        └─ rate_limit.py
└─ tests/
   ├─ __init__.py
   ├─ conftest.py
   ├─ fixtures/
   │  ├─ animead/
   │  ├─ kktix/
   │  └─ tixcraft/
   ├─ unit/
   └─ integration/
```

說明：

- 使用 `src/butler` 為 top-level package，避免 `bot` 名稱與 Discord bot instance 概念混淆
- **不**使用 `butler/discord/` 子目錄 —— 會與第三方 `discord` 套件 import 衝突（在 `from discord import app_commands` 時 Python 會優先解析到本地 sibling，而非真正的 discord.py）
- Discord 相關 code 放 `butler/bot/`（`bot` 不是已知的第三方套件名）
- 業務邏輯放 `services/`；資料存取放 `repositories/`；外部呼叫放 `crawlers/` 與 `services/llm.py`
- Cogs 只負責 Discord command adapter，不直接 SQL 或外部 HTTP

---

## 7. 設定與環境變數

### 7.1 `.env.example`

```env
# App
APP_ENV=development
APP_VERSION=0.1.0
LOG_LEVEL=INFO
JSON_LOGS=true
TZ=Asia/Taipei

# Discord
DISCORD_TOKEN=
DISCORD_GUILD_ID=
DISCORD_ADMIN_ROLE_ID=
DISCORD_SYNC_COMMANDS=true

# LLM / Gemini
LLM_PROVIDER=gemini
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash-lite
GEMINI_TIMEOUT_SECONDS=60
GEMINI_MAX_OUTPUT_TOKENS=1200

# PostgreSQL
POSTGRES_USER=butler
POSTGRES_PASSWORD=change-me
POSTGRES_DB=butler
DATABASE_URL=postgresql+asyncpg://butler:change-me@postgres:5432/butler

# Redis
REDIS_URL=redis://redis:6379/0

# FastAPI
API_HOST=0.0.0.0
API_PORT=8000

# Scheduler
ANIME_CHECK_INTERVAL_MINUTES=30
TICKET_CHECK_INTERVAL_MINUTES=10
SCHEDULER_LOCK_TTL_SECONDS=900

# Crawlers
CRAWLER_USER_AGENT=DiscordButlerBot/0.1 (+private friend guild)
HTTP_TIMEOUT_SECONDS=20
HTTP_RETRY_ATTEMPTS=2

# Rate limits
ASK_DAILY_LIMIT_PER_USER=30
SUMMARY_DAILY_LIMIT_PER_USER=10
SUMMARY_MAX_MESSAGES=200

# M6+ Cloudflare Tunnel
TUNNEL_TOKEN=
```

### 7.2 設定規則

- `config.py` 使用 `pydantic-settings`，啟動時即驗證必要 env
- `APP_ENV=production` 時，缺少 `DISCORD_TOKEN`、`DATABASE_URL`、`REDIS_URL` 必須**啟動失敗**（fail-fast）
- `LLM_PROVIDER` MVP 固定 `gemini`；不在 MVP 期間實作多 provider 切換
- `GEMINI_API_KEY` 缺少時 bot 仍可啟動，但 `/ask`、`/summary` 回覆「功能未設定」
- `GEMINI_MODEL` 預設 `gemini-2.5-flash-lite` 控制成本；摘要品質不足可改 `gemini-2.5-flash`
- 所有 interval 與 rate limit 透過 env 調整

---

## 8. 資料庫設計

### 8.1 命名規範

- Table 使用 plural snake_case
- Discord snowflake 使用 `BIGINT`
- 時間欄位使用 `TIMESTAMPTZ`
- 重要 unique constraint 必須明確命名（`uq_<table>_<purpose>`）
- 所有 schema 變更透過 Alembic，**不手改正式 DB**

### 8.2 Tables

#### `discord_users`

```sql
CREATE TABLE discord_users (
  id BIGINT PRIMARY KEY,
  username TEXT,
  global_name TEXT,
  display_name TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

#### `discord_guilds`

```sql
CREATE TABLE discord_guilds (
  id BIGINT PRIMARY KEY,
  name TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

#### `anime_subscriptions`

```sql
CREATE TABLE anime_subscriptions (
  id BIGSERIAL PRIMARY KEY,
  guild_id BIGINT NOT NULL REFERENCES discord_guilds(id),
  user_id BIGINT NOT NULL REFERENCES discord_users(id),
  channel_id BIGINT NOT NULL,
  keyword TEXT NOT NULL,
  anime_sn TEXT NOT NULL,
  anime_title TEXT NOT NULL,
  last_episode_no INT NOT NULL DEFAULT 0,
  last_episode_external_id TEXT,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  last_checked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_anime_subscription UNIQUE (guild_id, user_id, anime_sn)
);
```

#### `ticket_subscriptions`

```sql
CREATE TABLE ticket_subscriptions (
  id BIGSERIAL PRIMARY KEY,
  guild_id BIGINT NOT NULL REFERENCES discord_guilds(id),
  user_id BIGINT NOT NULL REFERENCES discord_users(id),
  channel_id BIGINT NOT NULL,
  source TEXT NOT NULL, -- kktix | tixcraft
  keyword_raw TEXT NOT NULL,
  keyword_normalized TEXT NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  last_checked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_ticket_subscription UNIQUE (guild_id, user_id, source, keyword_normalized)
);
```

#### `external_events`

```sql
CREATE TABLE external_events (
  id BIGSERIAL PRIMARY KEY,
  source TEXT NOT NULL,       -- animead | kktix | tixcraft
  event_type TEXT NOT NULL,   -- anime_episode | ticket_event
  external_id TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT,
  starts_at TIMESTAMPTZ,
  published_at TIMESTAMPTZ,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_external_event UNIQUE (source, event_type, external_id)
);
```

#### `notification_deliveries`

```sql
CREATE TABLE notification_deliveries (
  id BIGSERIAL PRIMARY KEY,
  event_id BIGINT NOT NULL REFERENCES external_events(id),
  subscription_kind TEXT NOT NULL, -- anime | ticket
  subscription_id BIGINT NOT NULL,
  guild_id BIGINT NOT NULL,
  channel_id BIGINT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', -- pending | sent | failed
  discord_message_id BIGINT,
  error_message TEXT,
  delivered_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_notification_delivery UNIQUE (event_id, subscription_kind, subscription_id)
);
```

#### `llm_usage`

```sql
CREATE TABLE llm_usage (
  id BIGSERIAL PRIMARY KEY,
  guild_id BIGINT,
  channel_id BIGINT,
  user_id BIGINT REFERENCES discord_users(id),
  command TEXT NOT NULL,
  provider TEXT NOT NULL DEFAULT 'gemini',
  model TEXT,
  input_tokens INT,
  output_tokens INT,
  estimated_cost_usd NUMERIC(12, 6),
  request_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

#### `command_invocations`

```sql
CREATE TABLE command_invocations (
  id BIGSERIAL PRIMARY KEY,
  interaction_id BIGINT UNIQUE,
  guild_id BIGINT,
  channel_id BIGINT,
  user_id BIGINT,
  command_name TEXT NOT NULL,
  status TEXT NOT NULL, -- success | failed | rate_limited | validation_error
  latency_ms INT,
  error_type TEXT,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

#### `crawler_runs`

```sql
CREATE TABLE crawler_runs (
  id BIGSERIAL PRIMARY KEY,
  source TEXT NOT NULL,
  job_name TEXT NOT NULL,
  status TEXT NOT NULL, -- success | failed | partial
  items_found INT NOT NULL DEFAULT 0,
  error_type TEXT,
  error_message TEXT,
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at TIMESTAMPTZ
);
```

### 8.3 Indexes

```sql
CREATE INDEX ix_anime_subscriptions_enabled ON anime_subscriptions (enabled);
CREATE INDEX ix_ticket_subscriptions_enabled ON ticket_subscriptions (enabled);
CREATE INDEX ix_external_events_seen ON external_events (first_seen_at DESC);
CREATE INDEX ix_notification_deliveries_status ON notification_deliveries (status);
CREATE INDEX ix_llm_usage_user_created ON llm_usage (user_id, created_at DESC);
CREATE INDEX ix_command_invocations_created ON command_invocations (created_at DESC);
CREATE INDEX ix_crawler_runs_source_started ON crawler_runs (source, started_at DESC);
```

### 8.4 Migration 規則

- 所有 schema 變更透過 Alembic
- Migration file 必須能 `alembic upgrade head` 重跑（idempotent 或新 revision）
- 不在 Alembic 之外手改 schema
- Production migration 由 entrypoint 自動跑（MVP 單 replica）

---

## 9. Redis 設計

| 用途 | Key | TTL |
|---|---|---|
| LLM daily limit | `ratelimit:llm:{command}:{guild_id}:{user_id}:{yyyyMMdd}` | 2 天 |
| Scheduler lock | `lock:scheduler:{job_name}` | `SCHEDULER_LOCK_TTL_SECONDS` |
| Anime search cache | `cache:anime:search:{normalized_keyword}` | 6 小時 |
| Ticket search cache | `cache:ticket:{source}:{normalized_keyword}` | 5-15 分鐘 |
| Health temporary state | `state:last_success:{job_name}` | 7 天 |

規則：

- Lock 使用 `SET key value NX EX ttl`
- Lock value 用 UUID，釋放時用 Lua script 確認 value 相同才 DEL
- Redis 失效時，訂閱查詢仍應可用；只有 rate limit、cache、scheduler lock 降級
- **Redis 不能作為唯一通知去重來源**（必須靠 PostgreSQL `notification_deliveries.uq_notification_delivery`）

---

## 10. Crawler 合約

### 10.1 共用 dataclass

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class AnimeSearchResult:
    source: str
    anime_sn: str
    title: str
    url: str
    latest_episode_no: int | None = None

@dataclass(frozen=True)
class AnimeEpisode:
    source: str
    anime_sn: str
    title: str
    episode_no: int
    external_id: str
    url: str
    published_at: datetime | None = None

@dataclass(frozen=True)
class TicketEvent:
    source: str
    external_id: str
    title: str
    url: str
    starts_at: datetime | None = None
    sale_starts_at: datetime | None = None
    raw: dict
```

### 10.2 Base interface

```python
class AnimeCrawler:
    async def search(self, keyword: str) -> list[AnimeSearchResult]: ...
    async def latest_episode(self, anime_sn: str) -> AnimeEpisode | None: ...

class TicketCrawler:
    async def search_events(self, keyword: str) -> list[TicketEvent]: ...
```

### 10.3 HTTP 規則

- 所有 request 透過共用 `httpx.AsyncClient`
- 設定 connect / read timeout（`HTTP_TIMEOUT_SECONDS`）
- 設定明確 user-agent（`CRAWLER_USER_AGENT`）
- retry 最多 `HTTP_RETRY_ATTEMPTS` 次，只 retry timeout / 429 / 5xx
- **MVP 不使用 headless browser**
- Parsing 必須有 HTML fixture 單元測試

### 10.4 External ID 規則

- 動畫集數：`animead:{anime_sn}:episode:{episode_no}`
- KKTIX：頁面有 stable event id 用原 id；否則用 canonical URL hash
- Tixcraft：同上，優先 stable id，其次 canonical URL hash

---

## 11. LLM 設計

### 11.1 Service interface

```python
class LLMService:
    async def ask(self, question: str, user_display_name: str | None = None) -> LLMResponse: ...
    async def summarize_messages(self, messages: list[MessageForSummary]) -> LLMResponse: ...
```

### 11.2 MVP 實作要求

- 只實作 Gemini provider
- SDK：Google 官方 `google-genai` Python package
- API key 由 `GEMINI_API_KEY` 注入，**不得寫死在程式碼或測試 fixture**
- 模型由 `GEMINI_MODEL` 控制，預設 `gemini-2.5-flash-lite`
- 本機開發可用 Gemini API free tier；正式環境建議使用已設 billing / prepay credit 的 API key，避免 production bot 因免費層 rate limit 中斷
- 未來加 Claude / OpenAI / 本地 LLM 時新增 provider adapter，**不改 cog**

### 11.3 Prompt 要求

`/ask`：

- system prompt 應說明 bot 是朋友群助手
- 回答使用繁體中文，除非使用者要求其他語言
- 不假裝能存取不存在的上下文

`/summary`：

- 輸出包含「重點摘要」、「決策/結論」、「待辦事項」、「需要回覆的問題」
- 訊息太少或內容不足時直接說明，不編造
- 不輸出過度敏感個資；保留必要暱稱即可

### 11.4 成本與 rate limit

- `/ask` 與 `/summary` 分開計算每日次數
- 先檢查 Redis rate limit，再呼叫 LLM
- Gemini 回應若提供 `usage_metadata`，將 input/output token 寫入 `llm_usage`
- `llm_usage.provider` 固定 `gemini`，`llm_usage.model` 寫入實際使用的 `GEMINI_MODEL`
- `estimated_cost_usd` 可先為 NULL；若要計算成本，使用專案內單一可維護的價格表，不要把價格硬編在多處

---

## 12. Discord 實作注意事項

### 12.1 Intents

| Intent | 必要 | 用途 |
|---|---|---|
| `guilds` | 是 | 基本 guild 資訊 |
| `messages` + `message_content` | `/summary` 需要 | privileged intent，需在 Developer Portal 啟用 |

注意：

- Message Content 是 **privileged intent**。未在 Developer Portal 啟用時，message object 的 `content` 會是空值
- 因專案是私人單一 server，使用 **guild-scoped slash commands**（command 更新傳播更快）

### 12.2 Interaction timeout

- 所有可能 > 2 秒的 command 必須先 `defer`
- `/ask`、`/summary`、crawler search 都需 `defer`

### 12.3 訊息長度

- Discord 單則訊息上限 2000 字
- 實作 `split_discord_message(text)` helper：先按段落、再按句子、最後硬切

### 12.4 權限

- 一般成員：`/ping`、`/anime`、`/ticket`、`/ask`、`/summary`
- `/admin`：Owner、guild admin、或 `DISCORD_ADMIN_ROLE_ID` 指定 role
- 朋友群濫用 LLM 時先調低 per-user limit，不做複雜封鎖系統

---

## 13. Scheduler 設計

### 13.1 Jobs

| Job | 預設頻率 | 說明 |
|---|---|---|
| `anime_check_updates` | `ANIME_CHECK_INTERVAL_MINUTES`（預設 30 分） | 檢查所有 enabled anime subscriptions |
| `ticket_check_events` | `TICKET_CHECK_INTERVAL_MINUTES`（預設 10 分） | 檢查所有 enabled ticket subscriptions |
| `cleanup_old_runtime_state` | 每日 | 清理過舊 command/crawler 暫存，保留核心使用紀錄 |

### 13.2 Idempotency

- 每個 job 執行前取得 Redis lock（防多 replica 重跑）
- 寫入 `external_events` 用 upsert
- 寫入 `notification_deliveries` 靠 unique constraint 防重
- Discord 發送成功後更新 delivery `status=sent`
- 發送失敗保留 `status=failed`，**不無限 retry**（未來可做 admin retry）

### 13.3 Startup 行為

- Bot 啟動後**不要立刻**對所有舊事件發通知
- 新 subscription 的 `last_episode_no` / cursor 以當下最新事件為 baseline
- 只有 baseline 之後的新事件才通知

---

## 14. FastAPI 端點

### 14.1 MVP 端點

| Method | Path | 說明 |
|---|---|---|
| GET | `/healthz` | process 活著就回 200（用於 docker healthcheck） |
| GET | `/readyz` | DB、Redis、Discord 都 ready 才回 200 |
| GET | `/version` | 回 app version、git sha、build time |

`/readyz` 範例：

```json
{
  "status": "ok",
  "discord": true,
  "postgres": true,
  "redis": true,
  "scheduler": true
}
```

### 14.2 M6+ 端點

| Method | Path | 說明 |
|---|---|---|
| GET | `/metrics` | Prometheus metrics（M6 才實作，詳見 §23） |

### 14.3 Port binding

- FastAPI port 在 docker compose 內**只 bind `127.0.0.1`**，不對外
- M6+ 要外部訪問時透過 Cloudflare Tunnel（不開 OCI security list port）

---

## 15. Docker 與 Compose

### 15.1 Dockerfile 要求

- Base：`python:3.12-slim` 系列（確認支援 `linux/arm64`）
- Multi-stage build
- 非 root user 執行 app
- 複製 lockfile 後先安裝 dependency，再複製 source（提高 build cache 效率）
- **install `curl`** 給 healthcheck 使用（slim image 預設沒有）
- 啟動命令走 `scripts/entrypoint.sh`

### 15.2 Entrypoint

`scripts/entrypoint.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail
alembic upgrade head
exec python -m butler.main
```

MVP 是單一 bot replica，啟動時跑 migration 可接受。多 replica 時 migration 應拆 release step。

### 15.3 Production compose（`docker-compose.yml`）

```yaml
services:
  bot:
    image: ghcr.io/<github-owner>/butler-bot:latest
    restart: unless-stopped
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    ports:
      - "127.0.0.1:8000:8000"
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://localhost:8000/healthz || exit 1"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 30s
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - ./data/redis:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
```

說明：

- `bot` FastAPI port 只 bind `127.0.0.1`
- M6+ 啟用 Cloudflare Tunnel 後可用 service name `http://bot:8000`，不需要 host port
- Bot healthcheck 要求 `curl` 在 image 內可用

### 15.4 Dev compose（`docker-compose.dev.yml`）

開發版差異：

- bot 從本機 build（不從 GHCR pull）
- mount 本機 `src/` 進 container 做 hot reload
- postgres / redis port 暴露到 host（5432 / 6379）方便 IDE 連線
- env 用 `.env`（與 production 同檔，但 token 是 dev 用）

### 15.5 M6+ Cloudflare Tunnel 片段（不在 MVP compose）

```yaml
  cloudflared:
    image: cloudflare/cloudflared:latest
    restart: unless-stopped
    command: tunnel --no-autoupdate run --token ${TUNNEL_TOKEN}
    env_file: .env
    depends_on:
      - bot
```

---

## 16. CI/CD

### 16.1 CI workflow（`.github/workflows/ci.yml`）

必須：

- checkout
- setup Python + uv
- `ruff format --check`
- `ruff check`
- `mypy src`
- `pytest`
- Docker build smoke test（不 push）

CI **不**呼叫真實外部服務（Discord、Gemini、巴哈、KKTIX、Tixcraft）。所有外部呼叫 mock 或用 fixtures。

### 16.2 Deploy workflow（`.github/workflows/deploy.yml`）

```yaml
name: Build and Deploy

on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-24.04-arm  # 優先：原生 ARM；不可用時改 ubuntu-latest + Buildx QEMU
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Login to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Build and push (arm64)
        uses: docker/build-push-action@v5
        with:
          context: .
          platforms: linux/arm64
          push: true
          tags: |
            ghcr.io/${{ github.repository_owner }}/butler-bot:latest
            ghcr.io/${{ github.repository_owner }}/butler-bot:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  deploy:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.OCI_HOST }}
          username: ${{ secrets.OCI_USER }}
          key: ${{ secrets.OCI_SSH_KEY }}
          script: |
            cd /opt/butler-bot
            echo "${{ secrets.GHCR_PAT }}" | docker login ghcr.io -u ${{ secrets.GHCR_USERNAME }} --password-stdin
            docker compose pull bot
            docker compose up -d bot
            docker image prune -f
```

### 16.3 ARM build 注意事項

- 優先 `runs-on: ubuntu-24.04-arm`（GitHub 自 2024 對 public repo 提供免費 ARM runner）
- 若不可用，fallback `ubuntu-latest` + Buildx + QEMU emulation。**警告**：QEMU emulate Python build 可能慢 5-10 分鐘
- **不要** build `linux/amd64` 部署 ARM instance —— OCI A1 跑不起來

### 16.4 GitHub Secrets

| Secret | 用途 |
|---|---|
| `OCI_HOST` | OCI public IP 或 hostname |
| `OCI_USER` | deploy user（`deploy`，§17.7 建立） |
| `OCI_SSH_KEY` | deploy 私鑰完整內容 |
| `GHCR_USERNAME` | 你的 GitHub username |
| `GHCR_PAT` | scope `read:packages`（server 用）/ `write:packages`（CI build 用） |

---

## 17. 部署：OCI Day-1 SOP

### 17.1 前置準備

- [ ] Oracle Cloud 帳號（已通過信用卡驗證）
- [ ] Cloudflare 帳號 + 自有網域（M6+ Tunnel 才需要）
- [ ] GitHub repo 已建，本機可正常 build / 跑
- [ ] Discord Bot Token、Gemini API Key 已取得
- [ ] 本機已產 SSH key pair（之後上傳 public key 到 OCI）

### 17.2 建立 OCI Compute Instance

OCI Console：

1. **Menu → Compute → Instances → Create Instance**
2. 設定：
   - Name：`butler-bot-prod`
   - Image：`Canonical Ubuntu 24.04` (aarch64)
   - Shape：`VM.Standard.A1.Flex` → 4 OCPU / 24 GB RAM（Always Free 上限）
   - Networking：default VCN，**勾「Assign a public IPv4 address」**
   - SSH keys：上傳本機 `~/.ssh/id_ed25519.pub`
   - Boot volume：50 GB
3. 記下 **Public IP**

### 17.3 OCI 雷點警告

#### 雷點 1：VCN security list 沒開 port，bot 連不上 Discord

預設 VCN egress 全開，但若改過規則，要確認 outbound 443 可通（Discord Gateway 走 WSS over 443）。

#### 雷點 2：Ubuntu image iptables 預設擋掉所有 port

OCI 的 Ubuntu image 在 `iptables` 把幾乎所有 port 擋了，只留 SSH (22)。即使 VCN 開過某 port，機器內也要：

```bash
sudo iptables -L INPUT --line-numbers
# 不對外開 port（用 Cloudflare Tunnel）→ 不用動
# 要開 80/443:
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

#### 雷點 3：Always Free instance 7 天閒置會被回收

對策：

- bot 持續跑就會持續產流量，正常使用不會中
- 偶爾 SSH 進去執行指令、看一下 status，當作保險

### 17.4 系統初始化

```bash
ssh ubuntu@<public-ip>

sudo apt update && sudo apt -y full-upgrade
sudo apt install -y \
  ca-certificates curl gnupg lsb-release \
  ufw fail2ban unattended-upgrades \
  htop vim git tmux jq
```

#### SSH 加固

```bash
sudo vim /etc/ssh/sshd_config.d/99-hardening.conf
```

內容：

```text
PasswordAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
ClientAliveInterval 60
ClientAliveCountMax 3
```

```bash
sudo systemctl restart ssh
```

#### unattended-upgrades

```bash
sudo dpkg-reconfigure --priority=low unattended-upgrades
```

#### fail2ban

```bash
sudo systemctl enable --now fail2ban
```

#### 時區與 NTP

```bash
sudo timedatectl set-timezone Asia/Taipei
timedatectl status   # 確認 System clock synchronized: yes
```

### 17.5 安裝 Docker（ARM 注意事項）

```bash
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

sudo usermod -aG docker ubuntu
```

重新登入後驗證：

```bash
docker version
uname -m   # 應為 aarch64
docker run --rm hello-world
```

**ARM image 雷**：之後選 image 時，若官方文件沒提 multi-arch，務必去 Docker Hub 確認該 tag 有 `linux/arm64`。本專案所有依賴（Python、PostgreSQL、Redis、Cloudflared）都有 arm64 官方 image。

### 17.6 應用部署

```bash
sudo mkdir -p /opt/butler-bot/{data/postgres,data/redis,backups,scripts}
sudo chown -R ubuntu:ubuntu /opt/butler-bot
cd /opt/butler-bot
```

撰寫 `.env`（內容見 §7.1）：

```bash
vim /opt/butler-bot/.env
chmod 600 /opt/butler-bot/.env   # 重要！
```

產隨機密碼：`openssl rand -base64 32`

撰寫 `/opt/butler-bot/docker-compose.yml`（內容見 §15.3）。

第一次手動部署測試（GitHub Actions 還沒設定時）：

```bash
echo $GHCR_PAT | docker login ghcr.io -u <your-username> --password-stdin

docker compose pull
docker compose up -d
docker compose logs -f bot
```

去 Discord 打 `/ping` 確認。

### 17.7 GitHub Actions deploy user

在 OCI instance：

```bash
sudo adduser --disabled-password --gecos "" deploy
sudo usermod -aG docker deploy
sudo mkdir -p /home/deploy/.ssh
sudo chown deploy:deploy /home/deploy/.ssh
sudo chmod 700 /home/deploy/.ssh
sudo chown -R deploy:deploy /opt/butler-bot
```

本機產專屬 deploy key：

```bash
ssh-keygen -t ed25519 -f ~/.ssh/butler_deploy -C "github-actions-butler"
```

把 public key 寫入 `/home/deploy/.ssh/authorized_keys`：

```bash
sudo -u deploy vim /home/deploy/.ssh/authorized_keys
sudo chmod 600 /home/deploy/.ssh/authorized_keys
```

到 GitHub repo Settings → Secrets 設定 §16.4 列的 5 個 secret。

---

## 18. 部署：Cloudflare Tunnel（M6+ 啟用條件）

**僅在以下任一條件成立時啟用**：

- M6 Web 管理面板需要外部訪問
- 需要將 `/metrics` 暴露給遠端 Prometheus
- 需要對外提供其他 HTTP service

純 Discord bot **不需要** public ingress —— Discord Gateway 是 bot 主動連出。

### 18.1 在 Cloudflare 建立 Tunnel

1. Dashboard → **Zero Trust → Networks → Tunnels → Create a tunnel**
2. 選 **Cloudflared**，命名 `butler-prod`
3. 複製 token，貼到 `.env` 的 `TUNNEL_TOKEN`
4. Public Hostname：
   - Subdomain：`butler`
   - Domain：你的網域
   - Service：`http://bot:8000`（compose 內部 service name）

### 18.2 加進 compose

加入 §15.5 的 `cloudflared` 區塊，然後：

```bash
docker compose up -d cloudflared
```

外網連 `https://butler.<你的網域>` 就會打到 bot FastAPI。

**為何用 Cloudflare Tunnel 而不開 port**：

- OCI 雙層防火牆（VCN security list + Ubuntu iptables）開洞容易出包
- Tunnel 從機器主動連出，server 無 public ingress
- 免費，自動 TLS，可加 Cloudflare Access 做身分驗證

---

## 19. 災難備援與還原

### 19.1 備份策略

| 資料 | 頻率 | 保留 | 位置 |
|---|---|---|---|
| PostgreSQL `pg_dump` | 每日 03:00 | 30 天 | OCI Object Storage（方案 A）/ 本機 + 偶爾手動 scp（方案 B） |
| `.env` | 每次手改後 | 永久 | 1Password / Bitwarden |
| Compose 設定 | 跟 git 走 | 永久 | GitHub repo |

### 19.2 Object Storage 備份前置條件

選一個方案：

#### 方案 A：oci-cli（推薦）

```bash
sudo apt install -y python3-pip
pip install --user oci-cli
~/.local/bin/oci setup config
# 互動式輸入 tenancy OCID、user OCID、region，自動產 API key
```

到 OCI Console → Identity → Users → 你的 user → API Keys 上傳剛產的 public key。

到 OCI Console → Object Storage → Create Bucket：

- Name：`butler-backups`
- Region：與 instance 同 region
- Tier：Standard

#### 方案 B：純本機保留 + 偶爾手動 scp

省去 oci-cli 設定，但 RTO 取決於 instance 本身是否還活著。MVP 期間可接受。

### 19.3 自動備份腳本

`/opt/butler-bot/scripts/backup.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR=/opt/butler-bot/backups
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
KEEP_DAYS=30

cd /opt/butler-bot

docker compose exec -T postgres pg_dump -U butler butler | gzip \
  > "${BACKUP_DIR}/butler-${TIMESTAMP}.sql.gz"

# 方案 A：上傳 Object Storage（需先完成 §19.2）
oci os object put \
  --bucket-name butler-backups \
  --file "${BACKUP_DIR}/butler-${TIMESTAMP}.sql.gz" \
  --force

# 清理本機舊檔
find "${BACKUP_DIR}" -name "butler-*.sql.gz" -mtime +${KEEP_DAYS} -delete
```

```bash
chmod +x /opt/butler-bot/scripts/backup.sh

# 加 cron
crontab -e
# 加入：
0 3 * * * /opt/butler-bot/scripts/backup.sh >> /var/log/butler-backup.log 2>&1
```

### 19.4 還原流程

```bash
cd /opt/butler-bot
docker compose stop bot                         # 先停 bot 避免寫入
gunzip -c backups/butler-YYYYMMDD-HHMMSS.sql.gz | \
  docker compose exec -T postgres psql -U butler -d butler
docker compose start bot
```

驗證：`/ping` 與 `/admin status` 回應正常。

### 19.5 Instance 完全失效的 Runbook

1. 跟著 §17.2-§17.5 重建一台 instance
2. clone repo 到 `/opt/butler-bot`
3. 從 1Password / Bitwarden 還原 `.env`
4. 從 OCI Object Storage 抓最新 dump
5. `docker compose up -d postgres redis` → 還原 dump → `docker compose up -d`

**目標 RTO**：< 1 小時。

---

## 20. Day-2 維運常用指令

```bash
# 看 bot log（即時）
docker compose -f /opt/butler-bot/docker-compose.yml logs -f bot

# 重啟單一服務
docker compose restart bot

# 看資源用量
docker stats

# 進 postgres 互動 shell
docker compose exec postgres psql -U butler -d butler

# 進 bot container
docker compose exec bot bash

# 強制拉最新 image 重啟（手動 deploy 用）
cd /opt/butler-bot
docker compose pull && docker compose up -d

# 看磁碟用量（OCI 50 GB boot volume，data/ 與 backups/ 容易吃滿）
df -h
du -sh /opt/butler-bot/data/*
docker system df

# 看 OOM 紀錄
dmesg | grep -i kill
```

---

## 21. 排錯速查表

| 症狀 | 第一步 | 常見原因 |
|---|---|---|
| bot 不上線 | `docker compose logs bot` | Discord token 錯 / 網路 / 程式 crash / migration 失敗 |
| Discord 沒回應 slash command | 檢查 Developer Portal 是否註冊指令 | 全域指令傳播要 1 小時，dev 用 guild 指令 |
| `/summary` 拿到空 content | 檢查 Message Content intent | Developer Portal 未啟用 privileged intent |
| `pg_isready` 一直 fail | `docker compose logs postgres` | `data/postgres` 權限錯 / 密碼跟 `.env` 不一致 |
| GitHub Actions deploy 卡 build | 看 build log 時間 | QEMU 跑 arm64 慢；改用 `ubuntu-24.04-arm` runner |
| 磁碟突然滿 | `docker system df` | log 沒設 rotation / 老 image 沒清 / postgres bloat |
| OOM | `dmesg \| grep -i kill` | bot memory leak / postgres `shared_buffers` 設太大 |
| 從外網連不到 | curl from instance 自己看 | iptables / Cloudflare Tunnel 沒跑 / DNS 沒設 |
| `/anime subscribe` 找不到作品 | 看 `crawler_runs` 最近紀錄 | 巴哈動畫瘋網頁改版 / fixture 過時 |
| `/ask` 回「功能未設定」 | 確認 `.env` 的 `GEMINI_API_KEY` | API key 缺失或無效 |
| `import discord` ModuleNotFoundError | 檢查 `src/butler/` 下有無 `discord/` 目錄 | 本地 sibling 與 third-party 套件衝突 |

---

## 22. 測試策略

### 22.1 Unit tests（必測）

- `config.py` env parsing
- `rate_limit.py` Redis key 與 limit 行為
- `split_discord_message`
- crawler parsing：用 fixtures，不打真實網站
- subscription service：新訂閱 baseline、不重複通知
- notification service：成功與失敗狀態
- LLM prompt builder：過長訊息截斷、空訊息處理

### 22.2 Integration tests

建議用 docker compose 或 testcontainers：

- PostgreSQL migration 可跑（從空 DB `alembic upgrade head`）
- repositories CRUD
- notification unique constraint
- Redis lock acquire/release

### 22.3 不在 CI 做的事

- 不連真實 Discord Gateway
- 不呼叫真實 Gemini API
- 不爬真實票券或動畫網站
- 不部署 OCI

### 22.4 Coverage

- MVP 目標 > 60%
- Crawler / services / repositories 優先補測試
- Cogs 用較薄 adapter tests，不追求完整 mock Discord internals

---

## 23. 里程碑與 Definition of Done

### M0 — 專案骨架

交付：

- `pyproject.toml`、`uv.lock`
- `src/butler/` package 樹（含空的 module placeholder）
- `Dockerfile`
- `docker-compose.yml`、`docker-compose.dev.yml`
- `.env.example`
- ruff、mypy、pytest 設定
- `.github/workflows/ci.yml`

DoD：

- [ ] `docker compose -f docker-compose.dev.yml up` 可啟動 postgres / redis / bot
- [ ] bot container 啟動到「等 Discord 連線」階段並印 structlog JSON 啟動 log（即使尚無 token 也應 graceful 等待）
- [ ] `pytest` 通過（即便只有 placeholder smoke test）
- [ ] `ruff check`、`mypy src` 全綠
- [ ] CI workflow 在 GitHub 跑通

### M1 — Discord lifecycle + `/ping` + health endpoints

交付：

- discord.py app_commands skeleton
- `/ping`
- FastAPI `/healthz`、`/readyz`、`/version`
- structlog JSON logs
- Alembic 第一版 migration（`discord_users`、`discord_guilds`、`command_invocations`）

DoD：

- [ ] Bot 可登入測試 server
- [ ] `/ping` 回應 latency 與 version
- [ ] `curl /healthz` 200
- [ ] `curl /readyz` 反映 DB / Redis 狀態
- [ ] `curl /version` 回 git sha
- [ ] `alembic upgrade head` 從空 DB 跑得起

### M2 — OCI 部署 + GitHub Actions（**早期部署，先驗證環境**）

交付：

- GHCR image build (linux/arm64) workflow
- `.github/workflows/deploy.yml`
- OCI instance 已建好（§17）
- `/opt/butler-bot` compose 已部署
- `scripts/backup.sh`
- README 快速使用說明

DoD：

- [ ] push main 後 5 分鐘內自動部署到 OCI
- [ ] OCI 上的 bot `/ping` 在 Discord 正常回應
- [ ] `docker compose ps` 三服務 healthy（含 bot healthcheck）
- [ ] 手動跑 `backup.sh` 成功，dump 出現在 Object Storage（或本機 backups/）
- [ ] `.env`、deploy key、GHCR PAT 已存密碼管理器
- [ ] 從 instance 上 `curl https://discord.com` 通暢（驗證 outbound 443）
- [ ] `/admin status` 在 production 上正常回覆

### M3 — 動畫更新通知

交付：

- `crawlers/animead.py` + fixtures tests
- `/anime subscribe`、`/anime list`、`/anime unsubscribe`
- `anime_subscriptions`、`external_events`、`notification_deliveries` migration
- scheduler `anime_check_updates`
- Redis lock 與通知去重

DoD：

- [ ] 使用者可訂閱作品
- [ ] 新集數會在排程內通知到正確 channel
- [ ] 同一集不會重複通知（重啟 bot 仍不重發）
- [ ] crawler 失敗會寫 `crawler_runs.status=failed`
- [ ] **在 OCI production 環境完成一次端到端通知**（M2 已部署，這裡用 production 驗證）

### M4 — LLM 問答與摘要

交付：

- `services/llm.py`（Gemini provider）
- `/ask`
- `/summary`
- Redis rate limit
- `llm_usage` table

DoD：

- [ ] `/ask` 可正常回覆
- [ ] `/summary` 可摘要指定 channel 近期訊息
- [ ] 超過 rate limit 時回覆清楚的提示
- [ ] LLM token usage 寫入 `llm_usage`
- [ ] `GEMINI_API_KEY` 缺失時 bot 仍可啟動，`/ask` 與 `/summary` 回「功能未設定」

### M5 — 票券監控

交付：

- `crawlers/kktix.py`、`crawlers/tixcraft.py` + fixtures tests
- `/ticket subscribe`、`/ticket list`、`/ticket unsubscribe`
- `ticket_subscriptions` migration
- scheduler `ticket_check_events`

DoD：

- [ ] 可訂閱關鍵字
- [ ] 新票券活動符合關鍵字時通知
- [ ] crawler 失敗不會讓 bot crash
- [ ] `source=all` 在查詢時擴展 kktix + tixcraft

### M6 — Observability

交付：

- FastAPI `/metrics`（prometheus_client）
- compose 加 Prometheus + Grafana + Loki + Promtail
- Grafana 儀表板：Bot Health Overview
- Cloudflare Tunnel（讓你從外網看 Grafana）
- Discord webhook alert（**獨立 webhook，不透過 bot**，bot 掛了才收得到）

DoD：

- [ ] 可看到 command latency、crawler success rate、LLM token usage、DB / Redis health
- [ ] bot 掛掉或磁碟 > 80% 會告警到獨立 webhook
- [ ] Prometheus 抓 bot `/metrics` + node_exporter 主機指標

### M7+（不在 MVP scope，依興趣排序）

- M7：Web 管理面板（React + FastAPI + Discord OAuth2）
- M8：Whisper 語音轉文字
- M9：翻譯助手 + 日語學習
- M10：YOLO 圖像辨識（呼應求職背景，可接既有 Triton inference server）

---

## 24. 風險與因應

| 風險 | 影響 | 因應 |
|---|---|---|
| 巴哈/KKTIX/拓元改版 | 通知失效 | crawler fixtures、錯誤告警、parser 模組化 |
| Discord Message Content intent 未啟用 | `/summary` 讀不到內容 | 啟動檢查 + 清楚錯誤訊息；文件提醒 |
| LLM 成本失控 | API 費用增加 | per-user daily limit、token usage、可調模型 |
| OCI instance 被回收或故障 | 服務中斷 | 每日備份、§19.5 Runbook、可搬遷 compose |
| ARM image 不相容 | 無法部署 | CI build `linux/arm64`，依賴選 multi-arch image |
| Scheduler 重複執行 | 重複通知 | Redis lock + PostgreSQL unique constraints |
| Redis 掛掉 | rate limit / cache 失效 | 降級處理；通知去重靠 DB |
| Discord rate limit | 訊息發送延遲 | discord.py 內建處理；通知批次與錯誤記錄 |
| OCI 雙層防火牆鎖死 | 服務無法外部訪問 | 用 Cloudflare Tunnel 不開 port；§17.3 雷點 |
| Always Free 7 天閒置回收 | 服務中斷 | 正常使用即可；偶爾 SSH 驗證 |

---

## 25. 工程實作守則

實作順序（嚴格依 §23 milestone）：

1. M0：骨架、CI、Docker、設定系統
2. M1：DB models 與第一版 migration、Discord bot lifecycle、FastAPI health、`/ping`
3. M2：GHCR build、OCI 部署、deploy workflow、backup script、README
4. M3：anime crawler 與 subscription flow
5. M4：LLM service、`/ask`、`/summary`
6. M5：ticket crawler 與 subscription flow
7. M6：observability stack

品質要求：

- 每個 service function 應可單元測試
- Cogs **不**直接寫 SQL query
- External clients **不**散落在 command handler
- 所有 async function 有清楚 timeout 邊界
- Error log 帶 `guild_id`、`channel_id`、`user_id`、`command/job`，**不輸出 secret**
- 對使用者的錯誤訊息要短、清楚、可行動

---

## 26. 上線前檢查表

- [ ] `.env` 已設定且 `chmod 600`
- [ ] `GEMINI_API_KEY` 已設定；若啟用 `/ask`、`/summary`，AI Studio 專案 quota 足夠
- [ ] `GEMINI_MODEL` 已選定（預設 `gemini-2.5-flash-lite`）
- [ ] Discord Developer Portal 已啟用必要 intents（含 Message Content）
- [ ] Bot 已邀請到目標 guild
- [ ] `docker compose ps` 全部 healthy（含 bot healthcheck）
- [ ] `/ping` 正常
- [ ] `/readyz` 回 200，所有子系統 true
- [ ] `/anime subscribe/list/unsubscribe` 正常（M3+）
- [ ] `/ask` 正常，rate limit 正常（M4+）
- [ ] `/summary` 正常，Message Content 可讀（M4+）
- [ ] `/ticket subscribe/list/unsubscribe` 正常（M5+）
- [ ] GitHub Actions CI 通過
- [ ] GitHub Actions deploy 成功
- [ ] 手動備份成功，並確認 Object Storage 看得到檔案
- [ ] `.env`、deploy key、GHCR PAT 已存密碼管理器
- [ ] OCI Console 設 instance monitoring alert（CPU > 80% / disk > 80%）
- [ ] README 有本機啟動、部署、排錯連結指向 §21

---

## 27. 參考連結

- Discord developer docs: <https://docs.discord.com/developers/docs/intro>
- Discord message content intent: <https://docs.discord.com/developers/events/gateway>
- discord.py docs: <https://discordpy.readthedocs.io/>
- Gemini API docs: <https://ai.google.dev/gemini-api/docs>
- Gemini API pricing: <https://ai.google.dev/gemini-api/docs/pricing>
- SQLAlchemy async ORM: <https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html>
- APScheduler docs: <https://apscheduler.readthedocs.io/>
- Oracle Cloud Always Free: <https://docs.oracle.com/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm>
- GitHub hosted runners: <https://docs.github.com/en/actions/reference/runners/github-hosted-runners>
- Cloudflare Tunnel docs: <https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/>
- OCI VCN security list: <https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securitylists.htm>
- Conventional Commits: <https://www.conventionalcommits.org/>

---

## 28. 變更紀錄

| 版本 | 日期 | 變更 |
|---|---|---|
| v2.0 | 2026-05-07 | 整合並重新分章為單一 self-contained 規格；package 命名修正為 `butler/bot/`（避開 `import discord` 衝突）；M2 提前部署以早期驗證 production pipeline；補入 OCI 雷點、排錯速查表、Day-2 維運、Object Storage 備份前置條件、bot compose healthcheck；移除履歷敘事章節；移除對其他 spec 文件的引用 |
| v1.1 | 2026-05-07 | 將主要 LLM provider 從 Anthropic/Claude 改為 Google Gemini API |
| v1.0 | 2026-05-07 | 整合產品規格與部署 SOP，補齊工程實作規格 |
