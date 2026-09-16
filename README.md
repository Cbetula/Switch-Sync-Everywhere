# Switch-Sync-Everywhere

一个本机 Python 网页服务，用于管理 Codex 的 `config.toml` 与 `auth.json` 配置模板。 注意python==3.11

## 启动

```bash

pip install -r requirements.txt
python -m cbe_switch --port 8000
```

安装后也可使用命令：

```bash
switch-sync-everywhere --port 8000
```

然后打开 <http://127.0.0.1:8000>。

可用参数：

```text
--host 127.0.0.1
--port 8000
```

配置默认保存到 `~/.config/switch-sync-everywhere`，启用时覆盖 `~/.codex/config.toml` 和 `~/.codex/auth.json`。如需测试或使用其他目录，可设置 `CBE_SWITCH_HOME` 和 `CODEX_HOME`。

模板支持 `{{KEY}}` 和 `{{URL}}`，保存与启用前会分别校验 TOML 和 JSON。
