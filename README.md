# SteamList — Steam 游戏价格历史追踪

自托管的 Steam 愿望单/关注游戏价格追踪面板：记录历史价格、绘制阶梯走势、统计历史低价（ATL）及命中次数、打折事件频次与折扣力度，并在降价 / 刷新历史低价 / 达到目标价时通过 Bark、邮件或 Webhook 通知。

> **历史数据从部署上线起开始积累。** Steam 没有公开的历史价格 API，SteamList 采用自采方式：每次轮询只在价格发生变化时落库，因此越早部署、记录越完整。界面上所有涉及历史的区域都会标注「记录起点」。

## 功能

- **仪表盘**：关注游戏卡片网格、当前价 / 原价 / 折扣、历史低价与命中次数、汇总统计、筛选排序、一键触发采集。
- **游戏详情**：ECharts 阶梯价格走势（当前价 + 原价 + ATL 参考线 + 记录起点标记）、时间范围切换（30 天 / 90 天 / 180 天 / 1 年 / 全部）、打折事件时间线、均价 / 频次 / 力度统计、目标价与提醒设置。
- **添加游戏**：Steam 商店搜索、直接粘贴 appid、Steam 心愿单批量导入。
- **私密心愿单**：在设置页扫码登录 Steam（手机 App 确认）后，可导入自己「仅好友可见 / 私密」的心愿单。
- **设置**：采集计划（每日 / 每 N 小时、执行时刻、时区）、商店区域与语言、代理、Steam 账号、通知通道（Bark / 邮件 / Webhook）与测试、通知日志、数据库备份（创建 / 下载）。
- **免登录**：设计用于内网 / Tailscale / VPN 环境，不内置用户体系，请勿直接暴露公网。

## 技术架构

```
┌─────────────────────────────── 单个容器 ───────────────────────────────┐
│  FastAPI (uvicorn :8080)                                              │
│   ├── /api/*   REST 接口（OpenAPI 文档见 /api/docs）                   │
│   ├── /        托管 React SPA（app/static，history fallback）          │
│   ├── APScheduler 后台轮询（默认每日 03:30 Asia/Shanghai）             │
│   └── SQLite  data/steamlist.db（WAL）+ data/backups/                  │
│  调度 → SteamClient（限速、批量、重试）→ 解析价格 → 仅变化落库          │
│       → 计算 ATL / 折扣事件 → Notifier（Bark / SMTP / Webhook）       │
└───────────────────────────────────────────────────────────────────────┘
```

- 后端：FastAPI + SQLAlchemy 2 + SQLite + APScheduler + httpx。
- 前端：React 18 + TypeScript + Vite + Tailwind CSS + ECharts，构建产物由后端同源托管。
- 镜像：`node:22-alpine` 构建前端 → `python:3.12-slim` 运行，单镜像、单端口。
- 金额在数据库与接口中统一使用**整数分**，避免浮点误差；前端按货币符号格式化。

## 快速开始（Docker Compose）

```bash
git clone <repo> steamlist
cd steamlist
cp .env.example .env        # 可选：修改端口 / 区域 / 代理
docker compose up -d --build
```

打开 `http://<主机>:8080`。首次启动可在「设置 → 采集计划」确认轮询时间，然后点仪表盘的「刷新价格」立即抓取一次。

数据持久化在宿主机 `./data`（SQLite 与备份），重建容器不会丢失。

### 代理 / Watt Toolkit（Steam++）环境

若本机依赖 hosts（Steam++ 等把 `store.steampowered.com` 指向 `127.0.0.1`）或系统代理访问 Steam，容器内**不能**直接复用：Docker Desktop 会把宿主机 hosts 条目带进容器，域名在容器里解析到 `127.0.0.1`（容器自身的回环），直连会得到 `Connection refused`。实测必须走宿主机代理：

```env
# 宿主机代理监听 127.0.0.1:10808 时
STEAMLIST_PROXY_URL=http://host.docker.internal:10808
```

`docker-compose.yml` 已声明 `host.docker.internal:host-gateway`（Linux 主机同样适用）。设置后可在「设置 → 测试连接」或仪表盘的「刷新价格」验证：能搜到游戏、历史价格开始落库即表示网络正常。远程主机若无代理，需保证其能直连 `store.steampowered.com`。

## 本地开发

```bash
# 后端
python -m venv .venv
.\.venv\Scripts\activate            # Linux: source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload --port 8080

# 前端（另一个终端，Vite 已把 /api 代理到 8080）
cd web
pnpm install
pnpm dev
```

