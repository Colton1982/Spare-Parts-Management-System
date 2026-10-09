# -*- coding: utf-8 -*-
"""
数据库层：建表、初始化、通用查询辅助
使用 SQLite（单服务端进程访问，放在公共盘也安全）。
"""
import os
import sqlite3
import threading
from datetime import datetime

import config
import db as _db

# 全局写锁：SQLite 单进程下串行化写操作，避免并发写入冲突
_write_lock = threading.Lock()


def get_conn():
    """获取一个新的数据库连接（每请求一个连接，用完即关）
    支持多数据库类型（系统设置中配置）：sqlite/mysql/mariadb/postgresql/mssql/oracle
    - SQLite 自动开启 WAL / busy_timeout / 外键
    - 其它数据库按配置连接，SQL 方言在 db 抽象层自动转换
    """
    conn = _db.connect(config.get_db_cfg())
    conn.execute("""CREATE TABLE IF NOT EXISTS restore_apps(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_no TEXT UNIQUE NOT NULL,
                backup_name TEXT NOT NULL,
                backup_dir TEXT DEFAULT '',
                backup_size INTEGER DEFAULT 0,
                applicant_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                assigned_approver_id INTEGER,
                approver_id INTEGER,
                approval_note TEXT DEFAULT '',
                created_at TEXT,
                processed_at TEXT)""")
    return conn


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str():
    return datetime.now().strftime("%Y-%m-%d")


def _migrate_transactions(conn):
    """兼容迁移：transactions 增加 line_name/device_name 列并回填历史申请数据"""
    cols = _db.list_columns(conn, "transactions")
    if "line_name" not in cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN line_name TEXT DEFAULT ''")
    if "device_name" not in cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN device_name TEXT DEFAULT ''")
    # 历史回填：申请单出库流水的线体/设备
    conn.execute(
        """UPDATE transactions SET line_name=(
               SELECT a.line_name FROM applications a WHERE a.id=transactions.ref_id
           ) WHERE ref_type='application' AND tx_type='out'
             AND (line_name IS NULL OR line_name='')"""
    )
    conn.execute(
        """UPDATE transactions SET device_name=(
               SELECT a.device_name FROM applications a WHERE a.id=transactions.ref_id
           ) WHERE ref_type='application' AND tx_type='out'
             AND (device_name IS NULL OR device_name='')"""
    )
    conn.commit()


