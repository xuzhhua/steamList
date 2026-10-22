# SteamList：Steam 关注游戏历史价格追踪站

日期：2026-10-22
状态：待用户确认

## 1. 背景与目标

想管理自己关注的 Steam 游戏价格：看走势、看历史低点出现的频次、看历史低价，并且要能远程部署（Docker）、界面现代漂亮。

本机环境：Windows + Docker Desktop 29.4.1 + Node 24 + pnpm + Python 3.10。参考项目 `D:\MyCode\Python\rss2Wechat`（Python + config.py + Docker + deploy.ps1「本地构建镜像 → docker save → scp → 远端 docker load → compose up --no-build」）。

目标：

- 关注列表管理（搜索添加 / 填 appid / 心愿单一键导入）。
- 每个游戏的价格走势图（阶梯图，支持 30 天 / 90 天 / 1 年 / 全部）。
- 历史低价（ATL）、ATL 出现的时间点与次数、打折事件与打折频次统计。
- 降价提醒：达到目标价 / 创历史新低 / 折扣达到阈值，推送 Bark、邮件或 Webhook。
- 单个 Docker 镜像交付，`docker compose up` 即可用，可部署到远程主机。
- 界面：暗色数据面板风，图表精致，移动端可用。

限制（用户确认）：只做单人本地/内网使用，**不做登录**；历史数据**只靠本站自采**，不接 ITAD 回填；v1 功能锁定为「关注列表 + 走势 + 历史低价 + 打折频次 + 心愿单导入 + 降价提醒」。

## 2. 调研结论：Steam 到底提供什么 API

结论先行：**现价有（免 key 的商店接口），历史价格没有**。历史低价必须自己按天记录并计算。

| 能力 | 端点 | 认证 | 实测（2026-10-22，本机） | 含历史 |
|---|---|---|---|---|
| 现价 / 折扣 | `GET https://store.steampowered.com/api/appdetails?appids=1245620,1086940&filters=price_overview&cc=cn&l=zh` | 免 key | 200，0.7s 返回 3 个游戏；免费游戏 `price_overview` 为 `null` 但 `success:true` | ❌ |
| 游戏元数据 | 同上，去掉 `filters`（或 `filters=basic`） | 免 key | 200，含 `name / type / header_image / short_description / developers / publishers / genres / platforms / release_date / screenshots / is_free` | ❌ |
| 名称搜索 | `GET https://store.steampowered.com/api/storesearch/?term=elden&cc=cn&l=schinese` | 免 key | 200，返回 `id / name / price{final,currency}`；中文关键词需配 `l=schinese` | ❌ |
| 心愿单 | `GET https://api.steampowered.com/IWishlistService/GetWishlist/v1/?steamid=<steamid64>` | 免 key，需公开 | 200，返回 `{"response":{"items":[{appid,priority,added}]}}`；私密/空返回 `{}` | ❌ |
| 历史价格 | 无官方端点 | — | 不存在 | ❌ |
| 全量 appid 表 | `IStoreService/GetAppList/v1`（需 key）/ `ISteamApps/GetAppList`（旧接口已 404） | key | 本机实测 `ISteamApps/GetAppList/v2` 返回 404「Method not found」 | ❌ |

关键实现事实（已实测，写进代码时要遵守）：

1. **多 appid 请求必须带 `filters`**，否则返回 `null`/400；`filters=price_overview` 最省流量，一次 100 个 appid。
2. 价格单位是**最小货币单位整数**（CNY 为分）：`29800` = `¥298.00`；`discount_percent` 为 0–100；`initial` 是原价、`final` 是现价。
3. 免费游戏（如 730 CS2）`price_overview` 字段直接不存在，不是 0。
4. 国区不可售 / 已下架的游戏：`success:false` 或缺少 `price_overview`，必须按「不可用」状态存，不能当作 0 元。
5. `appdetails` 是**未公开文档的内部接口**，Valve 可随时改/限流；社区口径限流 200 req / 5 min。工程上按 **1 请求 / 3 秒 + 批量 100 个 appid** 保守跑，429 读 `Retry-After` 退避。
6. 封面图可直接用 CDN：`https://cdn.akamai.steamstatic.com/steam/apps/<appid>/header.jpg`（实测 200，JPEG 32KB），建议由后端代理缓存或前端直连（直连需注意容器网络）。

不做的数据源：SteamDB、gg.deals 禁止自动化抓取，不碰；ITAD 有历史数据但需要 API key、有署名/不得改造等 ToS 约束，且用户选择 v1 不接——代码里保留一个 `PriceSource` 接口位即可（不实现）。

