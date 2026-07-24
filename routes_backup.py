"""Backup-API: Status, Konfiguration, manueller Trigger."""

from datetime import datetime

from flask import Blueprint, jsonify, request

import config
from backup import (
    _backup_env_lesen,
    _backup_env_schreiben,
    _nas_config,
    _nas_configured,
    backup_stats_lesen,
    run_backup,
)

bp = Blueprint("backup", __name__)


@bp.route("/api/backup/status", methods=["GET"])
def api_backup_status():
    stats = backup_stats_lesen()
    nas = _nas_config()
    return jsonify({
        "last_run": stats["last_run"],
        "runs_this_year": stats["laeufe_anzahl"] if stats["laeufe_jahr"] == datetime.now().year else 0,
        "nas_configured": _nas_configured(),
        "nas_host": nas.host,
        "nas_base": nas.base,
        "nas_auto": config.NAS_AUTO,
    })


@bp.route("/api/backup/config", methods=["GET"])
def api_backup_config():
    nas = _nas_config()
    return jsonify({
        "nas_host": nas.host,
        "nas_user": nas.user,
        "nas_base": nas.base,
        "nas_key": bool(nas.key_path),
        "nas_auto": config.NAS_AUTO,
        "nas_daily_keep": config.NAS_DAILY_KEEP,
        "local_dir": str(config.BACKUP_DIR),
        "local_max": config.BACKUP_MAX_COUNT,
    })


@bp.route("/api/backup/config", methods=["POST"])
def api_backup_config_save():
    data = request.get_json(silent=True) or {}
    env = _backup_env_lesen()
    mapping = {
        "nas_host": "KAPA_BACKUP_NAS_HOST",
        "nas_user": "KAPA_BACKUP_NAS_USER",
        "nas_base": "KAPA_BACKUP_NAS_BASE",
        "nas_key": "KAPA_BACKUP_NAS_KEY",
    }
    for key, env_key in mapping.items():
        if key in data:
            env[env_key] = str(data[key])
    if "nas_auto" in data:
        config.NAS_AUTO = str(data["nas_auto"]).lower() in ("1", "true", "yes")
    if "nas_daily_keep" in data:
        try:
            config.NAS_DAILY_KEEP = int(data["nas_daily_keep"])
        except (TypeError, ValueError):
            pass
    _backup_env_schreiben(env)
    return jsonify({"success": True})


@bp.route("/api/backup/run", methods=["POST"])
def api_backup_run():
    nas = _nas_config() if _nas_configured() else None
    result = run_backup(nas)
    return jsonify(result)
