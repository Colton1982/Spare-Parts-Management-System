# -*- coding: utf-8 -*-
"""
多数据库抽象层：统一连接、SQL 方言转换、通用辅助
支持数据库类型（开源 + 闭源）：
  sqlite（内置） / mysql / mariadb / postgresql / mssql（SQL Server） / oracle

设计原则：
- 业务代码继续写 SQLite 风格的 SQL（? 占位符、AUTOINCREMENT、INSERT OR IGNORE、
  ON CONFLICT、LIMIT、LIKE），本层在执行前自动转换为目标方言；
- 不支持原生语法的方言自动降级为「先查后写」，语义保持一致；
- 连接参数由系统设置中的「数据库类型」配置决定（settings.json），重启服务生效。
"""
import os
import re
import threading
import sqlite3

# 连接 → 方言映射（sqlite3/pymysql 等连接对象可能不允许自定义属性）
_DIALECTS = {}


def dialect(conn):
    return _DIALECTS.get(conn, "sqlite")

# 支持的方言（settings.json db_type 取值）
DIALECTS = ("sqlite", "mysql", "mariadb", "postgresql", "mssql", "oracle")

# 各方言对应的 Python 驱动（未安装时给出安装提示）
DRIVERS = {
    "sqlite": ("内置", None),
    "mysql": ("pymysql", "pip install pymysql"),
    "mariadb": ("pymysql", "pip install pymysql"),
    "postgresql": ("psycopg2", "pip install psycopg2-binary"),
    "mssql": ("pymssql", "pip install pymssql"),
    "oracle": ("oracledb", "pip install oracledb"),
}

_sqlite_lock = threading.Lock()  # SQLite 写串行化（多线程下）

# ---------------------------------------------------------------------------
# 连接
# ---------------------------------------------------------------------------

def connect(cfg):
    """按配置建立连接。cfg 为 dict：db_type, db_path(仅 sqlite),
    host/port/user/password/database(库名)/service_name(仅 oracle)"""
    d = (cfg.get("db_type") or "sqlite").strip().lower()
    if d not in DIALECTS:
        raise ValueError("不支持的数据库类型: %s（可选: %s）" % (d, "/".join(DIALECTS)))
    if d == "sqlite":
        path = (cfg.get("db_path") or "").strip()
        if not path:
            raise ValueError("SQLite 未配置数据库文件路径")
        d0 = os.path.dirname(path)
        if d0 and not os.path.exists(d0):
            os.makedirs(d0, exist_ok=True)
        conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _init_sqlite(conn)
        _DIALECTS[conn] = "sqlite"
        return wrap_conn(conn)
    mod, tip = DRIVERS[d]
    try:
        driver = __import__(mod)
    except ImportError:
        raise RuntimeError("缺少 %s 驱动（%s）：%s" % (mod, d, tip))
    kw = dict(cfg)
    if d in ("mysql", "mariadb"):
        import pymysql
        conn = pymysql.connect(
            host=kw.get("host") or "127.0.0.1", port=int(kw.get("port") or 3306),
            user=kw.get("user") or "root", password=kw.get("password") or "",
            database=kw.get("database") or "", charset="utf8mb4",
            autocommit=False, cursorclass=pymysql.cursors.DictCursor)
        _DIALECTS[conn] = "mariadb" if d == "mariadb" else "mysql"
        return wrap_conn(conn)
    if d == "postgresql":
        conn = psycopg2.connect(
            host=kw.get("host") or "127.0.0.1", port=int(kw.get("port") or 5432),
            user=kw.get("user") or "postgres", password=kw.get("password") or "",
            dbname=kw.get("database") or "postgres")
        conn.autocommit = False
        _DIALECTS[conn] = "postgresql"
        return wrap_conn(conn)
    if d == "mssql":
        conn = pymssql.connect(
            server=kw.get("host") or "127.0.0.1", port=int(kw.get("port") or 1433),
            user=kw.get("user") or "sa", password=kw.get("password") or "",
            database=kw.get("database") or "master", as_dict=True)
        _DIALECTS[conn] = "mssql"
        return wrap_conn(conn)
    if d == "oracle":
        conn = oracledb.connect(
            user=kw.get("user") or "", password=kw.get("password") or "",
            dsn=(kw.get("host") or "127.0.0.1") + ":" + str(kw.get("port") or 1521) + "/" +
                (kw.get("service_name") or kw.get("database") or "XE"))
        conn.autocommit = False
        _DIALECTS[conn] = "oracle"
        return wrap_conn(conn)
    raise ValueError("未实现的方言: " + d)