## 3. 用户确认的决策

| 决策点 | 结论 |
|---|---|
| 前端技术栈 | React 18 + TypeScript + Vite + Tailwind + shadcn/ui + ECharts |
| 历史数据来源 | 仅自主采集，从上线开始积累（页面必须标注「记录起点」） |
| 访问方式 | 完全免登录，仅内网 / Tailscale 访问 |
| v1 附加功能 | 降价提醒（Bark / 邮件 / Webhook）+ 心愿单导入 |
| 多区价格对比 | v1 不做（数据结构预留 `cc` 维度，默认 `cn`） |
| 多用户 | 不做 |
| 数据库 | SQLite（单文件，挂 volume，便于备份） |

## 4. 方案对比与选型

| 方案 | 说明 | 结论 |
|---|---|---|
| A. FastAPI + React SPA，单镜像 | 后端 FastAPI + SQLite + APScheduler；前端 Vite 构建产物由 FastAPI 静态托管；一个容器 | **采用**：交互上限高、部署最简单、和你选的栈一致 |
| B. FastAPI + Jinja2/HTMX | 无 Node 构建，部署更轻 | 否决：复杂图表联动与「现代漂亮」的要求吃亏 |
| C. 前后端分离 + Postgres + Nginx | 更「生产级」 | 否决：单人自用过度设计，多容器多故障点；表结构按 Postgres 兼容写，日后可迁移 |
| D. Streamlit / Gradio | 一天出原型 | 否决：样式受限，不符合美观要求 |

## 5. 总体架构

```
┌──────────────────────────── 单个 Docker 容器 ────────────────────────────┐
│  FastAPI (:8080)                                                        │
│   ├── /api/*           REST（Pydantic 响应模型）                          │
│   ├── /               前端 SPA 静态文件 + history fallback               │
│   ├── APScheduler      每日采集 / 元数据刷新 / 通知评估                   │
│   ├── SteamClient      httpx + 批量 + 限流退避 + 解析                     │
│   ├── Analytics        走势序列 / ATL / 打折事件（SQLite 窗口函数）        │
│   └── Notifier         Bark / SMTP / Webhook + 去重                      │
│  SQLite  /app/data/steamlist.db（WAL）                                    │
└─────────────────────────────────────────────────────────────────────────┘
        │ 唯一出站依赖：store.steampowered.com / api.steampowered.com
        ▼
   前端 React 18 + ECharts（构建期打包进镜像）
```

技术选型明细：

- 后端：Python 3.12（镜像内）、FastAPI、SQLAlchemy 2.0 + `sqlite3`、APScheduler、httpx、pydantic-settings、loguru。
- 前端：React 18、TypeScript、Vite 6、Tailwind CSS 4、shadcn/ui（Radix）、TanStack Query、React Router 7、ECharts 5 + echarts-for-react。
- 构建：pnpm；Docker 多阶段（`node:22-alpine` 构建前端 → `python:3.12-slim` 运行）。
- 不做 ORM 迁移框架（YAGNI）：启动时 `CREATE TABLE IF NOT EXISTS` + 一个 `schema_version` 表，升级只做向前兼容加列。

## 6. 数据模型（SQLite）

```
games(appid PK, name, type, header_image, capsule_image, short_description,
      developers JSON, publishers JSON, genres JSON, platforms JSON,
      release_date, is_free, store_url, meta_updated_at, created_at)

watch_items(id PK, appid UNIQUE FK->games, cc DEFAULT 'cn',
            target_price INT NULL,        -- 目标价，分为单位
            notify_enabled BOOL DEFAULT 1,
            discount_alert_threshold INT NULL,  -- 折扣 >= N% 才提醒，NULL=不启用
            sort_order INT, note, created_at)

price_changes(id PK, appid FK, cc, currency,
              initial_cents, final_cents, discount_percent,
              available BOOL,               -- 国区不可售/下架为 0
              changed_at DATETIME,          -- 变化发生（采集到）的时间
              UNIQUE(appid, cc, changed_at))
              INDEX(appid, changed_at)

watch_state(appid PK, cc, currency, initial_cents, final_cents, discount_percent,
            available, atl_cents, atl_first_at, atl_last_at, atl_hit_count,
            last_checked_at, last_changed_at)   -- 仪表盘/告警用的当前态缓存

notification_channels(id PK, name, kind,   -- bark | email | webhook
                      config JSON, enabled, created_at)
notification_log(id PK, appid, channel_id, rule,  -- target | atl | discount
                 dedupe_key UNIQUE, title, body, status, error, sent_at)
app_settings(key PK, value JSON, updated_at)
job_runs(id PK, job, started_at, finished_at, status, stats JSON, error)
```

