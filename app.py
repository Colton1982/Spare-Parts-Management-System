# -*- coding: utf-8 -*-
"""
备件管理系统 - 主程序（桌面直连版）
========================================
启动方式：双击 exe（或执行 python app.py）
访问方式：软件自动打开浏览器进入本机页面 http://127.0.0.1:端口
数据库：  首次启动进入初始化向导，填写内网公共盘数据库路径后所有用户共享
"""
import json
import logging
import os
import re
import threading
import time
import webbrowser
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, Response, send_file, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

import config
import database as db
import settings as _settings
import i18n as _i18n

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
# 模板修改立即生效（内网部署/迭代阶段无需重启服务即可刷新页面样式与布局）
app.config["TEMPLATES_AUTO_RELOAD"] = True

# ------------------------------------------------------------------
# 工具函数
# ------------------------------------------------------------------
def get_db():
    return db.get_conn()


def current_user():
    uid = session.get("uid")
    if not uid or not config.DB_PATH:
        return None
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE id=? AND active=1", (uid,)
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def can(role, module, action=None):
    """权限判断：数据库权限矩阵优先，未配置时按默认矩阵。
    action=None 表示模块级判断；action 指定时：
      模块级 (role,module,'') allow=1 → 拥有该模块全部操作（优先于操作级）；
      否则需操作级 (role,module,action) allow=1"""
    conn = get_db()
    try:
        row0 = conn.execute(
            "SELECT allow FROM permissions WHERE role=? AND module=? AND action=''",
            (role, module),
        ).fetchone()
        if action is not None:
            # 操作级优先：已配置则按操作级；未配置跟随模块级；模块级未配置回退默认矩阵
            row = conn.execute(
                "SELECT allow FROM permissions WHERE role=? AND module=? AND action=?",
                (role, module, action),
            ).fetchone()
            if row:
                return bool(row["allow"])
            if row0:
                return bool(row0["allow"])
            return module in config.DEFAULT_PERMS.get(role, [])
        if row0:
            return bool(row0["allow"])
        # 模块级未配置任何行：回退默认矩阵
        return module in config.DEFAULT_PERMS.get(role, [])
    finally:
        conn.close()


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("uid"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


def perm_required(module, action=None):
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                return redirect(url_for("login"))
            if not can(user["role"], module, action):
                abort(403)
            return f(*args, **kwargs)
        return wrapper
    return deco


def role_required(*roles):
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                return redirect(url_for("login"))
            if user["role"] not in roles:
                abort(403)
            return f(*args, **kwargs)
        return wrapper
    return deco


@app.context_processor
def inject_globals():
    user = current_user() if session.get("uid") else None
    _lang = _i18n.current_lang()
    return {
        "cur_user": user,
        "cur_lang": _lang,
        "ROLE_NAMES": {k: _i18n.t(v, _lang) for k, v in config.ROLE_NAMES.items()},
        "PERM_MODULES": {k: _i18n.t(v, _lang) for k, v in config.PERM_MODULES.items()},
        "PERM_ACTIONS": {m: {a: _i18n.t(al, _lang) for a, al in acts.items()} for m, acts in config.PERM_ACTIONS.items()},
        "SCREEN_MODULES": {k: _i18n.t(v, _lang) for k, v in config.SCREEN_MODULES.items()},
        "APP_PORT": config.PORT,
        "brand": get_brand(),
        "theme": get_theme(),
        "nav_style": get_nav_style(),
        "extra_fields": get_extra_fields(),
        "can": (lambda m, a=None: can(user["role"], m, a)) if user else (lambda m, a=None: False),
        "today": datetime.now().strftime("%Y-%m-%d"),
        "tr": (lambda key, **kw: _i18n.t(key, _i18n.current_lang(), **kw)),
        "tr_json": _i18n.tr_json(),
    }


DEFAULT_BRAND = {
    "logo_file": "",
    "title": "备件管理系统",
    "subtitle": "Spare Parts System",
    "logo_height": 40,        # LOGO 图片高度 px（宽度自适应）
    "title_size": 16,         # 标题字号 px
    "subtitle_size": 11,      # 副标题字号 px
    "title_color": "",        # 空=跟随侧栏文字色
    "subtitle_color": "",     # 空=默认半透明白
    "font_family": "",        # 品牌区字体（空=跟随系统）
}


def get_brand(conn=None):
    """读取品牌配置（数据库 sys_settings，管理员在系统设置页配置）"""
    brand = dict(DEFAULT_BRAND)
    if not db_configured():
        return brand
    own = conn is None
    if own:
        conn = get_db()
    try:
        raw = db.get_setting(conn, "brand")
        if raw:
            try:
                d = json.loads(raw)
                if isinstance(d, dict):
                    for k in brand:
                        if d.get(k) is not None and str(d.get(k)) != "":
                            brand[k] = d[k]
            except Exception:
                pass
    finally:
        if own:
            conn.close()
    # 数字/颜色边界校验
    try:
        brand["logo_height"] = max(12, min(int(brand["logo_height"]), 160))
    except (TypeError, ValueError):
        brand["logo_height"] = DEFAULT_BRAND["logo_height"]
    try:
        brand["title_size"] = max(10, min(int(brand["title_size"]), 36))
    except (TypeError, ValueError):
        brand["title_size"] = DEFAULT_BRAND["title_size"]
    try:
        brand["subtitle_size"] = max(8, min(int(brand["subtitle_size"]), 22))
    except (TypeError, ValueError):
        brand["subtitle_size"] = DEFAULT_BRAND["subtitle_size"]
    for k in ("title_color", "subtitle_color"):
        if brand[k] and not _is_hex_color(str(brand[k])):
            brand[k] = ""
    if not isinstance(brand.get("font_family"), str) or len(brand["font_family"]) > 80:
        brand["font_family"] = ""
    return brand


def get_theme(conn=None):
    """读取界面主题配置（管理员可自由配置色系）"""
    theme = dict(config.DEFAULT_THEME)
    if not db_configured():
        return theme
    own = conn is None
    if own:
        conn = get_db()
    try:
        raw = db.get_setting(conn, "theme")
        if raw:
            try:
                d = json.loads(raw)
                if isinstance(d, dict):
                    for k in theme:
                        if d.get(k):
                            theme[k] = d[k]
            except Exception:
                pass
    finally:
        if own:
            conn.close()
    return theme


def get_extra_fields(conn=None):
    """读取自定义表头配置（备件列表额外列），返回 [{key,label},...]"""
    if not db_configured():
        return []
    own = conn is None
    if own:
        conn = get_db()
    try:
        raw = db.get_setting(conn, "extra_fields")
        if raw:
            try:
                d = json.loads(raw)
                if isinstance(d, list):
                    out = []
                    for item in d:
                        if isinstance(item, dict) and item.get("key") and item.get("label"):
                            out.append({"key": str(item["key"])[:20], "label": str(item["label"])[:30]})
                    return out[: config.MAX_EXTRA_FIELDS]
            except Exception:
                pass
    finally:
        if own:
            conn.close()
    return []


def get_nav_style(conn=None):
    """读取左侧菜单外观配置（系统设置页可配置字号/图标大小/侧栏宽度/字体等）"""
    nav = dict(config.DEFAULT_NAV_STYLE)
    if not db_configured():
        return nav
    own = conn is None
    if own:
        conn = get_db()
    try:
        raw = db.get_setting(conn, "nav_style")
        if raw:
            try:
                d = json.loads(raw)
                if isinstance(d, dict):
                    for k in nav:
                        if d.get(k) is not None and str(d.get(k)) != "":
                            nav[k] = d[k]
            except Exception:
                pass
    finally:
        if own:
            conn.close()
    return nav


@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403, msg="您没有权限执行此操作，请联系高级管理人员配置权限。"), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, msg="页面不存在。"), 404


# ------------------------------------------------------------------
# 认证
# ------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        cs = _login_case_sensitive()
        collate = _username_collate(cs)
        conn = get_db()
        try:
            row = conn.execute(
                f"SELECT * FROM users WHERE username=?{collate} AND active=1", (username,)
            ).fetchone()
        finally:
            conn.close()
        if row and check_password_hash(row["password_hash"], password):
            _lang_keep = session.get("lang")
            session.clear()
            if _lang_keep:
                session["lang"] = _lang_keep
            session["uid"] = row["id"]
            session["role"] = row["role"]
            session["name"] = row["display_name"]
            nxt = request.args.get("next", "")
            if nxt.startswith("/") and not nxt.startswith("//"):
                return redirect(nxt)
            return redirect(url_for("dashboard"))
        flash(_i18n.t("用户名或密码错误，或账号已被停用", _i18n.current_lang()), "danger")
    # 未登录时也允许切换界面语言（写入会话，仅本机/本会话生效）
    lang = request.args.get("lang", "").strip()
    if lang in _i18n.LANGUAGES:
        session["lang"] = lang
    elif request.args.get("lang") == "" and "lang" not in session:
        session["lang"] = _i18n.current_lang()
    return render_template("login.html", ad_enabled=_ad_cfg().get("enabled") or False,
                           cur_lang=_i18n.current_lang(), LANGUAGES=_i18n.LANGUAGES)


# ------------------------------------------------------------------
# 登录用户名匹配策略：是否区分大小写（数据库 sys_settings 共享，所有电脑一致）
# 0=不区分（AD 用户输入 ZHANGSAN 也能匹配 zhangsan，默认）；1=区分（SQLite 默认行为）
# 同时作用于：普通账号登录（/login）与 AD 域登录白名单匹配（/login_ad）
# ------------------------------------------------------------------
def _login_case_sensitive(conn=None):
    """读取「用户名匹配是否区分大小写」设置；未配置时默认 0=不区分大小写"""
    if not db_configured():
        return 0
    own = conn is None
    if own:
        conn = get_db()
    try:
        raw = db.get_setting(conn, "login_case_sensitive")
        try:
            return 1 if int(raw) else 0
        except (TypeError, ValueError):
            return 0
    finally:
        if own:
            conn.close()


def _username_collate(cs):
    """根据大小写策略返回 SQL 匹配后缀：区分大小写=精确等值；不区分=COLLATE NOCASE"""
    return "" if cs else " COLLATE NOCASE"


# ------------------------------------------------------------------
# AD 域登录（公司总登录系统验证；验证通过后按用户名匹配白名单，不在则进入访客模式）
# ------------------------------------------------------------------
def _ad_cfg():
    return _settings.load().get("ad") or {}


def _ad_ldap_connect(srv, user, password, timeout, enc):
    """建立并绑定 LDAP 连接：enc=none 明文 / ldaps TLS / starttls 389 升级加密"""
    from ldap3 import Connection
    conn = Connection(srv, user=user, password=password,
                      raise_exceptions=True, receive_timeout=timeout)
    if enc == "starttls":
        conn.open()
        conn.start_tls()
        conn.bind()
    else:
        conn.bind()
    return conn


def _ad_authenticate(username, password):
    """通过 LDAP 连接公司 AD 验证账号密码。返回 (ok, errmsg)
    支持两种绑定方式（软件内配置）：
      direct  = 用户账号直接绑定（user@域名 / 域名\\user）
      search  = 服务账号搜索 + 用户 DN 再绑定（适合禁止用户直绑的域控）
    支持加密方式：明文 389 / LDAPS 636 / StartTLS（389 端口升级加密）"""
    cfg = _ad_cfg()
    if not cfg.get("enabled"):
        return False, "AD 登录未启用"
    server = (cfg.get("server") or "").strip()
    domain = (cfg.get("domain") or "").strip()
    if not server or not domain:
        return False, "AD 配置不完整，请联系管理员在「系统设置 → AD 域登录配置」填写服务器地址与域名"
    if not username or not password:
        return False, "请输入域用户名与密码"
    try:
        port = int(cfg.get("port") or 389)
        timeout = max(3, min(int(cfg.get("timeout") or 10), 60))
    except (TypeError, ValueError):
        port, timeout = 389, 10
    enc = (cfg.get("enc") or "").strip()
    if enc not in ("none", "ldaps", "starttls"):
        enc = "ldaps" if cfg.get("ssl") else "none"   # 兼容旧配置 ssl 布尔
    bind_mode = (cfg.get("bind_mode") or "direct").strip()
    nf = cfg.get("name_format") or "upn"  # upn=user@domain / ntdomain=domain\user
    # 登录账号自动识别：已含 @ 或 \ 则视为完整格式，不再重复拼接
    if nf == "upn":
        user_dn = username if "@" in username else f"{username}@{domain}"
    else:
        user_dn = username if ("\\" in username or "/" in username) else f"{domain}\\{username}"
    try:
        from ldap3 import Server, Connection
        from ldap3.core.exceptions import LDAPInvalidCredentialsResult, LDAPException
        srv = Server(server, port=port, use_ssl=(enc == "ldaps"), get_info="NO_INFO")
        if bind_mode == "search":
            # 方式二：服务账号搜索
            svc_dn = (cfg.get("svc_dn") or "").strip()
            svc_pwd = cfg.get("svc_pwd") or ""
            base_dn = (cfg.get("base_dn") or "").strip()
            attr = (cfg.get("search_attr") or "sAMAccountName").strip()
            if not svc_dn or not base_dn:
                return False, "AD 配置不完整：服务账号搜索模式需要「服务账号 DN、服务账号密码、Base DN、搜索属性」"
            try:
                conn = _ad_ldap_connect(srv, svc_dn, svc_pwd, timeout, enc)
            except LDAPInvalidCredentialsResult:
                return False, "服务账号连接 AD 失败（服务账号或密码错误，请检查系统设置）"
            try:
                import ldap3
                esc = username.replace("\\", r"\\").replace("*", r"\*") \
                              .replace("(", r"\(").replace(")", r"\)")
                conn.search(search_base=base_dn, search_filter=f"({attr}={esc})",
                            attributes=["distinguishedName"], size_limit=2)
                entries = conn.entries
                if not entries:
                    return False, f"在 AD 中未找到该账号（请检查 Base DN 与搜索属性 {attr} 是否正确）"
                user_dn = entries[0].entry_dn
                try:
                    conn.unbind()
                except Exception:
                    pass
                conn = _ad_ldap_connect(srv, user_dn, password, timeout, enc)
                try:
                    conn.unbind()
                except Exception:
                    pass
                return True, ""
            except LDAPInvalidCredentialsResult:
                return False, "域账号或密码错误"
            except LDAPException as e:
                return False, f"AD 搜索/验证失败，请检查系统设置：{str(e)[:120]}"
        # 方式一：直接绑定
        try:
            conn = _ad_ldap_connect(srv, user_dn, password, timeout, enc)
            try:
                conn.unbind()
            except Exception:
                pass
            return True, ""
        except LDAPInvalidCredentialsResult:
            return False, "域账号或密码错误"
        except LDAPException as e:
            return False, f"无法连接 AD 服务器，请检查系统设置：{str(e)[:120]}"
    except LDAPInvalidCredentialsResult:
        return False, "域账号或密码错误"
    except LDAPException as e:
        return False, f"无法连接 AD 服务器，请检查系统设置：{str(e)[:120]}"
    except Exception as e:
        return False, f"AD 验证异常：{str(e)[:120]}"


@app.route("/login_ad", methods=["POST"])
def login_ad():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    ok, err = _ad_authenticate(username, password)
    if not ok:
        flash(err, "danger")
        return redirect(url_for("login", tab="ad"))
    # AD 验证通过：按用户名查白名单（本系统 users 表）；不在则进入访客模式
    conn = get_db()
    try:
        cs = _login_case_sensitive(conn)
        collate = _username_collate(cs)
        local_name = username
        # 可配置：AD 登录账号匹配本地白名单时剥离 @域名后缀
        # （用户输 zhangsan@company.com 时，本地白名单通常存 zhangsan）
        if _ad_cfg().get("strip_upn_suffix", 1) and "@" in local_name:
            local_name = local_name.split("@", 1)[0]
        row = conn.execute(
            f"SELECT * FROM users WHERE username=?{collate} AND active=1", (local_name,)
        ).fetchone()
        guest_mode = False
        if not row:
            row = conn.execute(
                "SELECT * FROM users WHERE username='guest' AND active=1"
            ).fetchone()
            guest_mode = True
    finally:
        conn.close()
    if not row:
        flash(_i18n.t("访客账号不可用，请联系系统管理员", _i18n.current_lang()), "danger")
        return redirect(url_for("login", tab="ad"))
    _lang_keep = session.get("lang")
    session.clear()
    if _lang_keep:
        session["lang"] = _lang_keep
    session["uid"] = row["id"]
    session["role"] = row["role"]
    session["name"] = row["display_name"]
    if guest_mode:
        session["guest_ad_user"] = username
        flash(_i18n.t("AD 账号 {0} 不在白名单中，已以访客身份进入，仅可查阅备件与呆滞物料", _i18n.current_lang()).format(username), "warning")
        return redirect(url_for("parts_page"))
    flash(f"AD 登录成功，欢迎 {row['display_name']}", "success")
    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():
    _lang_keep = session.get("lang")
    session.clear()
    if _lang_keep:
        session["lang"] = _lang_keep
    return redirect(url_for("login"))


@app.route("/password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        old = request.form.get("old_pwd", "")
        new1 = request.form.get("new_pwd", "")
        new2 = request.form.get("new_pwd2", "")
        user = current_user()
        if not check_password_hash(user["password_hash"], old):
            flash(_i18n.t("原密码不正确", _i18n.current_lang()), "danger")
        elif len(new1) < 6:
            flash(_i18n.t("新密码长度至少 6 位", _i18n.current_lang()), "danger")
        elif new1 != new2:
            flash(_i18n.t("两次输入的新密码不一致", _i18n.current_lang()), "danger")
        else:
            conn = get_db()
            try:
                conn.execute(
                    "UPDATE users SET password_hash=? WHERE id=?",
                    (generate_password_hash(new1), user["id"]),
                )
                conn.commit()
            finally:
                conn.close()
            flash(_i18n.t("密码修改成功", _i18n.current_lang()), "success")
            return redirect(url_for("dashboard"))
    return render_template("password.html")


# ------------------------------------------------------------------
# 数据图表主页
# ------------------------------------------------------------------
@app.route("/")
@login_required
def index():
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
@login_required
@perm_required("dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/dashboard")
@login_required
def api_dashboard():
    """按 日/周/月 返回出入库数量与金额 + 首页统计卡片 + 库存预警
    金额为敏感内容：无「备件金额查看」权限的角色，分析视图金额强制隐藏（普通用户默认无权限）"""
    user = current_user()
    period = request.args.get("period", "day")
    conn = get_db()
    try:
        # ---- 汇总卡片 ----
        cards = _period_summary(conn, period)
        # ---- 图表序列 ----
        series = _chart_series(conn, period)
        # ---- 库存预警 ----
        alerts = _stock_alerts(conn)
        # ---- 分类占比 ----
        _lang = _i18n.current_lang()
        cats = conn.execute(
            """SELECT COALESCE(NULLIF(p.category,''),?) c, COALESCE(SUM(i.quantity*p.unit_price),0) v
               FROM parts p LEFT JOIN inventory i ON p.id=i.part_id
               WHERE p.deleted=0
               GROUP BY c ORDER BY v DESC""",
            (_i18n.t("未分类", _lang),),
        ).fetchall()
        # ---- 呆滞物料（阈值来自系统设置，默认90天）----
        stale = _stale_summary(conn, _stale_days(conn), 10)
        return jsonify({
            "cards": cards,
            "series": series,
            "alerts": alerts,
            "category": [{"name": r["c"], "value": round(r["v"], 2)} for r in cats],
            "stale": stale,
        })
    finally:
        conn.close()


# 图表风格（数据图表主页 5 种预设配色）
DASH_STYLES = {
    "tech":   {"name": "科技蓝",   "bars": ["#2563eb", "#3b82f6", "#60a5fa", "#93c5fd", "#1d4ed8", "#0ea5e9", "#38bdf8"],
               "pie": ["#2563eb", "#22c55e", "#f97316", "#8b5cf6", "#06b6d4", "#ef4444", "#eab308", "#14b8a6", "#f472b6", "#64748b"]},
    "green":  {"name": "墨绿商务", "bars": ["#047857", "#059669", "#10b981", "#34d399", "#065f46", "#14b8a6", "#0d9488"],
               "pie": ["#047857", "#059669", "#10b981", "#34d399", "#065f46", "#14b8a6", "#0d9488", "#84cc16", "#65a30d", "#4d7c0f"]},
    "gold":   {"name": "暗夜金",   "bars": ["#b45309", "#d97706", "#f59e0b", "#fbbf24", "#92400e", "#ea580c", "#fb923c"],
               "pie": ["#b45309", "#d97706", "#f59e0b", "#fbbf24", "#92400e", "#ea580c", "#fb923c", "#eab308", "#ca8a04", "#a16207"]},
    "clean":  {"name": "清新白",   "bars": ["#0284c7", "#0ea5e9", "#38bdf8", "#7dd3fc", "#0369a1", "#22d3ee", "#67e8f9"],
               "pie": ["#0284c7", "#0ea5e9", "#38bdf8", "#7dd3fc", "#0369a1", "#22d3ee", "#67e8f9", "#0891b2", "#06b6d4", "#0e7490"]},
    "orange": {"name": "活力橙",   "bars": ["#ea580c", "#f97316", "#fb923c", "#fdba74", "#c2410c", "#f59e0b", "#fbbf24"],
               "pie": ["#ea580c", "#f97316", "#fb923c", "#fdba74", "#c2410c", "#f59e0b", "#fbbf24", "#ef4444", "#f87171", "#b91c1c"]},
}
DASH_STYLE_ORDER = ["tech", "green", "gold", "clean", "orange"]


def _dash_cfg(conn=None):
    """数据图表主页配置（风格/TopN/图表类型/期间/显示金额），随数据库保存"""
    d = {"style": "tech", "top_n": 10, "chart_type": "bar", "range": "all"}
    try:
        c = conn or get_db()
        raw = db.get_setting(c, "dash_cfg")
        if raw:
            x = json.loads(raw)
            if x.get("style") in DASH_STYLES:
                d["style"] = x["style"]
            try:
                d["top_n"] = max(5, min(int(x.get("top_n") or 10), 200))
            except (TypeError, ValueError):
                pass
            if x.get("chart_type") in ("bar", "line"):
                d["chart_type"] = x["chart_type"]
            if x.get("range") in ("all", "30", "90", "year"):
                d["range"] = x["range"]
    except Exception:
        pass
    return d


def _wh_prefix(wh):
    """仓库号过滤前缀：WH-01 -> (WH-01, 'WH-01-%') 待定 -> 仅等值"""
    wh = (wh or "").strip()
    if not wh:
        return None
    if wh == "待定":
        return ("待定", None)
    return (wh, wh + "-%")


def _loc_wh(location):
    """库位文本 -> 仓库号（库位格式：仓库号-货架号-货位号-格位号，每段可能含连字符）
    如 'WH-01-R-01-S-01-B-01' -> 'WH-01'；旧格式 'WH-01' -> 'WH-01'"""
    loc = (location or "").strip()
    if not loc or loc == "待定":
        return "待定"
    parts = loc.split("-")
    if len(parts) >= 2:
        return parts[0] + "-" + parts[1]
    return parts[0] if parts else loc


def _loc_rack(location):
    """库位文本 -> 货架维度（仓库号-货架号）
    如 'WH-01-R-01-S-01-B-01' -> 'WH-01-R-01'；旧格式 'WH-01' -> 'WH-01'"""
    loc = (location or "").strip()
    if not loc or loc == "待定":
        return "待定"
    parts = loc.split("-")
    if len(parts) >= 4:
        return "-".join(parts[:4])
    if len(parts) >= 2:
        return "-".join(parts[:2])
    return parts[0] if parts else loc


def _loc_dim(location, dim):
    """按维度取库位归属：dim=wh 仓库号 / dim=rack 货架号(仓库-货架)"""
    return _loc_rack(location) if dim == "rack" else _loc_wh(location)


@app.route("/api/analysis/meta")
@login_required
def api_analysis_meta():
    """分析页筛选项：仓库列表 / 备件名称 / 备件编码"""
    conn = get_db()
    try:
        whs = {}
        for r in conn.execute("SELECT DISTINCT location FROM inventory WHERE location IS NOT NULL AND location<>''").fetchall():
            w = _loc_wh(r["location"])
            whs[w] = 1
        for r in conn.execute("SELECT DISTINCT location FROM transactions WHERE location IS NOT NULL AND location<>'' AND location<>'待定'").fetchall():
            w = _loc_wh(r["location"])
            whs[w] = 1
        names = [r["name"] for r in conn.execute(
            "SELECT DISTINCT name FROM parts WHERE name IS NOT NULL AND name<>'' AND deleted=0 ORDER BY name").fetchall()]
        codes = [r["part_code"] for r in conn.execute(
            "SELECT part_code FROM parts WHERE deleted=0 ORDER BY part_code").fetchall()]
        return jsonify({"ok": True,
                        "whs": sorted(whs.keys()),
                        "names": names,
                        "codes": codes})
    finally:
        conn.close()


@app.route("/api/analysis")
@login_required
def api_analysis():
    """库存/入库/出库 分析数据（筛选 + 统计 + 柱/线图 + 饼图 + 明细）"""
    user = current_user()
    tab = request.args.get("tab", "stock")
    wh = (request.args.get("wh") or "").strip()
    name = (request.args.get("name") or "").strip()
    code = (request.args.get("code") or "").strip()
    rng = request.args.get("range", "") or ""
    dim = (request.args.get("dim") or "wh").strip()
    if dim not in ("wh", "rack"):
        dim = "wh"
    cfg = _dash_cfg()
    if rng not in ("all", "30", "90", "year"):
        rng = cfg["range"]
    top = cfg["top_n"]
    try:
        top = max(5, min(int(request.args.get("top") or top), 200))
    except (TypeError, ValueError):
        pass
    chart_type = cfg["chart_type"]
    if request.args.get("chart") in ("bar", "line"):
        chart_type = request.args.get("chart")
    # 金额敏感：金额显示统一由「备件金额查看」权限（系统设置→权限配置）控制，
    # 无权限（普通用户默认无）→ 分析视图金额一律隐藏，不随请求参数变化
    show_amt = can(user["role"], "price")

    conn = get_db()
    try:
        if tab == "stock":
            res = _an_stock(conn, wh, name, code, top, dim, show_amt)
        elif tab in ("uline", "udevice"):
            res = _an_usage(conn, "line" if tab == "uline" else "device", rng, top, show_amt)
        else:
            res = _an_flow(conn, "in" if tab == "in" else "out", wh, name, code, rng, top, dim, show_amt)
        res["cfg"] = {"style": cfg["style"], "chart_type": chart_type,
                      "show_amount": show_amt, "top_n": top, "range": rng,
                      "dim": dim}
        return jsonify({"ok": True, **res})
    finally:
        conn.close()


def _an_stock(conn, wh, name, code, top, dim="wh", show_amt=True):
    sql = """SELECT p.id, p.part_code, p.name, p.spec, p.unit, p.qty_decimal,
                    COALESCE(p.min_stock,0) min_stock, COALESCE(p.unit_price,0) unit_price,
                    COALESCE(SUM(i.quantity),0) stock,
                    COALESCE((SELECT SUM(t.quantity) FROM transactions t WHERE t.part_id=p.id AND t.tx_type='in'),0) in_qty,
                    COALESCE((SELECT SUM(t.quantity) FROM transactions t WHERE t.part_id=p.id AND t.tx_type='out'),0) out_qty
             FROM parts p LEFT JOIN inventory i ON p.id=i.part_id
             WHERE p.deleted=0"""
    params = []
    wp = _wh_prefix(wh)
    if wp:
        if wp[1]:
            sql += " AND EXISTS(SELECT 1 FROM inventory i2 WHERE i2.part_id=p.id AND (i2.location=? OR i2.location LIKE ?))"
            params += [wp[0], wp[1]]
        else:
            sql += " AND EXISTS(SELECT 1 FROM inventory i2 WHERE i2.part_id=p.id AND i2.location=?)"
            params.append(wp[0])
    if name:
        sql += " AND p.name=?"; params.append(name)
    if code:
        sql += " AND p.part_code=?"; params.append(code)
    sql += " GROUP BY p.id ORDER BY stock DESC LIMIT ?"
    params.append(top * 3)
    rows = conn.execute(sql, params).fetchall()

    # 库位/仓库归属（按料号）
    loc_map = {}
    for r in conn.execute("SELECT part_id, location, quantity FROM inventory").fetchall():
        loc_map.setdefault(r["part_id"], []).append((r["location"], r["quantity"]))

    stats = {"cur_stock": 0.0, "safe_stock": 0.0, "part_count": 0, "stock_value": 0.0}
    bar = []
    pie = {}
    detail = []
    for r in rows:
        p = dict(r)
        stock = p["stock"] or 0
        stats["cur_stock"] += stock
        stats["safe_stock"] += p["min_stock"]
        stats["part_count"] += 1
        stats["stock_value"] += stock * p["unit_price"]
        bar.append({"name": p["part_code"], "label": f"{p['part_code']} {p['name']}", "value": round(stock, 3)})
        for loc, q in loc_map.get(p["id"], []):
            w = _loc_dim(loc, dim)
            pie[w] = round(pie.get(w, 0) + (q or 0), 3)
        locs = ", ".join(f"{l}({q})" for l, q in loc_map.get(p["id"], [])) or "待定"
        detail.append({
            "wh": ", ".join(sorted({_loc_wh(l) for l, _ in loc_map.get(p["id"], [])})) or "待定",
            "locations": locs,
            "part_code": p["part_code"], "name": p["name"], "spec": p["spec"] or "",
            "unit": p["unit"] or "", "in_qty": round(p["in_qty"] or 0, 3),
            "out_qty": round(p["out_qty"] or 0, 3), "safe": p["min_stock"],
            "stock": round(stock, 3), "diff": round(stock - p["min_stock"], 3),
        })
    bar = bar[:top]
    if not show_amt:
        stats["stock_value"] = None
    return {
        "stats": {k: (round(v, 2) if v is not None else None) for k, v in stats.items()},
        "bar": {"labels": [b["label"] for b in bar],
                "series": [{"name": _i18n.t("当前库存", _i18n.current_lang()), "data": [b["value"] for b in bar]}]},
        "pie": [{"name": k, "value": v} for k, v in sorted(pie.items(), key=lambda x: -x[1])],
        "rows": detail,
        "title": _i18n.t("各产品当前库存数", _i18n.current_lang()),
    }


def _an_flow(conn, tx, wh, name, code, rng, top, dim="wh", show_amt=True):
    now = datetime.now()
    since = None
    if rng == "30":
        since = now - timedelta(days=30)
    elif rng == "90":
        since = now - timedelta(days=90)
    elif rng == "year":
        since = now - timedelta(days=365)
    since_s = since.strftime("%Y-%m-%d %H:%M:%S") if since else None

    base = " FROM transactions t JOIN parts p ON t.part_id=p.id WHERE t.tx_type=?"
    params = [tx]
    if since_s:
        base += " AND t.created_at>=?"; params.append(since_s)
    wp = _wh_prefix(wh)
    if wp:
        if wp[1]:
            base += " AND (t.location=? OR t.location LIKE ?)"; params += [wp[0], wp[1]]
        else:
            base += " AND t.location=?"; params.append(wp[0])
    if name:
        base += " AND p.name=?"; params.append(name)
    if code:
        base += " AND p.part_code=?"; params.append(code)

    stats_row = conn.execute("SELECT COALESCE(SUM(t.quantity),0) q, COALESCE(SUM(t.amount),0) a, "
                             "COUNT(DISTINCT t.tx_no) n" + base, params).fetchone()
    stats = {"qty": round(stats_row["q"] or 0, 3), "amount": round(stats_row["a"] or 0, 2),
             "apps": stats_row["n"] or 0}

    bar_rows = conn.execute("SELECT p.part_code, p.name, SUM(t.quantity) q" + base +
                            " GROUP BY p.id ORDER BY q DESC LIMIT ?", params + [top]).fetchall()
    bar = [{"name": r["part_code"], "label": f"{r['part_code']} {r['name']}",
            "value": round(r["q"], 3)} for r in bar_rows]

    pie = {}
    for r in conn.execute("SELECT t.location, t.quantity" + base, params).fetchall():
        w = _loc_dim(r["location"], dim)
        pie[w] = round(pie.get(w, 0) + (r["quantity"] or 0), 3)

    rows = conn.execute(
        "SELECT t.tx_no, t.part_id, p.part_code, p.name, t.location, t.quantity, t.amount, "
        "t.created_at, COALESCE(u1.display_name,'') applicant, COALESCE(u2.display_name,'') operator"
        + base.replace("JOIN parts p ON t.part_id=p.id",
                       "JOIN parts p ON t.part_id=p.id "
                       "LEFT JOIN users u1 ON t.applicant_id=u1.id "
                       "LEFT JOIN users u2 ON t.operator_id=u2.id") +
        " ORDER BY t.id DESC LIMIT 500", params).fetchall()
    detail = [{"tx_no": r["tx_no"], "part_code": r["part_code"], "name": r["name"],
               "location": r["location"] or "待定", "quantity": round(r["quantity"], 3),
               "amount": (round(r["amount"] or 0, 2) if show_amt else None),
               "created_at": r["created_at"],
               "applicant": r["applicant"], "operator": r["operator"]} for r in rows]
    if not show_amt:
        stats["amount"] = None

    return {
        "stats": stats,
        "bar": {"labels": [b["label"] for b in bar],
                "series": [{"name": _i18n.t("出库数量" if tx == "out" else "入库数量", _i18n.current_lang()),
                            "data": [b["value"] for b in bar]}]},
        "pie": [{"name": k, "value": v} for k, v in sorted(pie.items(), key=lambda x: -x[1])],
        "rows": detail,
        "title": _i18n.t("各产品出库数量" if tx == "out" else "各产品入库数量", _i18n.current_lang()),
    }


def _an_usage(conn, dim, rng, top, show_amt):
    """按线体/设备统计领用（出库）数量与金额
    dim: 'line' 线体 / 'device' 设备"""
    now = datetime.now()
    since = None
    if rng == "30":
        since = now - timedelta(days=30)
    elif rng == "90":
        since = now - timedelta(days=90)
    elif rng == "year":
        since = now - timedelta(days=365)
    since_s = since.strftime("%Y-%m-%d %H:%M:%S") if since else None
    col = "line_name" if dim == "line" else "device_name"
    label = "线体" if dim == "line" else "设备"

    where = "tx_type='out'"
    params = []
    if since_s:
        where += " AND created_at>=?"
        params.append(since_s)

    stats_row = conn.execute(
        "SELECT COALESCE(SUM(quantity),0) q, COALESCE(SUM(amount),0) a, COUNT(DISTINCT tx_no) n"
        " FROM transactions WHERE " + where, params).fetchone()
    stats = {"qty": round(stats_row["q"] or 0, 3), "amount": round(stats_row["a"] or 0, 2),
             "apps": stats_row["n"] or 0}

    rows = conn.execute(
        "SELECT COALESCE(NULLIF(%s,''),'未分配') d, SUM(quantity) q, SUM(amount) a"
        " FROM transactions WHERE %s GROUP BY d ORDER BY q DESC LIMIT ?" % (col, where),
        params + [top]).fetchall()
    items = [{"name": r["d"], "qty": round(r["q"], 3), "amount": round(r["a"] or 0, 2)} for r in rows]

    title = "各%s领用数量" % label
    # 金额敏感：无查看金额权限时，金额图与明细金额一律不返回
    amt = None
    if show_amt:
        amt = {"labels": [i["name"] for i in items],
               "series": [{"name": "领用金额", "data": [i["amount"] for i in items]}]}
    return {
        "stats": {"qty": stats["qty"], "apps": stats["apps"],
                  "amount": stats["amount"] if show_amt else None},
        "bar": {"labels": [i["name"] for i in items],
                "series": [{"name": "领用数量", "data": [i["qty"] for i in items]}]},
        "amt": amt,
        "rows": [{"name": i["name"], "qty": i["qty"],
                  "amount": i["amount"] if show_amt else None} for i in items],
        "title": title,
        "dim_label": label,
    }


@app.route("/api/analysis/cfg", methods=["POST"])
@login_required
def api_analysis_cfg():
    """保存数据图表主页配置（风格/TopN/图表类型/期间/显示金额）"""
    d = _dash_cfg()
    f = request.form
    if f.get("style") in DASH_STYLES:
        d["style"] = f["style"]
    try:
        d["top_n"] = max(5, min(int(f.get("top_n") or d["top_n"]), 200))
    except (TypeError, ValueError):
        pass
    if f.get("chart_type") in ("bar", "line"):
        d["chart_type"] = f["chart_type"]
    if f.get("range") in ("all", "30", "90", "year"):
        d["range"] = f["range"]
    conn = get_db()
    try:
        db.set_setting(conn, "dash_cfg", json.dumps(d, ensure_ascii=False))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True, "cfg": d})