def _init_sqlite(conn):
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")


# ---------------------------------------------------------------------------
# 占位符转换（? -> %s / :n），忽略单引号内的 ?
# ---------------------------------------------------------------------------

def _quote_split(sql):
    """把 SQL 按单引号字符串与普通段切分"""
    parts, buf, in_q = [], [], False
    for ch in sql:
        if ch == "'":
            in_q = not in_q
        buf.append(ch)
        if in_q:
            continue
        if ch == "'":
            pass
    # 上面逐字符切分太慢，改用正则：
    return re.split(r"('[^']*')", sql)


def _convert_placeholders(dialect, sql):
    """把 sqlite 风格 ? 占位符转为目标方言占位符（忽略字符串常量内的 ?）"""
    if dialect == "sqlite":
        return sql
    if dialect == "oracle":
        n = [0]

        def repl(m):
            n[0] += 1
            return ":%d" % n[0]

        return re.sub(r"\?(?=(?:[^']*'[^']*')*[^']*$)", repl, sql)
    # %s 系列（mysql/pg/mssql）
    return re.sub(r"\?(?=(?:[^']*'[^']*')*[^']*$)", "%s", sql)


# ---------------------------------------------------------------------------
# SQL 方言转换
# ---------------------------------------------------------------------------

_AUTOINC_RE = re.compile(r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b", re.I)

def ddl(dialect, sql):
    """CREATE TABLE 方言化：自增主键语法"""
    if dialect == "sqlite":
        return sql
    m = {
        "mysql": "INT AUTO_INCREMENT PRIMARY KEY",
        "mariadb": "INT AUTO_INCREMENT PRIMARY KEY",
        "postgresql": "SERIAL PRIMARY KEY",
        "mssql": "INT IDENTITY(1,1) PRIMARY KEY",
        "oracle": "NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY",
    }.get(dialect)
    if m is None:
        return sql
    sql = _AUTOINC_RE.sub(m, sql)
    # TEXT 列不能作主键（mysql/mariadb/mssql 需长度；oracle CLOB 不可主键），转定长字符型
    sql = re.sub(r"\bTEXT\s+PRIMARY\s+KEY", "VARCHAR(191) PRIMARY KEY", sql, flags=re.I)
    # TEXT UNIQUE 索引超长（utf8mb4 上限 3072 字节），转 VARCHAR(255)
    sql = re.sub(r"\bTEXT\s+UNIQUE\b", "VARCHAR(255) UNIQUE", sql, flags=re.I)
    # 被 CREATE INDEX 引用的 TEXT 列（状态/时间/类型）在 mysql/mariadb/mssql 需定长，否则索引超长
    if dialect in ("mysql", "mariadb", "mssql"):
        sql = re.sub(r"\b(status|created_at|processed_at|updated_at|deleted_at)\s+TEXT\b",
                     r"\1 VARCHAR(32)", sql, flags=re.I)
        sql = re.sub(r"\bitem_type\s+TEXT\b", "item_type VARCHAR(64)", sql, flags=re.I)
    # 保留字列名（DDL 列定义）：key -> `key`（mysql/mariadb/mssql 均需；按后续类型词定位，兼容被 _normalize 压平的单行）
    if dialect in ("mysql", "mariadb", "mssql"):
        sql = re.sub(r"(?<![A-Za-z0-9_`])key(?=\s+(?:TEXT|VARCHAR|INTEGER|REAL|BLOB|NUMBER)\b)", "`key`", sql, flags=re.I)
    if dialect == "oracle":
        sql = re.sub(r"\bTEXT\b", "CLOB", sql, flags=re.I)
        sql = re.sub(r"\bREAL\b", "NUMBER", sql, flags=re.I)
        sql = re.sub(r"\bINTEGER\b(?!\s+PRIMARY)", "NUMBER(10)", sql, flags=re.I)
    elif dialect == "mssql":
        sql = re.sub(r"\bTEXT\b", "NVARCHAR(MAX)", sql, flags=re.I)
    return sql


def _normalize(sql):
    return re.sub(r"\s+", " ", sql.strip()).strip()


def convert_sql(dialect, sql, params=None):
    """执行前把 SQLite 风格 SQL 转换为目标方言。
    返回 (sql, params, mode)；mode: 'exec' 直接执行 / 'ignore' 先查后插 / 'upsert' 先查后改"""
    sql = _normalize(sql)
    mode = "exec"
    # 0) 保留字列名 key（mysql/mariadb/mssql），排除 PRIMARY KEY / FOREIGN KEY / INDEX key 等关键字组合
    if dialect in ("mysql", "mariadb", "mssql"):
        def _qk(m):
            pre = sql[max(0, m.start() - 12):m.start()].upper()
            if re.search(r"(PRIMARY|FOREIGN|UNIQUE|INDEX|KEY|CONSTRAINT)\s*$", pre):
                return m.group(0)  # PRIMARY KEY / FOREIGN KEY 等关键字组合，原样保留
            return "`key`"
        sql = re.sub(r"(?<![\w`])key(?=\s*[=,)]|$)", _qk, sql, flags=re.I)
    # 1) INSERT OR IGNORE
    if re.match(r"INSERT\s+OR\s+IGNORE\s+INTO", sql, re.I):
        if dialect in ("mysql", "mariadb"):
            sql = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT IGNORE INTO", sql, count=1, flags=re.I)
        elif dialect == "sqlite":
            pass  # 原生支持
        elif dialect == "postgresql":
            sql = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", sql, count=1, flags=re.I)
            sql += " ON CONFLICT DO NOTHING"
        else:  # mssql / oracle
            return (sql, params, "ignore")
    # 2) ON CONFLICT ... DO UPDATE SET a=excluded.a
    m = re.search(r"ON\s+CONFLICT\s*\(([^)]*)\)\s*DO\s+UPDATE\s+SET\s+(.+)", sql, re.I)
    if m and dialect in ("mysql", "mariadb"):
        cols = m.group(1)
        sets = m.group(2)
        sets = re.sub(r"excluded\.([A-Za-z0-9_]+)", r"VALUES(\1)", sets)
        sql = sql[:m.start()].rstrip() + " ON DUPLICATE KEY UPDATE " + sets
    elif m and dialect in ("mssql", "oracle"):
        return (sql, params, "upsert")
    # 3) LIKE ? -> pg ILIKE / oracle UPPER（保持 sqlite 不区分大小写语义）
    if dialect == "postgresql":
        sql = re.sub(r"(?<![A-Za-z0-9_])LIKE\s+(\?)", "ILIKE \\1", sql, flags=re.I)
    elif dialect == "oracle":
        sql = re.sub(r"([A-Za-z0-9_.]+)\s+LIKE\s+(\?)", "UPPER(\\1) LIKE UPPER(\\2)", sql, flags=re.I)
    # 3.5) COLLATE NOCASE（登录用户名大小写开关）：sqlite 保留；mysql/mssql 默认不区分删掉；pg/oracle 用 LOWER
    m_nocase = re.search(r"([A-Za-z0-9_.]+)\s*=\s*\?\s+COLLATE\s+NOCASE", sql, re.I)
    if m_nocase:
        col = m_nocase.group(1)
        if dialect == "sqlite":
            pass
        elif dialect in ("mysql", "mariadb", "mssql"):
            sql = sql[:m_nocase.start()] + "%s=?" % col + sql[m_nocase.end():]
        else:  # postgresql / oracle：默认区分大小写 -> 用 LOWER 保持不区分语义
            sql = sql[:m_nocase.start()] + "LOWER(%s)=LOWER(?)" % col + sql[m_nocase.end():]
    # 4) LIMIT
    if dialect == "oracle":
        sql = _oracle_limit(sql)
    elif dialect == "mssql":
        sql = _mssql_limit(sql)
    return (sql, params, mode)


def _oracle_limit(sql):
    m = re.search(r"\s+LIMIT\s+(\d+)(?:\s+OFFSET\s+(\d+))?\s*$", sql, re.I)
    if not m:
        return sql
    n, off = int(m.group(1)), int(m.group(2) or 0)
    body = sql[:m.start()]
    if not re.match(r"\s*SELECT", body, re.I):
        return sql
    if off:
        return "SELECT * FROM (SELECT a.*, ROWNUM rn FROM (%s) a WHERE ROWNUM <= %d) WHERE rn > %d" % (
            body, off + n, off)
    return "SELECT * FROM (%s) WHERE ROWNUM <= %d" % (body, n)


def _mssql_limit(sql):
    m = re.search(r"\s+LIMIT\s+(\d+)(?:\s+OFFSET\s+(\d+))?\s*$", sql, re.I)
    if not m:
        return sql
    n, off = int(m.group(1)), int(m.group(2) or 0)
    body = sql[:m.start()].rstrip()
    if not re.match(r"\s*SELECT", body, re.I):
        return sql
    if off == 0:
        return re.sub(r"^\s*SELECT", "SELECT TOP %d" % n, body, count=1, flags=re.I)
    # 有 OFFSET：需 ORDER BY 支持 OFFSET/FETCH
    if re.search(r"\sORDER\s+BY\s+[A-Za-z0-9_.]+", body, re.I):
        return body + " OFFSET %d ROWS FETCH NEXT %d ROWS ONLY" % (off, n)
    return re.sub(r"^\s*SELECT", "SELECT TOP %d" % (off + n), body, count=1, flags=re.I)


# ---------------------------------------------------------------------------
# 统一执行入口
# ---------------------------------------------------------------------------

def _exists(conn, insert_sql, params):
    """INSERT 先查后写：解析 INSERT INTO t(c1,c2,...) VALUES(?,?,...) → SELECT 1 FROM t WHERE c1=? AND c2=? ..."""
    m = re.match(
        r"INSERT\s+(?:OR\s+IGNORE\s+)?INTO\s+([A-Za-z0-9_]+)\s*\(([^)]*)\)\s*VALUES\s*\(([^)]*)\)",
        insert_sql, re.I)
    if not m:
        return None
    table, cols, vals = m.group(1), m.group(2), m.group(3)
    col_list = [c.strip().strip('"') for c in cols.split(",")]
    val_list = [v.strip() for v in vals.split(",")]
    use = [c for c, v in zip(col_list, val_list) if v == "?"]
    if not use:
        return None
    d = dialect(conn)
    ph = ":n" if d == "oracle" else "%s"
    q = []
    for i, c in enumerate(use):
        if d == "oracle":
            q.append("%s=:%d" % (c, i + 1))
        elif d in ("mysql", "mariadb"):
            q.append("`%s`=%s" % (c, ph))
        else:
            q.append("%s=%s" % (c, ph))
    where = " AND ".join(q)
    cur = _native_cursor(conn)
    try:
        cur.execute("SELECT 1 FROM %s WHERE %s%s" % (
            table, where, " AND ROWNUM<=1" if d == "oracle" else " LIMIT 1"),
            list(params or ())[:len(use)])
        return cur.fetchone() is not None
    except Exception:
        return None


def _native_cursor(conn):
    """返回原生 cursor（非 sqlite 包装连接走 _db_native_cursor，避免自递归）"""
    nc = getattr(conn, "_db_native_cursor", None)
    return nc() if nc else conn.cursor()


def _strip_sql_comments(sql):
    """剥离 SQL 行尾 `-- ` 注释（MariaDB/MySQL 等对含行尾注释的多列 DDL 报错）。
    跟踪单引号，避免误删字符串字面量内的内容。"""
    out, in_q, i = [], False, 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if ch == "'" and not in_q:
            in_q = True; out.append(ch); i += 1; continue
        if ch == "'" and in_q:
            in_q = False; out.append(ch); i += 1; continue
        if not in_q and ch == "-" and i + 1 < n and sql[i+1] == "-" and (i + 2 >= n or sql[i+2] in (" ", "\t")):
            # 跳到行尾
            while i < n and sql[i] != "\n":
                i += 1
            continue
        out.append(ch); i += 1
    return "".join(out)


def execute(conn, sql, params=None):
    """统一执行入口（自动方言转换）。返回 cursor。"""
    d = dialect(conn)
    if d != "sqlite":
        sql = _strip_sql_comments(sql)
    # 非 SQLite 驱动不支持一次执行多条语句（如整段 CREATE TABLE DDL），拆开逐条执行
    if d != "sqlite" and sql and ";" in sql and not params:
        stmts = [s.strip() for s in split_statements(sql) if s.strip()]
        if len(stmts) > 1:
            last = None
            for st in stmts:
                last = execute(conn, st, None)
            return last
    sql, params, mode = convert_sql(d, sql, params)
    sql = _convert_placeholders(d, sql)
    if sql.lstrip().upper().startswith("CREATE TABLE"):
        sql = ddl(d, sql)
    cur = _native_cursor(conn)
    if mode == "exec":
        cur.execute(sql, params or ())
    elif mode == "ignore":
        if not _exists(conn, sql, params):
            cur.execute(sql, params or ())
    elif mode == "upsert":
        # ON CONFLICT DO UPDATE 降级（mssql/oracle）：存在则更新，否则插入
        m = re.search(r"ON\s+CONFLICT\s*\(([^)]*)\)\s*DO\s+UPDATE\s+SET\s+(.+)", sql, re.I)
        base = re.sub(r"\s+ON\s+CONFLICT\s+.*$", "", sql, flags=re.I)
        base = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", base, count=1, flags=re.I)
        if m and _exists(conn, sql, params):
            cols = [c.strip() for c in m.group(1).split(",")]
            sets = [s.strip() for s in m.group(2).split(",")]
            upd = ", ".join(s.split("=")[0].strip() + "=?" for s in sets)
            wh = " AND ".join("%s=?" % c for c in cols)
            upd_sql = "UPDATE %s SET %s WHERE %s" % (re.match(
                r"INSERT\s+INTO\s+([A-Za-z0-9_]+)", base).group(1), upd, wh)
            upd_sql = _convert_placeholders(d, upd_sql)
            cur.execute(upd_sql, list(params or ()) + list(params or ())[:len(cols)])
        else:
            cur.execute(base, params or ())
    return cur


def executemany(conn, sql, seq):
    d = dialect(conn)
    sql, _, mode = convert_sql(d, sql)
    sql = _convert_placeholders(d, sql)
    cur = _native_cursor(conn)
    if mode == "exec":
        cur.executemany(sql, seq or [])
    elif mode == "ignore":
        for p in (seq or []):
            if not _exists(conn, sql, p):
                cur.execute(sql, p)
    return cur


# ---------------------------------------------------------------------------
# 元数据与通用辅助
# ---------------------------------------------------------------------------

def list_columns(conn, table):
    d = dialect(conn)
    cur = _native_cursor(conn)
    try:
        if d == "sqlite":
            return [r[1] for r in cur.execute("PRAGMA table_info(%s)" % table).fetchall()]
        if d in ("mysql", "mariadb"):
            cur.execute("SHOW COLUMNS FROM %s" % table)
            return [r["Field"] for r in cur.fetchall()]
        if d == "postgresql":
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s", (table,))
            return [r[0] for r in cur.fetchall()]
        if d == "mssql":
            cur.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME=%s", (table,))
            return [r["COLUMN_NAME"] for r in cur.fetchall()]
        if d == "oracle":
            cur.execute("SELECT column_name FROM user_tab_columns WHERE table_name=UPPER(:1)", (table,))
            return [r[0] for r in cur.fetchall()]
    except Exception:
        return []
    return []


def set_fk(conn, on):
    d = dialect(conn)
    if d == "sqlite":
        conn.execute("PRAGMA foreign_keys=%s" % ("ON" if on else "OFF"))
    elif d in ("mysql", "mariadb"):
        conn.execute("SET FOREIGN_KEY_CHECKS=%d" % (1 if on else 0))


# ---------------------------------------------------------------------------
# 行包装：统一支持 r["name"] 与 r[1] 两种访问（兼容原 sqlite3.Row 用法）
# ---------------------------------------------------------------------------

class _Row:
    __slots__ = ("_d", "_k")
    def __init__(self, data, keys=None):
        self._d = data  # dict
        self._k = keys  # list（dict 时可为 None）
    def __getitem__(self, k):
        if isinstance(k, int):
            if self._k is not None:
                return self._d[self._k[k]]
            return list(self._d)[k]
        return self._d[k]
    def __iter__(self):
        if self._k is not None:
            for k in self._k:
                yield self._d[k]
        else:
            for k in self._d:
                yield self._d[k]
    def __len__(self):
        return len(self._k) if self._k is not None else len(self._d)
    def keys(self):
        return self._k if self._k is not None else list(self._d.keys())
    def get(self, k, default=None):
        try:
            return self[k]
        except Exception:
            return default
    def items(self):
        if self._k is not None:
            return [(k, self._d[k]) for k in self._k]
        return list(self._d.items())


class _Curs:
    """cursor 包装：fetchone/fetchall/迭代结果统一转为 _Row"""
    def __init__(self, cur, dialect):
        self._c = cur
        self._d = dialect
    def __getattr__(self, name):
        return getattr(self._c, name)
    def _keys(self):
        try:
            desc = self._c.description or ()
            return [d[0] for d in desc]
        except Exception:
            return None
    def _wrap(self, row):
        if row is None:
            return None
        k = self._keys()
        if isinstance(row, dict):
            return _Row(row, None)
        return _Row(row, k)
    def fetchone(self):
        return self._wrap(self._c.fetchone())
    def fetchall(self):
        rows = self._c.fetchall()
        k = self._keys()
        if k is None:
            k = None
        if rows and isinstance(rows[0], dict):
            return [_Row(r, None) for r in rows]
        return [_Row(r, k) for r in rows]
    def fetchmany(self, size=None):
        k = self._keys()
        return [_Row(r, None) if isinstance(r, dict) else _Row(r, k) for r in self._c.fetchmany(size)]
    def __iter__(self):
        k = self._keys()
        for r in self._c:
            yield _Row(r, None) if isinstance(r, dict) else _Row(r, k)


def wrap_conn(conn):
    """给连接挂 execute/executescript/cursor 快捷方法，业务代码 conn.execute(...) 保持可用"""
    _d = dialect(conn)
    if _d == "sqlite":
        return conn  # sqlite 原生 execute/Row 已满足全部用法

    # 保留原生方法引用，避免覆盖后内部调用再次进入包装层造成自递归
    _native_cursor = conn.cursor
    _native_execute = getattr(conn, "execute", None)
    _native_executemany = getattr(conn, "executemany", None)
    conn._db_native_cursor = _native_cursor

    def _execute(sql, params=None):
        return _Curs(execute(conn, sql, params), _d)

    def _executemany(sql, seq):
        return _Curs(executemany(conn, sql, seq), _d)

    def _executescript(script):
        cur = _Curs(_native_cursor(), _d)
        # 逐条执行（忽略字符串常量内的分号）
        for stmt in _split_statements(script):
            if stmt.strip():
                cur = _Curs(execute(conn, stmt), _d)
        return cur

    def _cursor():
        return _Curs(_native_cursor(), _d)

    conn.execute = _execute
    conn.executemany = _executemany
    conn.executescript = _executescript
    conn.cursor = _cursor
    return conn


def split_statements(script):
    """按分号切分 SQL 脚本，忽略单引号字符串内的分号"""
    out, buf, in_q = [], [], False
    for ch in script:
        if ch == "'":
            in_q = not in_q
        buf.append(ch)
        if ch == ";" and not in_q:
            out.append("".join(buf)); buf = []
    if "".join(buf).strip():
        out.append("".join(buf))
    return out


# 统一异常（兼容原 sqlite3.OperationalError 捕获点）
def _op_err():
    try:
        import pymysql
        return (sqlite3.OperationalError, pymysql.err.OperationalError)
    except Exception:
        return (sqlite3.OperationalError,)
OperationalError = _op_err()


def blob_param(data):
    """二进制参数：sqlite 之外直接传 bytes"""
    if isinstance(data, (bytes, bytearray, memoryview)):
        return bytes(data)
    return data


def is_row(obj):
    return isinstance(obj, (_Row, sqlite3.Row, dict))


def test_connect(cfg):
    """测试连接：返回 (ok, msg)"""
    try:
        conn = connect(cfg)
        conn.close()
        return (True, "连接成功")
    except Exception as e:
        return (False, str(e))


# 供 database.py 兼容的别名
def get_write_lock():
    return _sqlite_lock