设计要点：

- **价格只在变化时追加**（`price_changes`），天然就是阶梯图；`watch_state` 是冗余的当前态，避免仪表盘每次扫历史表。
- `atl_*` 在每次写入变化后增量维护：`final_cents < atl_cents` 则刷新；`== atl_cents` 且从更高价进入则 `atl_hit_count += 1`。全量重算函数也保留，供数据修复用。
- 免登录：不做 users 表。
- 金额全程用整数分，禁止浮点。

## 7. 后端模块与职责边界

```
app/
  main.py            # create_app、lifespan（建表/启动调度器）、静态托管、异常处理
  config.py          # Settings：环境变量 > data 下的 .env > 默认值
  db.py              # engine/session、WAL、建表、schema_version
  models.py          # SQLAlchemy 模型（上表）
  schemas.py         # Pydantic 出入参
  api/
    watchlist.py     # 增删改查、排序、手动刷新
    games.py         # 搜索、详情、走势、统计
    settings.py      # 读写设置、通知渠道、测试发送、任务状态、备份下载
    health.py        # /api/health
  services/
    steam_client.py  # appdetails 批量、storesearch、wishlist、vanity 解析；限流/重试/缓存
    pricing.py       # 采集 → diff → 写 price_changes / watch_state；ATL 维护
    analytics.py     # 走势序列、ATL、打折事件、频次统计（SQL 窗口函数）
    wishlist.py      # steamid → 心愿单 → upsert games → 返回候选给前端勾选
    notifier.py      # 规则评估 + 三通道发送 + 去重/冷却
    scheduler.py     # 每日价格任务、每周元数据刷新、手动触发、job_runs 记录
    backup.py        # sqlite backup API → data/backups/，保留 7 份
web/                 # React 源码（src/pages、src/components、src/lib）
tests/               # pytest：fixtures 用真实抓包 JSON
docs/superpowers/specs/
```

每个模块单一职责；`steam_client` 不碰数据库，`pricing` 不直接发 HTTP，`analytics` 只读。

## 8. API 设计（REST，统一 `/api` 前缀）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查（容器 healthcheck 用） |
| GET | `/api/games/search?q=&cc=` | 代理 Steam 商店搜索，返回 appid/名称/价格/封面 |
| POST | `/api/watchlist` | body `{appid, cc?, target_price?, note?}`；立即抓一次现价+元数据 |
| GET | `/api/watchlist` | 列表：当前价、折扣、ATL、是否在打折、距目标价 |
| PATCH | `/api/watchlist/{appid}` | 改目标价 / 通知开关 / 阈值 / 备注 |
| DELETE | `/api/watchlist/{appid}` | 取消关注（保留历史数据） |
| GET | `/api/games/{appid}` | 元数据 + 当前态 |
| GET | `/api/games/{appid}/series?range=30d\|90d\|1y\|all` | 阶梯序列（含区间起点锚点、ATL 线、打折区间） |
| GET | `/api/games/{appid}/stats` | ATL、ATL 日期、命中次数、打折事件列表、频次/均值、记录起点 |
| POST | `/api/wishlist/import` | body `{steamid_or_url}` → 候选列表 |
| GET | `/api/settings` / PUT | 区域 `cc`、采集时间、采集间隔、通道配置 |
| POST | `/api/notifications/test` | 用当前配置发一条测试消息 |
| GET | `/api/notifications/log` | 发送记录（分页） |
| POST | `/api/jobs/refresh` | 立即采集（异步任务，返回 job id） |
| GET | `/api/jobs/status` | 最近任务状态 |
| GET | `/api/backup` | 下载 SQLite 备份文件 |

错误约定：`{"detail": "...", "code": "steam_unavailable"}`；Steam 侧失败统一 502 并带可读提示，前端 toast。

## 9. 统计口径（写死在测试里，避免歧义）

