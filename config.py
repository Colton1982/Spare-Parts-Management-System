# -*- coding: utf-8 -*-
"""
备件管理系统 - 全局配置
================================
架构说明（桌面直连版）：
1. 每个用户电脑上双击本软件即可运行（软件包已内置 Python 运行时与全部依赖，无需预装 Python）。
2. 数据库文件放在内网公共盘：首次启动软件会弹出「初始化向导」，
   填写公共盘上的数据库路径（如 \\\\192.168.1.100\\公共盘\\备件管理系统\\SPMS.db），
   之后所有用户都直连这一个数据库文件，数据实时共享。
3. 配置保存在软件目录 settings.json 中（可随时在「系统设置」页面修改数据库位置）。
"""
import os

import settings as _settings

# ------------------------------------------------------------------
# 由 settings.json 加载的运行配置
# ------------------------------------------------------------------
_CFG = _settings.load()

# 数据库类型：sqlite / mysql / mariadb / postgresql / mssql / oracle
DB_TYPE = (_CFG.get("db_type") or "sqlite").strip().lower()
if DB_TYPE not in ("sqlite", "mysql", "mariadb", "postgresql", "mssql", "oracle"):
    DB_TYPE = "sqlite"

# 数据库连接参数（sqlite 仅用 db_path；其余使用 host/port/user/password/database/service_name）
DB_HOST = (_CFG.get("db_host") or "").strip()
DB_PORT = _CFG.get("db_port") or 0
DB_USER = (_CFG.get("db_user") or "").strip()
DB_PASSWORD = _CFG.get("db_password") or ""
DB_NAME = (_CFG.get("db_database") or "").strip()
DB_SERVICE = (_CFG.get("db_service_name") or "").strip()

# 数据库文件位置（未配置前为 None，首次启动进入初始化向导）
DB_PATH = (_CFG.get("db_path") or "").strip() or None

# 备件图片目录（空 = 数据库同级 parts_img）
UPLOAD_DIR = (_CFG.get("upload_dir") or "").strip() or None

# 本机服务端口（每个用户只在本机监听，互不冲突）
PORT = _CFG.get("port", 5000)

# 局域网部署：True=监听 0.0.0.0，其他电脑可通过 http://本机IP:端口 访问
LAN_ENABLED = bool(_CFG.get("lan_enabled"))

# 会话加密密钥（本机会话，仅用于登录 Cookie 签名）
SECRET_KEY = "smt-parts-mgmt-2026-desktop"

# 允许上传的图片格式与大小上限
ALLOWED_IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
MAX_IMG_SIZE = 5 * 1024 * 1024  # 5MB

# 数据库目录不可访问时的备用默认位置（软件目录下 data）
BASE_DIR = _settings.APP_DIR
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "data", "SPMS.db")


def apply_settings(cfg):
    """应用新的运行配置（系统设置页保存后调用）"""
    global DB_PATH, UPLOAD_DIR, PORT, LAN_ENABLED, DB_TYPE, DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, DB_SERVICE
    _db_type = (cfg.get("db_type") or "sqlite").strip().lower()
    if _db_type not in ("sqlite", "mysql", "mariadb", "postgresql", "mssql", "oracle"):
        _db_type = "sqlite"
    DB_TYPE = _db_type
    DB_HOST = (cfg.get("db_host") or "").strip()
    try:
        DB_PORT = int(cfg.get("db_port") or 0)
    except Exception:
        DB_PORT = 0
    DB_USER = (cfg.get("db_user") or "").strip()
    DB_PASSWORD = cfg.get("db_password") or ""
    DB_NAME = (cfg.get("db_database") or "").strip()
    DB_SERVICE = (cfg.get("db_service_name") or "").strip()
    DB_PATH = (cfg.get("db_path") or "").strip() or None
    UPLOAD_DIR = (cfg.get("upload_dir") or "").strip() or None
    LAN_ENABLED = bool(cfg.get("lan_enabled"))
    try:
        PORT = int(cfg.get("port") or 5000)
    except Exception:
        PORT = 5000
    if not 1024 <= PORT <= 65535:
        PORT = 5000


def get_db_cfg():
    """返回数据库连接配置 dict（供 db.connect / 测试连接使用）"""
    return {
        "db_type": DB_TYPE, "db_path": DB_PATH or "",
        "host": DB_HOST, "port": DB_PORT, "user": DB_USER,
        "password": DB_PASSWORD, "database": DB_NAME,
        "service_name": DB_SERVICE,
    }


