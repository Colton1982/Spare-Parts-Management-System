# 备件管理系统 Spare Parts Management System (SPMS)

中文版 | [English](#english)

---

## 中文版

### 项目简介

面向制造工厂周边备件与辅料管理的 Web 系统：备件建档、多库位库存、出入库调库申请与审批、呆滞物料分析、回收站、多数据库、AD 域登录、数据大屏，支持 9 种界面语言。内置 Python 运行时，双击 `Start.bat` 即可运行，无需安装 Python 或第三方包。(需下载发行版)

### 功能模块

| 模块 | 说明 |
| --- | --- |
| 数据图表主页 `/dashboard` | 库存/入库/出库分析图表，图表风格可配置 |
| 备件信息维护 `/parts/manage` | 建档、编辑、删除、导入导出、多库位录入、数量类型（整数/小数）、操作记录查询 |
| 备件查询 `/parts` | 按料号/名称/规格/分类/呆滞状态查询 |
| 出入库调库申请 `/applications` | 领用/直接出入库申请、调库、撤销、审批 |
| 出入库管理 `/inout` | 仓管执行出入库、驳回、审批、导出；贵重备件走审批 |
| 货架管理 `/locations` | 仓库-货架-货位-格位四级库位、操作记录查询 |
| 产线与设备 `/lines` | 产线/设备配置（备件适用记录） |
| 部门配置 `/departments` | 部门管理 |
| 用户管理 `/users` | 用户增删改、重置密码、角色分配 |
| 权限配置 `/permissions` | 角色 × 模块 × 子操作三级权限矩阵 |
| 审批中心 `/approval` | 贵重备件出库审批 |
| 呆滞物料 `/stale` | 呆滞判定（默认 90 天可配）与清单导出 |
| 回收站 `/recycle` | 备件/货架/部门/用户分组回收，保留期自动清除（默认 3 天可配）、管理员恢复（覆盖冲突提示） |
| 备份恢复 `/restore` | 在线备份、自动备份（1 小时～每月）、整库恢复（审批流程） |
| 系统设置 `/settings` | 数据库/部署/语言/AD 登录/对外接口/界面主题（6 套预设 + 自定义手动配色）/自定义表头/库存规则 |
| 大屏 `/screen` | 车间数据大屏（多种布局 × 6 种配色 + 自定义手动配色，卡片拖拽排版、隐藏补位） |

### 技术结构

```
SPMS/
├── app.py                 # Flask 主程序（路由 + 业务逻辑，约 6650 行）
├── config.py              # 静态配置：角色/权限模块/大屏卡片/布局/图表风格
├── i18n.py                # 国际化入口：t()/tr()/TR() 与 current_lang()（flask.g 每请求缓存）
├── i18n_tool.py           # 翻译同步工具：scan（扫描未登记词条）/ skeleton（生成 _pending.json 补译骨架）
├── i18n/                  # 词条外置目录（中文原文作 key）
│   ├── zh.json            # 120 条 key 式特殊词条
│   ├── en.json            # 英文词条（2000+ 条）
│   ├── ja/ko/th/vi/ru/fr/de.json   # 日/韩/泰/越/俄/法/德
├── templates/             # 25 个 Jinja2 模板（文本经 tr()/TR() 包裹）
├── static/
│   ├── css/style.css      # 全局样式
│   └── js/app.js, charts.js        # 前端逻辑（中文经 TR() 包裹）
├── data/SPMS.db            # SQLite 默认数据库（可切换 MySQL/MariaDB/PostgreSQL/SQL Server/Oracle）
├── settings.json          # 运行时设置（数据库、语言、AD、接口密钥等，随安装生成）
├── Start.bat              # Windows 双击启动（内置运行时）
├── 业务流程文档.md        # 完整业务流程说明（中文）
└── README.md
```

### 多语言机制

- **词条外置**：全部界面文案以中文原文为 key 存放在 `i18n/*.json`；新增语言/修改译文不动主程序。
- **三层入口**：
  - `{{ tr('中文') }}` — Jinja 模板文本
  - `TR('中文')` — 内联/外部 JS
  - `_i18n.t('中文', _i18n.current_lang())` — Python（含 flash 提示）
- **缺译回退**：某语言缺词条时自动回退中文原文，界面不空白。
- **性能**：`current_lang()` 每请求只解析一次（flask.g 缓存）；词条查询为 dict O(1)。
- **业务数据不翻译**：备件名、部门名、用户名、申请原因等用户数据保持原文。
- **扩展新词条**：代码中直接写 `tr('新文案')` → `python3 i18n_tool.py scan` 查看未登记项 → `python3 i18n_tool.py skeleton` 生成 `i18n/_pending.json` 补译骨架 → 译文 merge 进各语言 json。

### 运行

```bash
python3 app.py              # 默认端口 5000
# 或 Windows 双击 Start.bat（无需安装 Python）
# 首次运行访问 /setup 完成数据库初始化
```

演示账号：`admin / admin123`（管理员）、`warehouse01 / 123456`（仓管）、`manager01 / 123456`（经理）、`user01 / 123456`（普通用户）。

### 数据与部署

- 数据库类型在系统设置中可选：SQLite（内置默认）、MySQL、MariaDB、PostgreSQL、SQL Server、Oracle。
- 局域网共享：各电脑指向同一公共盘数据库路径即可共用；备件图片以二进制存库，随数据库文件一起拷贝。
- 部署模式：开启部署设置后其他电脑可通过浏览器直接访问。
- 备份：在线备份方式，运行中不中断；可设置自动备份周期（1 小时～每月），保留天数超限自动压缩。

### 打包约定

交付 zip 以 `SPMS/` 为前缀打包，排除 `*.pyc`、`data/*`、`settings.json`。


### 开源

- **许可证**：Apache-2.0——完全开源，可自由商用、修改、再分发，并附带专利授权（Copyright 2026 菜鸟大叔，详见 `LICENSE`）
- **免责声明**：软件按「现状」(AS IS) 提供，作者不对使用后果承担任何责任，不提供任何明示或默示的担保（含适销性、特定用途适用性、不侵权）
- **发布说明**：见 `开源发布指南.md`（安全检查、建仓、推送、Release 步骤）
- **依赖安装**（使用方）：

```bash
pip install -r requirements.txt        # SQLite 即用：flask + ldap3 + pillow
pip install -r requirements-full.txt   # 需要 MySQL/MariaDB/PostgreSQL/SQL Server/Oracle 时
python app.py                          # 浏览器打开 http://127.0.0.1:5000
```

- **贡献**：欢迎提交 Issue / PR。新增界面文案按「多语言机制」补 `i18n/*.json` 并跑 `python3 i18n_tool.py scan` 校验后提交。

---

## English


### Overview

A web-based spare parts management system for production lines: part master data, multi-location inventory, inbound/outbound & transfer requests with approval, stagnant material analysis, recycle bin, multiple database backends, AD domain login, and a data screen — with 9 UI languages. It bundles its own Python runtime: double-click `Start.bat`, no Python or third-party packages required. （Requires downloading the release build）

### Modules

| Module | Description |
| --- | --- |
| Dashboard `/dashboard` | Inventory/in/out analytics charts; configurable chart styles |
| Part Master `/parts/manage` | Create/edit/delete, import/export, multi-location entry, quantity type (integer/decimal), operation audit log |
| Part Search `/parts` | Search by code/name/spec/category/stagnant state |
| Applications `/applications` | Issue, direct in/out, transfer requests, cancellation, approval |
| In/Out Management `/inout` | Warehouse execution, rejection, approval, export; valuable parts require approval |
| Locations `/locations` | 4-level location tree: warehouse–rack–shelf–bin, operation audit log |
| Lines & Equipment `/lines` | Line/equipment configuration with part applicability |
| Departments `/departments` | Department management |
| Users `/users` | User CRUD, password reset, role assignment |
| Permissions `/permissions` | Role × module × sub-operation matrix |
| Approval Center `/approval` | Valuable part issue approvals |
| Stagnant `/stale` | Stagnant judgment (default 90 days, configurable) and list export |
| Recycle Bin `/recycle` | Parts/racks/departments/users grouped; auto-purge after retention (default 3 days); admin restore with overwrite-conflict warning |
| Backup & Restore `/restore` | Online backup, scheduled backup (1h–monthly), full restore (approval workflow) |
| Settings `/settings` | Database, deployment, language, AD login, external API, UI theme (6 presets + custom colors), custom columns, stock rules |
| Screen `/screen` | Shop-floor data screen (multiple layouts × 6 palettes + custom colors, draggable cards, auto gap-fill) |

### Code Structure

```
SPMS/
├── app.py                 # Flask main app (routes + business logic, ~6650 lines)
├── config.py              # Static config: roles, permission modules, screen cards/layouts, chart styles
├── i18n.py                # i18n entry: t()/tr()/TR() and current_lang() (flask.g per-request cache)
├── i18n_tool.py           # i18n sync tools: scan / skeleton (generates i18n/_pending.json)
├── i18n/                  # Externalized term dictionaries (Chinese source text as key)
│   ├── zh.json            # 120 key-style special terms
│   ├── en.json            # English (2000+ entries)
│   ├── ja/ko/th/vi/ru/fr/de.json   # Japanese/Korean/Thai/Vietnamese/Russian/French/German
├── templates/             # 25 Jinja2 templates (text wrapped with tr()/TR())
├── static/
│   ├── css/style.css
│   └── js/app.js, charts.js        # Front-end logic (Chinese wrapped with TR())
├── data/SPMS.db            # Default SQLite DB (switchable to MySQL/MariaDB/PostgreSQL/SQL Server/Oracle)
├── settings.json          # Runtime settings (generated on setup)
├── Start.bat              # Windows launcher (bundled runtime)
├── 业务流程文档.md        # Full business-process documentation (Chinese)
└── README.md
```

### i18n Design

- **Externalized terms**: all UI texts are keyed by the Chinese source in `i18n/*.json`; adding languages or editing translations never touches the main app.
- **Three entry points**: `{{ tr('text') }}` (Jinja), `TR('text')` (JS), `_i18n.t('text', _i18n.current_lang())` (Python, incl. flash).
- **Fallback**: a missing translation falls back to the Chinese source — the UI never shows blank.
- **Performance**: `current_lang()` is resolved once per request (flask.g cache); lookups are O(1) dict reads.
- **Business data is not translated**: part names, department names, usernames, request reasons, etc. stay as entered.
- **Adding terms**: write `tr('new text')` in code, run `python3 i18n_tool.py scan` to list unregistered keys, `python3 i18n_tool.py skeleton` to generate `_pending.json`, then merge completed translations into each language file.

### Run

```bash
python3 app.py              # default port 5000
# or double-click Start.bat on Windows (no Python install needed)
# First run: visit /setup to initialize the database
```

Demo accounts: `admin / admin123` (Admin), `warehouse01 / 123456` (Warehouse), `manager01 / 123456` (Manager), `user01 / 123456` (User).

### Data & Deployment

- Database type selectable in Settings: SQLite (built-in default), MySQL, MariaDB, PostgreSQL, SQL Server, Oracle.
- LAN sharing: all computers point to the same shared-disk database path; part images are stored in the database as binary and travel with the DB file.
- Deployment mode: other computers can access directly via browser after enabling deployment settings.
- Backup: online, no interruption while running; scheduled backups from 1 hour to monthly with auto-compression beyond retention.

### Packaging

Delivered zips use the `SPMS/` prefix and exclude `*.pyc`, `data/*`, and `settings.json`.

### Open Source

- **License**: Apache-2.0 — fully open source, free for commercial use, modification and redistribution, with an explicit patent grant (Copyright 2026 Colton Zhou, see `LICENSE`)
- **Disclaimer**: The software is provided "AS IS", without warranty of any kind (merchantability, fitness for a particular purpose, or non-infringement). The author is not liable for any claims or damages.
- **Publishing guide**: `开源发布指南.md` (security check, repo setup, push, Release steps)
- **Dependencies**:

```bash
pip install -r requirements.txt        # SQLite only: flask + ldap3 + pillow
pip install -r requirements-full.txt   # for MySQL/MariaDB/PostgreSQL/SQL Server/Oracle
python app.py                          # open http://127.0.0.1:5000
```

- **Contributing**: Issues and PRs welcome. For new UI strings, add entries in `i18n/*.json` and run `python3 i18n_tool.py scan` before submitting.