- **历史低价 ATL**：所有 `available=1` 且 `final_cents>0` 的快照中 `min(final_cents)`；并列取最早出现时间。免费游戏不参与。
- **ATL 命中次数 `atl_hit_count`**：价格从更高值**进入** ATL 的连续区间数（50→40(ATL)→50→40 记 2 次）。用于「低价出现频次」。
- **打折事件**：`discount_percent>0` 的连续区间，事件 = `{start, end, discount_percent, final_cents, days}`；`end` 为下一个非打折变化点，未结束则为今天。
- **打折频次统计**：事件数、平均折扣、最大折扣、总打折天数、相邻事件起始间隔均值（不足 2 次显示 `—`）。
- **走势序列**：阶梯值；返回区间前最后一个变化点作为锚点，避免区间首点悬空；`range=all` 从第一条记录开始。
- **记录起点**：`first_change_at`，UI 在图表下方明确写「数据自 YYYY-MM-DD 开始记录，此前低价未知」。

## 10. 采集与调度

- 默认每日 03:30（`Asia/Shanghai`，可在设置里改）跑一次全量关注列表：按 100 个 appid/请求分组，串行，请求间 1–3 秒，指数退避（429/5xx，最多 4 次，尊重 `Retry-After`）。
- 设置项「采集间隔」可选 6h / 12h / 24h（大促期可临时调 6h）；手动刷新按钮走同一套任务。
- 元数据（名称/封面/类型/简介）每周刷新一次；价格采集只取 `filters=price_overview`，省流量。
- 每次任务写 `job_runs`（开始/结束/耗时/成功失败数/错误摘要），前端设置页可见。
- 单游戏失败不拖垮整批：记失败清单，下轮重试；连续失败 3 次在仪表盘点条目标记「数据异常」。

## 11. 通知系统

- 通道：Bark（`https://api.day.app/<key>/<title>/<body>?group=steamlist`）、SMTP 邮件（STARTTLS）、通用 Webhook（POST JSON，可自定义 headers）。
- 规则（按关注项独立开关）：
  1. **达到目标价**：`final_cents <= target_price`，且之前未推送过该价位。
  2. **创历史新低**：`final_cents < 旧 atl_cents`；关注满 7 天才启用，避免首日误报。
  3. **折扣阈值**：`discount_percent >= threshold`。
- 去重：`dedupe_key = appid + rule + price + 日期`，同一天同一规则同一价格只发一次；通道失败重试 2 次并写日志，绝不阻塞采集任务。
- 通知文案包含游戏名、现价、原价、折扣、ATL、商店链接。

## 12. 前端页面与设计方向

页面：

1. **仪表盘 `/`**：顶部统计（关注 N / 正在打折 N / 创新低 N / 低于目标 N）；卡片网格（封面、名称、当前价、划线原价、-X% 徽章、ATL 徽章、迷你 sparkline、最后采集时间）；筛选（全部/打折/创新低/低于目标）、排序（最近加入/折扣/价格/名称）、一键手动刷新。
2. **游戏详情 `/game/:appid`**：大阶梯图（范围切换、ATL 水平线+标注、打折区间底色、悬浮十字线 tooltip）、关键指标卡（ATL、ATL 日期、低价出现次数、打折频次、平均折扣、记录起点）、打折事件时间线表格、目标价与提醒设置。
3. **添加游戏**：搜索框（防抖，Steam 搜索代理）或粘贴 appid / 商店链接；心愿单导入向导（steamid → 候选列表多选）。
4. **设置 `/settings`**：区域与货币、采集时间/间隔、通知通道表单+测试按钮、任务状态、数据备份下载、通知日志。
5. 全局：暗色优先（可切亮色）、空状态、骨架屏、错误 toast、移动端单列布局。

视觉方向（实现时用 design-taste/high-end-visual-design 技能校准）：深色底 `#0b0f14`、Steam 蓝青强调色、细网格/噪点纹理、卡片 1px 描边+轻微内发光、数字用等宽字体、图表圆角阶梯线+渐变面积、过渡 150–200ms；避免紫色渐变、大圆角滥用、卡片套卡片。

## 13. Docker 与远程部署

- **Dockerfile**（多阶段）：`node:22-alpine` 里 `pnpm install --frozen-lockfile && pnpm build`；`python:3.12-slim` 里装依赖、拷 `app/` 与静态产物，`CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8080"]`，非 root 用户运行。
- **docker-compose.yml**：`ports: 8080:8080`、`volumes: ./data:/app/data`、`TZ`、`restart: unless-stopped`、`healthcheck` 用 `/api/health`；可选 `environment: HTTPS_PROXY/HTTP_PROXY` 与 `extra_hosts: host.docker.internal:host-gateway`（国内网络经本机代理时用）。
- **deploy.ps1**：沿用参考项目已验证的链路（本地 `docker compose build` → `docker save` → `scp` 两个文件 → `ssh` 远端 `docker load` + `docker compose up -d --no-build`），参数风格一致（`-RemoteUser/-RemoteHost/-RemotePort/-RemotePath/-ProxyUrl/-IdentityFile/-DryRun`），再加 `-EnvFile` 上传 `.env`；默认远端路径 `D:\ProgramFiles\steamList`。
- **README**：功能、本地开发（前后端分开跑）、生产 compose、远程部署、反向代理/Tailscale 说明、备份恢复、限流与免责声明（非官方接口，价格仅供参考）。