def resolved_upload_dir():
    """图片目录：未单独配置时与数据库同级 parts_img"""
    if UPLOAD_DIR:
        return UPLOAD_DIR
    if DB_PATH:
        return os.path.join(os.path.dirname(DB_PATH), "parts_img")
    return os.path.join(BASE_DIR, "uploads", "parts")


# ------------------------------------------------------------------
# 权限模块定义（可配置权限矩阵的基础）
# ------------------------------------------------------------------
PERM_MODULES = {
    "dashboard":       "数据图表主页",
    "query":           "备件查询",
    "apply":           "出入库调库申请",
    "parts_manage":    "备件信息维护(建档)",
    "stock_inout":     "出入库管理",
    "transfer":        "调库(已并入申请流程)",
    "approve":         "贵重备件出库审批",
    "departments":     "部门配置",
    "lines_equip":     "产线与设备配置",
    "user_manage":     "用户管理",
    "perm_config":     "权限配置",
    "stale":           "呆滞物料管理",
    "price":           "备件金额查看（单价/金额，敏感内容）",
}

# 操作级权限（模块内细分操作；模块级权限=拥有全部操作，操作级用于更细粒度控制）
PERM_ACTIONS = {
    "parts_manage": {
        "add": "新增备件",
        "edit": "编辑备件",
        "delete": "删除备件",
        "import": "导入备件",
        "export": "导出备件",
    },
    "stock_inout": {
        "execute": "执行出入库",
        "reject": "驳回申请",
        "undo_approval": "撤销审批",
        "export": "导出出入库报表",
    },
    "user_manage": {
        "add": "新增用户",
        "edit": "编辑用户",
        "reset_pwd": "重置密码",
        "delete": "删除用户",
    },
    "perm_config": {
        "edit": "修改权限",
    },
    "apply": {
        "cancel": "撤销申请",
    },
    "stale": {
        "export": "导出呆滞清单",
    },
    "approve": {
        "approve_out": "审批贵重出库",
    },
}

# 各角色默认权限（首次建库时写入；之后可在「权限配置」页面调整）
DEFAULT_PERMS = {
    "admin":     ["dashboard", "query", "apply", "parts_manage", "stock_inout",
                  "transfer", "approve", "departments", "lines_equip", "user_manage", "perm_config",
                  "stale", "price"],
    "manager":   ["dashboard", "query", "apply", "approve", "stale", "price"],
    "warehouse": ["dashboard", "query", "apply", "parts_manage", "stock_inout", "transfer", "stale",
                  "price"],
    "user":      ["dashboard", "query", "apply"],
    "guest":     ["query", "stale"],   # 访客（AD 自动进入）：仅备件查询 + 呆滞物料查阅
}

# 各角色默认操作级权限（按职责级别配置，仅列与模块级默认不同的细化项）
# 说明：操作级行存在即生效（优先于模块级）。模块级已勾选但某项操作级=0 时，该操作被禁止。
DEFAULT_PERM_ACTIONS = {
    # 高级管理人员：全部模块的细分操作都默认开放
    "admin": {
        "parts_manage": {"add": 1, "edit": 1, "delete": 1, "import": 1, "export": 1},
        "stock_inout": {"execute": 1, "reject": 1, "undo_approval": 1, "export": 1},
        "user_manage": {"add": 1, "edit": 1, "reset_pwd": 1, "delete": 1},
        "perm_config": {"edit": 1},
        "apply": {"cancel": 1},
        "stale": {"export": 1},
        "approve": {"approve_out": 1},
    },
    # 经理：可申请/审批贵重出库/撤销自己的申请/导出呆滞清单（无入库出库执行与建档权限）
    "manager": {
        "apply": {"cancel": 1},
        "stale": {"export": 1},
        "approve": {"approve_out": 1},
    },
    # 仓库管理人员：建档/出入库执行/调库/撤销申请/导出（各项全开；导入备件默认关闭——默认仅最高用户可导入，可按需勾选）
    "warehouse": {
        "parts_manage": {"add": 1, "edit": 1, "delete": 1, "import": 0, "export": 1},
        "stock_inout": {"execute": 1, "reject": 1, "undo_approval": 1, "export": 1},
        "apply": {"cancel": 1},
        "stale": {"export": 1},
    },
    # 普通用户：只能申请与撤销自己的申请（其余操作一律未配置=跟随模块级，模块级本身未开放）
    "user": {
        "apply": {"cancel": 1},
    },
    # 访客：仅查阅，禁止一切导出
    "guest": {"stale": {"export": 0}, "query": {"export": 0}},
}

