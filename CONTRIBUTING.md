# Contributing（贡献指南）

感谢你愿意为 **SPMS 备件管理系统** 贡献代码。请遵循以下约定，让协作更顺畅。

## 1. 环境准备

```bash
git clone <仓库地址>
cd SPMS
pip install -r requirements.txt    # SQLite 即用；多数据库另装 requirements-full.txt
python app.py                      # 本地起服务 http://127.0.0.1:5000
```

## 2. 分支与提交

- 新功能/修复从 `main` 拉分支：`git checkout -b feat/xxx` 或 `fix/xxx`。
- 提交信息用中文或英文均可，保持简洁：`fix: 修复库存数量取整问题`。
- 一次提交只做一件事；保持改动聚焦，不做无关重构。

## 3. 代码与界面约定

- **界面文案必须走翻译通道**：模板 `{{ tr('中文') }}`、JS `TR('中文')`、Python `_i18n.t('中文', lang)`，不要硬编码中文/英文。
- 新增界面文案后必须跑 `python3 i18n_tool.py scan` 确认 0 未登记，并补齐 9 种语言（zh/en/ja/ko/th/vi/ru/fr/de）。
- 业务数据（备件名、部门名、用户名、申请原因等）不翻译，属设计约定。
- 保持现有代码风格：函数命名一致、SQL 参数化（禁止拼接）、模板复用 base.html。

## 4. 提交 PR 前检查

- [ ] `python app.py` 可正常启动，无报错
- [ ] `python3 i18n_tool.py scan` 无未登记词条
- [ ] 涉及数据库改动时同步更新 `database.py` 建表逻辑（含升级路径）
- [ ] 不包含 `settings.json`、`data/*`、`logs/`、密钥等敏感内容

## 5. 议题（Issue）

- 描述问题：复现步骤 / 期望行为 / 实际行为 / 环境（系统、浏览器、Python 版本）。
- 建议类议题请说明使用场景，方便评估优先级。

## 6. 行为准则

保持友善与专业，就事论事；涉及安全问题时**不要公开披露漏洞细节**，请直接联系维护者或走 SECURITY.md 流程。