- 接口文档：<http://127.0.0.1:8080/api/docs>
- 健康检查：`GET /api/health`
- 测试：`python -m pytest -q`（84 个用例，覆盖 Steam 解析、ATL 统计、API、通知、调度、备份）。

## 配置

运行时配置支持两种方式：环境变量（`STEAMLIST_` 前缀）与「设置」页面。环境变量适合容器部署，页面中的设置会覆盖默认值并持久化到 SQLite。

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `STEAMLIST_PORT` | `8080` | compose 映射的宿主机端口 |
| `TZ` / `STEAMLIST_TIMEZONE` | `Asia/Shanghai` | 采集计划所在时区 |
| `STEAMLIST_DATA_DIR` | `/app/data` | 数据目录（SQLite 与备份） |
| `STEAMLIST_DB_FILENAME` | `steamlist.db` | 数据库文件名 |
| `STEAMLIST_DEFAULT_CC` | `cn` | 商店区域（决定货币与价格） |
| `STEAMLIST_DEFAULT_LANG` | `schinese` | 商店语言 |
| `STEAMLIST_PROXY_URL` | 空 | 容器访问 Steam 的 HTTP(S) 代理 |
| `STEAMLIST_ENABLE_SCHEDULER` | `true` | 是否启用后台轮询线程 |
| `STEAMLIST_LOG_LEVEL` | `INFO` | 日志级别 |

页面可配置项：轮询开关 / 间隔（小时）/ 执行时刻、区域、语言、SteamID（心愿单导入用）、代理、Steam 账号、通知通道、目标价与折扣阈值（每个游戏单独设置）。

## 扫码登录 Steam（导入私密心愿单）

Steam 的公开心愿单接口只返回公开数据。若只想读取**自己的私密心愿单**（资料 / 心愿单设为仅好友可见或私密），可在「设置 → Steam 账号」点击「扫码登录」，用 Steam 手机 App 扫码并确认。

- 流程：`IAuthenticationService/BeginAuthSessionViaQR` 生成二维码 → App 确认 → 轮询 `PollAuthSessionStatus` 拿到 refresh token → 导入时用 `GenerateAccessTokenForApp` 换短期 access token，以 `steamLoginSecure` Cookie 读取 `wishlist/profiles/<steamid>/wishlistdata`。
- 存储：refresh token 仅保存在本机 SQLite 的 `app_settings` 表（随 `./data` 卷持久化），不会发送给任何第三方；access token 只缓存在进程内存。
- 断开：设置页「断开」会在服务端调用 `RevokeToken` 吊销并清除本地令牌；删除 `./data` 也会一并清除。
- 限制：只能导入**已登录账号本人**的私密心愿单（接口按登录态返回）；若填入其他账号，仍走公开接口并给出提示。登录会话在 300 秒内有效，过期后重新生成二维码即可。
- 未登录时功能完全可用，只是无法读取不可见的心愿单。

## 部署到远程主机

`deploy.ps1` 适用于 Windows 开发机 → Windows Docker 主机（通过 OpenSSH Server）。

**推荐用 `deploy.cmd`**（内部以 `-ExecutionPolicy Bypass` 调用 PowerShell，不受系统执行策略限制）：

```bat
deploy.cmd -RemoteUser docker -RemoteHost 192.168.173.22 ^
    -RemotePath D:\ProgramFiles\steamlist ^
    -IdentityFile %USERPROFILE%\.ssh\DockerPub_ed25519 ^
    -ProxyUrl 127.0.0.1:10808

deploy.cmd -RemoteUser docker -DryRun
```

直接调用 PowerShell 脚本时同样需要绕过执行策略（`deploy.ps1` 未签名）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy.ps1 -RemoteUser docker -RemoteHost 192.168.173.22 ...
# 或一次性放行当前用户（需自行评估安全影响）
# Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

流程：本地 `docker build`（前端在镜像内构建）→ `docker save` → 打包项目（排除 `.git`、`data`、`node_modules`、构建产物）→ `scp` → 远端解压 → `docker load` → `docker compose -p steamlist up -d --no-build`。远端已有 `.env` 与 `./data` 会保留；传入 `-ProxyUrl` 时会更新 `.env` 中的 `STEAMLIST_PROXY_URL`。

远端要求：Docker 与 Docker Compose v2、OpenSSH Server、8080 端口放行。Linux 主机可直接把镜像与 `docker-compose.yml` 拷过去，手动执行 `docker load` 与 `docker compose up -d`（远端命令通过 PowerShell 执行，脚本默认面向 Windows 远端）。

## 数据与备份