# 角色中文名
ROLE_NAMES = {
    "admin":     "高级管理人员",
    "manager":   "经理",
    "warehouse": "仓库管理人员",
    "user":      "普通用户",
    "guest":     "访客（AD 未在白名单自动进入）",
}

# ------------------------------------------------------------------
# 数据库自动备份（管理员在系统设置页配置；备份文件与数据库同级 backups 目录）
# ------------------------------------------------------------------
DEFAULT_BACKUP = {
    "enabled": 0,           # 0=关闭 1=开启（软件运行期间后台线程自动检查并按间隔备份）
    "interval_hours": 24,   # 备份间隔（小时）：1/6/12/24/72/168(每周)/720(每月)
    "keep": 10,             # 保留最近 N 份备份，自动删除更早的
    "dir": "",              # 备份目录（空=数据库同级 backups 文件夹）
}


# ------------------------------------------------------------------
# 大屏展示配置
# ------------------------------------------------------------------
SCREEN_MODULES = {
    "stat_cards": "出入库统计卡片",
    "qty_trend":  "出入库数量趋势",
    "amt_trend":  "出入库金额趋势",
    "category":   "分类库存金额占比",
    "alerts":     "库存上下限预警",
    "recent_tx":  "最新出入库流水",
    "pending":    "待处理申请",
    "stale":      "呆滞物料监控",
    "usage_line_qty":   "线体领用数量柱状图",
    "usage_line_amt":   "线体领用金额柱状图",
    "usage_device_qty": "设备领用数量柱状图",
    "usage_device_amt": "设备领用金额柱状图",
}

# 大屏可排版卡片单元（key -> 名称 + 所属模块）。模块未勾选时整卡隐藏。
SCREEN_CARDS = {
    "stat_in_qty":  {"label": "今日入库数量", "module": "stat_cards"},
    "stat_in_amt":  {"label": "今日入库金额", "module": "stat_cards"},
    "stat_out_qty": {"label": "今日出库数量", "module": "stat_cards"},
    "stat_out_amt": {"label": "今日出库金额", "module": "stat_cards"},
    "pending":      {"label": "待处理申请", "module": "pending"},
    "qty_trend":    {"label": "出入库数量趋势", "module": "qty_trend"},
    "amt_trend":    {"label": "出入库金额趋势", "module": "amt_trend"},
    "category":     {"label": "分类库存金额占比", "module": "category"},
    "alerts":       {"label": "库存上下限预警", "module": "alerts"},
    "stale":        {"label": "呆滞物料监控", "module": "stale"},
    "recent_tx":    {"label": "最新出入库流水", "module": "recent_tx"},
    "line_qty":     {"label": "线体领用数量", "module": "usage_line_qty"},
    "line_amt":     {"label": "线体领用金额", "module": "usage_line_amt"},
    "dev_qty":      {"label": "设备领用数量", "module": "usage_device_qty"},
    "dev_amt":      {"label": "设备领用金额", "module": "usage_device_amt"},
}

# 大屏网格：12 列 x 10 行；x,y = 左上角格子，w,h = 占格数
SCREEN_GRID_COLS = 12
SCREEN_GRID_ROWS = 10

