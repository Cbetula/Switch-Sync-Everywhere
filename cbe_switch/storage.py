from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PLACEHOLDER_RE = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")
ALL_PLACEHOLDER_RE = re.compile(r"{{\s*([^{}]+?)\s*}}")
ALLOWED_PLACEHOLDERS = {"KEY", "URL"}


class ValidationError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ConfigStore:
    def __init__(self, root: Path | None = None, codex_home: Path | None = None):
        self.root = Path(root or os.environ.get("CBE_SWITCH_HOME", Path.home() / ".config" / "switch-sync-everywhere")).expanduser()
        self.codex_home = Path(codex_home or os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
        self.profiles_dir = self.root / "profiles"
        self.backups_dir = self.root / "backups"
        self.state_path = self.root / "state.json"
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)

    def _profile_dir(self, profile_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", profile_id):
            raise ValidationError("无效的配置 ID")
        return self.profiles_dir / profile_id

    def _read_json(self, path: Path, default: Any = None) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValidationError(f"{path.name} 不是有效 JSON: {exc.msg}") from exc

    def _write_json(self, path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _validate_and_render(self, template: str, value: str, kind: str) -> str:
        unknown = sorted({m.group(1) for m in ALL_PLACEHOLDER_RE.finditer(template)} - ALLOWED_PLACEHOLDERS)
        if unknown:
            raise ValidationError(f"{kind} 包含未知占位符: {', '.join(unknown)}")
        return PLACEHOLDER_RE.sub(lambda m: value[m.group(1)], template)

    def render(self, config_template: str, auth_template: str, key: str, url: str) -> tuple[str, str]:
        config = self._validate_and_render(config_template, {"KEY": key, "URL": url}, "config.toml")
        auth = self._validate_and_render(auth_template, {"KEY": key, "URL": url}, "auth.json")
        try:
            import tomllib
            tomllib.loads(config)
        except Exception as exc:
            raise ValidationError(f"config.toml 校验失败: {exc}") from exc
        try:
            parsed = json.loads(auth)
            if not isinstance(parsed, dict):
                raise ValidationError("auth.json 顶层必须是 JSON 对象")
        except json.JSONDecodeError as exc:
            raise ValidationError(f"auth.json 校验失败: {exc.msg}") from exc
        return config, auth

    def _summary(self, meta: dict[str, Any]) -> dict[str, Any]:
        return {**meta, "key": "" if not meta.get("key") else "*" * max(4, min(12, len(meta["key"]))) }

    def list_profiles(self) -> list[dict[str, Any]]:
        active = self.get_state().get("active_profile_id")
        result = []
        for directory in sorted(self.profiles_dir.iterdir() if self.profiles_dir.exists() else [], key=lambda p: p.name):
            if not directory.is_dir():
                continue
            meta = self._read_json(directory / "meta.json")
            if not isinstance(meta, dict):
                continue
            result.append({**self._summary(meta), "active": meta.get("id") == active})
        return result

    def get_state(self) -> dict[str, Any]:
        value = self._read_json(self.state_path, {})
        return value if isinstance(value, dict) else {}

    def get_profile(self, profile_id: str) -> dict[str, Any]:
        directory = self._profile_dir(profile_id)
        meta = self._read_json(directory / "meta.json")
        if not isinstance(meta, dict):
            raise FileNotFoundError(profile_id)
        return {
            **meta,
            "config_template": (directory / "config.toml").read_text(encoding="utf-8"),
            "auth_template": (directory / "auth.json").read_text(encoding="utf-8"),
        }

    def save_profile(self, payload: dict[str, Any], profile_id: str | None = None) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        key = str(payload.get("key", ""))
        url = str(payload.get("url", "")).strip()
        config_template = str(payload.get("config_template", ""))
        auth_template = str(payload.get("auth_template", ""))
        if not name:
            raise ValidationError("名称不能为空")
        if not url:
            raise ValidationError("URL 不能为空")
        if not config_template.strip() or not auth_template.strip():
            raise ValidationError("两个模板都不能为空")
        self.render(config_template, auth_template, key, url)
        profile_id = profile_id or uuid.uuid4().hex
        directory = self._profile_dir(profile_id)
        if directory.exists() and not (directory / "meta.json").exists():
            raise ValidationError("配置目录无效")
        now = utc_now()
        previous = self._read_json(directory / "meta.json", {}) or {}
        meta = {"id": profile_id, "name": name, "key": key, "url": url, "created_at": previous.get("created_at", now), "updated_at": now}
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "config.toml").write_text(config_template, encoding="utf-8")
        (directory / "auth.json").write_text(auth_template, encoding="utf-8")
        self._write_json(directory / "meta.json", meta)
        return self.get_profile(profile_id)

    def delete_profile(self, profile_id: str) -> None:
        directory = self._profile_dir(profile_id)
        if not directory.exists():
            raise FileNotFoundError(profile_id)
        if self.get_state().get("active_profile_id") == profile_id:
            self._write_json(self.state_path, {})
        shutil.rmtree(directory)

    def duplicate_profile(self, profile_id: str) -> dict[str, Any]:
        source = self.get_profile(profile_id)
        source["name"] = f"{source['name']} 副本"
        return self.save_profile(source)

    def _atomic_write(self, target: Path, content: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def activate(self, profile_id: str) -> dict[str, Any]:
        profile = self.get_profile(profile_id)
        config, auth = self.render(profile["config_template"], profile["auth_template"], profile["key"], profile["url"])
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_id = f"{timestamp}-{uuid.uuid4().hex[:8]}"
        backup = self.backups_dir / backup_id
        backup.mkdir(parents=True)
        manifest = {"id": backup_id, "created_at": utc_now(), "profile_id": profile_id, "files": {}}
        targets = {"config.toml": self.codex_home / "config.toml", "auth.json": self.codex_home / "auth.json"}
        for name, target in targets.items():
            existed = target.exists()
            manifest["files"][name] = existed
            if existed:
                shutil.copy2(target, backup / name)
        self._write_json(backup / "manifest.json", manifest)
        try:
            self._atomic_write(targets["config.toml"], config)
            self._atomic_write(targets["auth.json"], auth)
        except Exception:
            for name, target in targets.items():
                old = backup / name
                if manifest["files"][name] and old.exists():
                    shutil.copy2(old, target)
            raise
        self._write_json(self.state_path, {"active_profile_id": profile_id, "activated_at": utc_now(), "backup_id": backup_id})
        return {"profile": self.get_profile(profile_id), "config": config, "auth": auth, "backup_id": backup_id}

    def list_backups(self) -> list[dict[str, Any]]:
        result = []
        for directory in sorted(self.backups_dir.iterdir() if self.backups_dir.exists() else [], reverse=True):
            manifest = self._read_json(directory / "manifest.json") if directory.is_dir() else None
            if isinstance(manifest, dict):
                result.append(manifest)
        return result

    def restore(self, backup_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"[0-9TZ-]+-[a-f0-9]{8}", backup_id):
            raise ValidationError("无效的备份 ID")
        backup = self.backups_dir / backup_id
        manifest = self._read_json(backup / "manifest.json")
        if not isinstance(manifest, dict):
            raise FileNotFoundError(backup_id)
        for name, existed in manifest.get("files", {}).items():
            target = self.codex_home / name
            source = backup / name
            if existed and source.exists():
                self._atomic_write(target, source.read_text(encoding="utf-8"))
            elif not existed and target.exists():
                target.unlink()
        self._write_json(self.state_path, {"active_profile_id": None, "restored_backup_id": backup_id, "restored_at": utc_now()})
        return manifest
