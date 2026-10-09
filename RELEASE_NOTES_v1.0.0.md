# v1.0.0 Release Notes

## 中文版

### Spare Parts Management System (SPMS) — 备件管理系统 v1.0.0

面向 SMT 产线备件管理的开源 Web 系统：备件建档、多库位库存、出入库调库申请与审批、呆滞物料分析、回收站、多数据库、AD 域登录、数据大屏，支持 9 种界面语言。

**主要功能**

- 📦 备件信息维护：建档 / 编辑 / 删除 / Excel 导入导出 / 多库位录入 / 数量类型（整数/小数）自动适配
- 🗄️ 四级库位（仓库-货架-货位-格位），删除即释放库位
- 🔄 出入库调库申请与审批，贵重备件强制审批，仓管直出完整留痕（数量/申请人/线别/设备/原因）
- ♻️ 回收站：备件 / 货架 / 部门 / 用户 4 类分组，保留期自动清除（默认 3 天可配），管理员恢复（覆盖冲突确认）
- 📊 数据大屏：5 种布局 × 6 种配色，卡片拖拽排版，工厂深色大气风格
- 🌍 9 种界面语言（中 / 英 / 日 / 韩 / 泰 / 越 / 俄 / 法 / 德），词条外置，一行代码即可扩展新语言
- 🗃️ 多数据库：SQLite（默认）/ MySQL / MariaDB / PostgreSQL / SQL Server / Oracle，界面一键切换
- 🔐 AD 域登录（LDAPS / StartTLS / 明文），支持大小写匹配、@域名剥离、超时与白名单，全部界面可配
- 👤 三级权限矩阵：角色 × 模块 × 子操作
- 💾 在线备份 / 自动备份 / 整库恢复（审批流程）

**快速开始**

```bash
pip install -r requirements.txt        # SQLite 即用
python app.py                          # 打开 http://127.0.0.1:5000
# 首次运行进入初始化向导，填数据库路径（默认 data/SPMS.db）
```

**数据库切换**

```bash
pip install -r requirements-full.txt   # 安装全部数据库驱动
# 系统设置 → 数据库类型 → 填连接信息 → 测试连接 → 保存 → 重启
```

**许可证**：Apache-2.0 — 完全开源，可自由商用、修改、再分发，附带专利授权。Copyright 2026 周臣（软件按 AS IS 提供，不附带任何担保）

**贡献**：欢迎提交 Issue / PR；新增界面文案补 `i18n/*.json` 并跑 `python3 i18n_tool.py scan` 校验。

---

## English

### Spare Parts Management System (SPMS) v1.0.0

An open-source web system for SMT line spare parts management: parts master, multi-location inventory, stock in/out & transfer requests with approval, stale parts analysis, recycle bin, multiple databases, AD domain login, and a data dashboard — with 9 UI languages.

**Highlights**

- 📦 Parts Master: create / edit / delete / Excel import-export / multi-location entry / qty type (integer or decimal) auto-adjust
- 🗄️ 4-level locations (Warehouse → Rack → Slot → Cell); deleting a part frees its location
- 🔄 Stock in/out & transfer requests with approval; valuable parts require approval; direct stock-out keeps full trace (qty, applicant, line, device, reason)
- ♻️ Recycle Bin: parts / racks / departments / users, auto-purge after retention days (default 3, configurable), admin restore (conflict confirm)
- 📊 Data Screen: 5 layouts × 6 themes, drag-and-drop cards, dark industrial style
- 🌍 9 UI languages (ZH/EN/JA/KO/TH/VI/RU/FR/DE), externalized i18n, extendable with one line
- 🗃️ Multi-DB: SQLite (default) / MySQL / MariaDB / PostgreSQL / SQL Server / Oracle, switch in Settings
- 🔐 AD domain login (LDAPS / StartTLS / plain), case-matching, @domain strip, timeout & whitelist, all configurable in UI
- 👤 Permission matrix: role × module × sub-action
- 💾 Online backup / scheduled backup / full restore (with approval)

**Quick Start**

```bash
pip install -r requirements.txt        # SQLite only
python app.py                          # open http://127.0.0.1:5000
# First run: setup wizard asks for the DB path (default data/SPMS.db)
```

**DB switching**

```bash
pip install -r requirements-full.txt   # all database drivers
# Settings → Database type → connection info → Test → Save → Restart
```

**License**: Apache-2.0 — fully open source, free for commercial use, modification and redistribution, with patent grant. Copyright 2026 周臣 (provided AS IS, without warranty)

**Contributing**: Issues and PRs welcome; add new UI strings in `i18n/*.json` and run `python3 i18n_tool.py scan` before submitting.

---

# v1.1.0 Release Notes

## 中文版

### v1.1.0 主要更新

- 🎨 **界面主题 6 套预设 + 自定义（手动配色）**：科技蓝 / 墨绿商务 / 曜石金 / 云白现代 / 琥珀暖橙 / 典雅紫，其中 4 套为清新浅色系；点击色卡即时预览、直接保存，自定义面板可手动调色（主题色/侧边栏/渐变/字号/宽度/圆角）
- 📊 **大屏配色升级 + 语言本地化**：6 套配色重调（科技蓝保留，其余升级为商务/科技/优雅色系，含自定义手动配色）；右上角时钟日期/星期跟随界面语言（中/英/日/韩/泰/越/俄/法/德），图表图例多语言自动缩字号防重叠
- 🧾 **操作记录审计**：备件信息维护与货架管理新增「操作记录」，可查询新增/编辑（字段级差异）/删除/恢复/清除等操作内容与时间
- 🌍 **翻译全面修复**：新增页面/大屏日期/操作记录页等全部词条化，切换任意语言不残留中文、不挤压布局
- 🐛 **修复**：切换主题后保存按钮不可用；大屏日期未跟随全局语言；长语言下入出库图例重叠；备件页工具栏多语言挤压

## English

### v1.1.0 Highlights

- 🎨 **UI themes: 6 presets + custom (manual colors)**: Tech Blue / Dark Green Business / Obsidian Gold / Cloud White / Amber Warm / Elegant Purple, with 4 fresh light palettes; one-click preview & save, manual color panel included
- 📊 **Data screen palette upgrade + locale-aware clock**: 6 refined palettes (Tech Blue kept, others upgraded to business/tech/elegant tones, plus custom colors); top-right clock date/weekday follows UI language; chart legends auto-shrink to avoid overlap in long languages
- 🧾 **Operation audit logs**: Parts Master and Locations gain an "Operation Log" page showing add/edit (field-level diff)/delete/restore/purge actions with timestamps
- 🌍 **Translation hardening**: new pages, screen date and audit page fully tokenized — no leftover Chinese, no layout breakage in any language
- 🐛 **Fixes**: theme save button hidden after preset click; screen date not following global language; in/out legend overlap in long languages; parts toolbar squeezed by long button labels