# 5 种默认排列组合（key -> 名称 + 每张卡的位置）
SCREEN_LAYOUTS = {
    "classic": {
        "name": "经典布局",
        "cards": {
            "stat_in_qty":  (0, 0, 3, 1), "stat_in_amt":  (3, 0, 3, 1),
            "stat_out_qty": (6, 0, 3, 1), "stat_out_amt": (9, 0, 3, 1),
            "pending":      (0, 1, 12, 1),
            "qty_trend":    (0, 2, 6, 2), "amt_trend":    (6, 2, 6, 2),
            "category":     (0, 4, 4, 2), "alerts":       (4, 4, 4, 2),
            "stale":        (8, 4, 4, 2),
            "line_qty":     (0, 6, 3, 2), "line_amt":     (3, 6, 3, 2),
            "dev_qty":      (6, 6, 3, 2), "dev_amt":      (9, 6, 3, 2),
            "recent_tx":    (0, 8, 12, 2),
        },
        # 无金额版：金额类卡片隐藏后由该模板直接定位（比动态拉伸更规整）
        "noprice": {
            "stat_in_qty":  (0, 0, 6, 1), "stat_out_qty": (6, 0, 6, 1),
            "pending":      (0, 1, 12, 1),
            "qty_trend":    (0, 2, 12, 2),
            "line_qty":     (0, 4, 6, 2), "dev_qty":      (6, 4, 6, 2),
            "alerts":       (0, 6, 6, 2), "stale":        (6, 6, 6, 2),
            "recent_tx":    (0, 8, 12, 2),
        },
    },
    "split": {
        "name": "左图右表",
        "cards": {
            "stat_in_qty":  (0, 0, 3, 1), "stat_in_amt":  (3, 0, 3, 1),
            "stat_out_qty": (6, 0, 3, 1), "stat_out_amt": (9, 0, 3, 1),
            "pending":      (0, 1, 12, 1),
            "qty_trend":    (0, 2, 6, 3), "amt_trend":    (0, 5, 6, 2),
            "recent_tx":    (6, 2, 6, 5),
            "category":     (0, 7, 4, 1), "alerts":       (4, 7, 4, 1),
            "stale":        (8, 7, 4, 1),
            "line_qty":     (0, 8, 3, 2), "line_amt":     (3, 8, 3, 2),
            "dev_qty":      (6, 8, 3, 2), "dev_amt":      (9, 8, 3, 2),
        },
        "noprice": {
            "stat_in_qty":  (0, 0, 6, 1), "stat_out_qty": (6, 0, 6, 1),
            "pending":      (0, 1, 12, 1),
            "qty_trend":    (0, 2, 7, 5), "recent_tx":    (7, 2, 5, 5),
            "line_qty":     (0, 7, 6, 2), "dev_qty":      (6, 7, 6, 2),
            "alerts":       (0, 9, 6, 1), "stale":        (6, 9, 6, 1),
        },
    },
    "grid": {
        "name": "均布网格",
        "cards": {
            "stat_in_qty":  (0, 0, 3, 1), "stat_in_amt":  (3, 0, 3, 1),
            "stat_out_qty": (6, 0, 3, 1), "stat_out_amt": (9, 0, 3, 1),
            "pending":      (0, 1, 12, 1),
            "qty_trend":    (0, 2, 4, 3), "amt_trend":    (4, 2, 4, 3),
            "recent_tx":    (8, 2, 4, 3),
            "category":     (0, 5, 4, 2), "alerts":       (4, 5, 4, 1),
            "stale":        (8, 5, 4, 1),
            "line_qty":     (4, 6, 2, 2), "line_amt":     (6, 6, 2, 2),
            "dev_qty":      (8, 6, 2, 2), "dev_amt":      (10, 6, 2, 2),
        },
        "noprice": {
            "stat_in_qty":  (0, 0, 6, 1), "stat_out_qty": (6, 0, 6, 1),
            "pending":      (0, 1, 12, 1),
            "qty_trend":    (0, 2, 8, 3), "line_qty":     (8, 2, 4, 3),
            "dev_qty":      (0, 5, 4, 3), "alerts":       (4, 5, 4, 3),
            "stale":        (8, 5, 4, 3),
            "recent_tx":    (0, 8, 12, 2),
        },
    },
    "flow": {
        "name": "流水优先",
        "cards": {
            "recent_tx":    (0, 0, 12, 3),
            "stat_in_qty":  (0, 3, 3, 1), "stat_in_amt":  (3, 3, 3, 1),
            "stat_out_qty": (6, 3, 3, 1), "stat_out_amt": (9, 3, 3, 1),
            "pending":      (0, 4, 12, 1),
            "qty_trend":    (0, 5, 6, 2), "amt_trend":    (6, 5, 6, 2),
            "category":     (0, 7, 4, 1), "alerts":       (4, 7, 4, 1),
            "stale":        (8, 7, 4, 1),
            "line_qty":     (0, 8, 3, 2), "line_amt":     (3, 8, 3, 2),
            "dev_qty":      (6, 8, 3, 2), "dev_amt":      (9, 8, 3, 2),
        },
        "noprice": {
            "recent_tx":    (0, 0, 12, 3),
            "stat_in_qty":  (0, 3, 6, 1), "stat_out_qty": (6, 3, 6, 1),
            "pending":      (0, 4, 12, 1),
            "qty_trend":    (0, 5, 12, 2),
            "line_qty":     (0, 7, 6, 2), "dev_qty":      (6, 7, 6, 2),
            "alerts":       (0, 9, 6, 1), "stale":        (6, 9, 6, 1),
        },
    },
    "wide": {
        "name": "宽屏矩阵",
        "cards": {
            "stat_in_qty":  (0, 0, 3, 1), "stat_in_amt":  (3, 0, 3, 1),
            "stat_out_qty": (6, 0, 3, 1), "stat_out_amt": (9, 0, 3, 1),
            "pending":      (0, 1, 12, 1),
            "category":     (0, 2, 4, 2), "alerts":       (4, 2, 4, 2),
            "stale":        (8, 2, 4, 2),
            "qty_trend":    (0, 4, 6, 2), "amt_trend":    (6, 4, 6, 2),
            "line_qty":     (0, 6, 3, 2), "line_amt":     (3, 6, 3, 2),
            "dev_qty":      (6, 6, 3, 2), "dev_amt":      (9, 6, 3, 2),
            "recent_tx":    (0, 8, 12, 2),
        },
        "noprice": {
            "stat_in_qty":  (0, 0, 6, 1), "stat_out_qty": (6, 0, 6, 1),
            "pending":      (0, 1, 12, 1),
            "qty_trend":    (0, 2, 12, 2),
            "line_qty":     (0, 4, 6, 2), "dev_qty":      (6, 4, 6, 2),
            "alerts":       (0, 6, 6, 2), "stale":        (6, 6, 6, 2),
            "recent_tx":    (0, 8, 12, 2),
        },
    },
    # 无金额版独立布局（与上方带金额版一一对应；不含金额类卡片，避免留空，已重新优化排列）
    "classic_np": {
        "name": "经典布局（无金额）",
        "cards": {
            "stat_in_qty":  (0, 0, 6, 1), "stat_out_qty": (6, 0, 6, 1),
            "pending":      (0, 1, 12, 1),
            "qty_trend":    (0, 2, 12, 3),
            "line_qty":     (0, 5, 6, 2), "dev_qty":      (6, 5, 6, 2),
            "alerts":       (0, 7, 6, 1), "stale":        (6, 7, 6, 1),
            "recent_tx":    (0, 8, 12, 2),
        },
    },
    "split_np": {
        "name": "左图右表（无金额）",
        "cards": {
            "stat_in_qty":  (0, 0, 6, 1), "stat_out_qty": (6, 0, 6, 1),
            "pending":      (0, 1, 12, 1),
            "qty_trend":    (0, 2, 7, 5), "recent_tx":    (7, 2, 5, 5),
            "line_qty":     (0, 7, 6, 2), "dev_qty":      (6, 7, 6, 2),
            "alerts":       (0, 9, 6, 1), "stale":        (6, 9, 6, 1),
        },
    },
    "grid_np": {
        "name": "均布网格（无金额）",
        "cards": {
            "stat_in_qty":  (0, 0, 6, 1), "stat_out_qty": (6, 0, 6, 1),
            "pending":      (0, 1, 12, 1),
            "qty_trend":    (0, 2, 6, 4), "recent_tx":    (6, 2, 6, 4),
            "line_qty":     (0, 6, 6, 2), "dev_qty":      (6, 6, 6, 2),
            "alerts":       (0, 8, 6, 2), "stale":        (6, 8, 6, 2),
        },
    },
    "flow_np": {
        "name": "流水优先（无金额）",
        "cards": {
            "recent_tx":    (0, 0, 12, 3),
            "stat_in_qty":  (0, 3, 6, 1), "stat_out_qty": (6, 3, 6, 1),
            "pending":      (0, 4, 12, 1),
            "qty_trend":    (0, 5, 12, 2),
            "line_qty":     (0, 7, 6, 2), "dev_qty":      (6, 7, 6, 2),
            "alerts":       (0, 9, 6, 1), "stale":        (6, 9, 6, 1),
        },
    },
    "wide_np": {
        "name": "宽屏矩阵（无金额）",
        "cards": {
            "stat_in_qty":  (0, 0, 6, 1), "stat_out_qty": (6, 0, 6, 1),
            "pending":      (0, 1, 12, 1),
            "qty_trend":    (0, 2, 12, 3),
            "line_qty":     (0, 5, 4, 2), "dev_qty":      (4, 5, 4, 2),
            "alerts":       (8, 5, 4, 2),
            "stale":        (0, 7, 4, 3), "recent_tx":    (4, 7, 8, 3),
        },
    },
}

