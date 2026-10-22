# SteamList 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付 SteamList——自托管 Docker Web 应用，跟踪关注游戏的 Steam 国区价格历史，展示阶梯走势、历史低价（ATL）与命中频次、打折事件与频次，支持心愿单导入与 Bark/邮件/Webhook 降价提醒。

**Architecture:** 单镜像方案。后端 FastAPI + SQLAlchemy(SQLite) + 同步 APScheduler 后台调度；前端 React 18 SPA（Vite 构建），由 FastAPI 挂载 `app/static` 并做 history fallback。镜像两阶段：`node:22-alpine` 构建前端 → `python:3.12-slim` 运行。SQLite 文件与备份放 `data/` 卷。

**Tech Stack:** Python 3.12（本地 3.10 兼容）、FastAPI ≥0.115、SQLAlchemy 2、Pydantic 2、httpx、APScheduler 3、pytest；React 18、TypeScript、Vite 6、Tailwind CSS 4、ECharts 5、@tanstack/react-query、lucide-react、react-router-dom 7。

**设计文档：** `docs/superpowers/specs/2026-10-22-steam-price-tracker-design.md`

## Global Constraints

- 金额一律整数「分」(cents)，禁止 float 参与价格存储/比较；展示时格式化。
- 时区：后端存 UTC（`datetime.now(timezone.utc)`），接口输出 ISO8601 带时区；前端按浏览器本地时区展示；调度计划用 `Asia/Shanghai`。
- Steam 请求串行、批量 100 个 appid/请求、批间隔 1–3 秒，429/5xx 指数退避最多 4 次并尊重 `Retry-After`；任何单游戏失败不得中断整个任务。
- 多 appid 请求必须带 `filters=price_overview`；免费/不可售（`price_overview` 为空且 `is_free=false`）记为 `available=false`，绝不当作 0 元。
- 无登录、无多用户；不做多区比价；不引入 SteamDB/gg.deals/ITAD 抓取。
- 前端必须显示「记录起点」（首次变化时间）以标注历史数据仅从上线起积累。
- 本地 Python 3.10.11 运行，代码不得使用 3.11+ 语法；容器内 3.12。
- 所有金额、ATL、频次定义以设计文档「统计口径」为准。
- 提交信息用 Conventional Commits（feat/fix/test/docs/chore）。

## 文件结构

```
steamList/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 应用、lifespan、静态托管、异常处理
│   ├── config.py            # 环境变量/路径/默认设置（pydantic-settings）
│   ├── db.py                # Engine/Session、建表、迁移入口
│   ├── models.py            # SQLAlchemy ORM 模型
│   ├── schemas.py           # Pydantic 请求/响应模型
│   ├── api/
│   │   ├── __init__.py
│   │   ├── health.py        # /api/health
│   │   ├── games.py         # 搜索、详情、series、stats
│   │   ├── watchlist.py     # 关注列表 CRUD、心愿单导入
│   │   ├── settings.py      # 设置读写
│   │   ├── jobs.py          # 手动刷新、任务状态
│   │   └── notifications.py # 通道测试、通知日志
│   └── services/
│       ├── __init__.py
│       ├── steam_client.py  # appdetails / storesearch / wishlist / 限速重试
│       ├── pricing.py       # 入库去重、状态更新、ATL 事件
│       ├── analytics.py     # 阶梯序列、ATL、打折事件、频次统计
│       ├── wishlist.py      # 心愿单导入编排
│       ├── notifier.py      # 规则判定、通道发送、去重冷却
│       ├── scheduler.py     # tick 调度、任务执行、job_runs
│       └── backup.py        # SQLite 在线备份与保留策略
├── tests/
│   ├── conftest.py
│   ├── fixtures/*.json
│   ├── test_steam_client.py
│   ├── test_pricing.py
│   ├── test_analytics.py
│   ├── test_notifier.py
│   └── test_api.py
├── web/                     # 前端（Vite 工程）
│   ├── package.json, vite.config.ts, tsconfig.json, index.html
│   └── src/{main.tsx, App.tsx, index.css, lib/{api.ts,types.ts,format.ts},
│            components/..., pages/{Dashboard,GameDetail,AddGame,Settings}.tsx}
├── requirements.txt / requirements-dev.txt
├── Dockerfile / docker-compose.yml / .dockerignore / .gitignore / .env.example
├── deploy.ps1
└── README.md
```