def init_db(demo=False):
    """初始化数据库：建目录、建表、写入默认权限与管理员
    demo=True 时在空库中写入演示备件与流水（供试用/演示）
    """
    db_dir = os.path.dirname(config.DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    upd = config.resolved_upload_dir()
    if not os.path.exists(upd):
        os.makedirs(upd, exist_ok=True)

    conn = get_conn()
    try:
        ddl = _db.ddl(_db.dialect(conn), """
            CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                department TEXT DEFAULT '',          -- 所属部门（部门配置中维护）
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS departments(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                remark TEXT DEFAULT '',
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS permissions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                module TEXT NOT NULL,
                action TEXT NOT NULL DEFAULT '',   -- ''=模块级权限；具体操作名=操作级权限
                allow INTEGER NOT NULL DEFAULT 1,
                UNIQUE(role, module, action)
            );

            CREATE TABLE IF NOT EXISTS parts(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                part_code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                category TEXT DEFAULT '',
                spec TEXT DEFAULT '',
                unit TEXT DEFAULT '个',
                qty_decimal INTEGER NOT NULL DEFAULT 0,   -- 0=整数（个/PCS/卷…） 1=小数（米/克/KG…）
                unit_price REAL NOT NULL DEFAULT 0,
                min_stock REAL NOT NULL DEFAULT 0,
                max_stock REAL NOT NULL DEFAULT 0,
                is_valuable INTEGER NOT NULL DEFAULT 0,
                image_file TEXT DEFAULT '',
                supplier TEXT DEFAULT '',
                remark TEXT DEFAULT '',
                location_id INTEGER,               -- 固定放置位置（格位）
                extra TEXT DEFAULT '',             -- 自定义字段 JSON
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS locations(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                warehouse TEXT NOT NULL,           -- 仓库号
                rack TEXT NOT NULL,                -- 货架号
                shelf TEXT NOT NULL,               -- 货位号
                bin TEXT NOT NULL DEFAULT '',      -- 格位号（可空，空=整货位）
                remark TEXT DEFAULT '',
                created_at TEXT,
                UNIQUE(warehouse, rack, shelf, bin)
            );

            CREATE TABLE IF NOT EXISTS audit_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                obj_type TEXT NOT NULL,            -- part=备件 rack=货架位置
                obj_id INTEGER,
                obj_code TEXT DEFAULT '',          -- 备件编号 / 位置文本
                action TEXT NOT NULL,              -- add/edit/delete/restore/purge
                detail TEXT DEFAULT '',            -- JSON：{f:{字段:[旧,新]}, note:'...'}
                operator_id INTEGER,
                operator_name TEXT DEFAULT '',
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS images(
                name TEXT PRIMARY KEY,             -- 图片标识名（备件图片/品牌LOGO统一入库）
                data BLOB NOT NULL,                -- 图片二进制
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS inventory(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                part_id INTEGER NOT NULL,
                location_id INTEGER,               -- 关联 locations.id（NULL=旧文本库位）
                location TEXT NOT NULL,            -- 库位显示文本（位置文本或旧库位名）
                quantity REAL NOT NULL DEFAULT 0,
                FOREIGN KEY(part_id) REFERENCES parts(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS applications(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_no TEXT UNIQUE NOT NULL,
                part_id INTEGER NOT NULL,
                app_type TEXT NOT NULL,            -- in 入库申请 / out 出库申请 / transfer 调库申请
                quantity REAL NOT NULL DEFAULT 1,
                reason TEXT DEFAULT '',
                line_name TEXT DEFAULT '',          -- 出库申请：使用线别（来自产线与设备配置）
                device_name TEXT DEFAULT '',        -- 出库申请：使用设备
                from_location_id INTEGER,          -- 调库：源放置位置（locations.id）
                to_location_id INTEGER,            -- 调库：目标放置位置（locations.id，NULL=待定）
                applicant_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                -- pending 待处理 / approved 已批准(待出库) / rejected 已驳回 / completed 已完成
                -- cancel_req 申请人请求撤销(待仓管审批) / canceled 已撤销
                approval_note TEXT DEFAULT '',
                approver_id INTEGER,               -- 实际审批人（贵重出库）
                assigned_approver_id INTEGER,      -- 指定审批人（贵重出库：普通用户=部门经理；仓管/高级=手动选择）
                operator_id INTEGER,
                operator_note TEXT DEFAULT '',
                created_at TEXT,
                processed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS transactions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_no TEXT UNIQUE NOT NULL,
                part_id INTEGER NOT NULL,
                tx_type TEXT NOT NULL,             -- in 入库 / out 出库 / transfer_in 调拨入 / transfer_out 调拨出
                quantity REAL NOT NULL,
                unit_price REAL NOT NULL DEFAULT 0,
                amount REAL NOT NULL DEFAULT 0,
                location TEXT DEFAULT '',
                ref_type TEXT DEFAULT '',          -- direct 直接操作 / application 申请单
                ref_id INTEGER,
                operator_id INTEGER NOT NULL,
                applicant_id INTEGER,
                line_name TEXT DEFAULT '',         -- 出库领用线别（来自申请）
                device_name TEXT DEFAULT '',       -- 出库领用设备（来自申请）
                remark TEXT DEFAULT '',
                created_at TEXT
            );


            CREATE TABLE IF NOT EXISTS restore_apps(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_no TEXT UNIQUE NOT NULL,
                backup_name TEXT NOT NULL,           -- 备份文件名
                backup_dir TEXT DEFAULT '',          -- 备份所在目录
                backup_size INTEGER DEFAULT 0,
                applicant_id INTEGER NOT NULL,       -- 申请恢复人（仓管/最高）
                status TEXT NOT NULL DEFAULT 'pending',  -- pending/approved/rejected/completed/canceled
                assigned_approver_id INTEGER,        -- 指定审批人（仓管=部门经理或最高；最高自选自己或经理以上）
                approver_id INTEGER,
                approval_note TEXT DEFAULT '',
                created_at TEXT,
                processed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS sys_settings(
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS recycle_items(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_type TEXT NOT NULL,       -- 'location' / 'department' / 'user'
                item_id INTEGER NOT NULL,      -- 原记录 id（恢复时保留原 id，库存/流水引用自动重连）
                data TEXT NOT NULL,            -- 原记录 JSON 快照
                deleted_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_recycle_type ON recycle_items(item_type, deleted_at);

            CREATE TABLE IF NOT EXISTS production_lines(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                remark TEXT DEFAULT '',
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS equipment(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                line_id INTEGER,               -- 所属产线（可空=未分配）
                name TEXT NOT NULL,
                model TEXT DEFAULT '',
                remark TEXT DEFAULT '',
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS part_applications(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                part_id INTEGER NOT NULL,
                line_id INTEGER,                -- 可空：未分配产线的设备仅按设备适用
                equipment_id INTEGER,          -- 可空=整条产线适用
                created_at TEXT,
                UNIQUE(part_id, line_id, equipment_id),
                FOREIGN KEY(part_id) REFERENCES parts(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_tx_part ON transactions(part_id);
            CREATE INDEX IF NOT EXISTS idx_tx_time ON transactions(created_at);
            CREATE INDEX IF NOT EXISTS idx_app_status ON applications(status);
            """
        )
        # 多数据库：DDL 逐条方言化后执行（sqlite 兼容原脚本语义）
        for stmt in _db.split_statements(ddl):
            if stmt.strip():
                conn.execute(stmt)
        _migrate_transactions(conn)   # 建表后执行兼容迁移（新增库也安全）
        conn.commit()

        # 兼容旧库：permissions 表加 action 列（旧表无此列时重建，保留原有权限数据）
        try:
            cols = set(_db.list_columns(conn, "permissions"))
            if "action" not in cols:
                for stmt in _db.split_statements(_db.ddl(_db_dialect(conn), """
                    ALTER TABLE permissions RENAME TO permissions_old;
                    CREATE TABLE permissions(
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        role TEXT NOT NULL,
                        module TEXT NOT NULL,
                        action TEXT NOT NULL DEFAULT '',
                        allow INTEGER NOT NULL DEFAULT 1,
                        UNIQUE(role, module, action)
                    );
                    INSERT INTO permissions(role, module, action, allow)
                        SELECT role, module, '', allow FROM permissions_old;
                    DROP TABLE permissions_old;
                    """)):
                    if stmt.strip():
                        conn.execute(stmt)
                conn.commit()
        except _db.OperationalError:
            pass

        # 默认权限矩阵（action='' 表示模块级权限）
        for role, modules in config.DEFAULT_PERMS.items():
            for m in modules:
                conn.execute(
                    "INSERT OR IGNORE INTO permissions(role, module, action, allow) VALUES(?,?,?,1)",
                    (role, m, ""),
                )
        # 迁移：本轮新增模块（呆滞物料管理）为默认授权角色开启（旧库中该模块可能已按禁止写入）
        for role, modules in config.DEFAULT_PERMS.items():
            if "stale" in modules:
                conn.execute(
                    "UPDATE permissions SET allow=1 WHERE role=? AND module='stale' AND action=''", (role,)
                )
        # 默认操作级权限（按角色级别预置细化项；已配置的行不覆盖）
        for role, mods in config.DEFAULT_PERM_ACTIONS.items():
            for m, acts in mods.items():
                for a, allow in acts.items():
                    conn.execute(
                        "INSERT OR IGNORE INTO permissions(role, module, action, allow) VALUES(?,?,?,?)",
                        (role, m, a, allow),
                    )
        # 未配置的模块默认禁止
        all_mods = list(config.PERM_MODULES.keys())
        for role in config.DEFAULT_PERMS.keys():
            existing = {
                r["module"]
                for r in conn.execute(
                    "SELECT module FROM permissions WHERE role=? AND action=''", (role,)
                ).fetchall()
            }
            for m in all_mods:
                if m not in existing:
                    conn.execute(
                        "INSERT OR IGNORE INTO permissions(role, module, action, allow) VALUES(?,?,?,0)",
                        (role, m, ""),
                    )
        conn.commit()

        # 兼容旧库：为 parts 表补充新列（已存在则跳过）
        for col, ddl in (("location_id", "INTEGER"), ("extra", "TEXT"), ("qty_decimal", "INTEGER DEFAULT 0")):
            try:
                conn.execute(f"ALTER TABLE parts ADD COLUMN {col} {ddl}")
                conn.commit()
            except _db.OperationalError:
                pass
        # 回收站（软删除）：deleted=1 进入回收站（管理员可见/可恢复），deleted_at 删除时间（超期自动彻底清除）
        for col, ddl in (("deleted", "INTEGER NOT NULL DEFAULT 0"), ("deleted_at", "TEXT")):
            try:
                conn.execute(f"ALTER TABLE parts ADD COLUMN {col} {ddl}")
                conn.commit()
            except _db.OperationalError:
                pass
        # 兼容旧库：为 applications 表补充调库位置列
        for col, ddl in (("from_location_id", "INTEGER"), ("to_location_id", "INTEGER"),
                         ("quantity", "REAL DEFAULT 1")):
            try:
                conn.execute(f"ALTER TABLE applications ADD COLUMN {col} {ddl}")
                conn.commit()
            except _db.OperationalError:
                pass
        # 兼容旧库：为 users 表补充部门列
        try:
            conn.execute("ALTER TABLE users ADD COLUMN department TEXT DEFAULT ''")
            conn.commit()
        except _db.OperationalError:
            pass
        # 兼容旧库：part_applications.line_id 若为 NOT NULL（旧结构），重建为可空
        # （支持"只选未分配产线的设备"：line_id 为空、仅按设备适用）
        pa_cols = {c: {} for c in _db.list_columns(conn, "part_applications")}
        if pa_cols and pa_cols.get("line_id") and pa_cols["line_id"]["notnull"]:
            for stmt in _db.split_statements(_db.ddl(_db_dialect(conn), """
                ALTER TABLE part_applications RENAME TO part_applications_old;
                CREATE TABLE part_applications(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    part_id INTEGER NOT NULL,
                    line_id INTEGER,
                    equipment_id INTEGER,
                    created_at TEXT,
                    UNIQUE(part_id, line_id, equipment_id),
                    FOREIGN KEY(part_id) REFERENCES parts(id) ON DELETE CASCADE
                );
                INSERT INTO part_applications(id, part_id, line_id, equipment_id, created_at)
                    SELECT id, part_id, line_id, equipment_id, created_at FROM part_applications_old;
                DROP TABLE part_applications_old;
                """)):
                if stmt.strip():
                    conn.execute(stmt)
            conn.commit()
        # 兼容旧库：为 inventory 表补充 location_id 列（NULL=旧文本库位）
        try:
            conn.execute("ALTER TABLE inventory ADD COLUMN location_id INTEGER")
            conn.commit()
        except _db.OperationalError:
            pass
        # 兼容旧库：为 applications 表补充指定审批人列
        try:
            conn.execute("ALTER TABLE applications ADD COLUMN assigned_approver_id INTEGER")
            conn.commit()
        except _db.OperationalError:
            pass
        # 兼容旧库：为 applications 表补充出库领用线别/设备列
        for col, ddl in (("line_name", "TEXT DEFAULT ''"), ("device_name", "TEXT DEFAULT ''")):
            try:
                conn.execute(f"ALTER TABLE applications ADD COLUMN {col} {ddl}")
                conn.commit()
            except _db.OperationalError:
                pass
        # 兼容旧库：尝试把旧文本库位映射到 locations（location 文本=位置文本时关联）
        try:
            conn.execute(
                """UPDATE inventory SET location_id=(
                     SELECT l.id FROM locations l
                     WHERE l.warehouse||'-'||l.rack||'-'||l.shelf
                           ||COALESCE('-'||NULLIF(l.bin,''),'') = inventory.location)
                   WHERE location_id IS NULL"""
            )
            conn.commit()
        except _db.OperationalError:
            pass
        # 默认部门（首次建库时写入，可在「部门配置」中调整）
        for dname in ("生产部", "品质部", "设备部", "仓库", "办公室"):
            conn.execute(
                "INSERT OR IGNORE INTO departments(name, created_at) VALUES(?,?)",
                (dname, now_str()),
            )
        conn.commit()

        # 默认管理员（库中没有任何用户时自动创建）
        cur = conn.execute("SELECT COUNT(*) c FROM users")
        if cur.fetchone()["c"] == 0:
            from werkzeug.security import generate_password_hash
            conn.execute(
                "INSERT INTO users(username,password_hash,display_name,role,active,created_at) VALUES(?,?,?,?,1,?)",
                (
                    "admin",
                    generate_password_hash("admin123"),
                    "系统管理员",
                    "admin",
                    now_str(),
                ),
            )
            conn.commit()

        # 内置访客账号（AD 验证通过但不在白名单时以访客身份进入；无密码，不可直接登录）
        cur = conn.execute("SELECT COUNT(*) c FROM users WHERE username='guest'")
        if cur.fetchone()["c"] == 0:
            conn.execute(
                "INSERT INTO users(username,password_hash,display_name,role,active,created_at) VALUES(?,?,?,?,1,?)",
                ("guest", "!", "访客", "guest", now_str()),
            )
            conn.commit()

        if demo:
            _seed_demo_if_empty(conn)
            _seed_demo_locations_if_missing(conn)
    finally:
        conn.close()


# ------------------------------------------------------------------
# 图片入库：图片二进制统一存入主数据库 images 表（单文件随库带走）
# 备件图片与品牌 LOGO 都走这里；旧版已存在 upload_dir 目录中的图片
# 仍可被 /media 路由回退读取，新图片一律入库存取。
# ------------------------------------------------------------------
def image_save(conn, name, data):
    """保存图片二进制到 images 表（同名覆盖）。conn 须为已打开的主库连接"""
    conn.execute(
        "INSERT INTO images(name, data, created_at) VALUES(?,?,?) "
        "ON CONFLICT(name) DO UPDATE SET data=excluded.data, created_at=excluded.created_at",
        (name, data, now_str()),
    )


def image_load(conn, name):
    """按图片名读取二进制；不存在返回 None"""
    row = conn.execute("SELECT data FROM images WHERE name=?", (name,)).fetchone()
    return bytes(row["data"]) if row else None


def image_delete(conn, name):
    """删除图片记录"""
    conn.execute("DELETE FROM images WHERE name=?", (name,))


def backup_database(target_path):
    """在线备份主数据库到指定文件（仅 SQLite 支持：文件级备份）。
    其它数据库类型请使用数据库自身的备份机制（如 MySQL mysqldump、PostgreSQL pg_dump、SQL Server/Oracle 管理工具）"""
    if config.DB_TYPE != "sqlite":
        raise OSError("备份/恢复仅支持 SQLite 数据库；%s 请使用数据库自带备份工具" % config.DB_TYPE.upper())
    if not config.DB_PATH or not os.path.exists(config.DB_PATH):
        raise OSError("数据库未配置或文件不存在")
    src = sqlite3.connect(config.DB_PATH, timeout=30)
    dst = None
    try:
        dst = sqlite3.connect(target_path, timeout=30)
        src.backup(dst)
    finally:
        if dst is not None:
            dst.close()
        src.close()
    return target_path


def _seed_demo_if_empty(conn):
    """空库时生成演示数据，便于直接查看图表效果（初始化向导中勾选「演示数据」触发）"""
    if conn.execute("SELECT COUNT(*) c FROM parts").fetchone()["c"] > 0:
        return
    from werkzeug.security import generate_password_hash
    # 演示账号
    demo_users = [
        ("warehouse01", "123456", "王仓管", "warehouse", "仓库"),
        ("manager01", "123456", "李经理", "manager", "生产部"),
        ("user01", "123456", "张三", "user", "生产部"),
    ]
    uid_map = {}
    for u, p, n, r, dep in demo_users:
        cur = conn.execute(
            "INSERT INTO users(username,password_hash,display_name,role,department,active,created_at) VALUES(?,?,?,?,?,1,?)",
            (u, generate_password_hash(p), n, r, dep, now_str()),
        )
        uid_map[u] = cur.lastrowid

    # 演示备件
    demo_parts = [
        # code, name, category, spec, unit, price, min, max, valuable, supplier
        ("R-0603-10K", "贴片电阻 0603 10KΩ", "电阻", "0603 ±1% 1/10W", "盘", 2.5, 20, 200, 0, "国巨"),
        ("R-0805-4K7", "贴片电阻 0805 4.7KΩ", "电阻", "0805 ±1% 1/8W", "盘", 3.2, 20, 180, 0, "国巨"),
        ("C-0805-100N", "贴片电容 0805 100nF", "电容", "0805 50V X7R", "盘", 4.0, 15, 150, 0, "村田"),
        ("C-0603-1U", "贴片电容 0603 1uF", "电容", "0603 25V X5R", "盘", 4.8, 15, 150, 0, "村田"),
        ("IC-LDO-3V3", "稳压芯片 LDO 3.3V", "IC", "SOT-23-5", "个", 45.0, 50, 800, 1, "TI"),
        ("IC-MCU-STM32", "主控 MCU STM32F103", "IC", "LQFP-48", "个", 680.0, 10, 120, 1, "ST"),
        ("SN-0307", "焊锡丝 0.8mm 63/37", "辅料", "0.8mm 500g", "卷", 120.0, 5, 40, 0, "云锡"),
        ("PA-FLUX", "助焊剂 FLUX-881", "辅料", "1L 喷雾型", "瓶", 85.0, 6, 60, 0, "同方"),
        ("NOZ-503", "吸嘴 503 0402", "吸嘴", "0402 通用", "个", 25.0, 30, 300, 0, "雅马哈"),
        ("NOZ-505", "吸嘴 505 0603", "吸嘴", "0603 通用", "个", 25.0, 30, 300, 0, "雅马哈"),
    ]
    part_id_map = {}
    for (code, name, cat, spec, unit, price, mn, mx, val, sup) in demo_parts:
        cur = conn.execute(
            """INSERT INTO parts(part_code,name,category,spec,unit,unit_price,min_stock,max_stock,is_valuable,supplier,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (code, name, cat, spec, unit, price, mn, mx, val, sup, now_str(), now_str()),
        )
        part_id_map[code] = cur.lastrowid
        # 初始库存：两个库位
        conn.execute(
            "INSERT INTO inventory(part_id,location,quantity) VALUES(?,?,?)",
            (cur.lastrowid, "A线备件库", round(mx * 0.55)),
        )
        conn.execute(
            "INSERT INTO inventory(part_id,location,quantity) VALUES(?,?,?)",
            (cur.lastrowid, "B线备件库", round(mx * 0.2)),
        )

    # 演示产线 / 设备 / 备件适用对象
    line_map = {}
    for ln in ("SMT-1线", "SMT-2线", "DIP线"):
        cur = conn.execute(
            "INSERT INTO production_lines(name, remark, created_at) VALUES(?,?,?)",
            (ln, "演示产线", now_str()),
        )
        line_map[ln] = cur.lastrowid
    equip_rows = [
        (line_map["SMT-1线"], "贴片机1#", "YSM20"),
        (line_map["SMT-1线"], "回流焊1#", "RF-10"),
        (line_map["SMT-2线"], "印刷机2#", "SP-8"),
        (line_map["DIP线"], "波峰焊1#", "WS-450"),
        (None, "离线AOI", "AOI-200"),
    ]
    equip_map = {}
    for lid, en, m in equip_rows:
        cur = conn.execute(
            "INSERT INTO equipment(line_id, name, model, created_at) VALUES(?,?,?,?)",
            (lid, en, m, now_str()),
        )
        equip_map[en] = cur.lastrowid
    # 两个演示备件绑定适用产线/设备
    if "R-0603-10K" in part_id_map:
        set_part_apps(conn, part_id_map["R-0603-10K"],
                      [(line_map["SMT-1线"], equip_map["贴片机1#"]),
                       (line_map["SMT-1线"], None),
                       (line_map["SMT-2线"], equip_map["印刷机2#"]),
                       (None, equip_map["离线AOI"])])  # 未分配产线的设备也适用
    if "IC-MCU-STM32" in part_id_map:
        set_part_apps(conn, part_id_map["IC-MCU-STM32"],
                      [(line_map["SMT-1线"], None), (line_map["DIP线"], equip_map["波峰焊1#"])])

    # 故意制造两个预警示例：主控MCU 低于下限、焊锡丝 超过上限（便于演示上下限管理）
    mcu = conn.execute("SELECT id FROM parts WHERE part_code='IC-MCU-STM32'").fetchone()
    if mcu:
        conn.execute("UPDATE inventory SET quantity=2 WHERE part_id=? AND location='A线备件库'", (mcu["id"],))
        conn.execute("UPDATE inventory SET quantity=2 WHERE part_id=? AND location='B线备件库'", (mcu["id"],))
    sn = conn.execute("SELECT id FROM parts WHERE part_code='SN-0307'").fetchone()
    if sn:
        conn.execute("UPDATE inventory SET quantity=32 WHERE part_id=? AND location='A线备件库'", (sn["id"],))
        conn.execute("UPDATE inventory SET quantity=18 WHERE part_id=? AND location='B线备件库'", (sn["id"],))

    # 生成近 60 天的出入库流水（确定性随机，便于图表演示）
    import random
    rnd = random.Random(20260922)
    codes = list(part_id_map.keys())
    day0 = datetime.now()
    tx_idx = 1
    for i in range(60, -1, -1):
        d = datetime(day0.year, day0.month, day0.day, hour=rnd.randint(8, 18),
                     minute=rnd.randint(0, 59))
        for _ in range(rnd.randint(1, 4)):
            code = rnd.choice(codes)
            pid = part_id_map[code]
            price = conn.execute("SELECT unit_price FROM parts WHERE id=?", (pid,)).fetchone()["unit_price"]
            typ = "in" if rnd.random() < 0.45 else "out"
            qty = rnd.choice([10, 20, 30, 50, 100, 200, 5, 15, 25, 40, 80])
            loc = rnd.choice(["A线备件库", "B线备件库"])
            conn.execute(
                """INSERT INTO transactions(tx_no,part_id,tx_type,quantity,unit_price,amount,location,ref_type,operator_id,remark,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    f"TX{d.strftime('%Y%m%d%H%M%S')}{tx_idx:03d}", pid, typ, qty, price,
                    round(qty * price, 2), loc, "direct", uid_map["warehouse01"],
                    "演示数据", d.strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            tx_idx += 1
    conn.commit()


def _seed_demo_locations_if_missing(conn):
    """演示库升级：已有备件但无货架位置时补种位置并分配（兼容旧演示库）"""
    if conn.execute("SELECT COUNT(*) c FROM locations").fetchone()["c"] > 0:
        return
    demo_locs = [
        ("WH-01", "R-01", "S-01", "B-01"),
        ("WH-01", "R-01", "S-01", "B-02"),
        ("WH-01", "R-01", "S-02", "B-01"),
        ("WH-01", "R-01", "S-02", "B-02"),
        ("WH-01", "R-02", "S-01", "B-01"),
        ("WH-01", "R-02", "S-01", "B-02"),
        ("WH-01", "R-02", "S-02", "B-01"),
        ("WH-01", "R-02", "S-02", "B-02"),
        ("WH-02", "R-01", "S-01", "B-01"),
        ("WH-02", "R-01", "S-01", "B-02"),
        ("WH-02", "R-01", "S-02", ""),   # 格位号可空：整货位位置
        # 第二库位池（与主位置 0-9 不重叠，保证每备件两个独立库位）
        ("WH-02", "R-02", "S-01", "B-01"),
        ("WH-02", "R-02", "S-01", "B-02"),
        ("WH-02", "R-02", "S-02", "B-01"),
        ("WH-02", "R-02", "S-02", "B-02"),
        ("WH-02", "R-03", "S-01", "B-01"),
        ("WH-02", "R-03", "S-01", "B-02"),
        ("WH-02", "R-03", "S-02", "B-01"),
        ("WH-02", "R-03", "S-02", "B-02"),
        ("WH-03", "R-01", "S-01", "B-01"),
        ("WH-03", "R-01", "S-01", "B-02"),
    ]
    loc_id_map = {}
    for (wh, rk, sf, bn) in demo_locs:
        cur = conn.execute(
            "INSERT INTO locations(warehouse,rack,shelf,bin,created_at) VALUES(?,?,?,?,?)",
            (wh, rk, sf, bn, now_str()),
        )
        loc_id_map[f"{wh}-{rk}-{sf}-{bn}"] = cur.lastrowid
    rows = conn.execute("SELECT id FROM parts").fetchall()
    for idx, r in enumerate(rows):
        key = demo_locs[idx % len(demo_locs)]
        conn.execute(
            "UPDATE parts SET location_id=? WHERE id=?",
            (loc_id_map["-".join(key)], r["id"]),
        )
        # 把库存两行映射到两个货位（多库位演示：主位置 idx + 第二位置 idx+10，互不重叠）
        inv_rows = conn.execute(
            "SELECT id FROM inventory WHERE part_id=? ORDER BY id", (r["id"],)
        ).fetchall()
        key2 = demo_locs[(idx + 10) % len(demo_locs)]
        for k, inv in zip((key, key2), inv_rows):
            lid = loc_id_map["-".join(k)]
            conn.execute(
                "UPDATE inventory SET location_id=?, location=? WHERE id=?",
                (lid, location_text(get_location(conn, lid)), inv["id"]),
            )
    conn.commit()


# ------------------------------------------------------------------
# 业务辅助函数
# ------------------------------------------------------------------
def total_stock(conn, part_id):
    """某备件的总库存（跨库位合计）"""
    row = conn.execute(
        "SELECT COALESCE(SUM(quantity),0) s FROM inventory WHERE part_id=?", (part_id,)
    ).fetchone()
    return row["s"] if row else 0


def stock_locations(conn, part_id):
    """某备件在各库位的分布（每行含 inventory 行 id、位置 id 与显示文本）"""
    rows = conn.execute(
        """SELECT i.id inv_id, i.location_id, i.location, i.quantity
           FROM inventory i WHERE i.part_id=? ORDER BY i.location, i.id""",
        (part_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def part_detail(conn, part_id):
    """备件详情 + 库存汇总（已删除的备件视为不存在）"""
    p = conn.execute("SELECT * FROM parts WHERE id=? AND deleted=0", (part_id,)).fetchone()
    if not p:
        return None
    d = dict(p)
    d["total_stock"] = total_stock(conn, part_id)
    d["locations"] = stock_locations(conn, part_id)
    d["stock_status"] = (
        "low" if d["total_stock"] < d["min_stock"]
        else ("high" if (d["max_stock"] and d["total_stock"] > d["max_stock"]) else "ok")
    )
    return d


def gen_no(prefix, conn, table, col):
    """生成单据编号，如 APP20260922-001"""
    ts = datetime.now().strftime("%Y%m%d")
    row = conn.execute(
        f"SELECT {col} v FROM {table} WHERE {col} LIKE ? ORDER BY {col} DESC LIMIT 1",
        (f"{prefix}{ts}-%",),
    ).fetchone()
    seq = 1
    if row:
        try:
            seq = int(str(row["v"]).rsplit("-", 1)[1]) + 1
        except Exception:
            seq = 1
    return f"{prefix}{ts}-{seq:03d}"


def get_setting(conn, key, default=None):
    """读取系统设置（key-value 表）"""
    row = conn.execute("SELECT value FROM sys_settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn, key, value):
    """写入系统设置"""
    conn.execute(
        "INSERT INTO sys_settings(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


# ------------------------------------------------------------------
# 产线 / 设备 / 备件适用对象
# ------------------------------------------------------------------
def list_lines(conn):
    """全部产线"""
    return [dict(r) for r in conn.execute(
        "SELECT * FROM production_lines ORDER BY id").fetchall()]


def list_equipment(conn, line_id=None):
    """设备列表（可按产线过滤）"""
    if line_id:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM equipment WHERE line_id=? ORDER BY id", (line_id,)).fetchall()]
    return [dict(r) for r in conn.execute(
        "SELECT * FROM equipment ORDER BY line_id, id").fetchall()]


def part_apps(conn, part_id):
    """某备件的适用产线/设备列表（含产线/设备名称）"""
    rows = conn.execute(
        """SELECT pa.line_id, pa.equipment_id, pl.name line_name, e.name equip_name, e.model equip_model
           FROM part_applications pa
           LEFT JOIN production_lines pl ON pa.line_id=pl.id
           LEFT JOIN equipment e ON pa.equipment_id=e.id
           WHERE pa.part_id=? ORDER BY pa.id""",
        (part_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def set_part_apps(conn, part_id, pairs):
    """重设备件适用产线/设备：pairs=[(line_id_or_None, equipment_id_or_None), ...]
    同一备件同一组合只保留一行；
    - (line_id, equipment_id)   该产线下某台设备
    - (line_id, None)           整条产线适用
    - (None, equipment_id)      未分配产线的设备（按设备本身适用）
    """
    conn.execute("DELETE FROM part_applications WHERE part_id=?", (part_id,))
    for line_id, equip_id in pairs:
        if not line_id and not equip_id:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO part_applications(part_id, line_id, equipment_id, created_at) VALUES(?,?,?,?)",
            (part_id, int(line_id) if line_id else None, int(equip_id) if equip_id else None, now_str()),
        )


def get_location(conn, loc_id):
    """按 id 取货架位置"""
    if not loc_id:
        return None
    return conn.execute("SELECT * FROM locations WHERE id=?", (loc_id,)).fetchone()


def location_text(loc):
    """位置显示文本：仓库号-货架号-货位号-格位号（格位为空时只显示三级）
    loc 可为 sqlite3.Row / 统一行对象 或 dict
    """
    if not loc:
        return ""
    bin_v = loc["bin"] if "bin" in loc.keys() else loc.get("bin")
    base = f"{loc['warehouse']}-{loc['rack']}-{loc['shelf']}"
    if bin_v:
        return f"{base}-{bin_v}"
    return base


def move_stock(conn, part_id, loc, delta):
    """在指定库位增减库存（原子 SQL，多用户并发安全）
    loc 可为 int（locations.id）或 str（旧文本库位名，兼容）
    delta>0 入库，delta<0 出库（不允许出负库存）
    """
    if isinstance(loc, int):
        # 按位置 id 操作：位置文本同步刷新
        loc_row = get_location(conn, loc)
        loc_txt = location_text(loc_row) if loc_row else ""
        if not loc_row:
            return False, f"库位(id={loc})不存在"
        row = conn.execute(
            "SELECT id, quantity FROM inventory WHERE part_id=? AND location_id=? ORDER BY id LIMIT 1",
            (part_id, loc),
        ).fetchone()
        if delta >= 0:
            if row:
                conn.execute(
                    "UPDATE inventory SET quantity=quantity+?, location=? WHERE id=?",
                    (delta, loc_txt, row["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO inventory(part_id, location_id, location, quantity) VALUES(?,?,?,?)",
                    (part_id, loc, loc_txt, delta),
                )
            return True, "ok"
        # 出库：先校验该位置总库存，再逐行扣减（兼容同位置多行历史数据）
        tot = conn.execute(
            "SELECT COALESCE(SUM(quantity),0) s FROM inventory WHERE part_id=? AND location_id=?",
            (part_id, loc),
        ).fetchone()["s"]
        if tot + delta < 0:
            return False, f"库存不足：库位[{loc_txt}] 现有 {tot}"
        rem = -delta
        for r in conn.execute(
            "SELECT id, quantity FROM inventory WHERE part_id=? AND location_id=? AND quantity>0 ORDER BY id",
            (part_id, loc),
        ).fetchall():
            if rem <= 0:
                break
            take = min(r["quantity"], rem)
            conn.execute("UPDATE inventory SET quantity=quantity-? WHERE id=?", (take, r["id"]))
            rem -= take
        return True, "ok"
    # 旧文本库位路径（兼容旧流水回滚等；先查后改/插，兼容同位置多行历史数据）
    if delta >= 0:
        row = conn.execute(
            "SELECT id FROM inventory WHERE part_id=? AND location=? ORDER BY id LIMIT 1",
            (part_id, loc),
        ).fetchone()
        if row:
            conn.execute("UPDATE inventory SET quantity=quantity+? WHERE id=?", (delta, row["id"]))
        else:
            conn.execute(
                "INSERT INTO inventory(part_id, location, quantity) VALUES(?,?,?)",
                (part_id, loc, delta),
            )
        return True, "ok"
    cur = conn.execute(
        """UPDATE inventory SET quantity = quantity + ?
           WHERE part_id=? AND location=? AND quantity + ? >= 0""",
        (delta, part_id, loc, delta),
    )
    if cur.rowcount == 0:
        row = conn.execute(
            "SELECT quantity FROM inventory WHERE part_id=? AND location=?",
            (part_id, loc),
        ).fetchone()
        if row:
            return False, f"库存不足：库位[{loc}] 现有 {row['quantity']}"
        return False, f"库位[{loc}]无该备件库存"
    return True, "ok"