DEFAULT_SCREEN = {
    "modules": ["stat_cards", "qty_trend", "amt_trend", "category", "alerts", "recent_tx", "pending", "stale",
                "usage_line_qty", "usage_line_amt",
                "usage_device_qty", "usage_device_amt"],
    "refresh": 30,       # 刷新间隔（秒），默认 30
    "show_price": 0,     # 大屏是否显示金额类卡片（单价/金额为敏感内容，默认不展示；管理员可在大屏配置中开启）
    "period": "day",     # 统计周期 day/week/month
    "theme": "dark",     # dark 深色 / light 浅色
    # 各列表模块显示条数
    "limits": {"recent_tx": 10, "alerts": 10, "stale": 10},
    # 趋势图回溯长度：按日=近N天，按周=近N周，按月=近N月
    "trend": {"day": 14, "week": 8, "month": 6},
    # 大屏呆滞判定天数；0 = 跟随系统设置（默认90天）
    "stale_days": 0,
    # 大屏标题与 LOGO（空/0 = 跟随系统设置的侧栏品牌；sb_show_logo=0 则不显示 LOGO）
    "sb_title": "",
    "sb_subtitle": "",
    "sb_show_logo": 1,
    "sb_logo_height": 48,     # 大屏 LOGO 高度默认值；填 0 = 跟随系统品牌高度
    "sb_title_size": 28,      # 大屏标题字号默认值；填 0 = 跟随系统品牌字号
    "sb_subtitle_size": 14,   # 大屏副标题字号默认值；填 0 = 跟随系统品牌字号
    "sb_title_color": "",
    "sb_subtitle_color": "",
    "sb_font_family": "",
    # 大屏风格：预设名（tech-blue/midnight-gold/tech-cyan/nebula-purple/green-data/light-clean）或 custom（手动）
    "style": "tech-blue",
    # 手动自定义风格色值（custom 时生效，空项跟随科技蓝默认）
    "style_custom": {},
    # 卡片布局：mode = 预设名(classic/split/grid/flow/wide) 或 custom（手动排版）
    # cards = {卡片key: {"x":..,"y":..,"w":..,"h":..}}，网格 12 列 x 10 行
    "layout": {
        "mode": "classic",
        "cards": {k: {"x": v[0], "y": v[1], "w": v[2], "h": v[3]}
                  for k, v in SCREEN_LAYOUTS["classic"]["cards"].items()},
        "noprice": {k: {"x": v[0], "y": v[1], "w": v[2], "h": v[3]}
                    for k, v in SCREEN_LAYOUTS["classic"]["noprice"].items()},
    },
}