---

### Task 1: 仓库骨架与可运行的健康检查

**Files:**
- Create: `.gitignore`, `requirements.txt`, `requirements-dev.txt`, `app/__init__.py`, `app/config.py`, `app/main.py`, `app/api/__init__.py`, `app/api/health.py`, `tests/conftest.py`, `tests/test_api.py`
- Create: `pytest.ini`

**Interfaces:**
- Produces: `app.config.Settings`（`db_path: Path`, `data_dir: Path`, `timezone: str = "Asia/Shanghai"`, `default_cc: str = "cn"`, `default_lang: str = "schinese"`, proxy 字段）；`app.main.create_app() -> FastAPI`；`GET /api/health -> {"status":"ok","version":str,"db":"ok"}`。

- [ ] **Step 1: 写失败测试** `tests/test_api.py`

```python
from fastapi.testclient import TestClient

def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
```

`tests/conftest.py`：用 tmp_path 覆盖 `STEAMLIST_DATA_DIR` 环境变量，`from app.main import create_app`，fixture `client` 返回 `TestClient(create_app())`（with 上下文以触发 lifespan）。

- [ ] **Step 2: 运行确认失败**：`python -m pytest tests/test_api.py -q` → 期望 ImportError/404。
- [ ] **Step 3: 最小实现**：`config.py` 用 pydantic-settings 读 `STEAMLIST_DATA_DIR`（默认 `./data`），确保目录存在；`db.py` 先只提供 `init_engine()`/`get_session()` 与 WAL；`main.py` 的 `create_app()` 注册 health 路由，`app = create_app()` 供 uvicorn 使用。
- [ ] **Step 4: 测试通过**：`python -m pytest -q`。
- [ ] **Step 5: 提交**：`git add -A && git commit -m "chore: scaffold FastAPI app with health check"`。

---

### Task 2: 数据模型与设置存储

