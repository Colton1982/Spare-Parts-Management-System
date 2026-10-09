# -*- coding: utf-8 -*-
"""
i18n 同步工具（翻译扩展入口）
================================
用法：
  python3 i18n_tool.py scan        # 扫描全项目未登记的中文文案（模板/JS/Python/flash）
  python3 i18n_tool.py skeleton    # 为未登记词条生成 8 语言骨架（i18n/_pending.json），
                                   # 缺译语言回退中文，界面不会出现空白/占位

扩展流程（加新功能后）：
  1. 代码里照常写 {{ tr('中文') }} / TR('中文') / flash("中文")
  2. python3 i18n_tool.py scan       -> 看到新词条清单
  3. python3 i18n_tool.py skeleton   -> 生成 i18n/_pending.json（en 填英文，其余留空）
  4. 把 _pending.json 中的翻译合并进对应 i18n/<lang>.json
     缺译的词条界面自动显示中文原文，永不空白。
"""
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
LANGS = ["en", "ja", "ko", "th", "vi", "ru", "fr", "de"]


def _walk_files(dirs, exts):
    for d in dirs:
        for root, _dirs, files in os.walk(d):
            _dirs[:] = [x for x in _dirs if x not in ("runtime", "__pycache__", ".git", "node_modules", ".idea", "venv", "site-packages")]
            for fn in files:
                if fn.endswith(exts) and not fn.endswith(".pyc"):
                    yield os.path.join(root, fn)


def scan_texts():
    """扫描所有 tr()/TR()/t()/flash 里的中文原文，返回 {中文: [来源]}"""
    found = {}

    def add(txt, src):
        txt = txt.strip()
        if not txt or not re.search(r"[\u4e00-\u9fff]", txt):
            return
        found.setdefault(txt, set()).add(src)

    # 模板：{{ tr('中文') }} / tr("中文")
    pat_tpl = re.compile(r"tr\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")
    for f in _walk_files([os.path.join(BASE, "templates")], (".html",)):
        for i, line in enumerate(open(f, encoding="utf-8"), 1):
            for m in pat_tpl.finditer(line):
                add(m.group(1), f"{os.path.relpath(f, BASE)}:{i}")

    # JS：TR('中文')
    pat_js = re.compile(r"TR\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")
    for f in _walk_files([os.path.join(BASE, "static", "js")], (".js",)):
        for i, line in enumerate(open(f, encoding="utf-8"), 1):
            for m in pat_js.finditer(line):
                add(m.group(1), f"{os.path.relpath(f, BASE)}:{i}")

    # Python：t('中文', / tr 注入的 t 调用 / flash("中文")
    pat_py = re.compile(r"(?:t|flash)\s*\(\s*['\"]([^'\"]*[\u4e00-\u9fff][^'\"]*)['\"]")
    for f in _walk_files([BASE], (".py",)):
        if f.endswith("i18n.py") or f.endswith("i18n_tool.py"):
            continue
        for i, line in enumerate(open(f, encoding="utf-8"), 1):
            for m in pat_py.finditer(line):
                s = m.group(1)
                if "\\" in s:  # Python 源码转义还原，与运行时字符串一致
                    try:
                        s = s.encode("utf-8").decode("unicode_escape")
                    except Exception:
                        pass
                add(s, f"{os.path.relpath(f, BASE)}:{i}")

    return {k: sorted(v) for k, v in found.items()}


def existing_keys():
    keys = set()
    for lang in LANGS:
        try:
            d = json.load(open(os.path.join(BASE, "i18n", lang + ".json"), encoding="utf-8"))
            keys |= set(d.keys())
        except Exception:
            pass
    try:
        zh = json.load(open(os.path.join(BASE, "i18n", "zh.json"), encoding="utf-8"))
        keys |= set(zh.keys())
        keys |= set(zh.values())  # key 式词条的中文原文也算已覆盖
    except Exception:
        pass
    return keys


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "scan"
    texts = scan_texts()
    exist = existing_keys()
    missing = {k: v for k, v in texts.items() if k not in exist}
    if cmd == "scan":
        print(f"扫描到中文文案 {len(texts)} 条，未登记 {len(missing)} 条：")
        for k, v in sorted(missing.items(), key=lambda x: -len(x[1])):
            print(f"  {k}   [{','.join(sorted(v)[:3])}]")
    elif cmd == "skeleton":
        path = os.path.join(BASE, "i18n", "_pending.json")
        old = {}
        if os.path.exists(path):
            old = json.load(open(path, encoding="utf-8"))
        out = {}
        for k in missing:
            out[k] = {"zh": k, "en": old.get(k, {}).get("en", "")}
            for lang in LANGS:
                if lang != "en":
                    out[k][lang] = old.get(k, {}).get(lang, "")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print(f"已生成骨架 i18n/_pending.json（{len(out)} 条）。缺译语言界面自动回退中文，不会空白。")
    else:
        print("用法: python3 i18n_tool.py scan|skeleton")


if __name__ == "__main__":
    main()