# ------------------------------------------------------------------
# 界面主题（管理员可在系统设置页自由配置色系）
# 默认：侧边栏深蓝→墨蓝渐变 + 明亮蓝主色
# ------------------------------------------------------------------
DEFAULT_THEME = {
    "primary": "#3b82c4",    # 主色（按钮/菜单高亮，明亮蓝）
    "primary_d": "#2f6ea8",  # 主色深（hover）
    "sidebar": "#16314f",    # 侧边栏底色（渐变的起点兜底，深蓝）
    "sidebar_text": "#eaf3fb",  # 侧边栏文字
    "bg": "#f0f5fa",         # 页面背景（淡蓝灰）
}

# 自定义表头（备件列表额外列），存 sys_settings key=extra_fields
# 示例：[{"key": "f1", "label": "用途"}, {"key": "f2", "label": "责任人"}]
MAX_EXTRA_FIELDS = 8  # 最多可配置的自定义表头数量

# ------------------------------------------------------------------
# 左侧菜单外观（管理员可在系统设置页自行配置：字号/图标大小/侧栏宽度/字体等）
# 存 sys_settings key=nav_style
# ------------------------------------------------------------------
DEFAULT_NAV_STYLE = {
    "menu_width": 232,     # 侧栏宽度 px
    "font_size": 15,       # 菜单文字字号 px（更大更清晰）
    "icon_size": 19,       # 菜单图标尺寸 px（SVG 图标）
    "font_family": "",     # 菜单字体（空=跟随系统默认）
    "item_padding": 11,    # 菜单项上下内边距 px
    "item_radius": 10,     # 菜单项圆角 px
    "sidebar_top": "#14304f",     # 侧边栏渐变起点（深蓝）
    "sidebar_bottom": "#0e1e33",  # 侧边栏渐变终点（墨蓝）
}

# ------------------------------------------------------------------
# 对外数据接口（WEB API：备件库存查询 / 入库申请）
# 存 sys_settings key=open_api；启用后其他系统带 X-API-Token 头即可调用
# ------------------------------------------------------------------
DEFAULT_OPEN_API = {
    "enabled": False,   # 是否开放 WEB API
    "token": "",        # 接口密钥（调用方请求头 X-API-Token）
}