**Files:**
- Create: `app/models.py`, `app/db.py`（补全建表与 session 依赖）
- Create: `app/services/__init__.py`, `app/services/settings_store.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Produces ORM：`Game(appid: int PK, name, header_image, short_description, developers, publishers, genres, release_date, is_free: bool, last_synced_at)`；`WatchItem(id PK, appid UNIQUE FK, cc, target_price_cents: int|None, notify_enabled: bool, discount_alert_threshold: int|None, sort_order: int, note: str, created_at)`；`PriceChange(id PK, appid, cc, currency, initial_cents, final_cents, discount_percent, available: bool, changed_at, UNIQUE(appid,cc,changed_at))`；`WatchState(appid PK, cc, current_final_cents, current_initial_cents, current_discount_percent, available, currency, atl_cents, atl_first_at, atl_last_at, atl_hit_count, first_change_at, last_checked_at)`；`NotificationChannel(id PK, kind, name, config_json, enabled, created_at)`；`NotificationLog(id PK, appid, rule, dedupe_key UNIQUE, title, body, channel_id, status, error, created_at, sent_at)`；`AppSetting(key PK, value_json)`；`JobRun(id PK, job_type, status, started_at, finished_at, checked_count, changed_count, error)`。
- Produces：`settings_store.get_settings(session) -> dict` / `update_settings(session, patch: dict) -> dict`（键：`poll_enabled, poll_interval_hours, poll_time, cc, lang, steamid, wishlist_last_import_at, next_poll_at, meta_refresh_at, proxy_url`）。
- 建表幂等：`Base.metadata.create_all`，并启用 `PRAGMA journal_mode=WAL`、`foreign_keys=ON`。

- [ ] **Step 1: 写测试**：建表后插入 watch item，重复 `create_all` 不报错；`update_settings` 往返；默认值包含 `poll_time="03:30"`、`poll_interval_hours=24`、`cc="cn"`。
- [ ] **Step 2: 运行失败** → **Step 3: 实现** → **Step 4: 通过**。
- [ ] **Step 5: 提交**：`feat: add SQLAlchemy models and settings store`。

---

### Task 3: SteamClient（限速、批量、解析）

**Files:**
- Create: `app/services/steam_client.py`
- Test: `tests/test_steam_client.py` + `tests/fixtures/{appdetails_batch.json,appdetails_meta.json,storesearch.json,wishlist.json}`

**Interfaces:**
- `@dataclass PriceResult(appid: int, currency: str, initial_cents: int, final_cents: int, discount_percent: int, available: bool, is_free: bool)`
- `@dataclass GameMeta(appid, name, header_image, short_description, developers: str, publishers: str, genres: str, release_date: str, is_free: bool)`
- `@dataclass SearchItem(appid: int, name: str, header_image: str, price_cents: int|None, currency: str)`
- `class SteamClient`：`__init__(cc="cn", lang="schinese", proxy: str|None=None, timeout=25.0, min_interval=2.0, transport=None)`；`async fetch_prices(appids: Sequence[int]) -> dict[int, PriceResult|None]`（内部 100/批，批间 sleep）；`async fetch_meta(appid: int) -> GameMeta|None`；`async search(term: str, limit=12) -> list[SearchItem]`；`async fetch_wishlist(steamid: str) -> list[int]`；`async aclose()`。
- 解析约定：`success` 为真才解析；`price_overview` 缺失且 `is_free` 为真 → `PriceResult(available=True, final=0, is_free=True)`；缺失且非免费 → `PriceResult(available=False, final=0)`；金额字段为分，直接使用。
- 重试：`429/5xx/网络异常` 指数退避 `1,2,4,8` 秒，优先 `Retry-After`；4 次后返回空/None，记录 warning 日志，不抛给调用方（搜索除外，搜索失败抛 `SteamError`）。

- [ ] **Step 1: 写测试**：用 `httpx.MockTransport` 注入 fixture。
  - 批请求 URL 含 `filters=price_overview`，且 3 个 appid 解析出 1245620=29800、1086940=26800、730 为免费可用；
  - 免费/不可售区分：构造 `price_overview=null, is_free=false` → `available=False`；
  - meta 解析出 name/developers/genres/release_date；
  - storesearch 解析中文名与 CNY 价格；
  - wishlist 解析 `response.items[].appid`，空响应 → `[]`；
  - 429 一次后重试成功（transport 计数）。
- [ ] **Step 2: 失败** → **Step 3: 实现** → **Step 4: 通过** → **Step 5: 提交** `feat: add rate-limited Steam client`。

---

### Task 4: 入库与 ATL 状态（pricing）

**Files:**
- Create: `app/services/pricing.py`
- Test: `tests/test_pricing.py`

**Interfaces:**
- `@dataclass PriceEvent(appid: int, kind: Literal["atl","target","discount"], final_cents: int, previous_atl_cents: int|None, discount_percent: int, currency: str)`
- `@dataclass IngestResult(checked: int, changed: int, events: list[PriceEvent])`
- `def ingest_prices(session, results: dict[int, PriceResult|None], cc: str, now: datetime|None=None) -> IngestResult`
  - 仅处理 `watch_items` 中存在的 appid；`None` 结果计入 checked 但不改变状态。
  - 价格无变化（final/discount/available 全等）且已有 state → 只更新 `last_checked_at`，不插 `price_changes`。
  - 有变化 → 插入 `price_changes`，更新 `watch_state` 当前值；更新 `first_change_at`（若为空）与 ATL：
    - `final>0 且 available`：若 `atl_cents is None or final<atl_cents` → ATL=final, first=last=now, hit_count=1，事件 `atl`（previous_atl 非空时）；若 `final==atl_cents` 且 `previous_final>atl_cents` → hit_count+=1, last=now，事件 `atl`。
  - 事件 `discount`：`discount_percent>0` 且（无旧 state 或旧折扣为 0 或新折扣>旧折扣）。
  - 事件 `target`：`target_price_cents` 非空且 `0<final<=target` 且（旧值为空或旧值>target，或折扣刚出现）。
  - 免费游戏（final=0）不参与 ATL，事件规则跳过。
- `def ensure_game(session, meta: GameMeta) -> Game`（upsert 元数据）。

- [ ] **Step 1: 写测试**（关键用例）
```python
def test_first_snapshot_sets_atl(session):
    _add_watch(session, 1245620, target_price_cents=None)
    r = ingest_prices(session, {1245620: price(29800)}, cc="cn")
    assert r.changed == 1
    st = session.get(WatchState, 1245620)
    assert (st.atl_cents, st.atl_hit_count) == (29800, 1)
    assert session.query(PriceChange).count() == 1