@app.route("/api/analysis/export")
@login_required
def api_analysis_export():
    """数据图表主页：按当前筛选导出 Excel（统计 + 明细，纯标准库生成）"""
    user = current_user()
    tab = request.args.get("tab", "stock")
    wh = (request.args.get("wh") or "").strip()
    name = (request.args.get("name") or "").strip()
    code = (request.args.get("code") or "").strip()
    rng = request.args.get("range", "") or ""
    dim = (request.args.get("dim") or "wh").strip()
    if dim not in ("wh", "rack"):
        dim = "wh"
    cfg = _dash_cfg()
    if rng not in ("all", "30", "90", "year"):
        rng = cfg["range"]
    top = cfg["top_n"]
    try:
        top = max(5, min(int(request.args.get("top") or top), 200))
    except (TypeError, ValueError):
        pass
    show_amt = can(user["role"], "price")

    conn = get_db()
    try:
        if tab == "stock":
            res = _an_stock(conn, wh, name, code, top, dim, show_amt)
            stat_rows = [
                ["当前库存数(件)", res["stats"]["cur_stock"]],
                ["安全库存数下限合计(件)", res["stats"]["safe_stock"]],
                ["库存料号数(种)", res["stats"]["part_count"]],
                ["库存金额(元)", res["stats"]["stock_value"] if show_amt else "（无查看金额权限）"],
            ]
            headers = ["仓库", "库位明细", "备件编码", "备件名称", "规格型号", "单位",
                       "入库数量", "领用数量", "安全库存", "当前库存", "与安全库存差值"]
            detail = [[r["wh"], r["locations"], r["part_code"], r["name"], r["spec"],
                       r["unit"], r["in_qty"], r["out_qty"], r["safe"], r["stock"], r["diff"]]
                      for r in res["rows"]]
        elif tab in ("uline", "udevice"):
            res = _an_usage(conn, "line" if tab == "uline" else "device", rng, top, show_amt)
            label = "线体" if tab == "uline" else "设备"
            stat_rows = [
                ["领用数量(件)", res["stats"]["qty"]],
                ["领用金额(元)", res["stats"]["amount"] if show_amt else "（无查看金额权限）"],
                ["领用单据数(笔)", res["stats"]["apps"]],
            ]
            headers = [label, "领用数量", "领用金额(元)"] if show_amt else [label, "领用数量"]
            detail = [[r["name"], r["qty"]] + ([r["amount"]] if show_amt else []) for r in res["rows"]]
        else:
            res = _an_flow(conn, "in" if tab == "in" else "out", wh, name, code, rng, top, dim, show_amt)
            t2 = "入库" if tab == "in" else "出库"
            stat_rows = [
                [t2 + "数量(件)", res["stats"]["qty"]],
                [t2 + "金额(元)", res["stats"]["amount"] if show_amt else "（无查看金额权限）"],
                [t2 + "单据数(笔)", res["stats"]["apps"]],
            ]
            headers = ["时间", "单号", "备件编码", "备件名称", "库位", "数量",
                       "金额(元)", "申请人", "执行人"] if show_amt else                       ["时间", "单号", "备件编码", "备件名称", "库位", "数量", "申请人", "执行人"]
            detail = [[r["created_at"], r["tx_no"], r["part_code"], r["name"], r["location"],
                       r["quantity"]] + ([r["amount"]] if show_amt else []) +
                      [r["applicant"] or "-", r["operator"] or "-"] for r in res["rows"]]
        # 组装：统计摘要 + 空行 + 明细表
        out_rows = stat_rows + [[]] + [headers] + detail
        buf = _export_xlsx(["指标/列", "数值"], out_rows, "图表数据导出")
        from io import BytesIO
        bio = BytesIO(buf.getvalue())
        bio.seek(0)
        fname = "备件图表数据_%s_%s.xlsx" % (tab, datetime.now().strftime("%Y%m%d_%H%M"))
        return send_file(bio, as_attachment=True, download_name=fname,
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    finally:
        conn.close()


# ------------------------------------------------------------------
# 备份恢复（申请 + 审批流）
#   发起：仓库管理人员 / 最高用户(admin)；  审批：部门经理 或 最高用户
#   最高用户发起时可选择由自己审批，或选择任意经理以上人员审批
#   执行恢复：仓库管理人员 / 最高用户
# ------------------------------------------------------------------
def _restore_roles():
    return ("admin", "warehouse"), ("admin", "manager"), ("admin", "warehouse")


@app.route("/restore")
@login_required
def restore_page():
    user = current_user()
    if user["role"] not in ("admin", "warehouse", "manager"):
        abort(403)
    conn = get_db()
    try:
        backups = _list_backups()
        my_rows = conn.execute(
            """SELECT r.*, COALESCE(u1.display_name,'') applicant, COALESCE(u2.display_name,'') approver
               FROM restore_apps r
               LEFT JOIN users u1 ON r.applicant_id=u1.id
               LEFT JOIN users u2 ON r.approver_id=u2.id
               WHERE r.applicant_id=? ORDER BY r.id DESC""",
            (user["id"],)).fetchall()
        my_apps = [dict(r) for r in my_rows]
        if user["role"] == "admin":
            todo_rows = conn.execute(
                """SELECT r.*, COALESCE(u1.display_name,'') applicant
                   FROM restore_apps r LEFT JOIN users u1 ON r.applicant_id=u1.id
                   WHERE r.status='pending' ORDER BY r.id DESC""").fetchall()
        else:
            todo_rows = conn.execute(
                """SELECT r.*, COALESCE(u1.display_name,'') applicant
                   FROM restore_apps r LEFT JOIN users u1 ON r.applicant_id=u1.id
                   WHERE r.status='pending' AND r.assigned_approver_id=?
                   ORDER BY r.id DESC""", (user["id"],)).fetchall()
        todo = [dict(r) for r in todo_rows]
        # 最高用户发起时可选的审批人（自己 + 经理以上）
        approvers = []
        if user["role"] == "admin":
            approvers = conn.execute(
                """SELECT id, display_name, role, department FROM users
                   WHERE active=1 AND role IN ('admin','manager') ORDER BY role, department, display_name""").fetchall()
            approvers = [dict(x) for x in approvers]
        all_rows = conn.execute(
            """SELECT r.*, COALESCE(u1.display_name,'') applicant, COALESCE(u2.display_name,'') approver
               FROM restore_apps r
               LEFT JOIN users u1 ON r.applicant_id=u1.id
               LEFT JOIN users u2 ON r.approver_id=u2.id
               ORDER BY r.id DESC LIMIT 100""").fetchall()
        all_apps = [dict(r) for r in all_rows]
        return render_template("restore.html", backups=backups, my_apps=my_apps,
                               todo=todo, approvers=approvers, all_apps=all_apps,
                               pre_backup=request.args.get("backup", ""),
                               backup=_backup_cfg(conn))
    finally:
        conn.close()


def _backup_file_valid(name, bdir):
    """验证备份文件真实存在（防伪造路径）"""
    if not name or ".." in name or "/" in name or "\\" in name:
        return False
    if bdir and not os.path.isdir(bdir):
        return False
    fp = os.path.join(bdir or "", name)
    return os.path.isfile(fp) and os.path.basename(fp) == name


@app.route("/restore/apply", methods=["POST"])
@login_required
def restore_apply():
    user = current_user()
    if user["role"] not in ("admin", "warehouse"):
        abort(403)
    name = (request.form.get("backup_name") or "").strip()
    bdir = (request.form.get("backup_dir") or "").strip()
    if not _backup_file_valid(name, bdir):
        flash(_i18n.t("备份文件无效或不存在，请从列表中选择", _i18n.current_lang()), "danger")
        return redirect(url_for("restore_page"))
    fp = os.path.join(bdir, name)
    conn = get_db()
    try:
        # 指定审批人
        assigned = None
        if user["role"] == "admin":
            av = (request.form.get("approver_id") or "").strip()
            if av:
                row = conn.execute("SELECT id, role FROM users WHERE id=? AND active=1", (av,)).fetchone()
                if row and row["role"] in ("admin", "manager"):
                    assigned = row["id"]
            if not assigned:
                flash(_i18n.t("请选择审批人（你自己或经理以上人员）", _i18n.current_lang()), "danger")
                return redirect(url_for("restore_page"))
        else:
            # 仓管员：自动指派本部门经理；无经理则由最高用户(admin)审批
            mgr = _dept_manager(conn, dict(user))
            if mgr:
                assigned = mgr["id"]
            else:
                top = conn.execute("SELECT id FROM users WHERE role='admin' AND active=1 ORDER BY id LIMIT 1").fetchone()
                assigned = top["id"] if top else None
            if not assigned:
                flash(_i18n.t("未找到可审批的经理/最高用户，请联系系统管理员配置", _i18n.current_lang()), "danger")
                return redirect(url_for("restore_page"))
        app_no = db.gen_no("RST", conn, "restore_apps", "app_no")
        size = os.path.getsize(fp) if os.path.isfile(fp) else 0
        conn.execute(
            """INSERT INTO restore_apps(app_no, backup_name, backup_dir, backup_size, applicant_id,
               status, assigned_approver_id, created_at) VALUES(?,?,?,?,?,?,?,?)""",
            (app_no, name, bdir, size, user["id"], "pending", assigned, db.now_str()))
        conn.commit()
        flash(_i18n.t("恢复申请 {0} 已提交，等待审批", _i18n.current_lang()).format(app_no), "success")
    finally:
        conn.close()
    return redirect(url_for("restore_page"))


@app.route("/restore/<int:rid>/approve", methods=["POST"])
@login_required
def restore_approve(rid):
    user = current_user()
    if user["role"] not in ("admin", "manager"):
        abort(403)
    conn = get_db()
    try:
        r = conn.execute("SELECT * FROM restore_apps WHERE id=?", (rid,)).fetchone()
        if not r or r["status"] != "pending":
            flash(_i18n.t("申请不存在或已处理", _i18n.current_lang()), "danger"); return redirect(url_for("restore_page"))
        if user["role"] != "admin" and r["assigned_approver_id"] != user["id"]:
            abort(403)
        conn.execute(
            """UPDATE restore_apps SET status='approved', approver_id=?, approval_note=?,
               processed_at=? WHERE id=?""",
            (user["id"], (request.form.get("note") or "").strip()[:200], db.now_str(), rid))
        conn.commit()
        flash(f"已通过恢复申请 {r['app_no']}，发起人可执行恢复", "success")
    finally:
        conn.close()
    return redirect(url_for("restore_page"))


@app.route("/restore/<int:rid>/reject", methods=["POST"])
@login_required
def restore_reject(rid):
    user = current_user()
    if user["role"] not in ("admin", "manager"):
        abort(403)
    conn = get_db()
    try:
        r = conn.execute("SELECT * FROM restore_apps WHERE id=?", (rid,)).fetchone()
        if not r or r["status"] != "pending":
            flash(_i18n.t("申请不存在或已处理", _i18n.current_lang()), "danger"); return redirect(url_for("restore_page"))
        if user["role"] != "admin" and r["assigned_approver_id"] != user["id"]:
            abort(403)
        conn.execute(
            """UPDATE restore_apps SET status='rejected', approver_id=?, approval_note=?,
               processed_at=? WHERE id=?""",
            (user["id"], (request.form.get("note") or "驳回").strip()[:200], db.now_str(), rid))
        conn.commit()
        flash(f"已驳回恢复申请 {r['app_no']}", "warning")
    finally:
        conn.close()
    return redirect(url_for("restore_page"))


@app.route("/restore/<int:rid>/cancel", methods=["POST"])
@login_required
def restore_cancel(rid):
    user = current_user()
    conn = get_db()
    try:
        r = conn.execute("SELECT * FROM restore_apps WHERE id=?", (rid,)).fetchone()
        if not r or r["status"] != "pending":
            flash(_i18n.t("申请不存在或已处理", _i18n.current_lang()), "danger"); return redirect(url_for("restore_page"))
        if r["applicant_id"] != user["id"]:
            abort(403)
        conn.execute("UPDATE restore_apps SET status='canceled', processed_at=? WHERE id=?", (db.now_str(), rid))
        conn.commit()
        flash(f"已撤销恢复申请 {r['app_no']}", "success")
    finally:
        conn.close()
    return redirect(url_for("restore_page"))


def _restart_now():
    """拉起新进程并退出当前进程（恢复/部署后生效）"""
    try:
        import subprocess, sys as _s
        subprocess.Popen([_s.executable, os.path.abspath(__file__)],
                         cwd=os.path.dirname(os.path.abspath(__file__)))
    except Exception as e:
        log.warning("自动重启失败：%s（请手动重启软件）", e)
        return
    os._exit(0)


@app.route("/restore/<int:rid>/execute", methods=["POST"])
@login_required
def restore_execute(rid):
    user = current_user()
    if user["role"] not in ("admin", "warehouse"):
        abort(403)
    conn = get_db()
    try:
        r = conn.execute("SELECT * FROM restore_apps WHERE id=?", (rid,)).fetchone()
        if not r or r["status"] != "approved":
            flash(_i18n.t("申请不存在或未获审批，不能执行恢复", _i18n.current_lang()), "danger"); return redirect(url_for("restore_page"))
        if not _backup_file_valid(r["backup_name"], r["backup_dir"]):
            flash(_i18n.t("备份文件已不存在（可能已被清理），无法恢复", _i18n.current_lang()), "danger"); return redirect(url_for("restore_page"))
        src = config.DB_PATH
        if not src or not os.path.isfile(src):
            flash(_i18n.t("当前数据库文件不存在，无法执行恢复", _i18n.current_lang()), "danger"); return redirect(url_for("restore_page"))
        # 1) 恢复前自动备份当前库（安全兜底）
        cfg = _backup_cfg(conn)
        bdir = _backup_target_dir(cfg)
        try:
            os.makedirs(bdir, exist_ok=True)
        except OSError:
            bdir = os.path.dirname(src)
        pre = os.path.join(bdir, os.path.splitext(os.path.basename(src))[0] +
                          "_prerestore_" + datetime.now().strftime("%Y%m%d%H%M%S") + ".db")
        try:
            import shutil
            shutil.copy2(src, pre)
        except OSError as e:
            flash(_i18n.t("恢复前自动备份失败：{0}（已中止恢复）", _i18n.current_lang()).format(e), "danger"); return redirect(url_for("restore_page"))
        # 2) 关闭当前连接后用备份覆盖数据库
        try:
            conn.close()
        except Exception:
            pass
        bfile = os.path.join(r["backup_dir"], r["backup_name"])
        try:
            import shutil as _sh
            _sh.copy2(bfile, src)   # 复制覆盖（保留原备份文件，可重复使用）
        except OSError as e:
            flash(_i18n.t("覆盖数据库失败：{0}（恢复未完成）", _i18n.current_lang()).format(e), "danger"); return redirect(url_for("restore_page"))
        # 3) 把本次恢复申请写回恢复后的库（保留审批轨迹），标记完成
        conn2 = get_db()
        try:
            conn2.execute(
                """INSERT INTO restore_apps(id, app_no, backup_name, backup_dir, backup_size,
                   applicant_id, status, assigned_approver_id, approver_id, approval_note,
                   created_at, processed_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (r["id"], r["app_no"], r["backup_name"], r["backup_dir"], r["backup_size"],
                 r["applicant_id"], "completed", r["assigned_approver_id"], r["approver_id"],
                 r["approval_note"] or "", r["created_at"], db.now_str()))
            conn2.commit()
        finally:
            conn2.close()
        flash(f"数据库已从备份 {r['backup_name']} 恢复（恢复前库已另存，系统正在自动重启…）", "success")
    finally:
        try:
            conn.close()
        except Exception:
            pass
    import threading as _th
    _th.Timer(1.5, _restart_now).start()
    return redirect(url_for("restore_page"))


# 大屏/图表数据轻量缓存：20 秒内重复请求直接复用，显著加快大屏打开与刷新
_SCREEN_DATA_CACHE = {}
_SCREEN_CACHE_TTL = 20


def _screen_cache_get(key):
    hit = _SCREEN_DATA_CACHE.get(key)
    if hit and time.time() - hit[0] < _SCREEN_CACHE_TTL:
        return hit[1]
    return None


def _screen_cache_set(key, data):
    _SCREEN_DATA_CACHE[key] = (time.time(), data)


def _period_summary(conn, period):
    """按日/周/月统计当期与上一期 出入库数量、金额（20 秒缓存）"""
    ck = ("period", period)
    hit = _screen_cache_get(ck)
    if hit is not None:
        return hit
    now = datetime.now()
    if period == "day":
        cur_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        prev_start = cur_start - timedelta(days=1)
        prev_end = cur_start
    elif period == "week":
        cur_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        prev_start = cur_start - timedelta(days=7)
        prev_end = cur_start
    else:  # month
        cur_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        prev_start = (cur_start - timedelta(days=1)).replace(day=1)
        prev_end = cur_start
    cur_end = now

    def _stat(s, e):
        rows = conn.execute(
            """SELECT tx_type, COALESCE(SUM(quantity),0) q, COALESCE(SUM(amount),0) a
               FROM transactions
               WHERE created_at>=? AND created_at<? AND tx_type IN ('in','out')
               GROUP BY tx_type""",
            (s.strftime("%Y-%m-%d %H:%M:%S"), e.strftime("%Y-%m-%d %H:%M:%S")),
        ).fetchall()
        d = {"in": {"qty": 0, "amt": 0}, "out": {"qty": 0, "amt": 0}}
        for r in rows:
            if r["tx_type"] in d:
                d[r["tx_type"]] = {"qty": r["q"], "amt": round(r["a"], 2)}
        return d

    cur, prev = _stat(cur_start, cur_end), _stat(prev_start, prev_end)
    cards = {
        "period": period,
        "label": {"day": "今日", "week": "本周", "month": "本月"}[period],
        "in_qty": cur["in"]["qty"], "in_amt": cur["in"]["amt"],
        "out_qty": cur["out"]["qty"], "out_amt": cur["out"]["amt"],
        "prev": {
            "in_qty": prev["in"]["qty"], "in_amt": prev["in"]["amt"],
            "out_qty": prev["out"]["qty"], "out_amt": prev["out"]["amt"],
        },
    }
    _screen_cache_set(ck, cards)
    return cards


def _chart_series(conn, period, trend=None):
    """生成折线/柱状图数据：日→近N天(默认14)，周→近N周(默认8)，月→近N月(默认6)
    trend: dict {day, week, month} 各周期的回溯长度（来自大屏配置）；20 秒缓存"""
    if not trend:
        trend = {}
    tkey = "|".join(str(trend.get(k, "")) for k in ("day", "week", "month"))
    ck = ("series", period, tkey)
    hit = _screen_cache_get(ck)
    if hit is not None:
        return hit
    now = datetime.now()
    labels, in_qty, out_qty, in_amt, out_amt = [], [], [], [], []
    if period == "day":
        n = max(2, min(int(trend.get("day", 14)), 90))
        start = (now - timedelta(days=n - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        rows = conn.execute(
            """SELECT substr(created_at,1,10) d, tx_type, COALESCE(SUM(quantity),0) q,
                      COALESCE(SUM(amount),0) a
               FROM transactions
               WHERE created_at>=? AND created_at<? AND tx_type IN ('in','out')
               GROUP BY d, tx_type""",
            (start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")),
        ).fetchall()
        daymap = {}
        for r in rows:
            daymap.setdefault(r["d"], {}).setdefault(r["tx_type"],
                     {"q": r["q"], "a": r["a"]})
        for i in range(n - 1, -1, -1):
            d = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            labels.append(d[5:])
            m = daymap.get(d, {})
            in_qty.append(m.get("in", {}).get("q", 0))
            out_qty.append(m.get("out", {}).get("q", 0))
            in_amt.append(round(m.get("in", {}).get("a", 0), 2))
            out_amt.append(round(m.get("out", {}).get("a", 0), 2))
    elif period == "week":
        n = max(2, min(int(trend.get("week", 8)), 52))
        cur_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        start = cur_start - timedelta(weeks=n - 1)
        end = cur_start + timedelta(weeks=1)
        rows = conn.execute(
            """SELECT date(created_at) d, tx_type, COALESCE(SUM(quantity),0) q,
                      COALESCE(SUM(amount),0) a
               FROM transactions
               WHERE created_at>=? AND created_at<? AND tx_type IN ('in','out')
               GROUP BY d, tx_type""",
            (start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")),
        ).fetchall()
        wkmap = {}
        for r in rows:
            dd = datetime.strptime(r["d"], "%Y-%m-%d")
            wk = (dd - timedelta(days=dd.weekday())).strftime("%Y-%m-%d")
            wkmap.setdefault(wk, {}).setdefault(r["tx_type"],
                     {"q": r["q"], "a": r["a"]})
        for i in range(n - 1, -1, -1):
            s = cur_start - timedelta(weeks=i)
            labels.append("第%d周" % s.isocalendar()[1])
            m = wkmap.get(s.strftime("%Y-%m-%d"), {})
            in_qty.append(m.get("in", {}).get("q", 0))
            out_qty.append(m.get("out", {}).get("q", 0))
            in_amt.append(round(m.get("in", {}).get("a", 0), 2))
            out_amt.append(round(m.get("out", {}).get("a", 0), 2))
    else:  # month
        n = max(2, min(int(trend.get("month", 6)), 36))
        cur_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start = (cur_start - timedelta(days=1)).replace(day=1)
        start = (start - timedelta(days=(n - 1) * 31)).replace(day=1)
        end = (cur_start.replace(month=cur_start.month % 12 + 1, day=1)
               if cur_start.month < 12 else cur_start.replace(year=cur_start.year + 1, month=1, day=1))
        rows = conn.execute(
            """SELECT substr(created_at,1,7) m, tx_type, COALESCE(SUM(quantity),0) q,
                      COALESCE(SUM(amount),0) a
               FROM transactions
               WHERE created_at>=? AND created_at<? AND tx_type IN ('in','out')
               GROUP BY m, tx_type""",
            (start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")),
        ).fetchall()
        mmon = {}
        for r in rows:
            mmon.setdefault(r["m"], {}).setdefault(r["tx_type"],
                     {"q": r["q"], "a": r["a"]})
        for i in range(n - 1, -1, -1):
            s = (cur_start - timedelta(days=1)).replace(day=1) - timedelta(days=i * 31)
            s = s.replace(day=1)
            labels.append(s.strftime("%Y-%m"))
            m = mmon.get(s.strftime("%Y-%m"), {})
            in_qty.append(m.get("in", {}).get("q", 0))
            out_qty.append(m.get("out", {}).get("q", 0))
            in_amt.append(round(m.get("in", {}).get("a", 0), 2))
            out_amt.append(round(m.get("out", {}).get("a", 0), 2))
    out = {
        "labels": labels,
        "in_qty": in_qty, "out_qty": out_qty,
        "in_amt": in_amt, "out_amt": out_amt,
    }
    _screen_cache_set(ck, out)
    return out


def _append_stat(conn, s, e, iq, oq, ia, oa):
    rows = conn.execute(
        """SELECT tx_type, COALESCE(SUM(quantity),0) q, COALESCE(SUM(amount),0) a
           FROM transactions
           WHERE created_at>=? AND created_at<? AND tx_type IN ('in','out')
           GROUP BY tx_type""",
        (s.strftime("%Y-%m-%d %H:%M:%S"), e.strftime("%Y-%m-%d %H:%M:%S")),
    ).fetchall()
    d = {"in": [0, 0.0], "out": [0, 0.0]}
    for r in rows:
        if r["tx_type"] in d:
            d[r["tx_type"]] = [r["q"], round(r["a"], 2)]
    iq.append(d["in"][0]); oq.append(d["out"][0])
    ia.append(d["in"][1]); oa.append(d["out"][1])


def _stock_alerts(conn):
    rows = conn.execute(
        """SELECT p.id, p.part_code, p.name, p.category, p.min_stock, p.max_stock,
                  COALESCE(SUM(i.quantity),0) stock
           FROM parts p LEFT JOIN inventory i ON p.id=i.part_id
           WHERE p.deleted=0
           GROUP BY p.id"""
    ).fetchall()
    low, high = [], []
    for r in rows:
        if r["stock"] < r["min_stock"]:
            low.append({"id": r["id"], "code": r["part_code"], "name": r["name"],
                        "category": r["category"], "stock": r["stock"],
                        "limit": r["min_stock"]})
        elif r["max_stock"] and r["stock"] > r["max_stock"]:
            high.append({"id": r["id"], "code": r["part_code"], "name": r["name"],
                         "category": r["category"], "stock": r["stock"],
                         "limit": r["max_stock"]})
    return {"low": low, "high": high}


SCREEN_STYLES = {
    "tech-blue": {"name": "科技蓝", "light": False, "vars": {
        "sbg": "#0b1120", "sbg2": "#111c33", "head": "#111827", "head2": "#1e3a8a",
        "card": "#111a2e", "cardb": "#1e2a3d", "label": "#7d8aa0", "num": "#38bdf8",
        "title": "#e2e8f0", "text": "#e5e7eb", "sub": "#94a3b8", "accent": "#fbbf24",
        "alert_low": "#f87171", "alert_high": "#fb923c"}},
    "midnight-gold": {"name": "暗夜金", "light": False, "vars": {
        "sbg": "#0e0f12", "sbg2": "#191b21", "head": "#13151b", "head2": "#40331f",
        "card": "#171921", "cardb": "#282c36", "label": "#8d97a8", "num": "#d8ad55",
        "title": "#f3edda", "text": "#e8e9ed", "sub": "#9ca4b3", "accent": "#e8c766",
        "alert_low": "#f87171", "alert_high": "#fb923c"}},
    "tech-cyan": {"name": "青霓虹", "light": False, "vars": {
        "sbg": "#0a1219", "sbg2": "#102333", "head": "#0d1a26", "head2": "#17445d",
        "card": "#0f1f2c", "cardb": "#1b3747", "label": "#6f94a8", "num": "#3acfe9",
        "title": "#d8f1f7", "text": "#dde8ee", "sub": "#88b2c4", "accent": "#5eead4",
        "alert_low": "#f87171", "alert_high": "#fb923c"}},
    "nebula-purple": {"name": "星云紫", "light": False, "vars": {
        "sbg": "#0c0e1c", "sbg2": "#151a33", "head": "#111528", "head2": "#232a52",
        "card": "#151931", "cardb": "#252c50", "label": "#8894bd", "num": "#94a3f8",
        "title": "#e7eaf9", "text": "#dee1f0", "sub": "#9da6cc", "accent": "#c48ff0",
        "alert_low": "#f87171", "alert_high": "#fb923c"}},
    "green-data": {"name": "数据绿", "light": False, "vars": {
        "sbg": "#0b1311", "sbg2": "#13231c", "head": "#0f1b16", "head2": "#1d4a36",
        "card": "#12211a", "cardb": "#213629", "label": "#6f9c86", "num": "#3fd6a2",
        "title": "#daf4e9", "text": "#ddeae4", "sub": "#85b2a1", "accent": "#f0c14e",
        "alert_low": "#f87171", "alert_high": "#fb923c"}},
    "light-clean": {"name": "浅色商务", "light": True, "vars": {
        "sbg": "#f4f6f9", "sbg2": "#e3e9f0", "head": "#1e293b", "head2": "#334155",
        "card": "#ffffff", "cardb": "#dde3ec", "label": "#64748b", "num": "#2563eb",
        "title": "#1f2937", "text": "#1f2937", "sub": "#94a3b8", "accent": "#d97706",
        "alert_low": "#dc2626", "alert_high": "#ea580c"}},
}


def _screen_style_css(cfg):
    """根据大屏配置生成 body 内联 CSS 变量字符串与深浅标志"""
    name = cfg.get("style") or "tech-blue"
    st = SCREEN_STYLES.get(name) or SCREEN_STYLES["tech-blue"]
    varset = dict(st["vars"])
    if name == "custom":
        cu = cfg.get("style_custom") or {}
        for k in varset:
            v = str(cu.get(k) or "").strip()
            if _is_hex_color(v):
                varset[k] = v
    css = ";".join(f"--{k}:{v}" for k, v in varset.items())
    return css, bool(st["light"])


# ------------------------------------------------------------------
# 大屏展示（电视/会议室公共大屏，无需登录）
# ------------------------------------------------------------------
def _sanitize_layout(raw):
    """校验并规整大屏卡片布局（12 列 x 10 行网格）。
    raw: {"mode": "classic"|"custom", "cards": {key: {"x":..,"y":..,"w":..,"h":..}}}
    预设模式下卡片强制取该预设的完整布局；custom 模式取提交值（越界自动收敛）。"""
    try:
        mode = str(raw.get("mode") or "classic").strip()
    except Exception:
        mode = "classic"
    if mode not in config.SCREEN_LAYOUTS and mode != "custom":
        mode = "classic"
    cards = {}
    noprice = None
    if mode in config.SCREEN_LAYOUTS:
        cards = {k: {"x": int(v[0]), "y": int(v[1]), "w": int(v[2]), "h": int(v[3])}
                 for k, v in config.SCREEN_LAYOUTS[mode]["cards"].items()}
        np_ = config.SCREEN_LAYOUTS[mode].get("noprice")
        if np_:
            noprice = {k: {"x": int(v[0]), "y": int(v[1]), "w": int(v[2]), "h": int(v[3])}
                       for k, v in np_.items()}
    elif isinstance(raw.get("cards"), dict):
        for k, v in raw["cards"].items():
            if k not in config.SCREEN_CARDS or not isinstance(v, dict):
                continue
            try:
                x = max(0, min(int(v.get("x", 0)), 11))
                y = max(0, min(int(v.get("y", 0)), 9))
                w = max(1, min(int(v.get("w", 1)), 12 - x))
                h = max(1, min(int(v.get("h", 1)), 10 - y))
            except (TypeError, ValueError):
                continue
            cards[k] = {"x": x, "y": y, "w": w, "h": h}
        # 补齐缺失卡片（回退到经典预设位置）
        for k, v in config.SCREEN_LAYOUTS["classic"]["cards"].items():
            if k not in cards:
                cards[k] = {"x": int(v[0]), "y": int(v[1]), "w": int(v[2]), "h": int(v[3])}
    return {"mode": mode, "cards": cards, "noprice": noprice}


def get_screen_config(conn):
    """读取大屏配置（数据库 sys_settings，管理员可配）"""
    cfg = dict(config.DEFAULT_SCREEN)
    cfg["limits"] = dict(config.DEFAULT_SCREEN["limits"])
    cfg["trend"] = dict(config.DEFAULT_SCREEN["trend"])
    _dl = config.DEFAULT_SCREEN["layout"]
    cfg["layout"] = {"mode": _dl["mode"], "cards": {k: dict(v) for k, v in _dl["cards"].items()},
                     "noprice": {k: dict(v) for k, v in (_dl.get("noprice") or {}).items()}}
    raw = db.get_setting(conn, "screen_config")
    if raw:
        try:
            d = json.loads(raw)
            if isinstance(d, dict):
                for k in ("modules", "refresh", "period", "theme", "stale_days", "show_price",
                          "sb_title", "sb_subtitle", "sb_show_logo", "sb_logo_height",
                          "sb_title_size", "sb_subtitle_size", "sb_title_color",
                          "sb_subtitle_color", "sb_font_family", "style"):
                    if k in d:
                        cfg[k] = d[k]
                # 版本升级：把默认配置中新增的模块自动补入（保留用户已有勾选，新模块默认开启）
                if isinstance(d.get("modules"), list):
                    merged = list(d["modules"])
                    for m in config.DEFAULT_SCREEN["modules"]:
                        if m not in merged:
                            merged.append(m)
                    cfg["modules"] = merged
                if isinstance(d.get("style_custom"), dict):
                    cu = cfg.get("style_custom") or {}
                    for k, v in d["style_custom"].items():
                        if _is_hex_color(str(v).strip()):
                            cu[k] = str(v).strip().lower()
                    cfg["style_custom"] = cu
                    if k in d:
                        cfg[k] = d[k]
                if isinstance(d.get("limits"), dict):
                    cfg["limits"].update(d["limits"])
                if isinstance(d.get("trend"), dict):
                    cfg["trend"].update(d["trend"])
                if isinstance(d.get("layout"), dict):
                    cfg["layout"] = _sanitize_layout(d["layout"])
        except Exception:
            pass
    cfg["modules"] = [m for m in cfg["modules"] if m in config.SCREEN_MODULES]
    try:
        cfg["refresh"] = max(5, min(int(cfg["refresh"]), 3600))
    except Exception:
        cfg["refresh"] = 30
    if cfg["period"] not in ("day", "week", "month"):
        cfg["period"] = "day"
    if cfg["theme"] not in ("dark", "light"):
        cfg["theme"] = "dark"
    try:
        cfg["show_price"] = 1 if int(cfg.get("show_price") or 0) else 0
    except (TypeError, ValueError):
        cfg["show_price"] = 0
    if cfg.get("style") not in SCREEN_STYLES and cfg.get("style") != "custom":
        cfg["style"] = "tech-blue"
    # 显示条数边界
    for k in ("recent_tx", "alerts", "stale"):
        try:
            cfg["limits"][k] = max(3, min(int(cfg["limits"].get(k, 10)), 100))
        except Exception:
            cfg["limits"][k] = 10
    # 趋势回溯长度边界
    for k in ("day", "week", "month"):
        try:
            cfg["trend"][k] = max(2, min(int(cfg["trend"].get(k, config.DEFAULT_SCREEN["trend"][k])), 90))
        except Exception:
            cfg["trend"][k] = config.DEFAULT_SCREEN["trend"][k]
    # 呆滞天数：0=跟随系统设置
    try:
        cfg["stale_days"] = max(0, min(int(cfg.get("stale_days") or 0), 3650))
    except Exception:
        cfg["stale_days"] = 0
    # 大屏标题与 LOGO 边界
    cfg["sb_title"] = (str(cfg.get("sb_title") or "")).strip()[:30]
    cfg["sb_subtitle"] = (str(cfg.get("sb_subtitle") or "")).strip()[:50]
    try:
        cfg["sb_show_logo"] = 1 if int(cfg.get("sb_show_logo") or 1) else 0
    except Exception:
        cfg["sb_show_logo"] = 1
    for k, lo, hi in (("sb_logo_height", 0, 160), ("sb_title_size", 0, 36), ("sb_subtitle_size", 0, 22)):
        try:
            cfg[k] = max(lo, min(int(cfg.get(k) or 0), hi))
        except Exception:
            cfg[k] = 0
    for k in ("sb_title_color", "sb_subtitle_color"):
        v = str(cfg.get(k) or "").strip()
        cfg[k] = v.lower() if _is_hex_color(v) else ""
    if not isinstance(cfg.get("sb_font_family"), str) or len(cfg["sb_font_family"]) > 80:
        cfg["sb_font_family"] = ""
    return cfg


@app.route("/screen")
def screen_page():
    """大屏展示页（公共只读，无需登录；数据由 /api/screen 提供）
    顶部标题与 LOGO：优先用大屏配置中的值，未设置则跟随系统设置的侧栏品牌"""
    conn = get_db()
    try:
        cfg = get_screen_config(conn)
        brand = get_brand(conn)
        sb = {
            "title": cfg["sb_title"] or brand["title"],
            "subtitle": cfg["sb_subtitle"] or brand["subtitle"],
            "logo_file": brand["logo_file"] if cfg["sb_show_logo"] else "",
            "logo_height": cfg["sb_logo_height"] or brand["logo_height"],
            "title_size": cfg["sb_title_size"] or brand["title_size"],
            "subtitle_size": cfg["sb_subtitle_size"] or brand["subtitle_size"],
            # 仅大屏配置里显式设置标题色/副标题色才覆盖；默认跟随大屏风格（避免浅色品牌色盖住标题）
            "title_color": cfg["sb_title_color"] or "",
            "subtitle_color": cfg["sb_subtitle_color"] or "",
            "font_family": cfg["sb_font_family"] or brand["font_family"],
        }
    finally:
        conn.close()
    style_css, style_light = _screen_style_css(cfg)
    chart_cards = {"qty_trend", "amt_trend", "category",
                   "line_qty", "line_amt", "dev_qty", "dev_amt"}
    _lang = request.args.get("lang") or _i18n.current_lang()
    return render_template("screen.html", screen_brand=sb,
                           screen_style=style_css, screen_light=style_light,
                           screen_cards={k: _i18n.t(v["label"], _lang) if isinstance(v, dict) and "label" in v else v for k, v in config.SCREEN_CARDS.items()},
                           screen_chart_cards=chart_cards,
                           screen_lang=_lang,
                           tr_json=_i18n.tr_json(_lang),
                           initial_cfg=json.dumps(cfg, ensure_ascii=False))


@app.route("/api/screen")
def api_screen():
    """大屏聚合数据：按配置返回各模块数据（一次请求）"""
    _lang = request.args.get("lang") or _i18n.current_lang()
    conn = get_db()
    try:
        cfg = get_screen_config(conn)
        period = cfg["period"]
        modules = set(cfg["modules"])
        data = {"config": cfg, "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        if "stat_cards" in modules:
            data["cards"] = _period_summary(conn, period)
        if "qty_trend" in modules or "amt_trend" in modules:
            data["series"] = _chart_series(conn, period, cfg["trend"])
        if "category" in modules:
            cats = conn.execute(
                """SELECT COALESCE(NULLIF(p.category,''),?) c, COALESCE(SUM(i.quantity*p.unit_price),0) v
                   FROM parts p LEFT JOIN inventory i ON p.id=i.part_id
                   WHERE p.deleted=0
                   GROUP BY c ORDER BY v DESC""",
                (_i18n.t("未分类", _lang),),
            ).fetchall()
            data["category"] = [{"name": r["c"], "value": round(r["v"], 2)} for r in cats]
        if "alerts" in modules:
            alerts = _stock_alerts(conn)
            lim = cfg["limits"].get("alerts", 10)
            alerts["low"] = alerts["low"][:lim]
            alerts["high"] = alerts["high"][:lim]
            data["alerts"] = alerts
        if "recent_tx" in modules:
            lim = cfg["limits"].get("recent_tx", 10)
            txs = conn.execute(
                """SELECT t.created_at, p.part_code, p.name, t.tx_type, t.quantity, t.location,
                          COALESCE(u.display_name,'-') op_name
                   FROM transactions t
                   JOIN parts p ON t.part_id=p.id
                   LEFT JOIN users u ON t.operator_id=u.id
                   WHERE t.tx_type IN ('in','out')
                   ORDER BY t.id DESC LIMIT ?""",
                (lim,),
            ).fetchall()
            data["recent_tx"] = [dict(r) for r in txs]
        if "pending" in modules:
            pend = conn.execute(
                "SELECT COUNT(*) c FROM applications WHERE status='pending'"
            ).fetchone()["c"]
            val_out = conn.execute(
                """SELECT COUNT(*) c FROM applications a JOIN parts p ON a.part_id=p.id
                   WHERE a.status='pending' AND a.app_type='out' AND p.is_valuable=1"""
            ).fetchone()["c"]
            data["pending"] = {"all": pend, "valuable_out": val_out}
        if "stale" in modules:
            sd = cfg["stale_days"] or _stale_days(conn)
            data["stale"] = _stale_summary(conn, sd, cfg["limits"].get("stale", 10))
        # 线体/设备领用柱状图（数量/金额分卡；金额卡仅在开启「显示金额」时返回数据，避免敏感泄露）
        usage_specs = [
            ("usage_line_qty",   "line_name",   "line_qty", "领用数量"),
            ("usage_line_amt",   "line_name",   "line_amt", "领用金额"),
            ("usage_device_qty", "device_name", "dev_qty",  "领用数量"),
            ("usage_device_amt", "device_name", "dev_amt",  "领用金额"),
        ]
        lim = max(5, cfg["limits"].get("usage", 10))
        for mod, col, key, sname in usage_specs:
            if mod not in modules:
                continue
            if mod.endswith("_amt") and not cfg["show_price"]:
                continue
            sname = _i18n.t(sname, _lang)
            rows = conn.execute(
                """SELECT COALESCE(NULLIF(%s,''),?) d, COALESCE(SUM(quantity),0) q,
                          COALESCE(SUM(amount),0) a
                   FROM transactions WHERE tx_type='out' GROUP BY d ORDER BY q DESC LIMIT ?""" % col,
                (_i18n.t("未分配", _lang), lim),
            ).fetchall()
            items = [{"name": r["d"], "qty": round(r["q"], 3), "amount": round(r["a"], 2)} for r in rows]
            data[key] = {"labels": [i["name"] for i in items],
                         "series": [{"name": sname,
                                     "data": [i["qty"] if mod.endswith("_qty") else i["amount"] for i in items]}]}
        return jsonify(data)
    finally:
        conn.close()


def _layout_from_form(form):
    """从表单解析 layout_mode + layout_cards(JSON)"""
    try:
        raw = json.loads(form.get("layout_cards") or "{}")
    except Exception:
        raw = {}
    return _sanitize_layout({"mode": (form.get("layout_mode") or "classic").strip(), "cards": raw})


@app.route("/screen/config", methods=["GET", "POST"])
@login_required
@role_required("admin")
def screen_config():
    if request.method == "POST":
        modules = [k for k in config.SCREEN_MODULES if request.form.get("mod_" + k)]
        refresh = request.form.get("refresh", "30")
        period = request.form.get("period", "day")
        theme = request.form.get("theme", "dark")
        limits = {
            "recent_tx": int(request.form.get("lim_recent_tx", 10) or 10),
            "alerts": int(request.form.get("lim_alerts", 10) or 10),
            "stale": int(request.form.get("lim_stale", 10) or 10),
        }
        trend = {
            "day": int(request.form.get("trend_day", 14) or 14),
            "week": int(request.form.get("trend_week", 8) or 8),
            "month": int(request.form.get("trend_month", 6) or 6),
        }
        stale_days = int(request.form.get("stale_days", 0) or 0)
        style = request.form.get("style", "tech-blue")
        if style not in SCREEN_STYLES and style != "custom":
            style = "tech-blue"
        style_custom = {}
        for k in SCREEN_STYLES["tech-blue"]["vars"]:
            v = request.form.get("sc_" + k, "").strip()
            if _is_hex_color(v):
                style_custom[k] = v.lower()
        def _sb_int(k):
            try:
                return int(request.form.get(k, 0) or 0)
            except (TypeError, ValueError):
                return 0
        cfg = {
            "modules": modules,
            "refresh": refresh,
            "period": period,
            "theme": theme,
            "show_price": 1 if request.form.get("show_price") else 0,
            "limits": limits,
            "trend": trend,
            "stale_days": stale_days,
            # 大屏标题与 LOGO（空=跟随系统设置的侧栏品牌）
            "sb_title": request.form.get("sb_title", "").strip()[:30],
            "sb_subtitle": request.form.get("sb_subtitle", "").strip()[:50],
            "sb_show_logo": 1 if request.form.get("sb_show_logo") else 0,
            "sb_logo_height": _sb_int("sb_logo_height"),
            "sb_title_size": _sb_int("sb_title_size"),
            "sb_subtitle_size": _sb_int("sb_subtitle_size"),
            "sb_title_color": request.form.get("sb_title_color", "").strip(),
            "sb_subtitle_color": request.form.get("sb_subtitle_color", "").strip(),
            "sb_font_family": request.form.get("sb_font_family", "").strip(),
            "style": style,
            "style_custom": style_custom,
            "layout": _layout_from_form(request.form),
        }
        conn = get_db()
        try:
            db.set_setting(conn, "screen_config", json.dumps(cfg, ensure_ascii=False))
            conn.commit()
            flash(_i18n.t("大屏配置已保存（大屏页面将按新配置刷新）", _i18n.current_lang()), "success")
        finally:
            conn.close()
        return _screen_reply("大屏配置已保存（大屏页面将按新配置刷新）", "success")
    conn = get_db()
    try:
        cfg = get_screen_config(conn)
    finally:
        conn.close()
    _lang = _i18n.current_lang()
    _lay = {}
    for _mk, _mv in config.SCREEN_LAYOUTS.items():
        _lay[_mk] = dict(_mv)
        _lay[_mk]["name"] = _i18n.t(_mv.get("name", _mk), _lang)
    _sty = {}
    for _sk, _sv in SCREEN_STYLES.items():
        _sty[_sk] = dict(_sv)
        _sty[_sk]["name"] = _i18n.t(_sv.get("name", _sk), _lang)
    return render_template("screen_config.html", cfg=cfg, SCREEN_STYLES=_sty,
                           SCREEN_LAYOUTS=_lay,
                           SCREEN_CARDS={k: _i18n.t(v["label"], _lang) if isinstance(v, dict) and "label" in v else v for k, v in config.SCREEN_CARDS.items()})


# ------------------------------------------------------------------
# 备件管理（查询 + 信息维护建档）
# ------------------------------------------------------------------
def _query_parts(conn, kw="", cat="", state="", plain_apps=False):
    """备件查询公共逻辑（备件查询页 / 备件信息维护页共用）
    plain_apps=True：适用产线/设备不带「（整线）」「（未配产线）」标注（查询页）"""
    sql = """SELECT p.*, COALESCE(SUM(i.quantity),0) stock
             FROM parts p LEFT JOIN inventory i ON p.id=i.part_id
             WHERE p.deleted=0"""
    params = []
    if kw:
        sql += " AND (p.part_code LIKE ? OR p.name LIKE ? OR p.spec LIKE ?)"
        params += [f"%{kw}%"] * 3
    if cat:
        sql += " AND p.category=?"
        params.append(cat)
    sql += " GROUP BY p.id"
    rows = conn.execute(sql, params).fetchall()
    loc_map = {l["id"]: l for l in conn.execute("SELECT * FROM locations").fetchall()}
    parts = []
    for r in rows:
        d = dict(r)
        d["status"] = ("low" if d["stock"] < d["min_stock"]
                       else ("high" if (d["max_stock"] and d["stock"] > d["max_stock"]) else "ok"))
        d["location_text"] = db.location_text(loc_map.get(d.get("location_id"))) if d.get("location_id") else ""
        # 所有库存库位（多库位显示；含 0 库存的登记库位，避免「选了库位但列表看不到」）
        sls = db.stock_locations(conn, d["id"])
        d["stock_locs_text"] = "；".join(
            f"{s['location']} ×{s['quantity']}" for s in sls)
        # 适用产线/设备
        apps = db.part_apps(conn, d["id"])
        d["apps_text"] = "；".join(_apps_label(a, plain=plain_apps) for a in apps)
        try:
            d["extra"] = json.loads(d.get("extra") or "{}") or {}
        except Exception:
            d["extra"] = {}
        if state == "low" and d["status"] != "low":
            continue
        if state == "high" and d["status"] != "high":
            continue
        parts.append(d)
    return parts


def _categories(conn):
    return [c["category"] for c in conn.execute(
        "SELECT DISTINCT category FROM parts WHERE category<>'' AND deleted=0 ORDER BY category")]


@app.route("/parts")
@login_required
@perm_required("query")
def parts_page():
    kw = request.args.get("kw", "").strip()
    cat = request.args.get("category", "").strip()
    state = request.args.get("state", "").strip()  # low/high/all
    conn = get_db()
    try:
        parts = _query_parts(conn, kw, cat, state, plain_apps=True)
        cats = _categories(conn)
        locations = _all_locations(conn)
        total_kinds = conn.execute("SELECT COUNT(*) FROM parts WHERE deleted=0").fetchone()[0]
        total_stock = conn.execute("SELECT COALESCE(SUM(quantity),0) FROM inventory").fetchone()[0]
    finally:
        conn.close()
    return render_template("parts.html", parts=parts, categories=cats,
                           kw=kw, cat=cat, state=state, locations=locations,
                           total_kinds=total_kinds, total_stock=total_stock)


# ------------------------------------------------------------------
# 备件导入 / 导出（权限：parts_manage 的 import / export 操作级）
# ------------------------------------------------------------------
def _xlsx_col_to_idx(col):
    """列字母 → 0 基序号：A=0, Z=25, AA=26"""
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


def _read_xlsx_rows(fileobj):
    """纯标准库读取 .xlsx 第一个工作表 → 二维列表（含表头行，空单元格为''）"""
    import zipfile
    from xml.etree import ElementTree as ET
    NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    zf = zipfile.ZipFile(fileobj)
    shared = []
    try:
        with zf.open("xl/sharedStrings.xml") as f:
            root = ET.fromstring(f.read())
        for si in root.iter("{%s}si" % NS):
            shared.append("".join(t.text or "" for t in si.iter("{%s}t" % NS)))
    except KeyError:
        pass
    with zf.open("xl/worksheets/sheet1.xml") as f:
        root = ET.fromstring(f.read())
    grid_rows = []
    for row in root.iter("{%s}row" % NS):
        cells = {}
        for c in row.findall("{%s}c" % NS):
            ref = c.get("r") or ""
            col = "".join(ch for ch in ref if ch.isalpha())
            idx = _xlsx_col_to_idx(col)
            t = c.get("t") or ""
            v = c.find("{%s}v" % NS)
            is_ = c.find("{%s}is" % NS)
            val = ""
            if t == "s" and v is not None:
                n = int(v.text or 0)
                val = shared[n] if n < len(shared) else ""
            elif t == "inlineStr" and is_ is not None:
                val = "".join(x.text or "" for x in is_.iter("{%s}t" % NS))
            elif v is not None:
                val = v.text or ""
            cells[idx] = val
        if cells:
            grid_rows.append(cells)
    if not grid_rows:
        return []
    max_col = max(max(r.keys()) for r in grid_rows) + 1
    return [[r.get(i, "") for i in range(max_col)] for r in grid_rows]


def _read_csv_rows(fileobj):
    """读取 CSV（自动识别 UTF-8 / GBK 编码）"""
    import csv
    raw = fileobj.read()
    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    rows = list(csv.reader(text.splitlines()))
    return rows


def _parse_loc_text(conn, txt):
    """解析「仓库-货架-货位-格位」文本 → locations.id；无法解析/待定/无 → None"""
    if not txt:
        return None
    txt = str(txt).strip()
    if txt in ("待定", "无", "-", "—"):
        return None
    # 去掉可能的 ×数量 后缀
    txt = re.sub(r"×.*$", "", txt).strip()
    segs = [x.strip() for x in re.split(r"[-—]", txt)]
    segs = [x for x in segs if x]
    if len(segs) < 3:
        return None
    wh, rk, sh = segs[0], segs[1], segs[2]
    bn = segs[3] if len(segs) > 3 else ""
    row = conn.execute(
        "SELECT id FROM locations WHERE warehouse=? AND rack=? AND shelf=? AND COALESCE(bin,'')=?",
        (wh, rk, sh, bn)).fetchone()
    return row["id"] if row else None


def _loc_occupied(conn, loc_id, exclude_part_id=None):
    """某位置是否已被备件占用（库存存在；已删除备件不占位），exclude_part_id 忽略指定备件"""
    if not loc_id:
        return False
    if exclude_part_id:
        row = conn.execute(
            "SELECT i.part_id FROM inventory i JOIN parts p ON i.part_id=p.id AND p.deleted=0 "
            "WHERE i.location_id=? AND i.part_id<>? LIMIT 1",
            (loc_id, exclude_part_id)).fetchone()
    else:
        row = conn.execute(
            "SELECT i.part_id FROM inventory i JOIN parts p ON i.part_id=p.id AND p.deleted=0 "
            "WHERE i.location_id=? LIMIT 1",
            (loc_id,)).fetchone()
    return row is not None


def _import_parts_rows(rows, mode="append"):
    """导入备件数据：返回 (created, updated, skipped, errs, unmatched)
    表头：料号* 名称* 分类 规格 单位 数量类型 单价 最小库存 最大库存 当前库存 贵重 存放库位 适用产线/设备 备注 + 自定义列
    mode: append 追加导入（已有料号跳过）；overwrite 覆盖导入（更新同料号全部字段与库存）
    规则：数量类型填 float=小数、不填或填 int=整数（默认整数）；库存数量未填默认 0；分类/规格/备注等未填默认「无」；
         存放库位被占用或无法解析 → 库存导入「待定」"""
    if not rows or len(rows) < 1:
        return 0, 0, 0, ["文件为空"], []
    header = [str(x).strip() for x in rows[0]]

    def col(*names):
        for i, h in enumerate(header):
            if h in names:
                return i
        return -1

    def get(row, i):
        return str(row[i]).strip() if (0 <= i < len(row)) else ""

    i_code = col("料号", "物料编码", "part_code")
    i_name = col("名称", "name")
    i_cat = col("分类", "类别", "category")
    i_spec = col("规格", "spec")
    i_unit = col("单位", "unit")
    i_dec = col("数量类型", "小数属性", "qty_decimal")
    i_price = col("单价", "单价(元)", "unit_price")
    i_min = col("最小库存", "下限", "min_stock")
    i_max = col("最大库存", "上限", "max_stock")
    i_stock = col("当前库存", "库存数量", "库存", "stock")
    i_val = col("贵重", "is_valuable")
    i_loc = col("存放库位", "库位", "放置位置", "location")
    i_apps = col("适用产线/设备", "产线/设备", "apps")
    i_remark = col("备注", "remark")
    if i_code < 0 or i_name < 0:
        return 0, 0, 0, ["表头缺少必填列「料号」或「名称」。可先在建档页点「下载导入模板」获取标准模板。"], []

    conn = get_db()
    created = updated = skipped = 0
    errs = []
    unmatched = set()
    try:
        lines = {l["name"]: l for l in db.list_lines(conn)}
        equips = {e["name"]: e for e in db.list_equipment(conn)}
        efs = get_extra_fields(conn)
        ef_idx = {ef["label"]: col(ef["label"]) for ef in efs if ef["label"]}
        for n, row in enumerate(rows[1:], start=2):
            if not row or not any(str(x).strip() for x in row):
                continue
            code = get(row, i_code)
            name = get(row, i_name)
            if str(code).strip().startswith("示例"):
                continue  # 模板内置示例行，跳过不导入
            if not code:
                errs.append(f"第{n}行：料号为空，已跳过")
                skipped += 1
                continue
            if not name:
                errs.append(f"第{n}行：名称为空，已跳过")
                skipped += 1
                continue
            # 覆盖模式：验证除料号以外的所有数据（数字列必须可解析）
            if mode == "overwrite":
                bad = False
                for label, idx in (("单价", i_price), ("最小库存", i_min),
                                   ("最大库存", i_max), ("当前库存", i_stock)):
                    if idx >= 0 and get(row, idx) and _num_strict(get(row, idx)) is None:
                        errs.append(f"第{n}行：「{label}」不是有效数字，已跳过")
                        skipped += 1
                        bad = True
                        break
                if bad:
                    continue
            cat = get(row, i_cat) or "无"
            spec = get(row, i_spec) or "无"
            unit = get(row, i_unit) or "个"
            dec = _qdec(get(row, i_dec))  # 填 float=小数；不填或填 int=整数（默认整数）
            price = _num(get(row, i_price)) or 0
            mn = _num(get(row, i_min)) or 0
            mx = _num(get(row, i_max)) or 0
            qty = _num(get(row, i_stock)) or 0  # 库存数量未填 → 默认 0
            val = 1 if get(row, i_val).lower() in ("是", "1", "y", "yes", "true", "贵重") else 0
            remark = get(row, i_remark) or "无"
            extra = {}
            for label, idx in ef_idx.items():
                if idx >= 0:
                    extra[label] = get(row, idx) or ""
            # 适用产线/设备：按名称匹配
            pairs = []
            app_txt = get(row, i_apps)
            if app_txt:
                for seg in re.split(r"[;；,，/]", app_txt):
                    seg = seg.strip()
                    if not seg:
                        continue
                    if seg in lines:
                        pairs.append((lines[seg]["id"], None))
                    elif seg in equips:
                        e = equips[seg]
                        pairs.append((e["line_id"], e["id"]))
                    else:
                        unmatched.add(seg)
            # 回收站中的同料号不参与导入（避免误更新/重复建档）
            recycled = conn.execute(
                "SELECT id FROM parts WHERE part_code=? AND deleted=1", (code,)
            ).fetchone()
            if recycled:
                skipped += 1
                errs.append(f"料号 {code} 在回收站中，请先在回收站恢复或彻底清除后再导入")
                continue
            exist = conn.execute(
                "SELECT id FROM parts WHERE part_code=? AND deleted=0", (code,)
            ).fetchone()
            # 覆盖模式：已存在 → 更新全部字段；追加模式：已存在 → 跳过
            if exist and mode == "append":
                skipped += 1
                continue
            try:
                if exist:
                    conn.execute(
                        """UPDATE parts SET name=?, category=?, spec=?, unit=?, qty_decimal=?, unit_price=?,
                           min_stock=?, max_stock=?, is_valuable=?, remark=?, extra=?, updated_at=?
                           WHERE id=?""",
                        (name, cat, spec, unit, dec, price, mn, mx, val, remark,
                         json.dumps(extra, ensure_ascii=False), db.now_str(), exist["id"]),
                    )
                    db.set_part_apps(conn, exist["id"], pairs)
                    pid = exist["id"]
                    updated += 1
                else:
                    cur = conn.execute(
                        """INSERT INTO parts(part_code,name,category,spec,unit,qty_decimal,unit_price,min_stock,max_stock,
                           is_valuable,supplier,remark,location_id,extra,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,'',?,NULL,?,?,?)""",
                        (code, name, cat, spec, unit, dec, price, mn, mx, val, remark,
                         json.dumps(extra, ensure_ascii=False), db.now_str(), db.now_str()),
                    )
                    db.set_part_apps(conn, cur.lastrowid, pairs)
                    pid = cur.lastrowid
                    created += 1
                # 库存重建：删除旧库存行 → 按导入行写入
                conn.execute("DELETE FROM inventory WHERE part_id=?", (pid,))
                if qty and qty > 0:
                    loc_id = _parse_loc_text(conn, get(row, i_loc))
                    if loc_id and _loc_occupied(conn, loc_id, pid):
                        loc_id = None  # 位置被占用 → 导入待定
                    loc_txt = "待定"
                    if loc_id:
                        loc = conn.execute("SELECT * FROM locations WHERE id=?", (loc_id,)).fetchone()
                        loc_txt = db.location_text(loc)
                    conn.execute(
                        "INSERT INTO inventory(part_id, location_id, location, quantity) VALUES(?,?,?,?)",
                        (pid, loc_id, loc_txt, qty),
                    )
            except Exception as e:
                errs.append(f"第{n}行：{e}，已跳过")
                skipped += 1
        conn.commit()
    finally:
        conn.close()
    return created, updated, skipped, errs[:12], sorted(unmatched)


@app.route("/parts/import", methods=["POST"])
@login_required
@perm_required("parts_manage", "import")
def parts_import():
    """导入备件（.xlsx / .csv），mode=append 追加 / overwrite 覆盖"""
    file = request.files.get("file")
    mode = request.form.get("mode", "append")
    if mode not in ("overwrite", "append"):
        mode = "append"
    if not file or not file.filename:
        flash(_i18n.t("请选择要导入的 Excel / CSV 文件", _i18n.current_lang()), "danger")
        return redirect(url_for("parts_manage_page"))
    ext = os.path.splitext(file.filename)[1].lower()
    try:
        if ext == ".csv":
            rows = _read_csv_rows(file)
        elif ext in (".xlsx", ".xlsm"):
            rows = _read_xlsx_rows(file)
        else:
            flash(_i18n.t("仅支持 .xlsx / .csv 文件", _i18n.current_lang()), "danger")
            return redirect(url_for("parts_manage_page"))
    except Exception as e:
        flash(_i18n.t("文件解析失败：{0}", _i18n.current_lang()).format(e), "danger")
        return redirect(url_for("parts_manage_page"))
    created, updated, skipped, errs, unmatched = _import_parts_rows(rows, mode)
    mode_txt = "覆盖导入" if mode == "overwrite" else "追加导入"
    msg = f"{mode_txt}完成：新增 {created} 条，更新 {updated} 条，跳过 {skipped} 条"
    if unmatched:
        msg += "；以下产线/设备未匹配已忽略：" + "、".join(unmatched[:5])
    if errs:
        msg += "；问题：" + "；".join(errs)
    flash(msg, "success" if skipped == 0 else "warning")
    return redirect(url_for("parts_manage_page"))


@app.route("/parts/template")
@login_required
@perm_required("parts_manage", "import")
def parts_template():
    """下载备件导入 Excel 模板（标准表头，含自定义列）"""
    conn = get_db()
    try:
        efs = get_extra_fields(conn)
    finally:
        conn.close()
    headers = ["料号", "名称", "分类", "规格", "单位", "数量类型", "单价(元)",
               "最小库存", "最大库存", "当前库存", "贵重", "存放库位", "适用产线/设备"]
    for ef in efs:
        if ef["label"]:
            headers.append(ef["label"])
    headers.append("备注")
    # 两条填写示例（料号以「示例-」开头，导入时自动跳过，不产生备件记录）
    extra_n = len(efs)
    example_rows = [
        ["示例-R-0603-10K", "贴片电阻 0603 10KΩ", "电阻", "0603", "PCS", "int", 0.05,
         100, 10000, 5000, "否", "WH-01-R-01-S-01", "SMT-1线"]
        + [""] * extra_n
        + ["示例：数量类型填 int 或不填=整数，单位用 个/PCS/卷…，数量只能填正整数"],
        ["示例-锡膏SAC305", "无铅锡膏 SAC305", "辅料", "SAC305", "克", "float", 1.2,
         1000, 50000, 20000, "否", "待定", "SMT-2线"]
        + [""] * extra_n
        + ["示例：数量类型填 float=小数，单位用 米/克/KG…，数量可填小数（如 12.5）"],
    ]
    data = _export_xlsx(headers, example_rows, "导入模板")
    return Response(
        data.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=parts_import_template.xlsx"},
    )


@app.route("/parts/export")
@login_required
@perm_required("parts_manage", "export")
def parts_export():
    """导出备件清单（按当前筛选条件）为 Excel"""
    kw = request.args.get("kw", "").strip()
    cat = request.args.get("category", "").strip()
    state = request.args.get("state", "").strip()
    conn = get_db()
    try:
        parts = _query_parts(conn, kw, cat, state)
        efs = get_extra_fields(conn)
    finally:
        conn.close()
    headers = ["料号", "名称", "分类", "规格", "单位", "数量类型", "单价(元)",
               "最小库存", "最大库存", "当前库存", "贵重", "存放库位", "适用产线/设备"]
    for ef in efs:
        if ef["label"]:
            headers.append(ef["label"])
    headers.append("备注")
    rows = []
    for p in parts:
        loc_txt = p["stock_locs_text"] or ("待定" if p["stock"] > 0 else "")
        row = [p["part_code"], p["name"], p["category"], p["spec"], p["unit"],
               "float" if p["qty_decimal"] else "int",
               p["unit_price"], p["min_stock"], p["max_stock"], p["stock"],
               "是" if p["is_valuable"] else "否", loc_txt, p["apps_text"]]
        for ef in efs:
            if ef["label"]:
                row.append(p.get("extra", {}).get(ef["label"], ""))
        row.append(p.get("remark", ""))
        rows.append(row)
    data = _export_xlsx(headers, rows, "备件清单")
    return Response(
        data.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=parts_export.xlsx"},
    )

@app.route("/parts/manage")
@login_required
@perm_required("parts_manage")
def parts_manage_page():
    """备件信息维护（建档）：仓管员以上使用，新增/编辑/删除/图片/位置"""
    kw = request.args.get("kw", "").strip()
    cat = request.args.get("category", "").strip()
    state = request.args.get("state", "").strip()
    conn = get_db()
    try:
        parts = _query_parts(conn, kw, cat, state)
        cats = _categories(conn)
        locations = _all_locations(conn)
        lines = db.list_lines(conn)
        equipment = db.list_equipment(conn)
        total_kinds = conn.execute("SELECT COUNT(*) FROM parts WHERE deleted=0").fetchone()[0]
        total_stock = conn.execute("SELECT COALESCE(SUM(quantity),0) FROM inventory").fetchone()[0]
    finally:
        conn.close()
    return render_template("parts_manage.html", parts=parts, categories=cats,
                           kw=kw, cat=cat, state=state, locations=locations,
                           lines=lines, equipment=equipment,
                           total_kinds=total_kinds, total_stock=total_stock)


def _all_locations(conn):
    """全部货架位置，附占用备件信息（供编辑弹窗级联与占用判断）
    排序：空闲（未占用）位置在前，再按仓库-货架-货位-格位
    占用 = 该位置有任一【未删除】备件存放库存（多库位模型，不再依赖 parts.location_id）；
    已删除（回收站）备件的库存行不计占用——删除即释放库位"""
    rows = conn.execute(
        """SELECT l.*, iv.part_id, p.part_code, p.name
           FROM locations l
           LEFT JOIN (
              SELECT location_id, MIN(part_id) part_id FROM inventory
              WHERE location_id IS NOT NULL
                AND part_id IN (SELECT id FROM parts WHERE deleted=0)
              GROUP BY location_id
           ) iv ON iv.location_id=l.id
           LEFT JOIN parts p ON p.id=iv.part_id AND p.deleted=0
           ORDER BY CASE WHEN iv.part_id IS NULL THEN 0 ELSE 1 END,
                    l.warehouse, l.rack, l.shelf, l.bin"""
    ).fetchall()
    return [dict(r) for r in rows]


@app.route("/api/parts/search")
@login_required
def api_parts_search():
    """备件高级搜索（出入库申请/出入库管理/调库管理共用）"""
    kw = request.args.get("kw", "").strip()
    try:
        limit = min(int(request.args.get("limit", 50)), 100)
    except (TypeError, ValueError):
        limit = 50
    conn = get_db()
    try:
        base = """SELECT p.id, p.part_code, p.name, p.spec, p.unit, p.unit_price, p.is_valuable,
                         p.qty_decimal,
                         COALESCE(SUM(i.quantity),0) stock
                  FROM parts p LEFT JOIN inventory i ON p.id=i.part_id
                  WHERE p.deleted=0
                  %s GROUP BY p.id ORDER BY p.part_code LIMIT ?"""
        if kw:
            like = f"%{kw}%"
            sql = base % "AND (p.part_code LIKE ? OR p.name LIKE ? OR p.spec LIKE ? OR p.category LIKE ?)"
            rows = conn.execute(sql, (like, like, like, like, limit)).fetchall()
        else:
            sql = base % ""
            rows = conn.execute(sql, (limit,)).fetchall()
    finally:
        conn.close()
    out = [dict(r) for r in rows]
    # 金额敏感：无「备件金额查看」权限（普通用户默认）→ 不返回单价
    if not can(current_user()["role"], "price"):
        for r in out:
            r.pop("unit_price", None)
    return jsonify(out)


@app.route("/api/parts/<int:pid>")
@login_required
def api_part_detail(pid):
    conn = get_db()
    try:
        d = db.part_detail(conn, pid)
        if d:
            d = dict(d)
            loc = db.get_location(conn, d.get("location_id"))
            d["location_text"] = db.location_text(loc) if loc else ""
            d["apps"] = db.part_apps(conn, pid)
            try:
                d["extra"] = json.loads(d.get("extra") or "{}") or {}
            except Exception:
                d["extra"] = {}
    finally:
        conn.close()
    if not d:
        return jsonify({"error": "备件不存在"}), 404
    # 金额敏感：无「备件金额查看」权限（普通用户默认）→ 不返回单价
    if not can(current_user()["role"], "price"):
        d.pop("unit_price", None)
    d["image_url"] = url_for("media", fname=d["image_file"]) if d["image_file"] else ""
    return jsonify(d)


@app.route("/parts/add", methods=["POST"])
@login_required
@perm_required("parts_manage", "add")
def part_add():
    f = request.form
    part_code = f.get("part_code", "").strip()
    name = f.get("name", "").strip()
    if not part_code or not name:
        flash(_i18n.t("料号与名称必填", _i18n.current_lang()), "danger")
        return redirect(url_for("parts_manage_page"))
    conn = get_db()
    try:
        if conn.execute("SELECT id FROM parts WHERE part_code=? AND deleted=0", (part_code,)).fetchone():
            flash(_i18n.t("料号 {0} 已存在", _i18n.current_lang()).format(part_code), "danger")
            return redirect(url_for("parts_manage_page"))
        if conn.execute("SELECT id FROM parts WHERE part_code=? AND deleted=1", (part_code,)).fetchone():
            flash(_i18n.t("料号 {0} 在回收站中，请先在回收站恢复或彻底清除后再新增", _i18n.current_lang()).format(part_code), "danger")
            return redirect(url_for("parts_manage_page"))
        extra_json = json.dumps(_form_extra(f), ensure_ascii=False)
        qdec = _qdec(f.get("qty_decimal"))
        unit = f.get("unit", "个").strip()
        cur = conn.execute(
            """INSERT INTO parts(part_code,name,category,spec,unit,qty_decimal,unit_price,min_stock,max_stock,
               is_valuable,supplier,remark,location_id,extra,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (part_code, name, f.get("category", "").strip(), f.get("spec", "").strip(),
             unit, qdec,
             _num(f.get("unit_price", 0)),
             _num(f.get("min_stock", 0)), _num(f.get("max_stock", 0)),
             1 if f.get("is_valuable") else 0, f.get("supplier", "").strip(),
             f.get("remark", "").strip(), None, extra_json, db.now_str(), db.now_str()),
        )
        conn.commit()
        pid = cur.lastrowid
        _audit("part", pid, part_code, "add", {"f": {
            "part_code": ["", part_code], "name": ["", f.get("name", "").strip()],
            "category": ["", f.get("category", "").strip()], "spec": ["", f.get("spec", "").strip()],
            "unit": ["", unit], "qty_decimal": ["", _fmt_part_val("qty_decimal", qdec)],
            "unit_price": ["", _fmt_part_val("unit_price", _num(f.get("unit_price", 0)))],
            "min_stock": ["", _fmt_part_val("min_stock", _num(f.get("min_stock", 0)))],
            "max_stock": ["", _fmt_part_val("max_stock", _num(f.get("max_stock", 0)))],
            "is_valuable": ["", _fmt_part_val("is_valuable", 1 if f.get("is_valuable") else 0)],
            "supplier": ["", f.get("supplier", "").strip()], "remark": ["", f.get("remark", "").strip()],
        }})
        # 初始库存：可配置多个库位（位置 id + 数量 并行数组；数量留空=0 仅登记库位）
        inv_locs = f.getlist("inv_loc[]")
        inv_qtys = f.getlist("inv_qty[]")
        added = 0
        for lid, q in zip(inv_locs, inv_qtys):
            qv = max(0, _num(q))
            if not lid:
                continue
            # 整数类备件：库位库存数量必须为整数（前端已限制，后端兜底校验）
            if not qdec and qv != int(qv):
                flash(_i18n.t("该备件按『{0}』整数计数，库位库存数量不能填小数", _i18n.current_lang()).format(unit), "danger")
                continue
            qv = int(qv) if not qdec else qv
            # 位置被其他备件占用时拒绝（与编辑弹窗添加库位同规则）
            occ = conn.execute(
                """SELECT i.part_id, p.part_code FROM inventory i
                   JOIN parts p ON i.part_id=p.id AND p.deleted=0
                   WHERE i.location_id=? AND i.part_id<>? LIMIT 1""",
                (int(lid), pid),
            ).fetchone()
            if occ:
                flash(f"位置(id={lid})已配置给备件 [{occ['part_code']}]，未添加；请先将其调走", "warning")
                continue
            ok, msg = db.move_stock(conn, pid, int(lid), qv)
            if not ok:
                flash(msg, "warning")
            else:
                added += 1
        if inv_locs and any(x.strip() for x in inv_locs) and added == 0:
            flash(_i18n.t("初始库位未添加：所选位置不存在或已被其他备件占用", _i18n.current_lang()), "warning")
        # 适用产线/设备（只选设备/整线，产线自动带出）
        db.set_part_apps(conn, pid, _form_part_apps(f))
        conn.commit()
        flash(_i18n.t("备件 [{0}] 添加成功", _i18n.current_lang()).format(part_code), "success")
    finally:
        conn.close()
    return redirect(url_for("parts_manage_page"))


@app.route("/parts/<int:pid>/edit", methods=["POST"])
@login_required
@perm_required("parts_manage", "edit")
def part_edit(pid):
    f = request.form
    conn = get_db()
    try:
        row = conn.execute("SELECT id, part_code, name, category, spec, unit, qty_decimal, unit_price, min_stock, max_stock, is_valuable, supplier, remark FROM parts WHERE id=? AND deleted=0", (pid,)).fetchone()
        if not row:
            flash(_i18n.t("备件不存在或已被删除", _i18n.current_lang()), "danger")
            return redirect(url_for("parts_manage_page"))
        old_dec = row["qty_decimal"]
        new_dec = _qdec(f.get("qty_decimal"))
        extra_json = json.dumps(_form_extra(f), ensure_ascii=False)
        conn.execute(
            """UPDATE parts SET name=?, category=?, spec=?, unit=?, qty_decimal=?, unit_price=?,
               min_stock=?, max_stock=?, is_valuable=?, supplier=?, remark=?,
               extra=?, updated_at=?
               WHERE id=?""",
            (f.get("name", "").strip(), f.get("category", "").strip(),
             f.get("spec", "").strip(), f.get("unit", "个").strip(),
             new_dec,
             _num(f.get("unit_price", 0)), _num(f.get("min_stock", 0)),
             _num(f.get("max_stock", 0)), 1 if f.get("is_valuable") else 0,
             f.get("supplier", "").strip(), f.get("remark", "").strip(),
             extra_json, db.now_str(), pid),
        )
        # 数量类型 小数→整数：库存数量自动取整（四舍五入）
        rounded = 0
        if old_dec and not new_dec:
            cur = conn.execute(
                "UPDATE inventory SET quantity=ROUND(quantity) WHERE part_id=?", (pid,)
            )
            rounded = cur.rowcount if cur.rowcount > 0 else 0
        conn.commit()
        # 编辑时同步处理图片（上传/更换）
        file = request.files.get("image")
        if file and file.filename:
            _save_part_image(conn, pid, file)
        # 适用产线/设备（只选设备/整线，产线自动带出）
        db.set_part_apps(conn, pid, _form_part_apps(f))
        conn.commit()
        # 操作审计：记录编辑差异
        try:
            diff = {}
            nv = {
                "name": f.get("name", "").strip(), "category": f.get("category", "").strip(),
                "spec": f.get("spec", "").strip(), "unit": f.get("unit", "个").strip(),
                "qty_decimal": _fmt_part_val("qty_decimal", new_dec),
                "unit_price": _fmt_part_val("unit_price", _num(f.get("unit_price", 0))),
                "min_stock": _fmt_part_val("min_stock", _num(f.get("min_stock", 0))),
                "max_stock": _fmt_part_val("max_stock", _num(f.get("max_stock", 0))),
                "is_valuable": _fmt_part_val("is_valuable", 1 if f.get("is_valuable") else 0),
                "supplier": f.get("supplier", "").strip(), "remark": f.get("remark", "").strip(),
            }
            for k, newv in nv.items():
                oldv = _fmt_part_val(k, row[k])
                if oldv != newv:
                    diff[k] = [oldv, newv]
            if diff:
                _audit("part", pid, row["part_code"], "edit", {"f": diff}, conn=conn)
        except Exception:
            pass
        msg = "备件信息已更新"
        if rounded:
            msg += f"，数量类型已改为整数，库存数量已自动取整（{rounded} 处）"
        flash(msg, "success")
    finally:
        conn.close()
    return redirect(url_for("parts_manage_page", _anchor=f"part-{pid}"))


def _part_pending(conn, part_id):
    """备件是否处于「待定」状态：没有任何有放置位置的库存行
    （多库位模型：所有库存行都没有位置时整体待定，不可领用/出库）"""
    row = conn.execute(
        """SELECT COUNT(*) c FROM inventory WHERE part_id=? AND (
             (location_id IS NOT NULL)
             OR (location_id IS NULL AND location IS NOT NULL AND location != '' AND location != '待定'))""",
        (part_id,),
    ).fetchone()
    return not row or row["c"] == 0


def _part_stock_lines(conn, part_id):
    """备件全部库存行（含待定行），供调库选择源库位"""
    return db.stock_locations(conn, part_id)


def _form_extra(f):
    """收集自定义表头字段值（key 来自 extra_fields 配置）"""
    extra = {}
    for ef in get_extra_fields():
        v = f.get("extra_" + ef["key"], "").strip()
        if v:
            extra[ef["key"]] = v
    return extra


def _form_part_apps(f):
    """收集备件适用产线/设备：pa_line[] / pa_equip[] 并行数组
    每行可只选设备（产线留空=设备未分配产线）或只选产线（整线适用）
    返回 [(line_id_or_None, equipment_id_or_None), ...]"""
    lines = f.getlist("pa_line[]")
    equips = f.getlist("pa_equip[]")
    pairs = []
    for ln, eq in zip(lines, equips):
        ln = (ln or "").strip()
        eq = (eq or "").strip()
        try:
            lid = int(ln) if ln else None
        except (TypeError, ValueError):
            lid = None
        try:
            eid = int(eq) if eq else None
        except (TypeError, ValueError):
            eid = None
        if not lid and not eid:
            continue
        pairs.append((lid, eid))
    return pairs


def _apps_label(a, plain=False):
    """适用产线/设备的显示文本（统一简洁格式，不带「XX线/」「（整线）」「（未分配产线）」）：
    - 有设备 → 只显示设备名
    - 仅产线 → 显示产线名"""
    line = (a.get("line_name") or "").strip()
    equip = (a.get("equip_name") or "").strip()
    if equip:
        return equip
    if line:
        return line
    return ""


def _upload_compress_kb(conn=None):
    """读取「上传图片自动压缩」阈值（KB，0=不压缩）；随数据库走"""
    try:
        c = conn or get_db()
        raw = db.get_setting(c, "upload_cfg")
        if raw:
            d = json.loads(raw)
            return max(0, min(int(d.get("compress_kb") or 0), 10240))
    except Exception:
        pass
    return 400


def _compress_image(data, max_kb):
    """用 Pillow 把图片压缩到 max_kb KB 以内（尽力而为）；无法处理时原样返回
    返回 (bytes, 是否发生了压缩)"""
    if max_kb <= 0 or len(data) <= max_kb * 1024:
        return data, False
    try:
        from PIL import Image
        import io as _io
        img = Image.open(_io.BytesIO(data))
        img.load()
        w, h = img.size
        # 1) 尺寸过大先缩到最长边 4096 以内
        if max(w, h) > 4096:
            s = 4096 / max(w, h)
            img = img.resize((int(w * s), int(h * s)), Image.LANCZOS)
        # 2) 统一转 RGB（带透明通道的用白底合成）
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")
        limit = max_kb * 1024
        # 3) 质量迭代
        for quality in (90, 78, 65, 50, 40):
            buf = _io.BytesIO()
            img.save(buf, "JPEG", quality=quality, optimize=True)
            if buf.tell() <= limit:
                return buf.getvalue(), True
        # 4) 仍超：逐级缩小分辨率再压
        for longside in (2048, 1600, 1280, 1024, 800):
            w, h = img.size
            if max(w, h) <= longside:
                continue
            s = longside / max(w, h)
            small = img.resize((int(w * s), int(h * s)), Image.LANCZOS)
            buf = _io.BytesIO()
            small.save(buf, "JPEG", quality=78, optimize=True)
            if buf.tell() <= limit:
                return buf.getvalue(), True
        return data, False
    except Exception:
        return data, False


def _save_part_image(conn, pid, file):
    """保存备件图片（覆盖旧图），供新增/编辑使用——图片二进制存入主数据库 images 表"""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in config.ALLOWED_IMG_EXTS:
        flash(_i18n.t("不支持的图片格式（支持 jpg/png/gif/bmp/webp）", _i18n.current_lang()), "danger")
        return
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > config.MAX_IMG_SIZE:
        flash(_i18n.t("图片超过 5MB 限制", _i18n.current_lang()), "danger")
        return
    raw = file.read()
    max_kb = _upload_compress_kb(conn)
    data, compressed = _compress_image(raw, max_kb)
    save_name = f"part{pid}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(file.filename)}"
    db.image_save(conn, save_name, data)
    old = conn.execute("SELECT image_file FROM parts WHERE id=?", (pid,)).fetchone()
    if old and old["image_file"] and old["image_file"] != save_name:
        db.image_delete(conn, old["image_file"])
        # 兼容旧版：删除历史遗留的同名目录文件（失败忽略，图片已在库中）
        fp = os.path.join(config.resolved_upload_dir(), old["image_file"])
        if os.path.exists(fp):
            try:
                os.remove(fp)
            except OSError:
                pass
    conn.execute("UPDATE parts SET image_file=? WHERE id=?", (save_name, pid))
    conn.commit()
    if compressed:
        flash(_i18n.t("备件图片已更新（已自动压缩到 {0}KB 以内）", _i18n.current_lang()).format(max_kb), "success")
    else:
        flash(_i18n.t("备件图片已更新", _i18n.current_lang()), "success")


@app.route("/parts/<int:pid>/delete", methods=["POST"])
@login_required
@perm_required("parts_manage", "delete")
def part_delete(pid):
    """删除备件 → 移入回收站（软删除）。库存必须为 0、无未完成申请单；
    回收站仅管理员可见/可恢复，超保留期由后台线程自动彻底清除"""
    conn = get_db()
    try:
        stock = db.total_stock(conn, pid)
        if stock > 0:
            flash(_i18n.t("该备件仍有库存，不能删除；请先调拨或出库至 0", _i18n.current_lang()), "danger")
            return redirect(url_for("parts_manage_page"))
        # 未完成申请单校验：存在待处理/已批准待出库/撤销待审批的申请单时禁止删除
        pnd = conn.execute(
            """SELECT app_no, app_type, status FROM applications
               WHERE part_id=? AND status IN ('pending','approved','cancel_req')
               ORDER BY id LIMIT 1""",
            (pid,),
        ).fetchone()
        if pnd:
            status_name = {"pending": "待处理", "approved": "已批准·待出库", "cancel_req": "撤销待审批"}
            flash(
                _i18n.t("该备件存在未完成申请单 {0}（{1}），不能删除；请先处理该申请单（执行/驳回/撤销）后再删除", _i18n.current_lang())
                .format(pnd['app_no'], status_name.get(pnd['status'], pnd['status'])),
                "danger",
            )
            return redirect(url_for("parts_manage_page"))
        if not conn.execute("SELECT id FROM parts WHERE id=? AND deleted=0", (pid,)).fetchone():
            flash(_i18n.t("备件不存在或已被删除", _i18n.current_lang()), "danger")
            return redirect(url_for("parts_manage_page"))
        p_row = conn.execute("SELECT part_code FROM parts WHERE id=?", (pid,)).fetchone()
        conn.execute("UPDATE parts SET deleted=1, deleted_at=? WHERE id=?", (db.now_str(), pid))
        conn.commit()
        try:
            _audit("part", pid, p_row["part_code"] if p_row else str(pid), "delete", {"note": "删除备件（移入回收站）"}, conn=conn)
        except Exception:
            pass
        flash(_i18n.t("备件已移入回收站（管理员可在回收站恢复或彻底删除）", _i18n.current_lang()), "success")
    finally:
        conn.close()
    return redirect(url_for("parts_manage_page"))


# ------------------------------------------------------------------
# 回收站（备件软删除管理，仅管理员）：
#   删除备件 → deleted=1 进回收站；管理员可恢复/彻底删除；
#   保留天数可配置（默认 3 天，sys_settings key=recycle_days），超期由后台线程自动彻底清除
# ------------------------------------------------------------------
# ------------------------------------------------------------------
# 操作审计（备件 / 货架位置：新增、编辑、删除、恢复、彻底清除）
# ------------------------------------------------------------------
PART_FIELD_NAMES = {
    "part_code": "备件编号", "name": "备件名称", "category": "分类", "spec": "规格型号",
    "unit": "单位", "qty_decimal": "数量类型", "unit_price": "单价", "min_stock": "最小库存",
    "max_stock": "最大库存", "is_valuable": "贵重", "supplier": "供应商", "remark": "备注",
    "location_id": "存放位置",
}
def _fmt_part_val(k, v):
    if k == "qty_decimal":
        return "小数" if v else "整数"
    if k == "is_valuable":
        return "是" if v else "否"
    if v is None:
        return ""
    return str(v)

def _audit(obj_type, obj_id, obj_code, action, detail=None, conn=None):
    """写入操作审计记录。detail: dict 或 str"""
    own = conn is None
    if own:
        conn = get_db()
    try:
        u = None
        try:
            u = current_user()
        except Exception:
            u = None
        detail_json = json.dumps(detail, ensure_ascii=False) if isinstance(detail, (dict, list)) else (detail or "")
        conn.execute(
            "INSERT INTO audit_log(obj_type,obj_id,obj_code,action,detail,operator_id,operator_name,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (obj_type, obj_id, obj_code, action, detail_json,
             u.get("id") if u else None, u.get("username") if u else "", db.now_str()),
        )
        conn.commit()
    finally:
        if own:
            conn.close()


def _recycle_days(conn=None):
    """回收站保留天数（默认 3 天）"""
    own = conn is None
    if own:
        conn = get_db()
    try:
        try:
            d = int(db.get_setting(conn, "recycle_days") or 3)
            return d if 1 <= d <= 365 else 3
        except (TypeError, ValueError):
            return 3
    finally:
        if own:
            conn.close()


def _purge_part(conn, pid):
    """彻底清除一条备件：图片 + 适用关系 + 库存 + 主记录（回收站超期/手动彻底删除用）"""
    p = conn.execute("SELECT image_file FROM parts WHERE id=?", (pid,)).fetchone()
    if p and p["image_file"]:
        db.image_delete(conn, p["image_file"])
        fp = os.path.join(config.resolved_upload_dir(), p["image_file"])
        if os.path.exists(fp):
            try:
                os.remove(fp)
            except OSError:
                pass
    conn.execute("DELETE FROM part_applications WHERE part_id=?", (pid,))
    conn.execute("DELETE FROM inventory WHERE part_id=?", (pid,))
    conn.execute("DELETE FROM parts WHERE id=?", (pid,))


def _recycle_list(conn):
    """回收站列表：deleted=1 的备件 + 到期自动清除时间"""
    days = _recycle_days(conn)
    now = datetime.now()
    rows = conn.execute(
        """SELECT id, part_code, name, category, spec, unit, unit_price, image_file,
                  location_id, created_at, updated_at, deleted_at
           FROM parts WHERE deleted=1 ORDER BY deleted_at DESC"""
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["expire"] = None
        d["expired"] = False
        deleted_at = d.get("deleted_at")
        if deleted_at:
            try:
                dt = datetime.strptime(deleted_at[:19], "%Y-%m-%d %H:%M:%S")
                d["expire"] = (dt + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
                d["expired"] = now >= dt + timedelta(days=days)
            except (ValueError, TypeError):
                pass
        loc = db.get_location(conn, d.get("location_id"))
        d["location_text"] = db.location_text(loc) if loc else ""
        out.append(d)
    return out


@app.route("/parts/recycle")
@login_required
@role_required("admin")
def recycle_page():
    """回收站（仅管理员）：按类型分组展示 备件/货架位置/部门/用户；查看/恢复/彻底删除/保留天数设置"""
    conn = get_db()
    try:
        days = _recycle_days(conn)
        groups = []
        _rl = _i18n.current_lang()
        for t, label in (("parts", _i18n.t("备件", _rl)), ("location", _i18n.t("货架位置", _rl)),
                         ("department", _i18n.t("部门", _rl)), ("user", _i18n.t("用户", _rl))):
            items = _recycle_list(conn) if t == "parts" else _recycle_items_list(conn, t)
            groups.append({"type": t, "label": label, "rows": items})
    finally:
        conn.close()
    return render_template("recycle.html", groups=groups, days=days,
                           cover_pending=session.get("cover_pending"))


@app.route("/parts/recycle/restore", methods=["POST"])
@login_required
@role_required("admin")
def recycle_restore():
    """恢复回收站备件；原固定库位若已被其他备件占用 → 置为待定（不占位）"""
    try:
        pid = int(request.form.get("pid", 0))
    except (TypeError, ValueError):
        pid = 0
    conn = get_db()
    try:
        p = conn.execute("SELECT * FROM parts WHERE id=? AND deleted=1", (pid,)).fetchone()
        if not p:
            flash(_i18n.t("回收站中不存在该备件", _i18n.current_lang()), "danger")
            return redirect(url_for("recycle_page"))
        note = ""
        loc_id = p["location_id"]
        if loc_id:
            # 库位占用：其他未删除备件在该位置有库存，或其他备件固定占用该位置
            occ = conn.execute(
                """SELECT p2.part_code FROM inventory i
                   JOIN parts p2 ON i.part_id=p2.id AND p2.deleted=0
                   WHERE i.location_id=? AND i.part_id<>? AND i.quantity>0 LIMIT 1""",
                (loc_id, pid),
            ).fetchone()
            occ2 = conn.execute(
                "SELECT part_code FROM parts WHERE location_id=? AND id<>? AND deleted=0 LIMIT 1",
                (loc_id, pid),
            ).fetchone()
            if occ or occ2:
                conn.execute("UPDATE parts SET location_id=NULL WHERE id=?", (pid,))
                note = "；原固定库位已被其他备件占用，恢复后位置为【待定】，请重新指定"
        conn.execute("UPDATE parts SET deleted=0, deleted_at=NULL WHERE id=?", (pid,))
        conn.commit()
        try:
            _audit("part", pid, p["part_code"], "restore", {"note": "恢复备件" + (("；" + note.replace("；", "")) if note else "")}, conn=conn)
        except Exception:
            pass
        flash(f"备件 [{p['part_code']}] 已恢复{note}", "success")
    finally:
        conn.close()
    return redirect(url_for("recycle_page"))


@app.route("/parts/recycle/purge", methods=["POST"])
@login_required
@role_required("admin")
def recycle_purge():
    """彻底删除回收站中的单条备件（不可恢复）"""
    try:
        pid = int(request.form.get("pid", 0))
    except (TypeError, ValueError):
        pid = 0
    conn = get_db()
    try:
        p = conn.execute("SELECT part_code FROM parts WHERE id=? AND deleted=1", (pid,)).fetchone()
        if not p:
            flash(_i18n.t("回收站中不存在该备件", _i18n.current_lang()), "danger")
            return redirect(url_for("recycle_page"))
        try:
            _audit("part", pid, p["part_code"], "purge", {"note": "彻底删除备件"}, conn=conn)
        except Exception:
            pass
        _purge_part(conn, pid)
        conn.commit()
        flash(f"备件 [{p['part_code']}] 已彻底删除（不可恢复）", "warning")
    finally:
        conn.close()
    return redirect(url_for("recycle_page"))


@app.route("/parts/recycle/purge-all", methods=["POST"])
@login_required
@role_required("admin")
def recycle_purge_all():
    """清空回收站（所有已删除备件彻底清除）"""
    conn = get_db()
    try:
        rows = conn.execute("SELECT id, part_code FROM parts WHERE deleted=1").fetchall()
        for r in rows:
            try:
                _audit("part", r["id"], r["part_code"], "purge", {"note": "清空回收站（彻底删除）"}, conn=conn)
            except Exception:
                pass
            _purge_part(conn, r["id"])
        conn.commit()
        flash(_i18n.t("回收站已清空（{0} 条已彻底删除）", _i18n.current_lang()).format(len(rows)), "warning")
    finally:
        conn.close()
    return redirect(url_for("recycle_page"))


@app.route("/parts/recycle/settings", methods=["POST"])
@login_required
@role_required("admin")
def recycle_settings():
    """回收站保留天数设置（默认 3 天，超期自动彻底清除）"""
    try:
        days = max(1, min(int(request.form.get("days", 3)), 365))
    except (TypeError, ValueError):
        days = 3
    conn = get_db()
    try:
        db.set_setting(conn, "recycle_days", str(days))
        conn.commit()
    finally:
        conn.close()
    flash(_i18n.t("回收站保留天数已设置为 {0} 天（超期自动彻底清除）", _i18n.current_lang()).format(days), "success")
    return redirect(url_for("recycle_page"))


# ------------------------------------------------------------------
# 通用回收站（货架位置 / 部门 / 用户）：
#   删除 = 物理删除 + 记录快照进 recycle_items（唯一键随即释放，可新建同名）；
#   恢复 = 从快照重建（保留原 id，库存/流水引用自动重连）；
#   恢复时若已存在相同信息 → 提示「有相同信息已存在，恢复时会覆盖已有信息，请确认」，
#   确认后覆盖（删除现有同名，恢复旧记录）。
# ------------------------------------------------------------------
_RECYCLE_TYPES = {"location": "货架位置", "department": "部门", "user": "用户"}

_RECYCLE_KEY_SQL = {
    "location":   "SELECT id FROM locations WHERE warehouse=? AND rack=? AND shelf=? AND bin=?",
    "department": "SELECT id FROM departments WHERE name=?",
    "user":       "SELECT id FROM users WHERE username=?",
}

_RECYCLE_KEY_VALUES = {
    "location":   lambda d: (d["warehouse"], d["rack"], d["shelf"], d["bin"]),
    "department": lambda d: (d["name"],),
    "user":       lambda d: (d["username"],),
}

_RECYCLE_INSERT_SQL = {
    "location":   "INSERT INTO locations(id, warehouse, rack, shelf, bin, remark, created_at) VALUES(?,?,?,?,?,?,?)",
    "department": "INSERT INTO departments(id, name, remark, created_at) VALUES(?,?,?,?)",
    "user":       "INSERT INTO users(id, username, password_hash, display_name, role, department, active, created_at) VALUES(?,?,?,?,?,?,?,?)",
}

_RECYCLE_ITEM_LABEL = {
    "location":   lambda d: f"{d['warehouse']}-{d['rack']}-{d['shelf']}-{d['bin'] or _i18n.t('整货位')}",
    "department": lambda d: d["name"],
    "user":       lambda d: d["username"],
}


def _recycle_add(conn, item_type, item_id, row):
    """把被物理删除的记录存入通用回收站快照"""
    conn.execute(
        "INSERT INTO recycle_items(item_type, item_id, data, deleted_at) VALUES(?,?,?,?)",
        (item_type, item_id, json.dumps(dict(row), ensure_ascii=False), db.now_str()),
    )


def _recycle_items_list(conn, item_type):
    """通用回收站列表：item_type 全部快照 + 到期自动清除时间"""
    days = _recycle_days(conn)
    now = datetime.now()
    rows = conn.execute(
        "SELECT * FROM recycle_items WHERE item_type=? ORDER BY id DESC", (item_type,)
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["data_obj"] = json.loads(d["data"] or "{}")
        except (TypeError, ValueError):
            d["data_obj"] = {}
        d["label"] = _RECYCLE_ITEM_LABEL[item_type](d["data_obj"])
        d["expire"] = None
        d["expired"] = False
        if d.get("deleted_at"):
            try:
                dt = datetime.strptime(d["deleted_at"][:19], "%Y-%m-%d %H:%M:%S")
                d["expire"] = (dt + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
                d["expired"] = now >= dt + timedelta(days=days)
            except (ValueError, TypeError):
                pass
        out.append(d)
    return out


def _recycle_find_dup(conn, item_type, data_obj):
    """返回与快照唯一键相同的现存记录 id（无冲突返回 None）"""
    sql = _RECYCLE_KEY_SQL[item_type]
    vals = _RECYCLE_KEY_VALUES[item_type](data_obj)
    row = conn.execute(sql, vals).fetchone()
    return row["id"] if row else None


def _recycle_restore_other(conn, item_type, item_id, force=False):
    """恢复一条通用回收站记录。返回 (ok, msg, need_confirm)
    - 无同名冲突：直接恢复（保留原 id）
    - 有同名冲突且未 force：返回 need_confirm=True，等待用户确认覆盖
    - force=True：删除现有同名后恢复旧记录（覆盖），位置被占时顺带把库存引用改回原 id"""
    r = conn.execute(
        "SELECT * FROM recycle_items WHERE item_type=? AND item_id=?",
        (item_type, item_id),
    ).fetchone()
    if not r:
        return False, "回收站中不存在该记录", False
    try:
        data_obj = json.loads(r["data"] or "{}")
    except (TypeError, ValueError):
        return False, "回收站记录数据损坏，无法恢复", False
    dup_id = _recycle_find_dup(conn, item_type, data_obj)
    if dup_id is not None and not force:
        return False, "", True   # 需确认：有相同信息已存在
    if dup_id is not None:
        # 覆盖：删除现有同名记录；位置的库存引用改指回原 id（避免悬空）
        if item_type == "location":
            conn.execute(
                "UPDATE inventory SET location_id=? WHERE location_id=?",
                (item_id, dup_id),
            )
            conn.execute("UPDATE parts SET location_id=? WHERE location_id=?", (item_id, dup_id))
        conn.execute("DELETE FROM locations WHERE id=?" if item_type == "location"
                     else "DELETE FROM departments WHERE id=?" if item_type == "department"
                     else "DELETE FROM users WHERE id=?", (dup_id,))
    if item_type == "location":
        try:
            _audit("rack", item_id, _RECYCLE_ITEM_LABEL[item_type](data_obj), "restore", {"note": "从回收站恢复货架位置"}, conn=conn)
        except Exception:
            pass
    sql = _RECYCLE_INSERT_SQL[item_type]
    if item_type == "location":
        conn.execute(sql, (item_id, data_obj.get("warehouse", ""), data_obj.get("rack", ""),
                           data_obj.get("shelf", ""), data_obj.get("bin", "") or "",
                           data_obj.get("remark", "") or "", data_obj.get("created_at") or db.now_str()))
    elif item_type == "department":
        conn.execute(sql, (item_id, data_obj.get("name", ""), data_obj.get("remark", "") or "",
                           data_obj.get("created_at") or db.now_str()))
    else:
        conn.execute(sql, (item_id, data_obj.get("username", ""), data_obj.get("password_hash", ""),
                           data_obj.get("display_name", ""), data_obj.get("role", "user"),
                           data_obj.get("department", "") or "", data_obj.get("active", 1),
                           data_obj.get("created_at") or db.now_str()))
    conn.execute("DELETE FROM recycle_items WHERE id=?", (r["id"],))
    conn.commit()
    return True, f"[{_RECYCLE_ITEM_LABEL[item_type](data_obj)}] 已恢复", False


@app.route("/recycle/restore-other", methods=["POST"])
@login_required
@role_required("admin")
def recycle_restore_other():
    """恢复货架位置/部门/用户；有相同信息已存在时需确认覆盖"""
    item_type = request.form.get("type", "")
    try:
        item_id = int(request.form.get("item_id", 0))
    except (TypeError, ValueError):
        item_id = 0
    force = request.form.get("force") == "1"
    if item_type not in _RECYCLE_TYPES:
        flash(_i18n.t("无效的回收站类型", _i18n.current_lang()), "danger")
        return redirect(url_for("recycle_page"))
    conn = get_db()
    try:
        ok, msg, need_confirm = _recycle_restore_other(conn, item_type, item_id, force)
    finally:
        conn.close()
    if need_confirm:
        # 有相同信息已存在：提示确认覆盖，待用户在页面确认后以 force 提交
        session["cover_pending"] = {"item_type": item_type, "item_id": item_id}
        flash(_i18n.t("有相同信息已存在，恢复时会覆盖已有信息，请确认", _i18n.current_lang()), "warning")
        return redirect(url_for("recycle_page"))
    if ok:
        session.pop("cover_pending", None)
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("recycle_page"))


@app.route("/recycle/cover-confirm", methods=["POST"])
@login_required
@role_required("admin")
def recycle_cover_confirm():
    """用户确认覆盖后，强制恢复（覆盖现有同名记录）"""
    pend = session.pop("cover_pending", None)
    if not pend or pend.get("item_type") not in _RECYCLE_TYPES:
        flash(_i18n.t("没有待确认的覆盖恢复操作", _i18n.current_lang()), "warning")
        return redirect(url_for("recycle_page"))
    conn = get_db()
    try:
        ok, msg, _ = _recycle_restore_other(conn, pend["item_type"], pend.get("item_id", 0), force=True)
    finally:
        conn.close()
    if ok:
        flash(msg + "（已覆盖同名信息）", "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("recycle_page"))


@app.route("/recycle/cover-cancel", methods=["POST"])
@login_required
@role_required("admin")
def recycle_cover_cancel():
    """取消待确认的覆盖恢复"""
    pend = session.pop("cover_pending", None)
    if pend and pend.get("item_type") in _RECYCLE_TYPES:
        flash(_i18n.t("已取消覆盖恢复", _i18n.current_lang()), "warning")
    return redirect(url_for("recycle_page"))


@app.route("/recycle/purge-other", methods=["POST"])
@login_required
@role_required("admin")
def recycle_purge_other():
    """彻底删除一条通用回收站记录（不可恢复）"""
    item_type = request.form.get("type", "")
    try:
        rid = int(request.form.get("rid", 0))
    except (TypeError, ValueError):
        rid = 0
    if item_type not in _RECYCLE_TYPES or not rid:
        flash(_i18n.t("无效的回收站记录", _i18n.current_lang()), "danger")
        return redirect(url_for("recycle_page"))
    conn = get_db()
    try:
        rrow = conn.execute("SELECT * FROM recycle_items WHERE id=? AND item_type=?", (rid, item_type)).fetchone()
        if rrow and item_type == "location":
            try:
                dobj = json.loads(rrow["data"] or "{}")
                _audit("rack", rrow["item_id"], _RECYCLE_ITEM_LABEL[item_type](dobj), "purge", {"note": "彻底删除货架位置"}, conn=conn)
            except Exception:
                pass
        conn.execute("DELETE FROM recycle_items WHERE id=? AND item_type=?", (rid, item_type))
        conn.commit()
    finally:
        conn.close()
    flash(_i18n.t("记录已彻底删除（不可恢复）", _i18n.current_lang()), "warning")
    return redirect(url_for("recycle_page"))


@app.route("/recycle/purge-all-other", methods=["POST"])
@login_required
@role_required("admin")
def recycle_purge_all_other():
    """清空指定类型的通用回收站记录"""
    item_type = request.form.get("type", "")
    if item_type not in _RECYCLE_TYPES:
        flash(_i18n.t("无效的回收站类型", _i18n.current_lang()), "danger")
        return redirect(url_for("recycle_page"))
    conn = get_db()
    try:
        cur = conn.execute("DELETE FROM recycle_items WHERE item_type=?", (item_type,))
        conn.commit()
        n = cur.rowcount
    finally:
        conn.close()
    flash(_i18n.t("已彻底删除 {0} 条记录（不可恢复）", _i18n.current_lang()).format(n), "warning")
    return redirect(url_for("recycle_page"))


def _recycle_cleanup_once():
    """彻底清除所有超过保留天数的已删除备件与通用回收站记录（返回清除条数；供后台线程与测试调用）"""
    if not config.DB_PATH or not os.path.exists(config.DB_PATH):
        return 0
    days = _recycle_days()
    cut = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id FROM parts WHERE deleted=1 AND deleted_at IS NOT NULL AND deleted_at<=?",
            (cut,),
        ).fetchall()
        for r in rows:
            _purge_part(conn, r["id"])
        n = len(rows)
        # 通用回收站（位置/部门/用户）超期自动彻底清除
        n2 = conn.execute(
            "DELETE FROM recycle_items WHERE deleted_at IS NOT NULL AND deleted_at<=?", (cut,)
        ).rowcount
        if rows or n2:
            conn.commit()
        return n + n2
    finally:
        conn.close()


def _recycle_worker():
    """回收站自动清理线程：每小时检查一次，彻底清除超过保留天数的已删除备件"""
    log = logging.getLogger("recycle")
    while True:
        try:
            n = _recycle_cleanup_once()
            if n:
                log.info("回收站自动清理 %s 条", n)
        except Exception as e:
            log.warning("回收站自动清理失败：%s", e)
        time.sleep(3600)


@app.route("/parts/<int:pid>/image", methods=["POST"])
@login_required
@perm_required("parts_manage", "edit")
def part_upload_image(pid):
    file = request.files.get("image")
    if not file or not file.filename:
        flash(_i18n.t("请选择图片文件", _i18n.current_lang()), "danger")
        return redirect(url_for("parts_manage_page", _anchor=f"part-{pid}"))
    conn = get_db()
    try:
        _save_part_image(conn, pid, file)
    finally:
        conn.close()
    return redirect(url_for("parts_manage_page", _anchor=f"part-{pid}"))


@app.route("/parts/<int:pid>/image/delete", methods=["POST"])
@login_required
@perm_required("parts_manage", "edit")
def part_delete_image(pid):
    """删除备件图片（编辑备件中操作）"""
    conn = get_db()
    try:
        p = conn.execute("SELECT image_file FROM parts WHERE id=?", (pid,)).fetchone()
        if not p:
            flash(_i18n.t("备件不存在", _i18n.current_lang()), "danger")
            return redirect(url_for("parts_manage_page"))
        if p["image_file"]:
            db.image_delete(conn, p["image_file"])
            fp = os.path.join(config.resolved_upload_dir(), p["image_file"])
            if os.path.exists(fp):
                try:
                    os.remove(fp)
                except OSError:
                    pass
            conn.execute("UPDATE parts SET image_file='' WHERE id=?", (pid,))
            conn.commit()
            flash(_i18n.t("备件图片已删除", _i18n.current_lang()), "success")
        else:
            flash(_i18n.t("该备件暂无图片", _i18n.current_lang()), "warning")
    finally:
        conn.close()
    return redirect(url_for("parts_manage_page", _anchor=f"part-{pid}"))


@app.route("/media/<path:fname>")
def media(fname):
    """提供图片：优先从主数据库 images 表读取（图片已入库），
    旧版遗留的 upload_dir 目录文件仍可回退读取（兼容历史数据）"""
    from flask import Response, send_file
    fname = os.path.basename(fname)  # 只允许单文件名，防路径穿越
    if not db_configured():
        abort(404)
    conn = get_db()
    try:
        data = db.image_load(conn, fname)
        if data is not None:
            mime = "image/png"
            ext = os.path.splitext(fname)[1].lower()
            if ext in (".jpg", ".jpeg"):
                mime = "image/jpeg"
            elif ext == ".gif":
                mime = "image/gif"
            elif ext == ".bmp":
                mime = "image/bmp"
            elif ext == ".webp":
                mime = "image/webp"
            return Response(data, mimetype=mime, headers={"Cache-Control": "private, max-age=3600"})
    finally:
        conn.close()
    # 回退：旧版目录文件
    full = os.path.realpath(os.path.join(config.resolved_upload_dir(), fname))
    base = os.path.realpath(config.resolved_upload_dir())
    if not full.startswith(base + os.sep) or not os.path.isfile(full):
        abort(404)
    return send_file(full)


# ------------------------------------------------------------------
# 备件多库位配置（备件信息维护 → 编辑备件）：一个备件可占用多个货位
# ------------------------------------------------------------------
@app.route("/parts/<int:pid>/locations/add", methods=["POST"])
@login_required
@perm_required("parts_manage", "edit")
def part_location_add(pid):
    """为备件新增一个库存库位（位置 + 数量，数量可空=0 仅登记位置）；位置被其他备件占用时拒绝"""
    f = request.form
    qty = _num(f.get("qty", 0))
    if qty < 0:
        qty = 0
    lid = f.get("location_id", "").strip()
    if not lid:
        flash(_i18n.t("请选择库位（仓库号-货架号-货位号-格位号）", _i18n.current_lang()), "danger")
        return redirect(url_for("parts_manage_page", _anchor=f"part-{pid}"))
    conn = get_db()
    try:
        part = conn.execute(
            "SELECT qty_decimal, unit FROM parts WHERE id=? AND deleted=0", (pid,)
        ).fetchone()
        if part and not part["qty_decimal"]:
            if qty != int(qty):
                flash(f"该备件按『{part['unit']}』整数计数，库存数量不能填小数", "danger")
                return redirect(url_for("parts_manage_page", _anchor=f"part-{pid}"))
            qty = int(qty)
        loc = conn.execute("SELECT * FROM locations WHERE id=?", (int(lid),)).fetchone()
        if not loc:
            flash(_i18n.t("所选位置不存在，请先在货架管理中建立", _i18n.current_lang()), "danger")
            return redirect(url_for("parts_manage_page", _anchor=f"part-{pid}"))
        occ = conn.execute(
            """SELECT i.part_id, p.part_code FROM inventory i
               JOIN parts p ON i.part_id=p.id AND p.deleted=0
               WHERE i.location_id=? AND i.part_id<>? LIMIT 1""",
            (int(lid), pid),
        ).fetchone()
        if occ:
            flash(f"该位置已配置给备件 [{occ['part_code']}]，不能重复配置；请先将其调走", "danger")
            return redirect(url_for("parts_manage_page", _anchor=f"part-{pid}"))
        ok, msg = db.move_stock(conn, pid, int(lid), qty)
        if not ok:
            flash(msg, "danger")
            return redirect(url_for("parts_manage_page", _anchor=f"part-{pid}"))
        conn.commit()
        if qty > 0:
            flash(_i18n.t("已为备件增加库位 [{0}]，库存 +{1}", _i18n.current_lang()).format(db.location_text(loc), qty), "success")
        else:
            flash(_i18n.t("已为备件登记库位 [{0}]（库存 0，可后续入库）", _i18n.current_lang()).format(db.location_text(loc)), "success")
    finally:
        conn.close()
    return redirect(url_for("parts_manage_page", _anchor=f"part-{pid}"))


@app.route("/parts/<int:pid>/locations/<int:inv_id>/delete", methods=["POST"])
@login_required
@perm_required("parts_manage", "edit")
def part_location_delete(pid, inv_id):
    """删除备件的一个库存库位（仅该库位库存为 0 时可删）"""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM inventory WHERE id=? AND part_id=?", (inv_id, pid)
        ).fetchone()
        if not row:
            flash(_i18n.t("该库存库位不存在", _i18n.current_lang()), "danger")
            return redirect(url_for("parts_manage_page", _anchor=f"part-{pid}"))
        if row["quantity"] > 0:
            flash(f"库位 [{row['location']}] 仍有库存 {row['quantity']}，不能删除；请先出库/调拨清零", "danger")
            return redirect(url_for("parts_manage_page", _anchor=f"part-{pid}"))
        conn.execute("DELETE FROM inventory WHERE id=?", (inv_id,))
        conn.commit()
        flash(f"库位 [{row['location']}] 已删除", "success")
    finally:
        conn.close()
    return redirect(url_for("parts_manage_page", _anchor=f"part-{pid}"))


@app.route("/parts/<int:pid>/locations/<int:inv_id>/set-primary", methods=["POST"])
@login_required
@perm_required("parts_manage", "edit")
def part_location_set_primary(pid, inv_id):
    """（已废弃：多库位平等，无主放置位置概念）仅兼容旧入口，直接返回"""
    return redirect(url_for("parts_manage_page", _anchor=f"part-{pid}"))


# ------------------------------------------------------------------
# 货架位置管理（仓库号-货架号-货位号-格位号，仓管员以上）
# ------------------------------------------------------------------
@app.route("/locations")
@login_required
@perm_required("parts_manage")
def locations_page():
    conn = get_db()
    try:
        rows = _all_locations(conn)
    finally:
        conn.close()
    return render_template("locations.html", locations=rows)


@app.route("/audit")
@login_required
def audit_page():
    """操作审计查询：备件 / 货架位置的 新增、编辑、删除、恢复、彻底清除"""
    t = request.args.get("type", "part")
    if t not in ("part", "rack"):
        t = "part"
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    per = 20
    conn = get_db()
    try:
        tot = conn.execute("SELECT COUNT(*) FROM audit_log WHERE obj_type=?", (t,)).fetchone()[0]
        pages = max(1, (tot + per - 1) // per)
        page = min(page, pages)
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM audit_log WHERE obj_type=? ORDER BY id DESC LIMIT ? OFFSET ?",
            (t, per, (page - 1) * per),
        ).fetchall()]
        for r in rows:
            try:
                r["d"] = json.loads(r.get("detail") or "{}")
            except (TypeError, ValueError):
                r["d"] = {}
    finally:
        conn.close()
    return render_template("audit.html", rows=rows, t=t, page=page, pages=pages, tot=tot,
                           PART_FIELD_NAMES=PART_FIELD_NAMES, _fmt_part_val=_fmt_part_val)


@app.route("/locations/add", methods=["POST"])
@login_required
@perm_required("parts_manage")
def location_add():
    f = request.form
    warehouse = f.get("warehouse", "").strip()
    rack = f.get("rack", "").strip()
    shelf = f.get("shelf", "").strip()
    bin_ = f.get("bin", "").strip()   # 格位号可空：空 = 整个货位
    remark = f.get("remark", "").strip()
    if not (warehouse and rack and shelf):
        flash(_i18n.t("仓库号、货架号、货位号为必填项（格位号可空）", _i18n.current_lang()), "danger")
        return redirect(url_for("locations_page"))
    if len(warehouse) > 20 or len(rack) > 20 or len(shelf) > 20 or len(bin_) > 20:
        flash(_i18n.t("仓库号/货架号/货位号/格位号长度不能超过 20 字符", _i18n.current_lang()), "danger")
        return redirect(url_for("locations_page"))
    conn = get_db()
    try:
        if conn.execute(
            "SELECT id FROM locations WHERE warehouse=? AND rack=? AND shelf=? AND bin=?",
            (warehouse, rack, shelf, bin_),
        ).fetchone():
            flash(f"位置 [{warehouse}-{rack}-{shelf}-{bin_ or '(整货位)'}] 已存在", "danger")
            return redirect(url_for("locations_page"))
        cur = conn.execute(
            "INSERT INTO locations(warehouse,rack,shelf,bin,remark,created_at) VALUES(?,?,?,?,?,?)",
            (warehouse, rack, shelf, bin_, remark, db.now_str()),
        )
        conn.commit()
        try:
            _audit("rack", cur.lastrowid, f"{warehouse}-{rack}-{shelf}-{bin_ or ''}", "add", {"note": "建立货架位置"}, conn=conn)
        except Exception:
            pass
        flash(f"位置 [{warehouse}-{rack}-{shelf}-{bin_ or '(整货位)'}] 已建立", "success")
    finally:
        conn.close()
    return redirect(url_for("locations_page"))


@app.route("/locations/<int:lid>/delete", methods=["POST"])
@login_required
@perm_required("parts_manage")
def location_delete(lid):
    conn = get_db()
    try:
        loc = conn.execute("SELECT * FROM locations WHERE id=?", (lid,)).fetchone()
        if not loc:
            flash(_i18n.t("位置不存在", _i18n.current_lang()), "danger")
            return redirect(url_for("locations_page"))
        occ = conn.execute(
            """SELECT p.part_code FROM inventory i JOIN parts p ON i.part_id=p.id AND p.deleted=0
               WHERE i.location_id=? AND i.quantity>0 LIMIT 1""", (lid,)
        ).fetchone()
        if occ:
            flash(f"该位置正被备件 [{occ['part_code']}] 存放库存，请先将其调走/出库", "danger")
            return redirect(url_for("locations_page"))
        _recycle_add(conn, "location", lid, loc)
        try:
            _audit("rack", lid, f"{loc['warehouse']}-{loc['rack']}-{loc['shelf']}-{loc['bin'] or ''}", "delete", {"note": "删除货架位置（进入回收站）"}, conn=conn)
        except Exception:
            pass
        conn.execute("DELETE FROM locations WHERE id=?", (lid,))
        conn.commit()
        flash(_i18n.t("位置 [{0}-{1}-{2}-{3}] 已删除并进入回收站（管理员可恢复）", _i18n.current_lang())
              .format(loc['warehouse'], loc['rack'], loc['shelf'], loc['bin'] or _i18n.t('整货位')), "success")
    finally:
        conn.close()
    return redirect(url_for("locations_page"))


# ------------------------------------------------------------------
# 直接出入库（仓库人员）
# ------------------------------------------------------------------
@app.route("/inout")
@login_required
@perm_required("stock_inout")
def inout_page():
    """出入库管理：直接出入库 + 待处理的申请单（执行/驳回/撤销请求审批）+ 可按时间/类型筛选流水"""
    user = current_user()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    f_type = request.args.get("f_type", "").strip()
    conn = get_db()
    try:
        where = []
        args = []
        if date_from:
            where.append("t.created_at>=?")
            args.append(date_from + " 00:00:00")
        if date_to:
            where.append("t.created_at<=?")
            args.append(date_to + " 23:59:59")
        if f_type in ("in", "out", "transfer"):
            where.append("t.tx_type=?")
            args.append(f_type)
        cond = (" WHERE " + " AND ".join(where)) if where else ""
        # 流水分页：每页条数可在 5/10/20/100/全部 间切换（默认 10，记忆在当前电脑）
        per_page_raw = request.args.get("per_page", "")
        if per_page_raw not in ("5", "10", "20", "100", "all"):
            per_page_raw = str(session.get("inout_per_page", 10))
        session["inout_per_page"] = per_page_raw
        per_page = None if per_page_raw == "all" else int(per_page_raw)
        page = max(1, request.args.get("page", 1, type=int))
        total = conn.execute(
            "SELECT COUNT(*) c FROM transactions t" + cond, args
        ).fetchone()["c"]
        pages = 1
        if per_page:
            pages = max(1, (total + per_page - 1) // per_page)
            page = min(page, pages)
            txs = conn.execute(
                """SELECT t.*, p.part_code, p.name, u.display_name op_name
                   FROM transactions t
                   LEFT JOIN parts p ON t.part_id=p.id
                   LEFT JOIN users u ON t.operator_id=u.id"""
                + cond + " ORDER BY t.id DESC LIMIT ? OFFSET ?",
                args + [per_page, (page - 1) * per_page],
            ).fetchall()
        else:
            txs = conn.execute(
                """SELECT t.*, p.part_code, p.name, u.display_name op_name
                   FROM transactions t
                   LEFT JOIN parts p ON t.part_id=p.id
                   LEFT JOIN users u ON t.operator_id=u.id"""
                + cond + " ORDER BY t.id DESC",
                args,
            ).fetchall()
        # 待处理申请单（供仓管员执行/驳回；撤销请求供审批）
        pending_apps = conn.execute(
            """SELECT a.*, p.part_code, p.name, p.unit, p.is_valuable, u.display_name app_name,
                      CASE WHEN l.bin='' THEN l.warehouse||'-'||l.rack||'-'||l.shelf
                           ELSE l.warehouse||'-'||l.rack||'-'||l.shelf||'-'||l.bin END AS location_text,
                      CASE WHEN fl.bin='' THEN fl.warehouse||'-'||fl.rack||'-'||fl.shelf
                           ELSE fl.warehouse||'-'||fl.rack||'-'||fl.shelf||'-'||fl.bin END AS from_loc_text,
                      CASE WHEN tl.bin='' THEN tl.warehouse||'-'||tl.rack||'-'||tl.shelf
                           ELSE tl.warehouse||'-'||tl.rack||'-'||tl.shelf||'-'||tl.bin END AS to_loc_text
               FROM applications a
               LEFT JOIN parts p ON a.part_id=p.id
               LEFT JOIN locations l ON p.location_id=l.id
               LEFT JOIN locations fl ON a.from_location_id=fl.id
               LEFT JOIN locations tl ON a.to_location_id=tl.id
               LEFT JOIN users u ON a.applicant_id=u.id
               WHERE a.status IN ('pending','approved','cancel_req')
               ORDER BY a.id DESC LIMIT 200"""
        ).fetchall()
        # 多库位：待处理列表显示该备件所有存放库位
        pending_apps = [dict(r) for r in pending_apps]
        for a in pending_apps:
            sls = db.stock_locations(conn, a["part_id"])
            a["all_locs_text"] = "；".join(
                f"{s['location']} ×{s['quantity']}" for s in sls if s["quantity"])
        locations = _all_locations(conn)
        # 直出表单数据：申请人 / 审批经理 / 产线设备
        users = conn.execute(
            "SELECT id, display_name, department FROM users WHERE active=1 ORDER BY department, id"
        ).fetchall()
        managers = conn.execute(
            "SELECT id, display_name, department FROM users WHERE role='manager' AND active=1 ORDER BY department, id"
        ).fetchall()
        lines = db.list_lines(conn)
        equipment = db.list_equipment(conn)
        _lm = {l["id"]: l["name"] for l in lines}
        for _e in equipment:
            _e["line_name"] = _lm.get(_e["line_id"], "")
    finally:
        conn.close()
    return render_template("inout.html", txs=txs, pending_apps=pending_apps,
                           locations=locations, cur_uid=user["id"], cur_role=user["role"],
                           users=users, managers=managers, lines=lines, equipment=equipment,
                           date_from=date_from, date_to=date_to, f_type=f_type,
                           tx_total=total, tx_page=page, tx_pages=pages,
                           tx_per_page=per_page_raw)


@app.route("/inout/export")
@login_required
@perm_required("stock_inout", "export")
def inout_export():
    """按当前筛选条件导出出入库流水为 Excel（.xlsx，纯标准库生成）"""
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    f_type = request.args.get("f_type", "").strip()
    conn = get_db()
    try:
        where = []
        args = []
        if date_from:
            where.append("t.created_at>=?")
            args.append(date_from + " 00:00:00")
        if date_to:
            where.append("t.created_at<=?")
            args.append(date_to + " 23:59:59")
        if f_type in ("in", "out", "transfer"):
            where.append("t.tx_type=?")
            args.append(f_type)
        cond = (" WHERE " + " AND ".join(where)) if where else ""
        rows = conn.execute(
            """SELECT t.*, p.part_code, p.name, p.unit, u.display_name op_name
               FROM transactions t
               LEFT JOIN parts p ON t.part_id=p.id
               LEFT JOIN users u ON t.operator_id=u.id"""
            + cond + " ORDER BY t.id DESC LIMIT 10000",
            args,
        ).fetchall()
    finally:
        conn.close()
    type_name = {"in": "入库", "out": "出库", "transfer": "调库"}
    headers = ["单号", "时间", "料号", "名称", "单位", "类型", "库位", "数量",
               "单价", "金额(元)", "操作人", "备注"]
    data = []
    for r in rows:
        data.append([
            r["tx_no"], r["created_at"] or "", r["part_code"] or "", r["name"] or "",
            r["unit"] or "", type_name.get(r["tx_type"], r["tx_type"]),
            r["location"] or "", r["quantity"],
            round(r["unit_price"], 4), round(r["amount"], 2),
            r["op_name"] or "", r["remark"] or "",
        ])
    buf = _export_xlsx(headers, data, "出入库流水")
    return send_file(buf, as_attachment=True,
                     download_name=f"出入库流水_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ------------------------------------------------------------------
# 呆滞物料管理（以料号为锚点：超过 N 天未领用即呆滞，默认 90 天）
# ------------------------------------------------------------------
def _stale_rows(conn, stale_days, kw="", only_stale=True):
    """呆滞备件列表：有库存的备件，参考日=最后出库日(未出库过=建档日)，距今超 N 天=呆滞"""
    where = []
    args = []
    if kw:
        where.append("(p.part_code LIKE ? OR p.name LIKE ?)")
        args += [f"%{kw}%", f"%{kw}%"]
    sql = """SELECT p.id, p.part_code, p.name, p.unit, p.unit_price, p.qty_decimal, p.created_at,
                    (SELECT MAX(t.created_at) FROM transactions t
                      WHERE t.part_id=p.id AND t.tx_type='out') last_out
             FROM parts p
             WHERE p.deleted=0
               AND p.id IN (SELECT part_id FROM inventory GROUP BY part_id HAVING SUM(quantity)>0)
               AND """ + (" AND ".join(where) if where else "1=1") + """
             ORDER BY p.part_code"""
    rows = conn.execute(sql, args).fetchall()
    today = datetime.now().date()
    out = []
    for r in rows:
        last_out = r["last_out"]
        ref = last_out or r["created_at"] or today.strftime("%Y-%m-%d")
        try:
            ref_date = datetime.strptime(str(ref)[:10], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            ref_date = today
        days = (today - ref_date).days
        if days < 0:
            days = 0
        is_stale = days >= stale_days
        if only_stale and not is_stale:
            continue
        d = dict(r)
        d["last_out"] = last_out
        d["ref_date"] = str(ref_date)
        d["days"] = days
        d["stale"] = is_stale
        d["total_stock"] = db.total_stock(conn, r["id"])
        d["amount"] = round(d["total_stock"] * (d["unit_price"] or 0), 2)
        d["locs"] = "；".join(f"{s['location']} ×{s['quantity']}" for s in db.stock_locations(conn, r["id"]) if s["quantity"])
        out.append(d)
    out.sort(key=lambda x: (x["stale"] is False, -x["days"]))
    return out


def _stale_summary(conn, stale_days, top=10):
    """呆滞汇总：呆滞料号数、呆滞库存金额、呆滞 Top 列表（按未领用天数降序）"""
    rows = _stale_rows(conn, stale_days, "", only_stale=True)
    count = len(rows)
    amount = round(sum(r["amount"] for r in rows), 2)
    top_rows = rows[: max(1, top)]
    return {
        "days": stale_days,
        "count": count,
        "amount": amount,
        "top": top_rows,
    }


@app.route("/stale")
@login_required
@perm_required("stale")
def stale_page():
    """呆滞物料管理：按料号统计未领用天数，超过阈值（系统设置可配，默认90天）判定为呆滞"""
    conn = get_db()
    try:
        stale_days = _stale_days(conn)
        kw = request.args.get("q", "").strip()
        f_stale = request.args.get("f_stale", "all").strip()
        rows = _stale_rows(conn, stale_days, kw, only_stale=(f_stale == "stale"))
        if f_stale == "normal":
            rows = [r for r in rows if not r["stale"]]
    finally:
        conn.close()
    return render_template("stale.html", rows=rows, stale_days=stale_days,
                           q=kw, f_stale=f_stale)


@app.route("/stale/export")
@login_required
@perm_required("stale", "export")
def stale_export():
    """导出呆滞物料清单为 Excel"""
    conn = get_db()
    try:
        stale_days = _stale_days(conn)
        kw = request.args.get("q", "").strip()
        f_stale = request.args.get("f_stale", "all").strip()
        rows = _stale_rows(conn, stale_days, kw, only_stale=(f_stale == "stale"))
        if f_stale == "normal":
            rows = [r for r in rows if not r["stale"]]
    finally:
        conn.close()
    headers = ["料号", "名称", "单位", "当前库存", "库位分布", "最后领用日期",
               "参考日期", "未领用天数", f"呆滞阈值(天)={stale_days}", "状态", "单价(元)", "库存金额(元)"]
    data = []
    for r in rows:
        data.append([
            r["part_code"], r["name"], r["unit"], r["total_stock"], r["locs"],
            r["last_out"] or "从未出库", r["ref_date"], r["days"], stale_days,
            "呆滞" if r["stale"] else "正常", round(r["unit_price"] or 0, 4), r["amount"],
        ])
    buf = _export_xlsx(headers, data, "呆滞物料清单")
    return send_file(buf, as_attachment=True,
                     download_name=f"呆滞物料清单_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/inout/do", methods=["POST"])
@login_required
@perm_required("stock_inout", "execute")
def inout_do():
    """直接出入库：
    - 入库：仓库直接入库（不经过申请单）
    - 出库：与「出入库调库申请」中的出库业务一致——记录数量、申请人、使用线别、使用设备、原因；
      贵重备件出库自动转入审批流（审批经理审批通过后由仓库执行），非贵重直接扣库存"""
    f = request.form
    pid = int(f.get("part_id", 0))
    tx_type = f.get("tx_type", "")
    quantity = _num(f.get("quantity", 0))
    reason = (f.get("reason", "") or f.get("remark", "")).strip()
    if not pid or tx_type not in ("in", "out"):
        flash(_i18n.t("参数错误", _i18n.current_lang()), "danger")
        return redirect(url_for("inout_page"))
    if quantity <= 0:
        flash(_i18n.t("数量必须大于 0", _i18n.current_lang()), "danger")
        return redirect(url_for("inout_page"))
    user = current_user()
    conn = get_db()
    try:
        p = conn.execute("SELECT * FROM parts WHERE id=? AND deleted=0", (pid,)).fetchone()
        if not p:
            flash(_i18n.t("备件不存在", _i18n.current_lang()), "danger")
            return redirect(url_for("inout_page"))
        ok, msg = _qty_valid(p, quantity)
        if not ok:
            flash(msg, "danger")
            return redirect(url_for("inout_page"))
        if tx_type == "out" and _part_pending(conn, pid):
            flash(_i18n.t("该备件当前处于「待定」状态（所有库存均无放置位置），不允许领用；请先执行调库到具体位置", _i18n.current_lang()), "danger")
            return redirect(url_for("inout_page"))
        if tx_type == "out":
            # ================= 出库：与申请出库一致的业务流程 =================
            # 申请人（默认当前仓管，可指定其他用户）
            try:
                applicant_id = int(f.get("applicant_id") or 0)
            except (TypeError, ValueError):
                applicant_id = 0
            if not applicant_id:
                applicant_id = user["id"]
            app_user = conn.execute(
                "SELECT * FROM users WHERE id=? AND active=1", (applicant_id,)
            ).fetchone()
            if not app_user:
                flash(_i18n.t("所选申请人不存在或已停用", _i18n.current_lang()), "danger")
                return redirect(url_for("inout_page"))
            use_line = f.get("use_line", "").strip()
            use_device = f.get("use_device", "").strip()
            stock = db.total_stock(conn, pid)
            if quantity > stock:
                flash(f"出库数量超过当前库存（现有 {stock} {p['unit']}）", "danger")
                return redirect(url_for("inout_page"))
            # 贵重备件出库：转入审批流（与申请出库一致）
            assigned_approver_id = None
            if p["is_valuable"]:
                if app_user["role"] == "user":
                    mgr = _dept_manager(conn, app_user)
                    if not mgr:
                        flash(_i18n.t("该申请人所属部门暂无经理可审批贵重备件出库，请联系管理员在用户管理中配置部门经理", _i18n.current_lang()), "danger")
                        return redirect(url_for("inout_page"))
                    assigned_approver_id = mgr["id"]
                else:
                    sel = f.get("approver_id", "").strip()
                    if not sel:
                        flash(_i18n.t("贵重备件出库请选择审批经理", _i18n.current_lang()), "danger")
                        return redirect(url_for("inout_page"))
                    try:
                        sel_id = int(sel)
                    except (TypeError, ValueError):
                        sel_id = 0
                    mgr = conn.execute(
                        "SELECT id FROM users WHERE id=? AND role='manager' AND active=1", (sel_id,)
                    ).fetchone()
                    if not mgr:
                        flash(_i18n.t("所选审批经理不存在或已停用，请重新选择", _i18n.current_lang()), "danger")
                        return redirect(url_for("inout_page"))
                    assigned_approver_id = mgr["id"]
                app_no = db.gen_no("APP", conn, "applications", "app_no")
                conn.execute(
                    """INSERT INTO applications(app_no,part_id,app_type,quantity,reason,
                       line_name,device_name,applicant_id,status,assigned_approver_id,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (app_no, pid, "out", quantity, reason, use_line, use_device,
                     applicant_id, "pending", assigned_approver_id, db.now_str()),
                )
                conn.commit()
                mgr_name = conn.execute(
                    "SELECT display_name FROM users WHERE id=?", (assigned_approver_id,)
                ).fetchone()["display_name"]
                flash(f"贵重备件出库已提交审批：{p['part_code']} x{quantity}，待审批经理 [{mgr_name}] 审批后由仓库出库", "success")
                return redirect(url_for("inout_page"))
            # 非贵重：直接出库 = 创建申请单并立即执行（扣库存 + 记流水，含申请人/线别/设备/原因）
            loc_key, loc_text, err = _parse_exec_location(conn, f, p, True)
            if err:
                flash(err, "danger")
                return redirect(url_for("inout_page"))
            app_no = db.gen_no("APP", conn, "applications", "app_no")
            cur = conn.execute(
                """INSERT INTO applications(app_no,part_id,app_type,quantity,reason,
                   line_name,device_name,applicant_id,status,assigned_approver_id,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (app_no, pid, "out", quantity, reason, use_line, use_device,
                 applicant_id, "completed", None, db.now_str()),
            )
            aid = cur.lastrowid
            ok, msg = db.move_stock(conn, pid, loc_key, -quantity)
            if not ok:
                flash(msg, "danger")
                return redirect(url_for("inout_page"))
            amount = round(quantity * p["unit_price"], 2)
            conn.execute(
                """INSERT INTO transactions(tx_no,part_id,tx_type,quantity,unit_price,amount,location,
                   ref_type,ref_id,operator_id,applicant_id,line_name,device_name,remark,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (db.gen_no("TX", conn, "transactions", "tx_no"), pid, "out", quantity,
                 p["unit_price"], amount, loc_text, "application", aid, user["id"],
                 applicant_id, use_line, use_device, reason, db.now_str()),
            )
            conn.execute(
                "UPDATE applications SET operator_id=?, operator_note=?, processed_at=? WHERE id=?",
                (user["id"], "仓管直接出库", db.now_str(), aid),
            )
            conn.commit()
            flash(f"出库成功：{p['part_code']} x{quantity} @ {loc_text}", "success")
            return redirect(url_for("inout_page"))
        # ================= 入库：仓库直接入库 =================
        loc_key, loc_text, err = _parse_exec_location(conn, f, p, False)
        if err:
            flash(err, "danger")
            return redirect(url_for("inout_page"))
        delta = quantity
        ok, msg = db.move_stock(conn, pid, loc_key, delta)
        if not ok:
            flash(msg, "danger")
            return redirect(url_for("inout_page"))
        amount = round(quantity * p["unit_price"], 2)
        tx_no = db.gen_no("TX", conn, "transactions", "tx_no")
        conn.execute(
            """INSERT INTO transactions(tx_no,part_id,tx_type,quantity,unit_price,amount,location,
               ref_type,operator_id,remark,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (tx_no, pid, "in", quantity, p["unit_price"], amount, loc_text,
             "direct", user["id"], reason, db.now_str()),
        )
        conn.commit()
        flash(f"入库成功：{p['part_code']} x{quantity} @ {loc_text}", "success")
    finally:
        conn.close()
    return redirect(url_for("inout_page"))


@app.route("/transfer")
@login_required
@perm_required("apply")
def transfer_page():
    preset_part = request.args.get("part_id", type=int)
    return redirect(url_for("applications_page", part_id=preset_part, app_type="transfer") if preset_part
                    else url_for("applications_page", app_type="transfer"))


@app.route("/transfer/do", methods=["POST"])
@login_required
@perm_required("apply")
def transfer_do():
    return redirect(url_for("applications_page"))


# ------------------------------------------------------------------
# 出入库调库申请（普通用户发起，仓库执行，高级审批贵重出库）
# 说明：申请单列表只显示本用户记录；支持按 日期/类别/状态 筛选与导出 Excel；
#       pending 可直接撤销；已完成/已批准的申请可提交「撤销请求」，由仓管员审批后回滚
# ------------------------------------------------------------------
@app.route("/applications")
@login_required
@perm_required("apply")
def applications_page():
    user = current_user()
    preset_part = request.args.get("part_id", type=int)
    preset_type = request.args.get("app_type", "")
    if preset_type not in ("in", "out", "transfer"):
        preset_type = ""
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    f_type = request.args.get("f_type", "").strip()
    f_status = request.args.get("f_status", "").strip()
    conn = get_db()
    try:
        preset_name = ""
        if preset_part:
            r = conn.execute("SELECT part_code, name FROM parts WHERE id=? AND deleted=0", (preset_part,)).fetchone()
            if r:
                preset_name = f"{r['part_code']}｜{r['name']}"
        where = ["a.applicant_id=?"]
        args = [user["id"]]
        if date_from:
            where.append("a.created_at>=?")
            args.append(date_from + " 00:00:00")
        if date_to:
            where.append("a.created_at<=?")
            args.append(date_to + " 23:59:59")
        if f_type in ("in", "out", "transfer"):
            where.append("a.app_type=?")
            args.append(f_type)
        if f_status in ("pending", "approved", "rejected", "completed", "cancel_req", "canceled"):
            where.append("a.status=?")
            args.append(f_status)
        sql = """SELECT a.*, p.part_code, p.name, p.unit, p.is_valuable, u.display_name app_name,
                        am.display_name approver_name,
                        CASE WHEN l.bin='' THEN l.warehouse||'-'||l.rack||'-'||l.shelf
                             ELSE l.warehouse||'-'||l.rack||'-'||l.shelf||'-'||l.bin END AS location_text,
                        CASE WHEN fl.bin='' THEN fl.warehouse||'-'||fl.rack||'-'||fl.shelf
                             ELSE fl.warehouse||'-'||fl.rack||'-'||fl.shelf||'-'||fl.bin END AS from_loc_text,
                        CASE WHEN tl.bin='' THEN tl.warehouse||'-'||tl.rack||'-'||tl.shelf
                             ELSE tl.warehouse||'-'||tl.rack||'-'||tl.shelf||'-'||tl.bin END AS to_loc_text
                 FROM applications a
                 LEFT JOIN parts p ON a.part_id=p.id
                 LEFT JOIN locations l ON p.location_id=l.id
                 LEFT JOIN locations fl ON a.from_location_id=fl.id
                 LEFT JOIN locations tl ON a.to_location_id=tl.id
                 LEFT JOIN users u ON a.applicant_id=u.id
                 LEFT JOIN users am ON a.assigned_approver_id=am.id
                 WHERE """ + " AND ".join(where) + """
                 ORDER BY a.id DESC"""
        total = conn.execute(
            "SELECT COUNT(*) c FROM applications a WHERE " + " AND ".join(where), args
        ).fetchone()["c"]
        # 申请单分页：每页条数可在 5/10/20/100/全部 间切换（默认 10，记忆在当前电脑）
        per_page_raw = request.args.get("per_page", "")
        if per_page_raw not in ("5", "10", "20", "100", "all"):
            per_page_raw = str(session.get("app_per_page", 10))
        session["app_per_page"] = per_page_raw
        per_page = None if per_page_raw == "all" else int(per_page_raw)
        page = max(1, request.args.get("page", 1, type=int))
        pages = 1
        if per_page:
            pages = max(1, (total + per_page - 1) // per_page)
            page = min(page, pages)
            apps = conn.execute(sql + " LIMIT ? OFFSET ?",
                                args + [per_page, (page - 1) * per_page]).fetchall()
        else:
            apps = conn.execute(sql, args).fetchall()
        # 多库位：申请单列表的位置列显示该备件所有存放库位（便于仓管取放料）
        apps = [dict(r) for r in apps]
        for a in apps:
            sls = db.stock_locations(conn, a["part_id"])
            a["all_locs_text"] = "；".join(
                f"{s['location']} ×{s['quantity']}" for s in sls if s["quantity"])
        locations = _all_locations(conn)
        managers = conn.execute(
            """SELECT id, display_name, department FROM users
               WHERE role='manager' AND active=1 ORDER BY department, id"""
        ).fetchall()
        lines = db.list_lines(conn)
        equipment = db.list_equipment(conn)
        _lm = {l["id"]: l["name"] for l in lines}
        for _e in equipment:
            _e["line_name"] = _lm.get(_e["line_id"], "")
    finally:
        conn.close()
    return render_template("applications.html", apps=apps, locations=locations,
                           cur_uid=user["id"], cur_role=user["role"], managers=managers,
                           preset_part=preset_part, preset_type=preset_type,
                           preset_name=preset_name,
                           date_from=date_from, date_to=date_to,
                           f_type=f_type, f_status=f_status,
                           lines=lines, equipment=equipment,
                           app_total=total, app_page=page, app_pages=pages,
                           app_per_page=per_page_raw)


@app.route("/applications/export")
@login_required
@perm_required("apply")
def applications_export():
    """按当前筛选条件导出「我的申请单」为 Excel（.xlsx，纯标准库生成，无需额外组件）"""
    user = current_user()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    f_type = request.args.get("f_type", "").strip()
    f_status = request.args.get("f_status", "").strip()
    conn = get_db()
    try:
        where = ["a.applicant_id=?"]
        args = [user["id"]]
        if date_from:
            where.append("a.created_at>=?")
            args.append(date_from + " 00:00:00")
        if date_to:
            where.append("a.created_at<=?")
            args.append(date_to + " 23:59:59")
        if f_type in ("in", "out", "transfer"):
            where.append("a.app_type=?")
            args.append(f_type)
        if f_status in ("pending", "approved", "rejected", "completed", "cancel_req", "canceled"):
            where.append("a.status=?")
            args.append(f_status)
        sql = """SELECT a.*, p.part_code, p.name, p.unit,
                        CASE WHEN fl.bin='' THEN fl.warehouse||'-'||fl.rack||'-'||fl.shelf
                             ELSE fl.warehouse||'-'||fl.rack||'-'||fl.shelf||'-'||fl.bin END AS from_loc_text,
                        CASE WHEN tl.bin='' THEN tl.warehouse||'-'||tl.rack||'-'||tl.shelf
                             ELSE tl.warehouse||'-'||tl.rack||'-'||tl.shelf||'-'||tl.bin END AS to_loc_text
                 FROM applications a
                 LEFT JOIN parts p ON a.part_id=p.id
                 LEFT JOIN locations fl ON a.from_location_id=fl.id
                 LEFT JOIN locations tl ON a.to_location_id=tl.id
                 WHERE """ + " AND ".join(where) + """
                 ORDER BY a.id DESC LIMIT 2000"""
        rows = conn.execute(sql, args).fetchall()
    finally:
        conn.close()
    type_name = {"in": "入库", "out": "出库", "transfer": "调库"}
    status_name = {"pending": "待处理", "approved": "已批准·待出库", "rejected": "已驳回",
                   "completed": "已完成", "cancel_req": "撤销待审批", "canceled": "已撤销"}
    headers = ["单号", "申请时间", "料号", "名称", "单位", "类型", "数量",
               "源位置", "目标位置", "使用线别", "使用设备", "申请原因", "状态", "处理意见"]
    data = []
    for r in rows:
        data.append([
            r["app_no"], r["created_at"] or "", r["part_code"] or "", r["name"] or "",
            r["unit"] or "", type_name.get(r["app_type"], r["app_type"]),
            r["quantity"], r["from_loc_text"] or "待定", r["to_loc_text"] or "待定",
            r["line_name"] or "", r["device_name"] or "",
            r["reason"] or "", status_name.get(r["status"], r["status"]),
            r["approval_note"] or r["operator_note"] or "",
        ])
    buf = _export_xlsx(headers, data, "我的申请单")
    return send_file(buf, as_attachment=True,
                     download_name=f"我的申请单_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/applications/create", methods=["POST"])
@login_required
@perm_required("apply")
def application_create():
    f = request.form
    try:
        pid = int(f.get("part_id") or 0)
    except (TypeError, ValueError):
        pid = 0
    app_type = f.get("app_type", "")
    quantity = _num(f.get("quantity", 0))
    reason = f.get("reason", "").strip()
    to_loc = f.get("to_location_id", "").strip()
    if not pid or app_type not in ("in", "out", "transfer"):
        flash(_i18n.t("参数错误", _i18n.current_lang()), "danger")
        return redirect(url_for("applications_page"))
    user = current_user()
    conn = get_db()
    try:
        p = conn.execute("SELECT * FROM parts WHERE id=? AND deleted=0", (pid,)).fetchone()
        if not p:
            flash(_i18n.t("备件不存在", _i18n.current_lang()), "danger")
            return redirect(url_for("applications_page"))
        if app_type == "transfer":
            # 调库申请：从备件的库存行中选「源库位」（哪个位置的料），移动到目标位置（或待定）
            from_key = f.get("from_location_id", "").strip()
            lines = _part_stock_lines(conn, pid)
            # 解析源库位：loc_<id> = 具体位置；loc_NULL = 待定行
            src_line = None
            if from_key.startswith("loc_"):
                raw = from_key[4:]
                if raw == "NULL":
                    src_line = next((l for l in lines if l["location_id"] is None), None)
                else:
                    try:
                        fid = int(raw)
                    except (TypeError, ValueError):
                        fid = None
                    src_line = next((l for l in lines if l["location_id"] == fid), None)
            if src_line is None:
                flash(_i18n.t("请选择调库的源库位（移哪个位置的料）", _i18n.current_lang()), "danger")
                return redirect(url_for("applications_page"))
            src_loc_id = src_line["location_id"]
            try:
                to_id = int(to_loc) if to_loc else None
            except (TypeError, ValueError):
                to_id = None  # 目标位置传「待定」或非数字 → 视为调至待定
            if to_id:
                # 目标占用检查（多库位：其他备件的库存占用该位置时拒绝）
                occ = conn.execute(
                    """SELECT p.part_code FROM inventory i JOIN parts p ON i.part_id=p.id AND p.deleted=0
                       WHERE i.location_id=? AND i.part_id<>? AND i.quantity>0 LIMIT 1""",
                    (to_id, pid),
                ).fetchone()
                if occ:
                    flash(f"目标位置已被备件 [{occ['part_code']}] 存放库存，无法调入；请先将该备件调到待定或其他位置", "danger")
                    return redirect(url_for("applications_page"))
                if src_loc_id == to_id:
                    flash(_i18n.t("源库位与目标位置相同，无需调库", _i18n.current_lang()), "warning")
                    return redirect(url_for("applications_page"))
            else:
                if src_loc_id is None:
                    flash(_i18n.t("该库位已在「待定」状态，请选择目标位置或联系仓库处理", _i18n.current_lang()), "warning")
                    return redirect(url_for("applications_page"))
            # 调库数量合法性（整数备件只能调整数，小数备件可调小数）
            ok, msg = _qty_valid(p, quantity)
            if not ok:
                flash(msg, "danger")
                return redirect(url_for("applications_page"))
            if src_line["quantity"] < quantity:
                flash(f"源库位现有 {src_line['quantity']} {p['unit']}，调库数量超出可调数量", "danger")
                return redirect(url_for("applications_page"))
            app_no = db.gen_no("APP", conn, "applications", "app_no")
            conn.execute(
                """INSERT INTO applications(app_no,part_id,app_type,quantity,reason,
                   from_location_id,to_location_id,applicant_id,status,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (app_no, pid, "transfer", quantity, reason, src_loc_id, to_id,
                 user["id"], "pending", db.now_str()),
            )
            conn.commit()
            flash(_i18n.t("调库申请单 {0} 提交成功（等待仓库人员处理）", _i18n.current_lang()).format(app_no), "success")
            return redirect(url_for("applications_page"))
        # 出入库申请
        ok, msg = _qty_valid(p, quantity)
        if not ok:
            flash(msg, "danger")
            return redirect(url_for("applications_page"))
        if app_type == "out":
            if _part_pending(conn, pid):
                flash(_i18n.t("该备件当前处于「待定」状态（所有库存均无放置位置），不允许领用；请先执行调库到具体位置", _i18n.current_lang()), "danger")
                return redirect(url_for("applications_page"))
            stock = db.total_stock(conn, pid)
            if quantity > stock:
                flash(f"申请数量超过当前库存（现有 {stock} {p['unit']}）", "danger")
                return redirect(url_for("applications_page"))
        # 贵重备件出库：指派审批经理
        assigned_approver_id = None
        if app_type == "out" and p["is_valuable"]:
            if user["role"] == "user":
                # 普通用户：自动匹配本部门经理
                mgr = _dept_manager(conn, user)
                if not mgr:
                    flash(_i18n.t("本部门暂无经理可审批贵重备件出库，请联系管理员在用户管理中配置部门经理", _i18n.current_lang()), "danger")
                    return redirect(url_for("applications_page"))
                assigned_approver_id = mgr["id"]
            else:
                # 仓库/经理/高级管理人员：手动选择审批经理
                sel = request.form.get("approver_id", "").strip()
                if not sel:
                    flash(_i18n.t("贵重备件出库请选择审批经理", _i18n.current_lang()), "danger")
                    return redirect(url_for("applications_page"))
                mgr = conn.execute(
                    "SELECT id, display_name FROM users WHERE id=? AND role='manager' AND active=1",
                    (int(sel),),
                ).fetchone()
                if not mgr:
                    flash(_i18n.t("所选审批经理不存在或已停用，请重新选择", _i18n.current_lang()), "danger")
                    return redirect(url_for("applications_page"))
                assigned_approver_id = mgr["id"]
        # 出库申请：使用线别/设备（来自产线与设备配置），入库/调库可空
        use_line = f.get("use_line", "").strip()
        use_device = f.get("use_device", "").strip()
        if app_type == "out" and use_line and not use_device:
            flash(_i18n.t("选择了使用线别，请同时选择使用设备", _i18n.current_lang()), "warning")
            return redirect(url_for("applications_page"))
        app_no = db.gen_no("APP", conn, "applications", "app_no")
        conn.execute(
            """INSERT INTO applications(app_no,part_id,app_type,quantity,reason,
               line_name,device_name,applicant_id,status,assigned_approver_id,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (app_no, pid, app_type, quantity, reason, use_line, use_device,
             user["id"], "pending", assigned_approver_id, db.now_str()),
        )
        conn.commit()
        if app_type == "out" and p["is_valuable"]:
            mgr_name = conn.execute(
                "SELECT display_name FROM users WHERE id=?", (assigned_approver_id,)
            ).fetchone()["display_name"]
            flow = f"需审批经理 [{mgr_name}] 审批后由仓库出库"
        else:
            flow = "等待仓库人员处理"
        flash(_i18n.t("申请单 {0} 提交成功（{1}）", _i18n.current_lang()).format(app_no, flow), "success")
    finally:
        conn.close()
    return redirect(url_for("applications_page"))


@app.route("/applications/<int:aid>/approve", methods=["POST"])
@login_required
@perm_required("approve")
def application_approve(aid):
    return _approval_action(aid, "approve")


@app.route("/applications/<int:aid>/reject", methods=["POST"])
@login_required
@perm_required("stock_inout", "reject")
def application_reject(aid):
    return _approval_action(aid, "reject")


def _approval_action(aid, action):
    user = current_user()
    conn = get_db()
    try:
        app_row = conn.execute(
            """SELECT a.*, p.part_code, p.name, p.is_valuable FROM applications a
               JOIN parts p ON a.part_id=p.id WHERE a.id=?""",
            (aid,),
        ).fetchone()
        if not app_row:
            flash(_i18n.t("申请单不存在", _i18n.current_lang()), "danger")
            return redirect(url_for("applications_page"))
        if app_row["status"] != "pending":
            flash(_i18n.t("该申请单已被处理", _i18n.current_lang()), "warning")
            return redirect(url_for("applications_page"))
        if not (app_row["app_type"] == "out" and app_row["is_valuable"]):
            flash(_i18n.t("该申请无需审批（非贵重备件出库）", _i18n.current_lang()), "warning")
            return redirect(url_for("applications_page"))
        if app_row["assigned_approver_id"] != user["id"]:
            flash(_i18n.t("该申请未指派给您审批（请由指派审批经理处理）", _i18n.current_lang()), "warning")
            return redirect(url_for("applications_page"))
        note = request.form.get("note", "").strip()
        if action == "approve":
            conn.execute(
                "UPDATE applications SET status='approved', approval_note=?, approver_id=?, processed_at=? WHERE id=?",
                (note, user["id"], db.now_str(), aid),
            )
            conn.commit()
            flash(f"已批准出库：{app_row['app_no']}（{app_row['part_code']} x{app_row['quantity']}）", "success")
        else:
            conn.execute(
                "UPDATE applications SET status='rejected', approval_note=?, approver_id=?, processed_at=? WHERE id=?",
                (note or "审批经理驳回", user["id"], db.now_str(), aid),
            )
            conn.commit()
            flash(f"已驳回：{app_row['app_no']}", "warning")
    finally:
        conn.close()
    return redirect(url_for("applications_page"))


@app.route("/applications/<int:aid>/execute", methods=["POST"])
@login_required
@role_required("admin", "warehouse")
def application_execute(aid):
    """仓库人员执行申请单（出库扣库存 / 入库加库存 / 调库调整放置位置），也可驳回"""
    user = current_user()
    action = request.form.get("action", "complete")
    note = request.form.get("note", "").strip()
    conn = get_db()
    try:
        app_row = conn.execute(
            """SELECT a.*, p.part_code, p.name, p.unit, p.qty_decimal, p.is_valuable, p.unit_price
               FROM applications a JOIN parts p ON a.part_id=p.id WHERE a.id=?""",
            (aid,),
        ).fetchone()
        if not app_row:
            flash(_i18n.t("申请单不存在", _i18n.current_lang()), "danger")
            return redirect(url_for("inout_page"))
        # 仓库/高级管理人员可执行/驳回自己发起的申请（权限由 role_required 保证）
        if action == "reject":
            if app_row["status"] not in ("pending", "approved"):
                flash(_i18n.t("该申请单状态不可驳回", _i18n.current_lang()), "warning")
                return redirect(url_for("inout_page"))
            conn.execute(
                "UPDATE applications SET status='rejected', operator_note=?, operator_id=?, processed_at=? WHERE id=?",
                (note or "仓库驳回", user["id"], db.now_str(), aid),
            )
            conn.commit()
            flash(f"已驳回申请单 {app_row['app_no']}", "warning")
            return redirect(url_for("inout_page"))

        if app_row["app_type"] == "out" and app_row["is_valuable"]:
            if app_row["status"] != "approved":
                flash(_i18n.t("贵重备件出库需先由高级管理人员审批通过后才能出库", _i18n.current_lang()), "danger")
                return redirect(url_for("inout_page"))
        if app_row["status"] != "pending" and not (
                app_row["app_type"] == "out" and app_row["is_valuable"] and app_row["status"] == "approved"):
            flash(_i18n.t("该申请单状态不可执行", _i18n.current_lang()), "warning")
            return redirect(url_for("inout_page"))

        # ---------- 调库申请执行：把申请单指定的源库位整行移动到目标位置 ----------
        if app_row["app_type"] == "transfer":
            to_id = app_row["to_location_id"]
            src_loc_id = app_row["from_location_id"]
            # 定位源库存行：具体位置行 or 待定行
            if src_loc_id:
                src_inv = conn.execute(
                    """SELECT i.* FROM inventory i WHERE i.part_id=? AND i.location_id=?
                       ORDER BY i.id LIMIT 1""",
                    (app_row["part_id"], src_loc_id),
                ).fetchone()
            else:
                src_inv = conn.execute(
                    """SELECT i.* FROM inventory i WHERE i.part_id=? AND i.location_id IS NULL
                       ORDER BY i.id LIMIT 1""",
                    (app_row["part_id"],),
                ).fetchone()
            if not src_inv:
                flash(_i18n.t("源库位不存在（可能已被调整），无法执行调库", _i18n.current_lang()), "danger")
                return redirect(url_for("inout_page"))
            if to_id:
                occ = conn.execute(
                    """SELECT p.part_code FROM inventory i JOIN parts p ON i.part_id=p.id AND p.deleted=0
                       WHERE i.location_id=? AND i.part_id<>? AND i.quantity>0 LIMIT 1""",
                    (to_id, app_row["part_id"]),
                ).fetchone()
                if occ:
                    flash(f"目标位置已被备件 [{occ['part_code']}] 存放库存，无法调入；请先将该备件调到待定或其他位置", "danger")
                    return redirect(url_for("inout_page"))
                to_loc_row = db.get_location(conn, to_id)
                to_txt = db.location_text(to_loc_row) if to_loc_row else ""
            else:
                to_txt = "待定"
            from_txt = src_inv["location"] or "待定"
            # 数量合法性（整数备件只能调整数）+ 源库位存量检查
            qty = app_row["quantity"]
            ok, msg = _qty_valid(app_row, qty)
            if not ok:
                flash(msg, "danger")
                return redirect(url_for("inout_page"))
            if src_inv["quantity"] + 1e-9 < qty:
                flash(f"源库位 [{from_txt}] 现有 {src_inv['quantity']} {app_row['unit']}，不足调出 {qty}", "danger")
                return redirect(url_for("inout_page"))
            # 按申请数量调库：源位置扣减、目标位置增加（目标已有该备件则累加；源位置扣完则删除空行）
            if src_inv["quantity"] - qty < 1e-9:
                conn.execute("DELETE FROM inventory WHERE id=?", (src_inv["id"],))
            else:
                conn.execute(
                    "UPDATE inventory SET quantity=quantity-? WHERE id=?",
                    (qty, src_inv["id"]),
                )
            if to_id:
                tgt_inv = conn.execute(
                    """SELECT i.id FROM inventory i WHERE i.part_id=? AND i.location_id=?
                       ORDER BY i.id LIMIT 1""",
                    (app_row["part_id"], to_id),
                ).fetchone()
            else:
                tgt_inv = conn.execute(
                    """SELECT i.id FROM inventory i WHERE i.part_id=? AND i.location_id IS NULL
                       ORDER BY i.id LIMIT 1""",
                    (app_row["part_id"],),
                ).fetchone()
            if tgt_inv:
                conn.execute(
                    "UPDATE inventory SET quantity=quantity+? WHERE id=?",
                    (qty, tgt_inv["id"]),
                )
            else:
                conn.execute(
                    """INSERT INTO inventory(part_id, location_id, location, quantity)
                       VALUES(?,?,?,?)""",
                    (app_row["part_id"], to_id, to_txt, qty),
                )
            conn.execute(
                """INSERT INTO transactions(tx_no,part_id,tx_type,quantity,unit_price,amount,location,
                   ref_type,ref_id,operator_id,applicant_id,remark,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (db.gen_no("TX", conn, "transactions", "tx_no"), app_row["part_id"],
                 "transfer", qty, app_row["unit_price"], 0, to_txt,
                 "application", aid, user["id"], app_row["applicant_id"],
                 f"调库 {qty} {app_row['unit']}：{from_txt} → {to_txt} {note}".strip(), db.now_str()),
            )
            conn.execute(
                "UPDATE applications SET status='completed', operator_note=?, operator_id=?, processed_at=? WHERE id=?",
                (f"{from_txt} → {to_txt} {note}".strip(), user["id"], db.now_str(), aid),
            )
            conn.commit()
            flash(f"调库完成：{app_row['part_code']}  {from_txt} → {to_txt}", "success")
            return redirect(url_for("inout_page"))

        # ---------- 出入库申请执行 ----------
        if app_row["app_type"] == "out":
            if _part_pending(conn, app_row["part_id"]):
                flash(_i18n.t("该备件当前处于「待定」状态（所有库存均无放置位置），不允许领用；请先执行调库到具体位置", _i18n.current_lang()), "danger")
                return redirect(url_for("inout_page"))
            if app_row["is_valuable"] and app_row["status"] != "approved":
                flash(_i18n.t("贵重备件出库需先由审批经理审批通过后才能出库", _i18n.current_lang()), "danger")
                return redirect(url_for("inout_page"))
        loc_key, loc_text, err = _parse_exec_location(conn, request.form, app_row, app_row["app_type"] == "out")
        if err:
            flash(err, "danger")
            return redirect(url_for("inout_page"))
        qty = app_row["quantity"]
        ok, msg = _qty_valid(app_row, qty)
        if not ok:
            flash(msg, "danger")
            return redirect(url_for("inout_page"))
        delta = qty if app_row["app_type"] == "in" else -qty
        ok, msg = db.move_stock(conn, app_row["part_id"], loc_key, delta)
        if not ok:
            flash(msg, "danger")
            return redirect(url_for("inout_page"))
        amount = round(qty * app_row["unit_price"], 2)
        conn.execute(
            """INSERT INTO transactions(tx_no,part_id,tx_type,quantity,unit_price,amount,location,
               ref_type,ref_id,operator_id,applicant_id,line_name,device_name,remark,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (db.gen_no("TX", conn, "transactions", "tx_no"), app_row["part_id"],
             app_row["app_type"], qty, app_row["unit_price"], amount, loc_text,
             "application", aid, user["id"], app_row["applicant_id"],
             app_row["line_name"] or "", app_row["device_name"] or "", note, db.now_str()),
        )
        conn.execute(
            "UPDATE applications SET status='completed', operator_note=?, operator_id=?, processed_at=? WHERE id=?",
            (note, user["id"], db.now_str(), aid),
        )
        conn.commit()
        flash(f"申请单 {app_row['app_no']} 已执行完成：{app_row['part_code']} x{qty} {app_row['unit']} @ {loc_text}", "success")
    finally:
        conn.close()
    return redirect(url_for("inout_page"))


@app.route("/applications/<int:aid>/cancel", methods=["POST"])
@perm_required("apply", "cancel")
@login_required
def application_cancel(aid):
    """申请人撤销自己尚未处理的申请（仅本人、仅待处理状态）"""
    user = current_user()
    conn = get_db()
    try:
        app_row = conn.execute("SELECT * FROM applications WHERE id=?", (aid,)).fetchone()
        if not app_row:
            flash(_i18n.t("申请单不存在", _i18n.current_lang()), "danger")
            return redirect(url_for("applications_page"))
        if app_row["applicant_id"] != user["id"]:
            flash(_i18n.t("只能撤销自己发起的申请", _i18n.current_lang()), "danger")
            return redirect(url_for("applications_page"))
        if app_row["status"] != "pending":
            flash(_i18n.t("仅待处理的申请单可以直接撤销；已完成/已批准的请使用「申请撤销」走仓管审批", _i18n.current_lang()), "warning")
            return redirect(url_for("applications_page"))
        conn.execute(
            "UPDATE applications SET status='canceled', operator_note=?, operator_id=?, processed_at=? WHERE id=?",
            ("申请人撤销", user["id"], db.now_str(), aid),
        )
        conn.commit()
        flash(f"申请单 {app_row['app_no']} 已撤销", "success")
    finally:
        conn.close()
    return redirect(url_for("applications_page"))


@app.route("/applications/<int:aid>/cancel-request", methods=["POST"])
@login_required
@perm_required("apply")
def application_cancel_request(aid):
    """申请人请求撤销已完成/已批准的申请（需仓管员审批，审批通过后回滚库存/位置）"""
    user = current_user()
    note = request.form.get("note", "").strip()
    conn = get_db()
    try:
        app_row = conn.execute(
            """SELECT a.*, p.part_code FROM applications a JOIN parts p ON a.part_id=p.id WHERE a.id=?""",
            (aid,),
        ).fetchone()
        if not app_row:
            flash(_i18n.t("申请单不存在", _i18n.current_lang()), "danger")
            return redirect(url_for("applications_page"))
        if app_row["applicant_id"] != user["id"]:
            flash(_i18n.t("只能对本人发起的申请提交撤销请求", _i18n.current_lang()), "danger")
            return redirect(url_for("applications_page"))
        if app_row["status"] not in ("completed", "approved"):
            flash(_i18n.t("仅「已完成」或「已批准·待出库」的申请可以申请撤销", _i18n.current_lang()), "warning")
            return redirect(url_for("applications_page"))
        # 调库已执行后若目标行已被再次调整，撤销会导致回滚冲突，拒绝
        # （校验"申请单的目标位置行是否还在"：调到待定=查待定行，调到位置=查该位置行）
        if app_row["app_type"] == "transfer" and app_row["status"] == "completed":
            to_loc = app_row["to_location_id"]
            if to_loc:
                cur = conn.execute(
                    "SELECT location_id FROM inventory WHERE part_id=? AND location_id=? LIMIT 1",
                    (app_row["part_id"], to_loc),
                ).fetchone()
            else:
                cur = conn.execute(
                    "SELECT location_id FROM inventory WHERE part_id=? AND location_id IS NULL LIMIT 1",
                    (app_row["part_id"],),
                ).fetchone()
            if not cur:
                flash(_i18n.t("该调库完成后目标位置已被再次调整，无法撤销，请联系仓管员处理", _i18n.current_lang()), "warning")
                return redirect(url_for("applications_page"))
        conn.execute(
            "UPDATE applications SET status='cancel_req', operator_note=?, operator_id=?, processed_at=? WHERE id=?",
            (_i18n.t("申请人申请撤销", _i18n.current_lang()) + ": " + note, user["id"], db.now_str(), aid),
        )
        conn.commit()
        flash(f"撤销请求已提交（{app_row['app_no']}），等待仓管员审批", "success")
    finally:
        conn.close()
    return redirect(url_for("applications_page"))


@app.route("/applications/<int:aid>/cancel-approve", methods=["POST"])
@login_required
@perm_required("stock_inout", "undo_approval")
def application_cancel_approve(aid):
    """仓管员批准撤销请求：回滚库存/位置，申请单置为已撤销"""
    user = current_user()
    note = request.form.get("note", "").strip()
    conn = get_db()
    try:
        app_row = conn.execute(
            """SELECT a.*, p.part_code FROM applications a JOIN parts p ON a.part_id=p.id WHERE a.id=?""",
            (aid,),
        ).fetchone()
        if not app_row:
            flash(_i18n.t("申请单不存在", _i18n.current_lang()), "danger")
            return redirect(url_for("inout_page"))
        if app_row["status"] != "cancel_req":
            flash(_i18n.t("该申请单当前无待审批的撤销请求", _i18n.current_lang()), "warning")
            return redirect(url_for("inout_page"))
        # 高级管理人员 / 仓库管理人员可以审批本人发起的撤销请求；其他角色（普通用户/经理）不允许
        if app_row["applicant_id"] == user["id"] and user["role"] not in ("admin", "warehouse"):
            flash(_i18n.t("不能审批本人发起的撤销请求，请由其他仓管员处理", _i18n.current_lang()), "danger")
            return redirect(url_for("inout_page"))
        if app_row["app_type"] == "in":
            # 回滚：原入库扣回
            tx = conn.execute(
                "SELECT location FROM transactions WHERE ref_type='application' AND ref_id=? AND tx_type='in' ORDER BY id DESC LIMIT 1",
                (aid,),
            ).fetchone()
            if not tx:
                flash(_i18n.t("未找到该入库流水，无法回滚", _i18n.current_lang()), "danger")
                return redirect(url_for("inout_page"))
            ok, msg = db.move_stock(conn, app_row["part_id"], tx["location"], -app_row["quantity"])
            if not ok:
                flash(_i18n.t("回滚失败：{0}（该库位现有库存不足，无法扣回）", _i18n.current_lang()).format(msg), "danger")
                return redirect(url_for("inout_page"))
        elif app_row["app_type"] == "out":
            tx = conn.execute(
                "SELECT location FROM transactions WHERE ref_type='application' AND ref_id=? AND tx_type='out' ORDER BY id DESC LIMIT 1",
                (aid,),
            ).fetchone()
            if not tx:
                flash(_i18n.t("未找到该出库流水，无法回滚", _i18n.current_lang()), "danger")
                return redirect(url_for("inout_page"))
            db.move_stock(conn, app_row["part_id"], tx["location"], app_row["quantity"])
        elif app_row["app_type"] == "transfer":
            # 回滚：把调出的数量从目标位置扣回、源位置加回（目标行不足/已被再次调整则拒绝）
            qty = app_row["quantity"]
            src_loc = app_row["from_location_id"]
            to_loc = app_row["to_location_id"]
            if to_loc:
                inv_row = conn.execute(
                    """SELECT i.id, i.quantity, i.location FROM inventory i
                       WHERE i.part_id=? AND i.location_id=? ORDER BY i.id LIMIT 1""",
                    (app_row["part_id"], to_loc),
                ).fetchone()
            else:
                inv_row = conn.execute(
                    """SELECT i.id, i.quantity, i.location FROM inventory i
                       WHERE i.part_id=? AND i.location_id IS NULL ORDER BY i.id LIMIT 1""",
                    (app_row["part_id"],),
                ).fetchone()
            if not inv_row:
                flash(_i18n.t("未找到调库后的目标库位库存，无法撤销（该库位可能已被再次调整），请联系仓管员处理", _i18n.current_lang()), "danger")
                return redirect(url_for("inout_page"))
            if inv_row["quantity"] + 1e-9 < qty:
                flash(_i18n.t("目标库位现有库存不足，无法撤销（该库位可能已被再次调整），请联系仓管员处理", _i18n.current_lang()), "danger")
                return redirect(url_for("inout_page"))
            # 目标行扣回 qty（扣完删除空行）
            if inv_row["quantity"] - qty < 1e-9:
                conn.execute("DELETE FROM inventory WHERE id=?", (inv_row["id"],))
            else:
                conn.execute(
                    "UPDATE inventory SET quantity=quantity-? WHERE id=?",
                    (qty, inv_row["id"]),
                )
            # 源位置加回 qty（存在则累加，否则新建）
            if src_loc:
                src_inv = conn.execute(
                    """SELECT i.id FROM inventory i WHERE i.part_id=? AND i.location_id=?
                       ORDER BY i.id LIMIT 1""",
                    (app_row["part_id"], src_loc),
                ).fetchone()
                src_row = db.get_location(conn, src_loc)
                src_txt = db.location_text(src_row) if src_row else ""
            else:
                src_inv = conn.execute(
                    """SELECT i.id FROM inventory i WHERE i.part_id=? AND i.location_id IS NULL
                       ORDER BY i.id LIMIT 1""",
                    (app_row["part_id"],),
                ).fetchone()
                src_txt = "待定"
            if src_inv:
                conn.execute(
                    "UPDATE inventory SET quantity=quantity+? WHERE id=?",
                    (qty, src_inv["id"]),
                )
            else:
                conn.execute(
                    """INSERT INTO inventory(part_id, location_id, location, quantity)
                       VALUES(?,?,?,?)""",
                    (app_row["part_id"], src_loc, src_txt, qty),
                )
        conn.execute(
            "UPDATE applications SET status='canceled', operator_note=?, operator_id=?, processed_at=? WHERE id=?",
            (("批准撤销回滚：" + note).strip(), user["id"], db.now_str(), aid),
        )
        conn.commit()
        flash(f"已批准撤销，库存/位置已回滚：{app_row['app_no']}", "success")
    finally:
        conn.close()
    return redirect(url_for("inout_page"))


@app.route("/applications/<int:aid>/cancel-reject", methods=["POST"])
@login_required
@perm_required("stock_inout", "undo_approval")
def application_cancel_reject(aid):
    """仓管员驳回撤销请求：申请单恢复为已完成"""
    user = current_user()
    note = request.form.get("note", "").strip()
    conn = get_db()
    try:
        app_row = conn.execute("SELECT * FROM applications WHERE id=?", (aid,)).fetchone()
        if not app_row:
            flash(_i18n.t("申请单不存在", _i18n.current_lang()), "danger")
            return redirect(url_for("inout_page"))
        if app_row["status"] != "cancel_req":
            flash(_i18n.t("该申请单当前无待审批的撤销请求", _i18n.current_lang()), "warning")
            return redirect(url_for("inout_page"))
        # 高级管理人员 / 仓库管理人员可以驳回本人发起的撤销请求；其他角色不允许
        if app_row["applicant_id"] == user["id"] and user["role"] not in ("admin", "warehouse"):
            flash(_i18n.t("不能审批本人发起的撤销请求，请由其他仓管员处理", _i18n.current_lang()), "danger")
            return redirect(url_for("inout_page"))
        conn.execute(
            "UPDATE applications SET status='completed', operator_note=?, operator_id=?, processed_at=? WHERE id=?",
            (("驳回撤销：" + note).strip(), user["id"], db.now_str(), aid),
        )
        conn.commit()
        flash(f"已驳回撤销请求：{app_row['app_no']}", "warning")
    finally:
        conn.close()
    return redirect(url_for("inout_page"))


# ------------------------------------------------------------------
# 审批中心（高级管理人员）
# ------------------------------------------------------------------
@app.route("/approval")
@login_required
@perm_required("approve")
def approval_page():
    """审批中心：仅显示指派给当前审批经理的贵重备件出库申请"""
    user = current_user()
    conn = get_db()
    try:
        apps = conn.execute(
            """SELECT a.*, p.part_code, p.name, p.spec, p.unit_price, u.display_name app_name,
                      u.department app_dept,
                      CASE WHEN l.bin='' THEN l.warehouse||'-'||l.rack||'-'||l.shelf
                           ELSE l.warehouse||'-'||l.rack||'-'||l.shelf||'-'||l.bin END AS location_text
               FROM applications a
               JOIN parts p ON a.part_id=p.id
               LEFT JOIN locations l ON p.location_id=l.id
               LEFT JOIN users u ON a.applicant_id=u.id
               WHERE a.app_type='out' AND p.is_valuable=1 AND a.assigned_approver_id=?
               ORDER BY (a.status='pending') DESC, a.id DESC LIMIT 200""",
            (user["id"],),
        ).fetchall()
        apps = [dict(r) for r in apps]
        for a in apps:
            sls = db.stock_locations(conn, a["part_id"])
            a["all_locs_text"] = "；".join(
                f"{s['location']} ×{s['quantity']}" for s in sls if s["quantity"])
    finally:
        conn.close()
    return render_template("approval.html", apps=apps)


# ------------------------------------------------------------------
# 我的记录（每个用户查看自己的出入库与操作流水）
# ------------------------------------------------------------------
@app.route("/my-records")
@login_required
def my_records_page():
    user = current_user()
    conn = get_db()
    try:
        txs = conn.execute(
            """SELECT t.*, p.part_code, p.name, p.unit, u.display_name op_name
               FROM transactions t
               LEFT JOIN parts p ON t.part_id=p.id
               LEFT JOIN users u ON t.operator_id=u.id
               WHERE t.operator_id=? OR t.applicant_id=?
               ORDER BY t.id DESC LIMIT 200""",
            (user["id"], user["id"]),
        ).fetchall()
        apps = conn.execute(
            """SELECT a.*, p.part_code, p.name, p.is_valuable
               FROM applications a LEFT JOIN parts p ON a.part_id=p.id
               WHERE a.applicant_id=?
               ORDER BY a.id DESC LIMIT 200""",
            (user["id"],),
        ).fetchall()
    finally:
        conn.close()
    return render_template("my_records.html", txs=txs, apps=apps)


# ------------------------------------------------------------------
# 用户管理（高级管理人员）
# ------------------------------------------------------------------
@app.route("/users")
@login_required
@perm_required("user_manage")
def users_page():
    conn = get_db()
    try:
        users = conn.execute(
            "SELECT id, username, display_name, role, department, active, created_at FROM users ORDER BY id"
        ).fetchall()
        departments = conn.execute(
            "SELECT * FROM departments ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return render_template("users.html", users=users,
                           roles=[r for r in config.ROLE_NAMES if r != "guest"],   # 访客为内置角色，不手动分配
                           departments=departments,
                           cur_uid=current_user()["id"])


@app.route("/users/add", methods=["POST"])
@login_required
@perm_required("user_manage", "add")
def user_add():
    f = request.form
    username = f.get("username", "").strip()
    pwd = f.get("password", "")
    name = f.get("display_name", "").strip()
    role = f.get("role", "user")
    department = f.get("department", "").strip()
    if not re.fullmatch(r"[\w.\-]{2,30}", username or ""):
        flash(_i18n.t("用户名需为 2-30 位字母/数字/下划线/点/横线", _i18n.current_lang()), "danger")
        return redirect(url_for("users_page"))
    if len(pwd) < 6:
        flash(_i18n.t("密码至少 6 位", _i18n.current_lang()), "danger")
        return redirect(url_for("users_page"))
    if not name:
        flash(_i18n.t("请填写姓名/工号", _i18n.current_lang()), "danger")
        return redirect(url_for("users_page"))
    if role not in config.ROLE_NAMES:
        role = "user"
    conn = get_db()
    try:
        if conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
            flash(_i18n.t("用户名 {0} 已存在", _i18n.current_lang()).format(username), "danger")
            return redirect(url_for("users_page"))
        if department and not conn.execute(
                "SELECT id FROM departments WHERE name=?", (department,)).fetchone():
            department = ""
        conn.execute(
            "INSERT INTO users(username,password_hash,display_name,role,department,active,created_at) VALUES(?,?,?,?,?,1,?)",
            (username, generate_password_hash(pwd), name, role, department, db.now_str()),
        )
        conn.commit()
        flash(_i18n.t("用户 [{0}] 添加成功", _i18n.current_lang()).format(name), "success")
    finally:
        conn.close()
    return redirect(url_for("users_page"))


@app.route("/users/<int:uid>/edit", methods=["POST"])
@login_required
@perm_required("user_manage", "edit")
def user_edit(uid):
    f = request.form
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not row:
            flash(_i18n.t("用户不存在", _i18n.current_lang()), "danger")
            return redirect(url_for("users_page"))
        name = f.get("display_name", "").strip()
        role = f.get("role", row["role"])
        department = f.get("department", "").strip()
        active = 1 if f.get("active") else 0
        new_pwd = f.get("password", "")
        if role not in config.ROLE_NAMES:
            role = row["role"]
        if not name:
            flash(_i18n.t("姓名不能为空", _i18n.current_lang()), "danger")
            return redirect(url_for("users_page"))
        # 防止把自己停用/降级后无法管理（若系统只剩一个 admin）
        admins = conn.execute(
            "SELECT COUNT(*) c FROM users WHERE role='admin' AND active=1"
        ).fetchone()["c"]
        if uid == current_user()["id"]:
            if not active or role != "admin":
                if admins <= 1:
                    flash(_i18n.t("不能停用或降级自己（系统至少保留一名启用中的高级管理人员）", _i18n.current_lang()), "danger")
                    return redirect(url_for("users_page"))
        if department and not conn.execute(
                "SELECT id FROM departments WHERE name=?", (department,)).fetchone():
            department = ""
        if new_pwd:
            if len(new_pwd) < 6:
                flash(_i18n.t("新密码至少 6 位", _i18n.current_lang()), "danger")
                return redirect(url_for("users_page"))
            conn.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new_pwd), uid))
        conn.execute(
            "UPDATE users SET display_name=?, role=?, department=?, active=? WHERE id=?",
            (name, role, department, active, uid),
        )
        conn.commit()
        flash(_i18n.t("用户信息已更新", _i18n.current_lang()), "success")
    finally:
        conn.close()
    return redirect(url_for("users_page"))


@app.route("/users/<int:uid>/reset", methods=["POST"])
@login_required
@perm_required("user_manage", "reset_pwd")
def user_reset(uid):
    pwd = request.form.get("password", "")
    if len(pwd) < 6:
        flash(_i18n.t("新密码至少 6 位", _i18n.current_lang()), "danger")
        return redirect(url_for("users_page"))
    conn = get_db()
    try:
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(pwd), uid))
        conn.commit()
        flash(_i18n.t("密码已重置", _i18n.current_lang()), "success")
    finally:
        conn.close()
    return redirect(url_for("users_page"))


@app.route("/users/<int:uid>/delete", methods=["POST"])
@login_required
@perm_required("user_manage", "delete")
def user_delete(uid):
    """删除用户 → 进入回收站（管理员可恢复）；不能删除自己，系统至少保留一名启用的 admin"""
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not row:
            flash(_i18n.t("用户不存在", _i18n.current_lang()), "danger")
            return redirect(url_for("users_page"))
        if uid == current_user()["id"]:
            flash(_i18n.t("不能删除自己", _i18n.current_lang()), "danger")
            return redirect(url_for("users_page"))
        if row["role"] == "admin":
            admins = conn.execute(
                "SELECT COUNT(*) c FROM users WHERE role='admin' AND active=1 AND id<>?", (uid,)
            ).fetchone()["c"]
            if admins < 1:
                flash(_i18n.t("系统至少保留一名启用中的高级管理人员，不能删除该用户", _i18n.current_lang()), "danger")
                return redirect(url_for("users_page"))
        _recycle_add(conn, "user", uid, row)
        conn.execute("DELETE FROM users WHERE id=?", (uid,))
        conn.commit()
        flash(f"用户 [{row['display_name']}] 已删除并进入回收站（管理员可恢复）", "success")
    finally:
        conn.close()
    return redirect(url_for("users_page"))


# ------------------------------------------------------------------
# 部门配置（高级管理人员）：维护部门列表，用户新增/编辑时下拉选择
# ------------------------------------------------------------------
@app.route("/departments")
@login_required
@perm_required("departments")
def departments_page():
    conn = get_db()
    try:
        deps = conn.execute(
            """SELECT d.*, (SELECT COUNT(*) FROM users u WHERE u.department=d.name) user_count
               FROM departments d ORDER BY d.id"""
        ).fetchall()
    finally:
        conn.close()
    return render_template("departments.html", deps=deps)


@app.route("/departments/add", methods=["POST"])
@login_required
@perm_required("departments")
def department_add():
    name = request.form.get("name", "").strip()
    remark = request.form.get("remark", "").strip()
    if not name:
        flash(_i18n.t("部门名称不能为空", _i18n.current_lang()), "danger")
        return redirect(url_for("departments_page"))
    conn = get_db()
    try:
        if conn.execute("SELECT id FROM departments WHERE name=?", (name,)).fetchone():
            flash(_i18n.t("部门 [{0}] 已存在", _i18n.current_lang()).format(name), "danger")
            return redirect(url_for("departments_page"))
        conn.execute(
            "INSERT INTO departments(name, remark, created_at) VALUES(?,?,?)",
            (name, remark, db.now_str()),
        )
        conn.commit()
        flash(_i18n.t("部门 [{0}] 添加成功", _i18n.current_lang()).format(name), "success")
    finally:
        conn.close()
    return redirect(url_for("departments_page"))


@app.route("/departments/<int:did>/edit", methods=["POST"])
@login_required
@perm_required("departments")
def department_edit(did):
    name = request.form.get("name", "").strip()
    remark = request.form.get("remark", "").strip()
    if not name:
        flash(_i18n.t("部门名称不能为空", _i18n.current_lang()), "danger")
        return redirect(url_for("departments_page"))
    conn = get_db()
    try:
        old = conn.execute("SELECT * FROM departments WHERE id=?", (did,)).fetchone()
        if not old:
            flash(_i18n.t("部门不存在", _i18n.current_lang()), "danger")
            return redirect(url_for("departments_page"))
        if name != old["name"]:
            if conn.execute("SELECT id FROM departments WHERE name=?", (name,)).fetchone():
                flash(_i18n.t("部门 [{0}] 已存在", _i18n.current_lang()).format(name), "danger")
                return redirect(url_for("departments_page"))
            # 同步更新用户表中的旧部门名
            conn.execute("UPDATE users SET department=? WHERE department=?", (name, old["name"]))
        conn.execute("UPDATE departments SET name=?, remark=? WHERE id=?", (name, remark, did))
        conn.commit()
        flash(_i18n.t("部门已更新", _i18n.current_lang()), "success")
    finally:
        conn.close()
    return redirect(url_for("departments_page"))


@app.route("/departments/<int:did>/delete", methods=["POST"])
@login_required
@perm_required("departments")
def department_delete(did):
    conn = get_db()
    try:
        dep = conn.execute("SELECT * FROM departments WHERE id=?", (did,)).fetchone()
        if not dep:
            flash(_i18n.t("部门不存在", _i18n.current_lang()), "danger")
            return redirect(url_for("departments_page"))
        cnt = conn.execute(
            "SELECT COUNT(*) c FROM users WHERE department=?", (dep["name"],)
        ).fetchone()["c"]
        if cnt:
            flash(_i18n.t("该部门下还有 {0} 名用户，请先在用户管理中调整其部门后再删除", _i18n.current_lang()).format(cnt), "danger")
            return redirect(url_for("departments_page"))
        _recycle_add(conn, "department", did, dep)
        conn.execute("DELETE FROM departments WHERE id=?", (did,))
        conn.commit()
        flash(f"部门 [{dep['name']}] 已删除并进入回收站（管理员可恢复）", "success")
    finally:
        conn.close()
    return redirect(url_for("departments_page"))


# ------------------------------------------------------------------
# 产线与设备配置（产线、设备名称维护；备件建档时可绑定适用产线/设备）
# ------------------------------------------------------------------
@app.route("/lines", methods=["GET", "POST"])
@login_required
@perm_required("lines_equip")
def lines_page():
    conn = get_db()
    try:
        lines = db.list_lines(conn)
        equip = db.list_equipment(conn)
        # 设备挂产线名称、产线设备数
        line_map = {l["id"]: l["name"] for l in lines}
        eq_cnt = {}
        for e in equip:
            e["line_name"] = line_map.get(e["line_id"], "未分配")
            if e["line_id"]:
                eq_cnt[e["line_id"]] = eq_cnt.get(e["line_id"], 0) + 1
        for l in lines:
            l["equip_count"] = eq_cnt.get(l["id"], 0)
    finally:
        conn.close()
    return render_template("lines.html", lines=lines, equip=equip)


@app.route("/lines/add", methods=["POST"])
@login_required
@perm_required("lines_equip")
def line_add():
    name = request.form.get("name", "").strip()
    remark = request.form.get("remark", "").strip()
    if not name:
        flash(_i18n.t("产线名称不能为空", _i18n.current_lang()), "danger")
        return redirect(url_for("lines_page"))
    conn = get_db()
    try:
        if conn.execute("SELECT id FROM production_lines WHERE name=?", (name,)).fetchone():
            flash(_i18n.t("产线 [{0}] 已存在", _i18n.current_lang()).format(name), "danger")
            return redirect(url_for("lines_page"))
        conn.execute(
            "INSERT INTO production_lines(name, remark, created_at) VALUES(?,?,?)",
            (name, remark, db.now_str()),
        )
        conn.commit()
        flash(_i18n.t("产线 [{0}] 添加成功", _i18n.current_lang()).format(name), "success")
    finally:
        conn.close()
    return redirect(url_for("lines_page"))


@app.route("/lines/<int:lid>/delete", methods=["POST"])
@login_required
@perm_required("lines_equip")
def line_delete(lid):
    conn = get_db()
    try:
        ln = conn.execute("SELECT * FROM production_lines WHERE id=?", (lid,)).fetchone()
        if not ln:
            flash(_i18n.t("产线不存在", _i18n.current_lang()), "danger")
            return redirect(url_for("lines_page"))
        equip_cnt = conn.execute(
            "SELECT COUNT(*) c FROM equipment WHERE line_id=?", (lid,)
        ).fetchone()["c"]
        app_cnt = conn.execute(
            "SELECT COUNT(*) c FROM part_applications WHERE line_id=?", (lid,)
        ).fetchone()["c"]
        if equip_cnt or app_cnt:
            flash(f"产线 [{ln['name']}] 下还有 {equip_cnt} 台设备、{app_cnt} 条备件适用记录，请先清理", "danger")
            return redirect(url_for("lines_page"))
        conn.execute("DELETE FROM production_lines WHERE id=?", (lid,))
        conn.commit()
        flash(f"产线 [{ln['name']}] 已删除", "success")
    finally:
        conn.close()
    return redirect(url_for("lines_page"))


@app.route("/equipment/add", methods=["POST"])
@login_required
@perm_required("lines_equip")
def equipment_add():
    name = request.form.get("name", "").strip()
    model = request.form.get("model", "").strip()
    line_id = request.form.get("line_id", "").strip()
    remark = request.form.get("remark", "").strip()
    if not name:
        flash(_i18n.t("设备名称不能为空", _i18n.current_lang()), "danger")
        return redirect(url_for("lines_page"))
    try:
        line_id = int(line_id) if line_id else None
    except (TypeError, ValueError):
        line_id = None
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO equipment(line_id, name, model, remark, created_at) VALUES(?,?,?,?,?)",
            (line_id, name, model, remark, db.now_str()),
        )
        conn.commit()
        flash(_i18n.t("设备 [{0}] 添加成功", _i18n.current_lang()).format(name), "success")
    finally:
        conn.close()
    return redirect(url_for("lines_page"))


@app.route("/equipment/<int:eid>/delete", methods=["POST"])
@login_required
@perm_required("lines_equip")
def equipment_delete(eid):
    conn = get_db()
    try:
        eq = conn.execute("SELECT * FROM equipment WHERE id=?", (eid,)).fetchone()
        if not eq:
            flash(_i18n.t("设备不存在", _i18n.current_lang()), "danger")
            return redirect(url_for("lines_page"))
        app_cnt = conn.execute(
            "SELECT COUNT(*) c FROM part_applications WHERE equipment_id=?", (eid,)
        ).fetchone()["c"]
        if app_cnt:
            flash(f"设备 [{eq['name']}] 正被 {app_cnt} 条备件适用记录引用，请先在备件信息维护中解除", "danger")
            return redirect(url_for("lines_page"))
        conn.execute("DELETE FROM equipment WHERE id=?", (eid,))
        conn.commit()
        flash(f"设备 [{eq['name']}] 已删除", "success")
    finally:
        conn.close()
    return redirect(url_for("lines_page"))


@app.route("/api/lines")
@login_required
def api_lines():
    conn = get_db()
    try:
        return jsonify(db.list_lines(conn))
    finally:
        conn.close()


@app.route("/api/equipment")
@login_required
def api_equipment():
    line_id = request.args.get("line_id", "").strip()
    try:
        line_id = int(line_id) if line_id else None
    except (TypeError, ValueError):
        line_id = None
    conn = get_db()
    try:
        return jsonify(db.list_equipment(conn, line_id))
    finally:
        conn.close()


# ------------------------------------------------------------------
# 权限配置（高级管理人员）
# ------------------------------------------------------------------
@app.route("/permissions", methods=["GET", "POST"])
@login_required
@perm_required("perm_config")
def permissions_page():
    conn = get_db()
    try:
        if request.method == "POST":
            for role in config.ROLE_NAMES:
                for m in config.PERM_MODULES:
                    allow = 1 if request.form.get(f"perm_{role}_{m}") else 0
                    conn.execute(
                        "INSERT INTO permissions(role,module,action,allow) VALUES(?,?,?,?) "
                        "ON CONFLICT(role,module,action) DO UPDATE SET allow=excluded.allow",
                        (role, m, "", allow),
                    )
                for m, actions in config.PERM_ACTIONS.items():
                    for a in actions:
                        st = request.form.get(f"perm_action_state_{role}_{m}_{a}", "follow")
                        if st == "1":
                            conn.execute(
                                "INSERT INTO permissions(role,module,action,allow) VALUES(?,?,?,?) "
                                "ON CONFLICT(role,module,action) DO UPDATE SET allow=excluded.allow",
                                (role, m, a, 1),
                            )
                        elif st == "0":
                            conn.execute(
                                "INSERT INTO permissions(role,module,action,allow) VALUES(?,?,?,?) "
                                "ON CONFLICT(role,module,action) DO UPDATE SET allow=excluded.allow",
                                (role, m, a, 0),
                            )
                        else:
                            # follow：删除操作级行，恢复"跟随模块级"语义
                            conn.execute(
                                "DELETE FROM permissions WHERE role=? AND module=? AND action=?",
                                (role, m, a),
                            )
            conn.commit()
            flash(_i18n.t("权限配置已保存（立即生效）", _i18n.current_lang()), "success")
        perms = conn.execute("SELECT * FROM permissions ORDER BY role, module, action").fetchall()
        matrix = {}
        amatrix = {}
        for p in perms:
            if p["action"]:
                amatrix[(p["role"], p["module"], p["action"])] = p["allow"]
            else:
                matrix[(p["role"], p["module"])] = p["allow"]
    finally:
        conn.close()
    _lang = _i18n.current_lang()
    return render_template("permissions.html", matrix=matrix, amatrix=amatrix,
                           roles=list(config.ROLE_NAMES.keys()),
                           PERM_MODULES={k: _i18n.t(v, _lang) for k, v in config.PERM_MODULES.items()},
                           perm_actions={m: {a: _i18n.t(al, _lang) for a, al in acts.items()} for m, acts in config.PERM_ACTIONS.items()})


# ------------------------------------------------------------------
# 系统初始化向导（首次运行配置数据库位置）与系统设置
# ------------------------------------------------------------------
def db_configured():
    """数据库是否已配置：SQLite 看路径，其它数据库类型看 db_type"""
    return bool(config.DB_PATH) or config.DB_TYPE != "sqlite"


@app.before_request
def check_db_configured():
    """数据库未配置时，只允许访问初始化向导"""
    if db_configured():
        return None
    allow = ("/setup", "/login", "/static")
    if request.path.startswith(allow):
        return None
    return redirect(url_for("setup"))


@app.route("/setup", methods=["GET", "POST"])
def setup():
    if db_configured():
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        db_path = request.form.get("db_path", "").strip()
        upload_dir = request.form.get("upload_dir", "").strip()
        demo = 1 if request.form.get("demo_data") else 0
        if not db_path:
            flash(_i18n.t("请填写数据库文件路径", _i18n.current_lang()), "danger")
            return render_template("setup.html", default_db=config.DEFAULT_DB_PATH)
        # 检查路径可用性：所在目录必须可创建
        db_dir = os.path.dirname(db_path)
        if not db_dir:
            flash(_i18n.t("数据库路径需包含目录，例如 \\\\192.168.1.100\\公共盘\\备件管理系统\\SPMS.db", _i18n.current_lang()), "danger")
            return render_template("setup.html", default_db=config.DEFAULT_DB_PATH)
        try:
            os.makedirs(db_dir, exist_ok=True)
            probe = os.path.join(db_dir, ".smt_write_test")
            with open(probe, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(probe)
        except OSError as e:
            flash(_i18n.t("无法写入该位置（请确认目录存在且有权访问）：{0}", _i18n.current_lang()).format(e), "danger")
            return render_template("setup.html", default_db=config.DEFAULT_DB_PATH)
        cfg = {"db_path": db_path, "upload_dir": upload_dir,
               "port": _settings_cfg().get("port", 5000), "demo_data": demo}
        save_path = _settings.save(cfg)
        config.apply_settings(cfg)
        db.init_db(demo=bool(demo))
        flash(_i18n.t("初始化完成，数据库位置：{0}（配置已保存到 {1}）", _i18n.current_lang()).format(db_path, save_path), "success")
        return redirect(url_for("dashboard"))
    return render_template("setup.html", default_db=config.DEFAULT_DB_PATH)


@app.route("/api/browse_dir")
@login_required
@role_required("admin")
def browse_dir():
    """备份目录选择窗体：浏览服务端可访问的目录（本机/内网共享盘）"""
    import os
    path = request.args.get("path", "").strip().strip('"')
    if not path:
        path = os.path.abspath(os.sep)
    if not os.path.isdir(path):
        return jsonify({"ok": False, "msg": f"目录不存在或不可访问：{path}"})
    try:
        entries = sorted(os.listdir(path), key=str.lower)
    except OSError as e:
        return jsonify({"ok": False, "msg": f"无法读取该目录：{e}"})
    dirs = [n for n in entries if os.path.isdir(os.path.join(path, n)) and not n.startswith("$")]
    parent = os.path.dirname(path)
    if parent == path:
        parent = ""
    return jsonify({"ok": True, "cur": path, "parent": parent, "dirs": dirs[:500]})


@app.route("/settings/backups")
@login_required
@role_required("admin")
def settings_backups():
    """备份文件列表片段（AJAX 局部刷新用）"""
    return render_template("_backups.html", backups=_list_backups())


def _is_ajax():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _settings_reply(msg, kind="success", anchor=None, **extra):
    """系统设置页各保存操作的统一返回：AJAX→JSON（页面不刷新），普通→flash+跳转锚点"""
    if _is_ajax():
        data = {"ok": kind == "success", "msg": msg}
        data.update(extra)
        return jsonify(data)
    flash(msg, kind)
    if anchor:
        return redirect(url_for("system_settings", _anchor=anchor))
    return redirect(url_for("system_settings"))


def _screen_reply(msg, kind="success"):
    """大屏配置页保存的统一返回：AJAX→JSON，普通→flash+跳转"""
    if _is_ajax():
        return jsonify({"ok": kind == "success", "msg": msg})
    flash(msg, kind)
    return redirect(url_for("screen_config", _anchor="card-screen"))


@app.route("/settings", methods=["GET", "POST"])
@login_required
@role_required("admin")
def system_settings():
    if request.method == "POST":
        # 数据库类型配置表单（保存 / 测试连接 / 保存并初始化）
        if request.form.get("db_save") is not None:
            return _save_database()
        if request.form.get("db_test"):
            return _test_database()
        # 界面主题与外观表单（theme + nav_style + 品牌 LOGO/文字 一次保存）
        if request.form.get("appearance_save") is not None or request.form.get("appearance_reset"):
            return _save_appearance()
        # 品牌信息表单（系统名称 / 副标题 / LOGO / 样式）单独提交，不切换数据库
        if request.form.get("brand_title") is not None or request.files.get("brand_logo"):
            return _save_brand()
        # 自定义表头表单
        if request.form.get("extra_fields_save"):
            return _save_extra_fields()
        # 呆滞管理设置表单
        if request.form.get("stale_save"):
            return _save_stale()
        # 数据库自动备份表单（保存 / 立即备份）
        if request.form.get("backup_save"):
            return _save_backup()
        if request.form.get("backup_now"):
            return _backup_now()
        # 上传图片自动压缩阈值（随数据库保存）
        if request.form.get("upload_cfg_save"):
            try:
                kb = max(0, min(int(request.form.get("upload_compress_kb", "400") or "0"), 10240))
            except (TypeError, ValueError):
                kb = 400
            conn = get_db()
            try:
                db.set_setting(conn, "upload_cfg", json.dumps({"compress_kb": kb}, ensure_ascii=False))
                conn.commit()
            finally:
                conn.close()
            return _settings_reply(f"上传图片自动压缩已保存（大于 {kb}KB 的图片上传时自动压缩）", "success", "card-db")
        # 界面语言表单
        if request.form.get("language_save"):
            return _save_language()
        # 对外数据接口表单（外系统查询 / 入库操作）
        if request.form.get("open_api_save"):
            return _save_open_api()
        # AD 域登录配置表单
        if request.form.get("ad_save"):
            return _save_ad()
        # 局域网部署表单（保存并重启）
        if request.form.get("deploy_save"):
            return _save_deploy()
        # 删除备份文件
        if request.form.get("backup_delete"):
            return _backup_delete()
        db_path = request.form.get("db_path", "").strip()
        upload_dir = request.form.get("upload_dir", "").strip()
        demo = 1 if request.form.get("demo_data") else 0
        if not db_path:
            return _settings_reply("数据库路径不能为空", "danger", "card-db")
        db_dir = os.path.dirname(db_path)
        try:
            os.makedirs(db_dir, exist_ok=True)
            probe = os.path.join(db_dir, ".smt_write_test")
            with open(probe, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(probe)
        except OSError as e:
            return _settings_reply(f"无法写入该位置：{e}", "danger", "card-db")
        cfg = {"db_path": db_path, "upload_dir": upload_dir,
               "port": _settings_cfg().get("port", 5000), "demo_data": demo}
        save_path = _settings.save(cfg)
        config.apply_settings(cfg)
        try:
            db.init_db(demo=bool(demo))
            return _settings_reply(f"数据库位置已切换并初始化完成：{db_path}", "success", "card-db", db_path=db_path)
        except Exception as e:
            return _settings_reply(f"切换失败：{e}", "danger", "card-db")
    st = _settings_cfg()
    conn2 = get_db()
    try:
        sd = _stale_days(conn2)
    finally:
        conn2.close()
    return render_template("settings.html", db_path=config.DB_PATH or "",
                           upload_dir=config.UPLOAD_DIR or "",
                           default_db=config.DEFAULT_DB_PATH,
                           demo_enabled=bool(st.get("demo_data")),
                           brand=get_brand(), theme=get_theme(),
                           nav_style=get_nav_style(),
                           extra_fields=get_extra_fields(),
                           stale_days=sd,
                           backup=get_backup(),
                           backups=_list_backups(),
                           upload_compress_kb=_upload_compress_kb(),
                           ad_cfg=_ad_cfg(),
                           login_case_sensitive=_login_case_sensitive(),
                           lan_enabled=bool(config.LAN_ENABLED),
                           lan_port=config.PORT,
                           lan_ip=_local_ip(),
                           cur_lang=_i18n.current_lang(),
                           LANGUAGES=_i18n.LANGUAGES,
                           open_api=get_open_api(),
                           db_cfg=config.get_db_cfg(),
                           DB_DIALECTS=("sqlite", "mysql", "mariadb", "postgresql", "mssql", "oracle"))


def _save_database():
    """保存数据库类型与连接参数到 settings.json（保留其他配置）。
    - SQLite：仅数据库文件路径
    - 其它类型：host/port/user/password/database/service_name
    - 保存后重启服务生效；提供「保存并初始化」在当前进程内立即建表迁移"""
    st = _settings.load()
    _db_type = (request.form.get("db_type", "sqlite") or "sqlite").strip().lower()
    if _db_type not in ("sqlite", "mysql", "mariadb", "postgresql", "mssql", "oracle"):
        return _settings_reply("不支持的数据库类型", "danger", "card-db")
    cfg = dict(st)
    cfg["db_type"] = _db_type
    cfg["db_path"] = (request.form.get("db_path", "") or "").strip()
    cfg["db_host"] = (request.form.get("db_host", "") or "").strip()
    try:
        cfg["db_port"] = int(request.form.get("db_port", "0") or "0")
    except (TypeError, ValueError):
        cfg["db_port"] = 0
    cfg["db_user"] = (request.form.get("db_user", "") or "").strip()
    cfg["db_password"] = request.form.get("db_password", "") or ""
    cfg["db_database"] = (request.form.get("db_database", "") or "").strip()
    cfg["db_service_name"] = (request.form.get("db_service_name", "") or "").strip()
    if _db_type == "sqlite" and not cfg["db_path"]:
        return _settings_reply("SQLite 数据库文件路径不能为空", "danger", "card-db")
    # 连接校验
    import db as _db
    ok, msg = _db.test_connect(cfg)
    if not ok:
        return _settings_reply("连接测试失败：" + msg, "danger", "card-db")
    try:
        save_path = _settings.save(cfg)
    except OSError as e:
        return _settings_reply(f"配置保存失败：{e}", "danger", "card-db")
    config.apply_settings(cfg)
    note = "已保存。重启软件后生效" if _db_type != "sqlite" else "已保存并立即生效"
    if request.form.get("db_init"):
        try:
            db.init_db()
            note += "，新库已初始化（建表+默认管理员）"
        except Exception as e:
            return _settings_reply(f"配置已保存，但新库初始化失败：{e}（可重启软件后重试）", "danger", "card-db")
    return _settings_reply(
        f"数据库配置已保存（{msg}）。{note}；当前数据库类型：{_db_type.upper()}",
        "success", "card-db", db_path=cfg["db_path"] or config.DB_PATH or "")


def _test_database():
    """AJAX 测试数据库连接（不保存）"""
    import db as _db
    _db_type = (request.form.get("db_type", "sqlite") or "sqlite").strip().lower()
    try:
        _port = int(request.form.get("db_port", "0") or "0")
    except (TypeError, ValueError):
        _port = 0
    cfg = {
        "db_type": _db_type,
        "db_path": (request.form.get("db_path", "") or "").strip(),
        "host": (request.form.get("db_host", "") or "").strip(),
        "port": _port,
        "user": (request.form.get("db_user", "") or "").strip(),
        "password": request.form.get("db_password", "") or "",
        "database": (request.form.get("db_database", "") or "").strip(),
        "service_name": (request.form.get("db_service_name", "") or "").strip(),
    }
    if _db_type == "sqlite" and not cfg["db_path"]:
        return jsonify({"ok": False, "msg": "请填写数据库文件路径"})
    ok, msg = _db.test_connect(cfg)
    return jsonify({"ok": ok, "msg": msg})


def _save_language():
    """保存界面语言到 settings.json（保留其他配置）"""
    st = _settings.load()
    lang = request.form.get("language", "zh").strip()
    if lang not in _i18n.LANGUAGES:
        return _settings_reply("所选语言无效", "danger", "card-language")
    st["language"] = lang
    try:
        _settings.save(st)
    except OSError as e:
        return _settings_reply(f"配置保存失败：{e}", "danger", "card-language")
    return _settings_reply(f"界面语言已切换为 {_i18n.LANGUAGES.get(lang, lang)}，刷新后全局生效", "success", "card-language")


def _save_ad():
    """保存 AD 域登录配置到 settings.json（保留其他配置）。
    - 端口：放开为 1-65535 任意合法端口，不再静默重置（非法值直接报错提示）
    - 加密方式：none 明文 / ldaps（636）/ starttls（389 升级加密）
    - 绑定方式：direct 直接绑定 / search 服务账号搜索（Base DN + 搜索属性）
    - 同时保存「用户名匹配是否区分大小写」到数据库（共享，作用于普通登录 + AD 登录）"""
    st = _settings.load()
    port_raw = request.form.get("ad_port", "389").strip() or "389"
    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        port = 0
    if not 1 <= port <= 65535:
        return _settings_reply("AD 端口必须是 1-65535 之间的数字（如 389/636/3268/3269 或自定义端口）", "danger", "card-ad")
    enc = request.form.get("ad_enc", "none").strip()
    if enc not in ("none", "ldaps", "starttls"):
        enc = "none"
    bind_mode = request.form.get("ad_bind_mode", "direct").strip()
    if bind_mode not in ("direct", "search"):
        bind_mode = "direct"
    try:
        timeout = max(3, min(int(request.form.get("ad_timeout", "10") or 10), 60))
    except (TypeError, ValueError):
        timeout = 10
    st["ad"] = {
        "enabled": 1 if request.form.get("ad_enabled") else 0,
        "server": request.form.get("ad_server", "").strip(),
        "port": port,
        "enc": enc,
        "domain": request.form.get("ad_domain", "").strip(),
        "name_format": request.form.get("ad_name_format", "upn").strip() or "upn",
        "bind_mode": bind_mode,
        "svc_dn": request.form.get("ad_svc_dn", "").strip(),
        "svc_pwd": request.form.get("ad_svc_pwd", ""),
        "base_dn": request.form.get("ad_base_dn", "").strip(),
        "search_attr": (request.form.get("ad_search_attr", "sAMAccountName").strip()
                        or "sAMAccountName"),
        "timeout": timeout,
        "strip_upn_suffix": 1 if request.form.get("ad_strip_upn_suffix") else 0,
    }
    try:
        _settings.save(st)
    except OSError as e:
        return _settings_reply(f"配置保存失败：{e}", "danger", "card-ad")
    # 用户名匹配大小写（数据库共享设置，所有电脑一致；同时作用于普通登录与 AD 登录）
    cs = 1 if request.form.get("login_case_sensitive") else 0
    conn = get_db()
    try:
        db.set_setting(conn, "login_case_sensitive", str(cs))
        conn.commit()
    finally:
        conn.close()
    # 提示安全提醒
    tip = ""
    if st["ad"].get("enabled"):
        tip = "；已启用 AD 登录，登录页将显示「AD 域账号登录」入口"
    return _settings_reply(f"AD 域登录配置已保存{tip}", "success", "card-ad")


def _is_hex_color(v):
    return bool(re.fullmatch(r"#[0-9a-fA-F]{6}", v or ""))


def _save_appearance():
    """保存界面主题与外观（theme + nav_style + 侧栏品牌 LOGO/文字样式，合并为一张配置卡片，一次提交）"""
    if request.form.get("appearance_reset"):
        conn = get_db()
        try:
            old_logo = get_brand(conn).get("logo_file", "")
            if old_logo:
                db.image_delete(conn, old_logo)
                fp = os.path.join(config.resolved_upload_dir(), old_logo)
                if os.path.exists(fp):
                    try:
                        os.remove(fp)
                    except OSError:
                        pass
            db.set_setting(conn, "theme", json.dumps(dict(config.DEFAULT_THEME), ensure_ascii=False))
            db.set_setting(conn, "nav_style", json.dumps(dict(config.DEFAULT_NAV_STYLE), ensure_ascii=False))
            db.set_setting(conn, "brand", json.dumps(dict(DEFAULT_BRAND), ensure_ascii=False))
            conn.commit()
        finally:
            conn.close()
        return _settings_reply("界面主题与外观已恢复默认", "success", "card-theme")
    # 品牌（LOGO/标题/副标题 + 样式），先校验上传文件
    cur_brand = get_brand()
    logo = request.files.get("brand_logo")
    if logo and logo.filename:
        ext = os.path.splitext(logo.filename)[1].lower()
        if ext not in config.ALLOWED_IMG_EXTS:
            return _settings_reply("LOGO 图片格式不支持（jpg/png/gif/bmp/webp）", "danger", "card-theme")
        logo.seek(0, os.SEEK_END)
        size = logo.tell()
        logo.seek(0)
        if size > config.MAX_IMG_SIZE:
            return _settings_reply("LOGO 图片超过 5MB 限制", "danger", "card-theme")
    brand = _collect_brand(cur_brand)
    # 界面主题色（侧栏背景已由渐变起止色控制，不再单独配置）
    t = get_theme()
    for k in ("primary", "primary_d", "sidebar_text", "bg"):
        v = request.form.get("theme_" + k, "").strip()
        if _is_hex_color(v):
            t[k] = v.lower()
    # 左侧菜单外观（含侧栏渐变起止色）
    nav = get_nav_style()
    def _num(k, lo, hi, cur):
        try:
            v = float(request.form.get(k, "").strip())
            return lo if v < lo else (hi if v > hi else v)
        except Exception:
            return cur
    nav["menu_width"] = int(_num("nav_menu_width", 160, 360, nav["menu_width"]))
    nav["font_size"] = _num("nav_font_size", 10, 24, nav["font_size"])
    nav["icon_size"] = _num("nav_icon_size", 10, 40, nav["icon_size"])
    nav["item_padding"] = _num("nav_item_padding", 2, 24, nav["item_padding"])
    nav["item_radius"] = _num("nav_item_radius", 0, 20, nav["item_radius"])
    ff = request.form.get("nav_font_family", "").strip()
    nav["font_family"] = ff if len(ff) <= 60 else nav["font_family"]
    for k in ("sidebar_top", "sidebar_bottom"):
        v = request.form.get("nav_" + k, "").strip()
        if _is_hex_color(v):
            nav[k] = v.lower()
    conn = get_db()
    try:
        # 品牌 LOGO 二进制写入 images 表；移除/替换时清理旧记录与旧文件
        old_logo = cur_brand.get("logo_file", "")
        logo_bytes = brand.pop("_logo_bytes", None)
        if logo_bytes is not None:
            db.image_save(conn, brand["logo_file"], logo_bytes)
            if old_logo and old_logo != brand["logo_file"]:
                db.image_delete(conn, old_logo)
        elif brand["logo_file"] == "" and old_logo:
            db.image_delete(conn, old_logo)
        if old_logo and old_logo != brand["logo_file"]:
            fp = os.path.join(config.resolved_upload_dir(), old_logo)
            if os.path.exists(fp):
                try:
                    os.remove(fp)
                except OSError:
                    pass
        db.set_setting(conn, "theme", json.dumps(t, ensure_ascii=False))
        db.set_setting(conn, "nav_style", json.dumps(nav, ensure_ascii=False))
        db.set_setting(conn, "brand", json.dumps(brand, ensure_ascii=False))
        conn.commit()
    finally:
        conn.close()
    return _settings_reply("界面主题与外观已保存（立即生效）", "success", "card-theme", theme=t, nav=nav)


def _save_open_api():
    """保存对外数据接口设置（系统设置页）"""
    cfg = {
        "enabled": 1 if request.form.get("open_api_enabled") else 0,
        "token": request.form.get("open_api_token", "").strip(),
    }
    conn = get_db()
    try:
        db.set_setting(conn, "open_api", json.dumps(cfg, ensure_ascii=False))
        conn.commit()
    finally:
        conn.close()
    return _settings_reply("对外数据接口设置已保存（" + ("已开放" if cfg["enabled"] else "已关闭") + "）", "success", "card-api")


def get_open_api(conn=None):
    """读取对外数据接口配置（sys_settings key=open_api）"""
    cfg = dict(config.DEFAULT_OPEN_API)
    if not db_configured():
        return cfg
    own = conn is None
    if own:
        conn = get_db()
    try:
        raw = db.get_setting(conn, "open_api")
        if raw:
            try:
                d = json.loads(raw)
                if isinstance(d, dict):
                    for k in cfg:
                        if d.get(k) is not None:
                            cfg[k] = d[k]
            except Exception:
                pass
    finally:
        if own:
            conn.close()
    cfg["enabled"] = bool(cfg.get("enabled"))
    cfg["token"] = str(cfg.get("token") or "").strip()
    return cfg


def _api_token_ok(cfg):
    """校验请求 X-API-Token 是否有效"""
    if not cfg["enabled"]:
        return False, "接口未启用（请先在系统设置中开放）"
    if not cfg["token"]:
        return False, "系统未配置接口密钥"
    if request.headers.get("X-API-Token", "") != cfg["token"]:
        return False, "API Token 无效"
    return True, ""


def _system_robot(conn):
    """获取/创建「系统机器人」用户（外部系统提交的申请记录，申请人显示为系统机器人）"""
    row = conn.execute("SELECT id FROM users WHERE username='system_robot'").fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        """INSERT INTO users(username, display_name, role, department, password_hash, active, created_at)
           VALUES(?,?,?,?,?,1,?)""",
        ("system_robot", "系统机器人", "user", "", "*", db.now_str()),
    )
    return cur.lastrowid


@app.route("/api/inventory/list")
def api_inventory_list():
    """外系统查询备件库存列表（GET）
    请求头：X-API-Token: <接口密钥>
    返回：{ok, total, items:[{part_code,name,category,spec,unit,qty_decimal,stock,min_stock,max_stock,
                              is_valuable, locations:[{location,quantity}], apps}]}"""
    if not db_configured():
        return jsonify({"ok": False, "error": "系统尚未初始化"}), 400
    conn = get_db()
    try:
        cfg = get_open_api(conn)
    finally:
        conn.close()
    ok, err = _api_token_ok(cfg)
    if not ok:
        return jsonify({"ok": False, "error": err}), (401 if "无效" in err else 400)
    kw = (request.args.get("kw") or "").strip()
    conn = get_db()
    try:
        sql = """SELECT p.*, COALESCE(SUM(i.quantity),0) stock
                 FROM parts p LEFT JOIN inventory i ON p.id=i.part_id WHERE 1=1"""
        params = []
        if kw:
            sql += " AND (p.part_code LIKE ? OR p.name LIKE ? OR p.spec LIKE ?)"
            params += [f"%{kw}%"] * 3
        sql += " GROUP BY p.id ORDER BY p.part_code"
        rows = conn.execute(sql, params).fetchall()
        items = []
        for r in rows:
            p = dict(r)
            locs = db.stock_locations(conn, p["id"])
            apps = db.part_apps(conn, p["id"])
            items.append({
                "part_code": p["part_code"], "name": p["name"], "category": p["category"] or "",
                "spec": p["spec"] or "", "unit": p["unit"] or "",
                "qty_decimal": 1 if p["qty_decimal"] else 0,
                "stock": p["stock"] or 0, "min_stock": p["min_stock"] or 0,
                "max_stock": p["max_stock"] or 0,
                "is_valuable": 1 if p["is_valuable"] else 0,
                "locations": [{"location": l["location"], "quantity": l["quantity"]} for l in locs],
                "apps": [_apps_label(a, plain=True) for a in apps],
            })
        return jsonify({"ok": True, "total": len(items), "items": items})
    finally:
        conn.close()


@app.route("/api/inbound", methods=["POST"])
def api_inbound():
    """外系统提交备件入库申请（POST）
    请求头：X-API-Token: <接口密钥>；Content-Type: application/json
    请求体字段：
      part_code  料号（必填，若系统中不存在则自动建档，存放库位=待定）
      quantity   入库数量（必填，>0；已存在备件按数量属性校验整数/小数）
      name/unit/category/spec/unit_price/qty_decimal  自动建档时的可选属性
      remark/note 备注（可选）
    流程：与网页申请一致，生成入库申请单（申请人=系统机器人），需仓库人员执行后入库
    返回：{ok, app_no, part_created}"""
    if not db_configured():
        return jsonify({"ok": False, "error": "系统尚未初始化"}), 400
    conn = get_db()
    try:
        cfg = get_open_api(conn)
    finally:
        conn.close()
    ok, err = _api_token_ok(cfg)
    if not ok:
        return jsonify({"ok": False, "error": err}), (401 if "无效" in err else 400)
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({"ok": False, "error": "请求体不是合法 JSON"}), 400
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "请求体需为 JSON 对象"}), 400
    part_code = str(data.get("part_code") or "").strip()
    if not part_code:
        return jsonify({"ok": False, "error": "缺少必填字段 part_code（料号）"}), 400
    try:
        qty = float(data.get("quantity"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "quantity（数量）必须是数字"}), 400
    if qty <= 0:
        return jsonify({"ok": False, "error": "quantity（数量）必须大于 0"}), 400
    remark = str(data.get("remark") or data.get("note") or "").strip()

    conn = get_db()
    try:
        part = conn.execute("SELECT * FROM parts WHERE part_code=?", (part_code,)).fetchone()
        part_created = False
        if not part:
            # 自动建档：库位=待定（建档本身不建库存，由入库执行时产生库存）
            name = str(data.get("name") or part_code).strip()
            unit = str(data.get("unit") or "个").strip() or "个"
            qdec = data.get("qty_decimal")
            if qdec is None or str(qdec).strip() == "":
                qdec = 0 if unit.lower() in ("个", "pcs", "pcs.", "件", "套", "片", "张", "支", "台", "包", "只", "根", "条", "块") else 1
            else:
                try:
                    qdec = _qdec(qdec) if isinstance(qdec, str) else (1 if float(qdec) else 0)
                except (TypeError, ValueError):
                    qdec = 0
            price = 0.0
            try:
                price = float(data.get("unit_price") or 0)
            except (TypeError, ValueError):
                price = 0.0
            cur = conn.execute(
                """INSERT INTO parts(part_code,name,category,spec,unit,qty_decimal,unit_price,min_stock,max_stock,
                   is_valuable,supplier,remark,location_id,extra,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,0,'',?,NULL,'{}',?,?)""",
                (part_code, name, str(data.get("category") or "无").strip() or "无",
                 str(data.get("spec") or "无").strip() or "无", unit, qdec, price,
                 _num(data.get("min_stock")) or 0, _num(data.get("max_stock")) or 0,
                 remark or "无", db.now_str(), db.now_str()),
            )
            pid = cur.lastrowid
            part_created = True
            part = conn.execute("SELECT * FROM parts WHERE id=?", (pid,)).fetchone()
        # 数量属性校验
        qok, qmsg = _qty_valid(part, qty)
        if not qok:
            return jsonify({"ok": False, "error": qmsg}), 400
        robot_id = _system_robot(conn)
        app_no = db.gen_no("APP", conn, "applications", "app_no")
        conn.execute(
            """INSERT INTO applications(app_no,part_id,app_type,quantity,reason,applicant_id,
               status,created_at) VALUES(?,?,?,?,?,?,?,?)""",
            (app_no, part["id"], "in", qty, remark, robot_id, "pending", db.now_str()),
        )
        conn.commit()
        return jsonify({"ok": True, "app_no": app_no, "part_created": part_created})
    finally:
        conn.close()


def _save_stale():
    """保存呆滞物料天数配置（默认 90 天，以料号为锚点：超过 N 天未领用即呆滞）"""
    try:
        v = int(request.form.get("stale_days", "").strip() or 90)
    except (TypeError, ValueError):
        v = 90
    v = max(1, min(3650, v))
    conn = get_db()
    try:
        db.set_setting(conn, "stale_days", str(v))
        conn.commit()
    finally:
        conn.close()
    return _settings_reply(f"呆滞物料天数已保存：超过 {v} 天未领用即判定为呆滞", "success", "card-stale")


def _stale_days(conn):
    """呆滞判定天数（sys_settings，默认 90）"""
    try:
        return int(db.get_setting(conn, "stale_days") or 90)
    except (TypeError, ValueError):
        return 90


def _save_extra_fields():
    """保存自定义表头（数量可配置，最多 MAX_EXTRA_FIELDS 个）"""
    labels = [request.form.get(f"ef_label_{i}", "").strip() for i in range(config.MAX_EXTRA_FIELDS)]
    labels = [l for l in labels if l]  # 去空
    used = set()
    fields = []
    for i, label in enumerate(labels[: config.MAX_EXTRA_FIELDS]):
        key = f"f{i + 1}"
        if key in used:
            continue
        used.add(key)
        fields.append({"key": key, "label": label})
    conn = get_db()
    try:
        db.set_setting(conn, "extra_fields", json.dumps(fields, ensure_ascii=False))
        conn.commit()
    finally:
        conn.close()
    return _settings_reply(f"自定义表头已保存（共 {len(fields)} 列）", "success", "card-ef")


def _collect_brand(cur):
    """从表单收集品牌字段（标题/副标题/LOGO 上传与移除/图片大小/文字大小/字体/字色）"""
    title = request.form.get("brand_title", "").strip() or DEFAULT_BRAND["title"]
    subtitle = request.form.get("brand_subtitle", "").strip()
    logo_file = cur.get("logo_file", "")
    logo_bytes = None
    logo = request.files.get("brand_logo")
    if logo and logo.filename:
        ext = os.path.splitext(logo.filename)[1].lower()
        if ext in config.ALLOWED_IMG_EXTS and logo.tell() <= config.MAX_IMG_SIZE:
            logo.seek(0)
            logo_bytes, _ = _compress_image(logo.read(), _upload_compress_kb())
            save_name = f"brand_{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(logo.filename)}"
            logo_file = save_name
    if request.form.get("brand_remove_logo"):
        logo_file = ""
        logo_bytes = None

    def _num(k, lo, hi, cur_v):
        try:
            v = int(request.form.get(k, "").strip())
            return lo if v < lo else (hi if v > hi else v)
        except Exception:
            return cur_v

    def _color(k, cur_v):
        v = request.form.get(k, "").strip()
        return v.lower() if _is_hex_color(v) else cur_v

    ff = request.form.get("brand_font_family", "").strip()
    return {
        "logo_file": logo_file,
        "_logo_bytes": logo_bytes,   # 新上传 LOGO 的二进制（由调用方写入 images 表）
        "title": title[:30],
        "subtitle": subtitle[:50],
        "logo_height": _num("brand_logo_height", 12, 160, cur["logo_height"]),
        "title_size": _num("brand_title_size", 10, 36, cur["title_size"]),
        "subtitle_size": _num("brand_subtitle_size", 8, 22, cur["subtitle_size"]),
        "title_color": _color("brand_title_color", cur.get("title_color", "")),
        "subtitle_color": _color("brand_subtitle_color", cur.get("subtitle_color", "")),
        "font_family": ff[:80],
    }


def _save_brand():
    """保存品牌信息（侧栏 LOGO / 标题 / 副标题 + 图片大小、文字大小、字体、字色）"""
    cur = get_brand()
    logo = request.files.get("brand_logo")
    if logo and logo.filename:
        ext = os.path.splitext(logo.filename)[1].lower()
        if ext not in config.ALLOWED_IMG_EXTS:
            return _settings_reply("LOGO 图片格式不支持（jpg/png/gif/bmp/webp）", "danger", "card-theme")
        logo.seek(0, os.SEEK_END)
        size = logo.tell()
        logo.seek(0)
        if size > config.MAX_IMG_SIZE:
            return _settings_reply("LOGO 图片超过 5MB 限制", "danger", "card-theme")
    brand = _collect_brand(cur)
    logo_bytes = brand.pop("_logo_bytes", None)
    conn = get_db()
    try:
        # 新 LOGO 二进制写入 images 表；移除/替换时清理旧记录与旧文件
        old_logo = cur.get("logo_file", "")
        if logo_bytes is not None:
            db.image_save(conn, brand["logo_file"], logo_bytes)
            if old_logo and old_logo != brand["logo_file"]:
                db.image_delete(conn, old_logo)
        elif brand["logo_file"] == "" and old_logo:
            db.image_delete(conn, old_logo)
        if old_logo and old_logo != brand["logo_file"]:
            fp = os.path.join(config.resolved_upload_dir(), old_logo)
            if os.path.exists(fp):
                try:
                    os.remove(fp)
                except OSError:
                    pass
        db.set_setting(conn, "brand", json.dumps(brand, ensure_ascii=False))
        conn.commit()
    finally:
        conn.close()
    return _settings_reply("品牌信息已保存（侧边栏立即生效）", "success", "card-theme")


def _settings_cfg():
    return _settings.load()


# ------------------------------------------------------------------
# 数据库自动备份（后台线程按间隔检查，任意一台运行软件的电脑都会自动备份到共享盘）
# ------------------------------------------------------------------
def get_backup(conn=None):
    """读取数据库自动备份配置（sys_settings key=backup）"""
    cfg = dict(config.DEFAULT_BACKUP)
    if not db_configured():
        return cfg
    own = conn is None
    if own:
        conn = get_db()
    try:
        raw = db.get_setting(conn, "backup")
        if raw:
            try:
                d = json.loads(raw)
                if isinstance(d, dict):
                    for k in cfg:
                        if d.get(k) is not None:
                            cfg[k] = d[k]
            except Exception:
                pass
    finally:
        if own:
            conn.close()
    return cfg


def _backup_cfg(conn):
    """读取并做边界校验的备份配置"""
    cfg = get_backup(conn)
    try:
        cfg["enabled"] = 1 if int(cfg.get("enabled")) else 0
    except (TypeError, ValueError):
        cfg["enabled"] = 0
    try:
        cfg["interval_hours"] = max(1, min(int(cfg.get("interval_hours") or 24), 24 * 30))
    except (TypeError, ValueError):
        cfg["interval_hours"] = 24
    try:
        cfg["keep"] = max(1, min(int(cfg.get("keep") or 10), 99))
    except (TypeError, ValueError):
        cfg["keep"] = 10
    cfg["dir"] = (str(cfg.get("dir") or "")).strip()
    return cfg


def _backup_target_dir(cfg):
    return cfg["dir"] or os.path.join(os.path.dirname(config.DB_PATH), "backups")


def _do_backup(cfg=None):
    """执行一次备份：返回备份文件绝对路径"""
    if cfg is None:
        conn = get_db()
        try:
            cfg = _backup_cfg(conn)
        finally:
            conn.close()
    bdir = _backup_target_dir(cfg)
    if not os.path.exists(bdir):
        os.makedirs(bdir, exist_ok=True)
    base = os.path.splitext(os.path.basename(config.DB_PATH))[0]
    target = os.path.join(bdir, f"{base}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
    db.backup_database(target)
    # 清理：只保留最近 keep 份
    try:
        files = [f for f in os.listdir(bdir) if f.startswith(base + "_backup_") and f.endswith(".db")]
        full = [(os.path.join(bdir, f), os.path.getmtime(os.path.join(bdir, f))) for f in files]
        full.sort(key=lambda x: x[1], reverse=True)
        for fp, _ in full[cfg["keep"]:]:
            try:
                os.remove(fp)
            except OSError:
                pass
    except OSError:
        pass
    return target


def _maybe_auto_backup():
    """后台线程每次调用：检查是否到期，到期则备份（多台电脑运行时，任何一台到期都会备份）"""
    if not config.DB_PATH or not os.path.exists(config.DB_PATH):
        return
    conn = get_db()
    try:
        cfg = _backup_cfg(conn)
    except Exception:
        return
    finally:
        conn.close()
    if not cfg["enabled"]:
        return
    bdir = _backup_target_dir(cfg)
    if not os.path.exists(bdir):
        try:
            os.makedirs(bdir, exist_ok=True)
        except OSError:
            return
    base = os.path.splitext(os.path.basename(config.DB_PATH))[0]
    newest = 0.0
    try:
        for f in os.listdir(bdir):
            if f.startswith(base + "_backup_") and f.endswith(".db"):
                try:
                    newest = max(newest, os.path.getmtime(os.path.join(bdir, f)))
                except OSError:
                    pass
    except OSError:
        return
    if time.time() - newest < cfg["interval_hours"] * 3600:
        return
    try:
        _do_backup(cfg)
    except Exception as e:
        log.warning("自动备份失败：%s", e)


def _backup_worker():
    """后台守护线程：每 60 秒检查一次是否需要自动备份"""
    while True:
        try:
            _maybe_auto_backup()
        except Exception:
            pass
        time.sleep(60)


def _save_backup():
    """保存自动备份设置（系统设置页）"""
    try:
        interval = max(1, min(int(request.form.get("backup_interval_hours", 24) or 24), 24 * 30))
    except (TypeError, ValueError):
        interval = 24
    try:
        keep = max(1, min(int(request.form.get("backup_keep", 10) or 10), 99))
    except (TypeError, ValueError):
        keep = 10
    cfg = {
        "enabled": 1 if request.form.get("backup_enabled") else 0,
        "interval_hours": interval,
        "keep": keep,
        "dir": request.form.get("backup_dir", "").strip(),
    }
    conn = get_db()
    try:
        db.set_setting(conn, "backup", json.dumps(cfg, ensure_ascii=False))
        conn.commit()
    finally:
        conn.close()
    return _settings_reply("自动备份设置已保存", "success", "card-backup")


def _backup_now():
    """立即备份一次（系统设置页按钮；仅 SQLite 支持文件级备份）"""
    if config.DB_TYPE != "sqlite":
        return _settings_reply("备份/恢复仅支持 SQLite 数据库；%s 请使用数据库自带备份工具" % config.DB_TYPE.upper(), "danger", "card-backup")
    if not config.DB_PATH or not os.path.exists(config.DB_PATH):
        return _settings_reply("数据库未配置或文件不存在，无法备份", "danger", "card-backup")
    conn = get_db()
    try:
        cfg = _backup_cfg(conn)
    finally:
        conn.close()
    try:
        target = _do_backup(cfg)
    except Exception as e:
        return _settings_reply(f"备份失败：{e}", "danger", "card-backup")
    return _settings_reply(f"备份完成：{os.path.basename(target)}", "success", "card-backup",
                           backups_html=render_template("_backups.html", backups=_list_backups()))


def _list_backups():
    """列出当前备份文件（名称/大小/时间，最新的在前）；仅 SQLite"""
    if config.DB_TYPE != "sqlite" or not config.DB_PATH:
        return []
    conn = get_db()
    try:
        cfg = _backup_cfg(conn)
    finally:
        conn.close()
    bdir = _backup_target_dir(cfg)
    if not os.path.isdir(bdir):
        return []
    base = os.path.splitext(os.path.basename(config.DB_PATH))[0]
    files = [f for f in os.listdir(bdir) if f.startswith(base + "_backup_") and f.endswith(".db")]
    rows = []
    for f in sorted(files, reverse=True):
        fp = os.path.join(bdir, f)
        try:
            st = os.stat(fp)
            rows.append({
                "name": f,
                "dir": bdir,
                "size": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            })
        except OSError:
            pass
    return rows


def _backup_delete():
    """删除指定的备份文件（系统设置页）"""
    name = os.path.basename(request.form.get("backup_file", "").strip() or "")
    if not name:
        return _settings_reply("未指定备份文件", "danger", "card-backup")
    conn = get_db()
    try:
        cfg = _backup_cfg(conn)
    finally:
        conn.close()
    bdir = _backup_target_dir(cfg)
    base = os.path.splitext(os.path.basename(config.DB_PATH))[0]
    if not name.startswith(base + "_backup_") or not name.endswith(".db"):
        return _settings_reply("非法的备份文件名", "danger", "card-backup")
    fp = os.path.join(bdir, name)
    try:
        if os.path.exists(fp):
            os.remove(fp)
            msg, kind = f"备份已删除：{name}", "success"
        else:
            msg, kind = "备份文件不存在", "warning"
    except OSError as e:
        return _settings_reply(f"删除失败：{e}", "danger", "card-backup")
def _local_ip():
    """获取本机局域网 IP（用于部署提示）"""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _save_deploy():
    """保存局域网部署设置并自动重启服务（保存到 settings.json 后拉起新进程）"""
    lan = 1 if request.form.get("lan_enabled") else 0
    try:
        port = int(request.form.get("lan_port", 5000) or 5000)
    except (TypeError, ValueError):
        port = 5000
    if not 1024 <= port <= 65535:
        port = 5000
    cfg = _settings_cfg()
    cfg["lan_enabled"] = bool(lan)
    cfg["port"] = port
    _settings.save(cfg)
    config.apply_settings(cfg)
    flash(_i18n.t("部署设置已保存：其他电脑可通过 http://{0}:{1} 访问（正在重启服务…）", _i18n.current_lang()).format(_local_ip(), port), "success")
    # 自动重启：启动新进程并退出当前进程
    try:
        import subprocess, sys
        subprocess.Popen([sys.executable, os.path.abspath(__file__)],
                         cwd=os.path.dirname(os.path.abspath(__file__)))
    except Exception as e:
        log.warning("自动重启失败：%s（请手动重启软件）", e)
        return _settings_reply(f"自动重启失败：{e}（请手动重启软件）", "danger", "card-lan")
    os._exit(0)


# 辅助
# ------------------------------------------------------------------
def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0


def _num_strict(v):
    """严格数字解析：失败返回 None（用于导入覆盖模式的数据验证）"""
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _qdec(v):
    """数量类型解析：填 float=小数；不填或填 int=整数（兼容旧写法 小数/是/1… 与 整数/否/0…）"""
    s = str(v or "").strip().lower()
    if s in ("float", "小数", "是", "1", "y", "yes", "true", "真"):
        return 1
    return 0  # int / integer / 整数 / 否 / 0 / false / 空 → 整数


def _qty_valid(p, q):
    """数量合法性：q>0；整数类备件（个/PCS/卷…）必须为正整数，小数类（米/克/KG…）允许小数"""
    if q <= 0:
        return False, "数量必须大于 0"
    if not p["qty_decimal"] and float(q) != int(q):
        return False, f"该备件按『{p['unit']}』计数，数量必须为整数（如 10），不能填小数"
    return True, ""


def _dept_manager(conn, applicant):
    """申请人所在部门的经理（role='manager' 且同部门且启用）；无则返回 None"""
    if not applicant.get("department"):
        return None
    return conn.execute(
        """SELECT id, display_name FROM users
           WHERE role='manager' AND department=? AND active=1
           ORDER BY id LIMIT 1""",
        (applicant["department"],),
    ).fetchone()


def _parse_exec_location(conn, f, part, is_out):
    """解析执行/直接出入库的库位参数
    返回 (loc_key, loc_text, err)：
      loc_key: int=locations.id 传给 move_stock；str=旧文本库位
    出库：必须选择现有库存库位（不允许新库位）
    入库：可现有库位或新库位（位置 id 或文本）
    """
    loc_id = f.get("location_id", "").strip()
    if loc_id and loc_id != "__NEW__":
        try:
            lid = int(loc_id)
        except (TypeError, ValueError):
            return None, "", "库位参数错误"
        loc = db.get_location(conn, lid)
        if not loc:
            return None, "", "所选库位不存在"
        return lid, db.location_text(loc), ""
    if is_out:
        return None, "", "出库请选择该备件有库存的库位"
    # 入库新库位：位置 id 优先，其次文本
    new_lid = f.get("new_location_id", "").strip()
    new_txt = f.get("new_location", "").strip()
    if new_lid:
        try:
            nid = int(new_lid)
        except (TypeError, ValueError):
            return None, "", "新库位参数错误"
        loc = db.get_location(conn, nid)
        if not loc:
            return None, "", "新库位不存在，请先在货架管理中建立"
        occ = conn.execute(
            """SELECT i.part_id, p.part_code FROM inventory i
               JOIN parts p ON i.part_id=p.id AND p.deleted=0
               WHERE i.location_id=? AND i.part_id<>? AND i.quantity>0 LIMIT 1""",
            (nid, part["id"]),
        ).fetchone()
        if occ:
            return None, "", f"该位置已有备件 [{occ['part_code']}] 存放库存，不能重复入库"
        return nid, db.location_text(loc), ""
    if new_txt:
        return None, new_txt, ""
    return None, "", "请选择库位（入库可选新库位）"


def _export_xlsx(headers, rows, sheet_name="导出数据"):
    """纯标准库生成 .xlsx（zip+xml，零第三方依赖），返回 BytesIO"""
    import zipfile
    from io import BytesIO

    def col_name(i):
        s = ""
        i += 1
        while i:
            i, m = divmod(i - 1, 26)
            s = chr(65 + m) + s
        return s

    xml_esc = lambda v: (str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                         .replace('"', "&quot;"))
    # sheet1.xml：表头 + 数据行（标准结构：<row r="N"> 包裹单元格）
    def make_row(r_num, values):
        cells = []
        for c_i, v in enumerate(values):
            r = col_name(c_i) + str(r_num)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                cells.append(f'<c r="{r}"><v>{v}</v></c>')
            else:
                cells.append(f'<c r="{r}" t="inlineStr"><is><t>{xml_esc(v)}</t></is></c>')
        return f'<row r="{r_num}">{"".join(cells)}</row>'

    data_rows = [make_row(1, headers)]
    for r_i, row in enumerate(rows, start=2):
        data_rows.append(make_row(r_i, row))
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(data_rows)}</sheetData></worksheet>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{xml_esc(sheet_name)}" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    wb_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>'
    )
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        z.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    buf.seek(0)
    return buf


# ------------------------------------------------------------------
# 启动入口（桌面直连版）
# ------------------------------------------------------------------
def setup_logging():
    """日志写入软件目录 logs/app.log（打包成无窗口 exe 后仍可排查问题）"""
    log_dir = os.path.join(_settings.APP_DIR, "logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError:
        log_dir = os.path.join(os.path.expanduser("~"), "备件管理系统", "logs")
        os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        filename=os.path.join(log_dir, "app.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )
    # 控制台（有窗口时）同步输出
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    logging.getLogger().addHandler(console)


def find_free_port(prefer):
    """端口被占用时自动向后找空闲端口"""
    import socket as _sock
    for p in range(prefer, prefer + 10):
        with _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM) as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return prefer


def is_port_in_use(port):
    import socket as _sock
    with _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main():
    setup_logging()
    log = logging.getLogger("main")
    # 若本机已有实例在运行，直接打开浏览器并退出（避免重复启动）
    if is_port_in_use(config.PORT):
        log.info("检测到本机端口 %s 已有实例在运行，直接打开浏览器", config.PORT)
        webbrowser.open(f"http://127.0.0.1:{config.PORT}")
        return
    port = find_free_port(config.PORT)
    if db_configured():
        try:
            db.init_db()
            log.info("数据库就绪：%s", config.DB_PATH)
        except Exception as e:
            log.error("数据库初始化失败：%s", e)
            _show_fatal("数据库初始化失败", f"{config.DB_PATH}\n{e}")
            return
    else:
        log.info("数据库未配置，进入初始化向导模式")
    # 延迟 0.8s 等服务起来再打开浏览器（测试环境可设 SMT_NO_BROWSER=1 关闭自动打开）
    if not os.environ.get("SMT_NO_BROWSER"):
        import threading as _th
        _th.Timer(0.8, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    # 数据库自动备份后台线程（按系统设置中的间隔自动备份到共享盘/指定目录）
    threading.Thread(target=_backup_worker, daemon=True).start()
    # 回收站自动清理后台线程（超保留期备件自动彻底清除）
    threading.Thread(target=_recycle_worker, daemon=True).start()
    if config.LAN_ENABLED:
        # 局域网部署：监听所有网卡，其他电脑通过 http://本机IP:端口 访问
        host = "0.0.0.0"
        log.info("备件管理系统启动（局域网部署）：http://0.0.0.0:%s", port)
    else:
        host = "127.0.0.1"
        log.info("备件管理系统启动：http://127.0.0.1:%s", port)
    app.run(host=host, port=port, debug=False, threaded=True)


@app.after_request
def _no_cache_html(resp):
    # 页面 HTML 不缓存：避免部署/升级后浏览器仍显示旧界面（自定义表头等修改即时生效）
    ct = (resp.headers.get("Content-Type") or "")
    if ct.startswith("text/html"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


def _show_fatal(title, msg):
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, msg)
        root.destroy()
    except Exception:
        pass


if __name__ == "__main__":
    import logging
    import webbrowser
    main()