## 14. 测试与验收

自动化：

- `pytest`：`steam_client` 解析（用本次实测的真实 JSON 存 fixtures：1245620 CNY、730 免费、1086940 USD、批量 3 个、storesearch 结果）、`analytics` 的 ATL/命中次数/打折区间边界（空序列、单点、并列 ATL、跨区间锚点）、`pricing` 的 diff 不重复写入、`notifier` 去重与模板、API 路由（临时 SQLite + TestClient）。
- 前端：`tsc --noEmit` + `eslint` + `vite build` 通过；图表数据转换函数用 vitest 覆盖（阶梯序列与打折区间）。
- 可选 `-m live` 联网冒烟（默认跳过）。

验收（人工）：

1. `docker compose up -d` → `http://localhost:8080` 正常打开，暗色主题、无控制台报错。
2. 搜索添加 3 个游戏（含 1 个免费游戏），首次抓价成功；免费游戏显示「免费」而非 ¥0。
3. 手动刷新后，卡片与详情页数据一致；图表 4 个范围切换正常，ATL 线与打折区间标注正确。
4. 改本机数据构造几段历史价格后，统计数字（ATL/次数/打折频次）与手算一致。
5. 配 Bark 通道点「测试」收到消息；把目标价设低于现价后手动触发规则，日志出现记录且不重复发送。
6. 重启容器后数据仍在（volume 生效）；`/api/backup` 能下载 db 并可用 sqlite 打开。
7. 按 README 用 deploy.ps1 `-DryRun` 走通，实际部署到远端后同样验收。

## 15. 里程碑

| 阶段 | 内容 | 退出标准 |
|---|---|---|
| M1 骨架 | 仓库结构、FastAPI 骨架、DB 建表、steam_client + fixtures 测试 | `pytest` 绿；能抓 3 个游戏现价 |
| M2 采集与统计 | pricing diff、watch_state/ATL、analytics、watchlist/series/stats API | 构造数据后统计口径测试全绿 |
| M3 前端核心 | 仪表盘、详情页图表、添加游戏、TanStack Query 接入 | `vite build` 通过；本地页面联调完成 |
| M4 附加功能 | 心愿单导入、设置页、三通道通知、去重、任务状态 | 测试发送成功，规则触发不重复 |
| M5 交付 | 多阶段 Dockerfile、compose、deploy.ps1、README、备份 | 验收清单 1–6 通过 |
| M6 打磨 | 视觉校准（设计技能）、移动端、空/错状态、截图 | 验收清单 7 通过，出交付截图 |

## 16. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| `appdetails` 是未公开接口，可能改/限/封 | 采集失败 | 单独适配层 + 保守限流 + 429 退避 + 失败可见（task 状态/错误卡片） |
| 国区不可售或下架 | 缺价 | `available=0` 显式存，「该区域暂不可售」徽章，设置可切 `cc` |
| 心愿单私密 | 导入失败 | 明确提示去 Steam 隐私设置公开；同时永远支持手动搜索/appid 添加 |
| 只有自采数据 | 新游戏无历史 | UI 标注记录起点；详情页展示「已记录 N 天，低价次数逐步积累」 |
| 容器访问 Steam 受限（本机依赖本地代理/Steam++） | 采集超时 | compose 预留 proxy + host-gateway；文档写明；采集失败有明确报错 |
| SQLite 并发 | 写冲突 | WAL + 单进程 worker；日后可迁 Postgres（SQLAlchemy） |
| 数据丢失 | 历史归零 | volume + `/api/backup` + 每日自动备份留 7 份 |

## 17. 明确不做（YAGNI）

多用户/登录、多区比价、ITAD 历史回填、SteamDB/gg.deals 抓取、Steam 库存/成就、i18n 多语言、PWA/离线、K8s 部署、Redis/队列。

## 18. 下一步

用户确认本文档后进入 `writing-plans`，产出可执行的分阶段实施计划（含每步的验收命令），再开始 M1。