def test_unchanged_price_no_duplicate_row(session):
    ingest_prices(session, {1245620: price(29800)})
    r = ingest_prices(session, {1245620: price(29800)})
    assert r.changed == 0
    assert session.query(PriceChange).count() == 1

def test_new_low_increments_hit_count_and_emits_atl_event(session):
    ingest_prices(session, {1245620: price(29800)})
    r = ingest_prices(session, {1245620: price(14900, discount=50)})
    st = session.get(WatchState, 1245620)
    assert st.atl_cents == 14900 and st.atl_hit_count == 2
    assert [e.kind for e in r.events] == ["discount", "atl"]

def test_returning_to_atl_counts_new_hit_only_after_rising(session):
    # 29800 → 14900 → 29800 → 14900 期望 hit_count == 3
```
- [ ] **Step 2: 失败** → **Step 3: 实现** → **Step 4: 通过** → **Step 5: 提交** `feat: persist price changes and track ATL`。

---

### Task 5: 分析（series / stats）

**Files:**
- Create: `app/services/analytics.py`
- Test: `tests/test_analytics.py`

**Interfaces:**
- `@dataclass Point(at: datetime, initial_cents: int, final_cents: int, discount_percent: int, available: bool)`
- `def load_points(session, appid: int, cc: str|None=None) -> list[Point]`（按 changed_at 升序，cc 默认取 watch item 的 cc）
- `def build_series(points, start: datetime|None, end: datetime) -> list[dict]`：先取 `start` 之前最后一个点作锚点；输出 `{"t": iso, "final": int, "initial": int, "discount": int, "available": bool}`；当 `start` 为 None 时从第一个点开始。
- `@dataclass Stats(at_least...)`：`def compute_stats(points, now) -> dict`，字段：
  `first_change_at, last_change_at, change_count, current_final_cents, current_discount_percent, atl_cents, atl_first_at, atl_last_at, atl_hit_count, discount_event_count, discount_days, max_discount_percent, avg_discount_percent, avg_interval_days, last_discount_at, days_tracked`
- 打折事件：`discount>0` 的连续区间；区间内折扣变化仍算同一事件；`end` 为下一个 `discount==0` 的点或 `now`。事件数、总天数、最大/平均折扣（取区间内最大折扣）、相邻事件起始间隔均值。
- 空列表返回全 None / 0，且 `days_tracked=0`，不抛异常。

- [ ] **Step 1: 写测试**：构造 29800 → 14900(50%) → 29800 → 14900；断言 ATL=14900、hit_count=2、series 首点锚点、事件数=2、avg_interval；空数据处理。
- [ ] **Step 2: 失败** → **Step 3: 实现** → **Step 4: 通过** → **Step 5: 提交** `feat: add price series and discount analytics`。

---

### Task 6: 关注列表与游戏 API

**Files:**
- Create: `app/api/watchlist.py`, `app/api/games.py`, `app/schemas.py`
- Test: `tests/test_api_watchlist.py`（用 `dependency_overrides` 注入假 SteamClient）

**Interfaces:**
- `POST /api/watchlist` body `{appid:int, cc?:str, target_price_cents?:int, discount_alert_threshold?:int, note?:str}` → 201 `WatchItemOut`（含 `game` 元数据、`state` 摘要）。若已存在 → 200 返回既有项。创建时立即抓一次 meta+price（Steam 失败也创建，state 为空）。
- `GET /api/watchlist` → `{items: [...], summary: {count, atl_count, discounting_count, last_checked_at}}`，每项含 `appid/name/header_image/current price(initial/final/discount)/atl_cents/atl_hit_count/target_price_cents/notify_enabled/discount_alert_threshold/note/sort_order/record_started_at`。
- `PATCH /api/watchlist/{appid}` → 更新 `target_price_cents/notify_enabled/discount_alert_threshold/note/sort_order`（`target_price_cents` 允许 null 清除）。
- `DELETE /api/watchlist/{appid}` → 204，同时删除 state；保留 `price_changes` 历史。
- `GET /api/games/search?term=&cc=` → `{items: [{appid,name,header_image,price_cents,currency}]}`；term 长度 <2 → 400。
- `GET /api/games/{appid}` → meta + state；`GET /api/games/{appid}/series?range=30d|90d|1y|all` → `{appid, range, start, end, points: [...], record_started_at}`；`GET /api/games/{appid}/stats` → `{appid, stats: {...}, record_started_at}`。
- 422/404 语义：appid 不在关注列表 → 404 `{"detail": "game not watched"}`。

- [ ] **Step 1: 写测试**：添加→列表→改目标价→series/stats→删除；重复添加幂等；搜索短词 400；未关注 appid 404。
- [ ] **Step 2: 失败** → **Step 3: 实现** → **Step 4: 通过** → **Step 5: 提交** `feat: add watchlist and games API`。

---

### Task 7: 设置、任务与调度

**Files:**
- Create: `app/api/settings.py`, `app/api/jobs.py`, `app/services/scheduler.py`
- Test: `tests/test_scheduler.py`

**Interfaces:**
- `GET /api/settings` / `PUT /api/settings`（部分更新，返回完整设置）；`PUT` 变更 `cc` 时仅影响后续采集。
- `POST /api/jobs/refresh` → `202 {"job_id": int}`；若已有运行中任务 → `409 {"detail": "job already running"}`。
- `GET /api/jobs/status` → `{running: bool, current: JobRunOut|null, last: JobRunOut|null, next_poll_at: iso|null}`。
- `class Scheduler`：`start()/shutdown()`；`run_poll(manual=False) -> JobRun`（串行：加载 watch items → 批量抓价 → `ingest_prices` → 通知评估 → 写 job_runs → 更新 `next_poll_at`）；`run_meta_refresh()`；`tick()` 每 5 分钟检查 `poll_enabled and now>=next_poll_at`；单实例锁 `threading.Lock`，只允许一个轮询线程。
- `next_poll_at` 计算：`poll_interval_hours` 小时；若设置了 `poll_time` 且为每日模式，则取下一个本地 `poll_time`（Asia/Shanghai）。简化：`next_poll_at = now + interval_hours`，`poll_time` 仅用于首次对齐/文档展示。
- 启动时若 `next_poll_at` 为空则立即排一次（不阻塞启动，后台线程）。

- [ ] **Step 1: 写测试**：`run_poll` 用假 client，断言 job_runs 记录 status=success、changed_count、next_poll_at 前进；并发调用第二次返回 409（或锁生效）；`tick` 未到期不执行。
- [ ] **Step 2: 失败** → **Step 3: 实现** → **Step 4: 通过** → **Step 5: 提交** `feat: add scheduler and job endpoints`。

---

### Task 8: 通知（Bark/邮件/Webhook）与心愿单导入

**Files:**
- Create: `app/services/notifier.py`, `app/services/wishlist.py`, `app/api/notifications.py`
- Test: `tests/test_notifier.py`

**Interfaces:**
- `@dataclass NotificationMessage(title: str, body: str)`
- `def dispatch(session, messages: list[tuple[int, str, NotificationMessage]], now) -> int`：对每个启用通道发送；写 `notification_log`；失败重试 2 次；`dedupe_key=f"{appid}:{rule}:{final_cents}:{date}"`，已存在或同 rule 24h 内已发 → 跳过。
- 通道实现：`send_bark(config, msg)`（POST `{server}/push`，body `{"title","body","device_key","group":"SteamList"}`）；`send_email(config, msg)`（smtplib SSL/STARTTLS）；`send_webhook(config, msg)`（httpx POST JSON `{title,body,appid,rule,price}`，超时 10s）。Bark/Webhook 同步 httpx，邮件同步。
- `POST /api/notifications/test` body `{channel_id?: int}` → 发送测试消息，返回每通道 `{channel_id, ok, error}`。
- `GET /api/notifications/log?limit=50` → 最近日志倒序。
- 通道管理（v1 简化，设置页内嵌）：`PUT /api/settings` 中 `channels: [{kind,name,config,enabled}]` 全量替换 `notification_channels`（删除后重建），避免额外端点。
- `import_wishlist(session, client, steamid, cc) -> {imported, skipped, total}`：拉心愿单 appid（上限 200），逐批抓 meta+价格，写入 watch_items（`notify_enabled=false` 默认 false 以避免骚扰，UI 可批量开启），生成 `ImportResult`。

- [ ] **Step 1: 写测试**：target 命中生成 1 条并落库；同价同日重复调度 → 不重复；24h 冷却；Bark payload 字段正确（MockTransport）；webhook 失败重试后 status=failed；心愿单导入去重。
- [ ] **Step 2: 失败** → **Step 3: 实现** → **Step 4: 通过** → **Step 5: 提交** `feat: add notifications and wishlist import`。

---

### Task 9: 备份、静态托管与应用装配

**Files:**
- Create: `app/services/backup.py`, `app/api/backup.py`; Modify: `app/main.py`
- Test: `tests/test_backup.py`

**Interfaces:**
- `def create_backup(data_dir: Path, db_path: Path) -> Path`：`sqlite3` 在线备份到 `data/backups/steamlist-YYYYmmdd-HHMMSS.db`；`prune_backups(dir, keep=7)`。
- `GET /api/backup` → `FileResponse` 最新备份（不存在则实时创建）。
- `main.py`：lifespan 建表/初始化设置/启动 Scheduler/关闭；挂载 `/api` 路由；`app.mount("/assets", StaticFiles(...))` + `GET /{path:path}` 返回 `index.html`（存在 dist 时）；`/docs` 保留。

- [ ] **Step 1: 写测试**：备份文件存在且可 `sqlite3.connect` 查询；保留策略删除旧文件；`GET /api/backup` 200 且 content-type 含 sqlite。
- [ ] **Step 2: 失败** → **Step 3: 实现** → **Step 4: 通过** → **Step 5: 提交** `feat: add backup and SPA hosting`。

---

### Task 10: 前端脚手架、类型与 API 客户端（冻结契约）

**Files:**
- Create: `web/package.json`, `web/vite.config.ts`, `web/tsconfig.json`, `web/tsconfig.node.json`, `web/index.html`, `web/postcss.config.js`, `web/src/main.tsx`, `web/src/App.tsx`, `web/src/index.css`, `web/src/lib/{types.ts,api.ts,format.ts,cn.ts}`, `web/src/components/ui/*`

**Interfaces（冻结，前端所有页面依赖）：**
- `types.ts` 与后端响应一一对应：`WatchItem`, `WatchSummary`, `WatchlistResponse`, `GameDetail`, `SeriesResponse`, `StatsResponse`, `Settings`, `JobStatus`, `NotificationLogEntry`, `ChannelConfig`。
- `api.ts`：`getWatchlist()`, `addWatch({appid,...})`, `patchWatch(appid, body)`, `removeWatch(appid)`, `searchGames(term)`, `getGame(appid)`, `getSeries(appid, range)`, `getStats(appid)`, `getSettings()`, `putSettings(patch)`, `refreshPrices()`, `getJobStatus()`, `testNotification(channelId?)`, `getNotificationLog()`, `importWishlist(steamid)`, `backupUrl()`；统一 `request<T>` 抛 `ApiError{status,message}`。
- `format.ts`：`formatPrice(cents, currency)`, `formatPercent`, `formatDate(iso)`, `formatRelative(iso)`, `formatDurationDays`。
- 设计令牌（Tailwind 4 `@theme`）：深色底 `#0b0f14`，面板 `#111820`，描边 `#1e2a36`，Steam 蓝 `#66c0f4`，青 `#2dd4bf`，低价绿 `#4ade80`，折扣橙 `#fbbf24`，字体 `Inter`/`system-ui`，数字用 `font-variant-numeric: tabular-nums`。

- [ ] **Step 1: 脚手架**：`cd web && pnpm create vite@latest . --template react-ts`（若网络受限则手写配置）；安装 `pnpm add @tanstack/react-query react-router-dom echarts lucide-react clsx tailwind-merge class-variance-authority`，开发依赖 `tailwindcss @tailwindcss/vite`。
- [ ] **Step 2: 验证**：`pnpm build` 成功产出 `web/dist/index.html`。
- [ ] **Step 3: 提交** `feat: scaffold React frontend with API client`。

---

### Task 11: 页面实现（前端 teammate 负责，Lead 只 review）

**Files:**
- Create: `web/src/pages/Dashboard.tsx`, `GameDetail.tsx`, `Settings.tsx`, `components/{AppShell,GameCard,StatBar,PriceChart,DiscountTimeline,AddGameDialog,WishlistImportDialog,StatusPill,EmptyState}.tsx`, `web/src/components/ui/*`

**Interfaces:**
- 路由：`/` 仪表盘、`/games/:appid` 详情、`/settings` 设置；`AppShell` 顶栏（品牌、刷新按钮、任务状态、设置入口）。
- 仪表盘：4 个统计卡（关注数、正在打折、历史低价命中、上次采集时间）；游戏卡片网格（封面、名称、当前价/原价/折扣徽章、ATL、命中次数、迷你 sparkline 可选）；筛选（全部/打折中/低于目标价/未通知）+ 排序（添加时间/折扣/名称）；点击进详情；空状态引导添加游戏。
- 详情：头部（封面/名称/开发商/发行日期/记录起点「数据自 YYYY-MM-DD 起累计」）；KPI 行（当前价、历史低价+命中次数+首次/最近时间、打折事件数、平均折扣、平均间隔天数）；ECharts 阶梯图（final 阶梯线 + initial 虚线可选 + ATL markLine + 打折区间 markArea + 时间范围切换 30d/90d/1y/all + tooltip 显示原价/现价/折扣）；事件时间线（最近价格变化，含涨跌标记）；设置目标价/提醒开关（PATCH）。
- 设置：区域 cc/lang、轮询开关/间隔、SteamID + 导入心愿单、通知通道（Bark server/device_key、SMTP、Webhook URL）增删与测试、任务状态、通知日志表、下载备份。
- 全部页面 loading skeleton、错误态（提示后端未启动）、移动端可用（1 列 → 2 列 → 3 列）。

- [ ] **Step 1:** Lead 先提供 `web/src/lib/{types,api,format}.ts` 与设计令牌（Task 10）。
- [ ] **Step 2:** teammate 实现 Dashboard + AppShell。
- [ ] **Step 3:** teammate 实现 GameDetail（ECharts）。
- [ ] **Step 4:** teammate 实现 AddGame/WishlistImport + Settings。
- [ ] **Step 5:** `pnpm build` 通过；Lead 启动后端 + dist 做视觉验收（截图/浏览器核对），列出修复清单，teammate 修复。
- [ ] **Step 6:** 提交 `feat: build dashboard, game detail and settings UI`。

---

### Task 12: Docker、compose、deploy.ps1、README

**Files:**
- Create: `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `deploy.ps1`, `README.md`

**Interfaces:**
- `Dockerfile` 两阶段：
  1. `FROM node:22-alpine AS web`：`WORKDIR /web`，`COPY web/package.json web/pnpm-lock.yaml*`，`RUN corepack enable && pnpm install --frozen-lockfile`（无 lock 时 `pnpm install`），`COPY web/`，`RUN pnpm build`。
  2. `FROM python:3.12-slim`：`ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Shanghai`；`WORKDIR /app`；`COPY requirements.txt` + `pip install --no-cache-dir -r requirements.txt`；`COPY app/ app/`；`COPY --from=web /web/dist app/static/`；`RUN mkdir -p /app/data`；`EXPOSE 8080`；`HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/api/health',timeout=3)"`；`CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8080"]`。
- `docker-compose.yml`：service `steamlist`，`build: .`，`image: steamlist:latest`，`container_name: steamlist`，`restart: unless-stopped`，`ports: ["8080:8080"]`，`volumes: ["./data:/app/data"]`，`environment: TZ, STEAMLIST_DATA_DIR=/app/data, HTTP_PROXY/HTTPS_PROXY/NO_PROXY 可选注入`，`extra_hosts: ["host.docker.internal:host-gateway"]`，healthcheck 同 Dockerfile。
- `deploy.ps1`（参数与参考项目一致）：`-RemoteUser`(必填) `-RemoteHost`(默认 192.168.173.22) `-RemotePort`(22) `-RemotePath`(D:\ProgramFiles\steamlist) `-ProxyUrl`(可选) `-NoProxy` `-IdentityFile`(默认 ~/.ssh/DockerPub_ed25519) `-DryRun`。步骤：本地 `docker build -t steamlist:latest .` → `docker save` 到临时 tar → 打包项目 zip（排除 `.git`, `data`, `web/node_modules`, `app/static`, `__pycache__`, `*.db`）→ `scp` zip 与 tar → `ssh`（EncodedCommand，UTF-16LE base64）远端 `Expand-Archive -Force` → `docker load -i` → `docker compose -p steamlist up -d --no-build` → `docker compose ps` → 打印远端访问 URL（`http://<host>:8080`）。`-DryRun` 只打印命令不执行；失败即抛错退出非 0。
- `README.md`：项目简介、功能截图（可选）、架构图（文字）、快速开始（docker compose）、本地开发（后端 uvicorn + 前端 pnpm dev + vite proxy /api → 8080）、配置项表（环境变量/设置页）、部署到远程（deploy.ps1 示例与 SSH 要求）、价格数据来源与限速说明、历史数据仅自上线起累积的说明、备份恢复、FAQ（代理/Steam++ 环境、免费游戏显示、时区）。

- [ ] **Step 1:** 写 Dockerfile/compose/.dockerignore，`docker build -t steamlist:test .` 成功。
- [ ] **Step 2:** `docker compose up -d`，冒烟：`curl http://127.0.0.1:8080/api/health`，添加 1245620，触发刷新，查看 series/stats。容器内网络受限时通过 `--add-host`/代理验证并记录。
- [ ] **Step 3:** 写 deploy.ps1（先用 `-DryRun` 验证参数与命令生成，再本机模拟）。
- [ ] **Step 4:** 写 README。
- [ ] **Step 5:** 提交 `feat: add docker image, compose, deploy script and docs`。

---

### Task 13: 端到端验收

- [ ] **1. 测试**：`python -m pytest -q` 全绿；`cd web && pnpm build` 成功。
- [ ] **2. 镜像**：`docker build -t steamlist:latest .`；`docker compose up -d`；`docker compose ps` 显示 healthy。
- [ ] **3. 真实数据**：通过 API 添加 ELDEN RING(1245620)、Baldur's Gate 3(1086940)、CS2(730)，触发刷新；断言 watchlist 返回真实名称/价格/ATL，730 标记免费可用，series 有 1 个点且 `record_started_at` 非空，stats 返回 ATL；搜索 "赛博朋克" 返回中文结果。
- [ ] **4. 页面**：浏览器打开 `http://127.0.0.1:8080`，核对三页无控制台报错、图表渲染、手动刷新后数据更新；截图存档。
- [ ] **5. 重启持久化**：`docker compose restart` 后数据仍在；`GET /api/backup` 可下载。
- [ ] **6. README 命令逐条验证**（至少本地开发与 compose 路径）。
- [ ] **7. 提交** `chore: final acceptance fixes` + `git log --oneline` 汇总。

## 执行分工

| 范围 | 负责人 | 写作用域 |
| --- | --- | --- |
| app/、tests/、Dockerfile、compose、deploy.ps1、README | Lead | `app/`, `tests/`, `Dockerfile`, `docker-compose.yml`, `deploy.ps1`, `README.md` |
| web/src/pages、web/src/components（页面与业务组件） | frontend teammate | `web/src/pages/`, `web/src/components/` |
| web 脚手架、lib 契约、ui 基础组件、构建配置 | Lead（Task 10）后移交 | `web/`（Task 10 阶段） |

依赖顺序：Task 10（契约冻结）→ Task 11（前端并行）可与我方 Task 6–9 并行；Task 12 依赖 Task 4–11；Task 13 最后。