- SQLite 文件：`data/steamlist.db`；备份目录：`data/backups/`（默认保留最近 14 份，可在设置页手动创建与下载）。
- 恢复：停止容器 → 用备份文件覆盖 `data/steamlist.db`（同时删除 `-wal` / `-shm`）→ 启动容器。
- 每次采集任务记录在 `job_runs` 表，可在「设置」页查看最近任务状态。

## 数据来源与限速

- 价格来自 Steam 商店 `appdetails` 接口，**非官方公开 API**，接口与字段可能无预警变化；请勿高频调用。
- 默认每日 03:30 采集一次；促销期可在设置中改为每 6 小时。批量请求每 100 个 appid 一次，串行且带间隔，遇到 429/5xx 指数退避并尊重 `Retry-After`。
- 只在价格变化时写入数据库，避免数据膨胀。
- 免费游戏、下架/不可售游戏按「不可用」处理，不参与 ATL 统计（避免 0 元污染历史低价）。
- 历史价格为自采数据，无法回溯部署前的记录；不同区域的货币与折扣可能不同。

## 目录结构

```
app/
  main.py            FastAPI 装配（路由、SPA 托管、调度器生命周期）
  config.py          环境变量配置
  db.py / models.py  SQLite 引擎与 ORM 模型
  schemas.py         API 契约
  api/               health / watchlist / games / settings / jobs / notifications / backup
  services/          steam_client / pricing / analytics / scheduler / notifier / wishlist / backup
web/                 前端工程（Vite + React + TS + Tailwind + ECharts）
tests/               pytest 用例与 Steam 响应 fixtures
Dockerfile           多阶段构建
docker-compose.yml   单服务编排
deploy.ps1           远程部署脚本
```

## FAQ

**为什么看不到很久以前的价格？** Steam 不提供历史价格接口，数据从部署当天开始采集。

**搜索不到游戏？** 搜索使用商店搜索接口，需至少 2 个字符；国区（`cc=cn`）对部分游戏可能不返回结果，可切换区域或直接粘贴 appid。

**免费游戏显示什么？** 显示为「免费 / 不可用」，不记录 0 元历史低价。

**如何修改抓取频率？** 设置页修改轮询间隔；默认 24 小时制下按「执行时刻」每天一次。

**通知重复怎么办？** 同一天、同一游戏、同一规则、同一价格只发送一次（24 小时去重）。

**容器内访问 Steam 失败？** 检查 `STEAMLIST_PROXY_URL` 是否配置为 `host.docker.internal` 形式，并确认宿主机代理允许局域网/容器访问。

**导入心愿单提示「心愿单不可见」？** 两种情况：

1. **自己的私密心愿单**：到「设置 → Steam 账号」扫码登录（Steam 手机 App 确认）后重新导入，即可读取仅好友可见 / 私密的心愿单；
2. **别人的公开心愿单**：对方需要打开 Steam → 个人资料 → 编辑个人资料 → 隐私设置，把「我的个人资料」设为「公开」（若列表里有「心愿单」选项也设为「公开」）。

输入支持三种形式：17 位 SteamID64、`steamcommunity.com/profiles/...` 或 `steamcommunity.com/id/...` 链接、以及自定义链接名（如 `gaben`）。若提示「资料已公开但心愿单里没有游戏」，说明心愿单确实为空；若提示「当前已登录账号与要导入的账号不一致」，请先在设置页断开并改用目标账号扫码登录。

**运行 `.\deploy.ps1` 报「未对文件进行数字签名 / 无法加载文件」？** 这是 PowerShell 执行策略拦截了未签名脚本。改用 `.\deploy.cmd -RemoteUser ...`，或显式执行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy.ps1 ...`；也可 `Unblock-File .\deploy.ps1` 后重试（仅解除文件锁定，对 AllSigned 策略无效）。

## 许可

本项目以 **GNU Affero General Public License v3.0（AGPL-3.0 或更高版本）** 发布，完整条款见 [LICENSE](LICENSE)。

- 你可以自由使用、修改、分发本项目；分发修改版时需同样以 AGPL-3.0 开源。
- AGPL 第 13 条：如果把修改后的版本作为网络服务提供给他人使用，需要向这些用户提供对应的完整源码。部署本项目的未修改版本时，提供本仓库地址即可。
- 本项目按「现状」提供，不附带任何担保；详见 LICENSE 第 15、16 条。
- 前端依赖（React、ECharts 等）、Python 依赖与 Steam 商店数据分别遵循各自的许可与使用条款；Steam 价格数据来自非官方接口，仅供个人自用。

Copyright (C) 2026 SteamList contributors
