from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .storage import ConfigStore, ValidationError

app = FastAPI(title="CBE Switch")
store = ConfigStore()
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(404, "配置或备份不存在")
    return HTTPException(400, str(exc))


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/profiles")
def profiles() -> list[dict[str, Any]]:
    return store.list_profiles()


@app.get("/api/profiles/{profile_id}")
def profile(profile_id: str) -> dict[str, Any]:
    try:
        return store.get_profile(profile_id)
    except Exception as exc:
        raise error(exc) from exc


@app.post("/api/profiles")
def create_profile(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return store.save_profile(payload)
    except Exception as exc:
        raise error(exc) from exc


@app.put("/api/profiles/{profile_id}")
def update_profile(profile_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return store.save_profile(payload, profile_id)
    except Exception as exc:
        raise error(exc) from exc


@app.post("/api/profiles/{profile_id}/duplicate")
def duplicate_profile(profile_id: str) -> dict[str, Any]:
    try:
        return store.duplicate_profile(profile_id)
    except Exception as exc:
        raise error(exc) from exc


@app.delete("/api/profiles/{profile_id}")
def delete_profile(profile_id: str) -> dict[str, bool]:
    try:
        store.delete_profile(profile_id)
        return {"ok": True}
    except Exception as exc:
        raise error(exc) from exc


@app.post("/api/profiles/{profile_id}/preview")
def preview_profile(profile_id: str, payload: dict[str, Any] | None = None) -> dict[str, str]:
    try:
        profile = store.get_profile(profile_id)
        if payload:
            profile.update(payload)
        config, auth = store.render(profile["config_template"], profile["auth_template"], profile["key"], profile["url"])
        return {"config": config, "auth": auth}
    except Exception as exc:
        raise error(exc) from exc


@app.post("/api/profiles/{profile_id}/activate")
def activate_profile(profile_id: str) -> dict[str, Any]:
    try:
        return store.activate(profile_id)
    except Exception as exc:
        raise error(exc) from exc


@app.get("/api/backups")
def backups() -> list[dict[str, Any]]:
    return store.list_backups()


@app.post("/api/backups/{backup_id}/restore")
def restore_backup(backup_id: str) -> dict[str, Any]:
    try:
        return store.restore(backup_id)
    except Exception as exc:
        raise error(exc) from exc

