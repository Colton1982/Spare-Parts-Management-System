# -*- coding: utf-8 -*-
"""
配置持久化：数据库路径等设置保存在软件目录 settings.json 中
（软件放公共盘时，所有用户共享同一份配置；也可各自复制到本机后各自配置）
"""
import json
import os
import sys

# 软件运行目录：打包成 exe 后为 exe 所在目录
def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

APP_DIR = app_dir()
SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")
_FALLBACK_FILE = None  # 软件目录不可写时回退到用户目录

DEFAULTS = {
    "db_path": "",        # SQLite 数据库文件位置（默认空=未配置，启动后进入初始化向导）
    "db_type": "sqlite",  # 数据库类型：sqlite/mysql/mariadb/postgresql/mssql/oracle
    "db_host": "",        # 服务器地址（非 SQLite）
    "db_port": 0,         # 端口（非 SQLite）
    "db_user": "",        # 用户名（非 SQLite）
    "db_password": "",    # 密码（非 SQLite）
    "db_database": "",    # 数据库/库名（非 SQLite；Oracle 用 service_name 时可为空）
    "db_service_name": "",# Oracle 服务名（仅 Oracle）
    "upload_dir": "",     # 备件图片目录（空=数据库同级 parts_img）
    "port": 5000,         # 本机服务端口
    "demo_data": False,   # 首次建库是否写入演示数据
    "lan_enabled": False, # 局域网部署：True=监听 0.0.0.0，其他电脑可用 http://本机IP:端口 访问
    "ad": {},             # AD 域登录配置（enabled/server/port/ssl/domain/name_format）
    "language": "zh",     # 界面语言（zh/en/ja/ko/th/vi/ru/fr/de）
}


def _fallback_file():
    global _FALLBACK_FILE
    if _FALLBACK_FILE:
        return _FALLBACK_FILE
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "备件管理系统")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        d = os.path.dirname(SETTINGS_FILE)
    _FALLBACK_FILE = os.path.join(d, "settings.json")
    return _FALLBACK_FILE


def load():
    """读取配置（不存在返回默认值）"""
    data = dict(DEFAULTS)
    for path in (SETTINGS_FILE, _fallback_file()):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data.update(json.load(f))
                break
            except Exception:
                continue
    # 类型与边界清理
    try:
        data["port"] = int(data.get("port") or 5000)
    except Exception:
        data["port"] = 5000
    if not 1024 <= data["port"] <= 65535:
        data["port"] = 5000
    return data


def save(settings):
    """保存配置：优先写软件目录，写失败回退用户目录；返回实际保存位置"""
    data = dict(DEFAULTS)
    data.update(settings)
    # 先尝试软件目录
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return SETTINGS_FILE
    except OSError:
        path = _fallback_file()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path
