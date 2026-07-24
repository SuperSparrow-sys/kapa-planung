"""Backup-API: Status, Konfiguration, manueller Trigger."""

from datetime import datetime

from flask import Blueprint, jsonify, request

from backup import (
    _backup_ziel_laden,
    _backup_ziel_speichern,
    _env_lesen,
    _env_schreiben,
    backup_stats_lesen,
    run_all_backups,
)

bp = Blueprint("backup", __name__)

_ziele = [_backup_ziel_laden(1), _backup_ziel_laden(2)]


def _backup_unlock_pw() -> str:
    return _env_lesen().get("BACKUP_UNLOCK_PASSWORD", "backup!")


def _backup_unlock_pw_speichern(pw: str) -> None:
    data = _env_lesen()
    data["BACKUP_UNLOCK_PASSWORD"] = pw
    _env_schreiben(data)


def _backup_api_config(idx: int) -> dict:
    z = _ziele[idx - 1]
    return {
        "nas_host": z.nas_host,
        "nas_user": z.nas_user,
        "nas_base": z.nas_base,
        "nas_key_path": bool(z.nas_key_path),
    }


def _backup_api_voll(idx: int) -> dict:
    z = _ziele[idx - 1]
    return {
        "nas_host": z.nas_host,
        "nas_user": z.nas_user,
        "nas_base": z.nas_base,
        "nas_key_path": z.nas_key_path,
    }


@bp.route("/api/backup/unlock", methods=["POST"])
def api_backup_unlock():
    data = request.get_json(silent=True) or {}
    pw = str(data.get("password", ""))
    if pw != _backup_unlock_pw():
        return jsonify({"success": False, "error": "Passwort falsch"}), 401
    return jsonify({
        "success": True,
        "unlock_password": _backup_unlock_pw(),
        "ziel1": _backup_api_voll(1),
        "ziel2": _backup_api_voll(2),
    })


@bp.route("/api/backup/unlock-password", methods=["POST"])
def api_backup_unlock_password_aendern():
    data = request.get_json(silent=True) or {}
    alt = str(data.get("altes_passwort", ""))
    neu = str(data.get("neues_passwort", ""))
    if alt != _backup_unlock_pw():
        return jsonify({"success": False, "error": "Altes Passwort falsch"}), 401
    if not neu:
        return jsonify({"success": False, "error": "Neues Passwort darf nicht leer sein"}), 400
    _backup_unlock_pw_speichern(neu)
    return jsonify({"success": True})


@bp.route("/api/backup/config/<int:idx>", methods=["GET"])
def api_backup_config(idx):
    if idx not in (1, 2):
        return jsonify({"success": False, "error": "Ungültiger Index"}), 400
    return jsonify(_backup_api_config(idx))


@bp.route("/api/backup/config/<int:idx>", methods=["POST"])
def api_backup_save(idx):
    if idx not in (1, 2):
        return jsonify({"success": False, "error": "Ungültiger Index"}), 400
    z = _ziele[idx - 1]
    data = request.get_json(silent=True) or {}
    for k in ("nas_host", "nas_user", "nas_base", "nas_key_path"):
        if k in data:
            setattr(z, k, str(data[k]))
    _backup_ziel_speichern(idx, z)
    return jsonify({"success": True})


@bp.route("/api/backup/status", methods=["GET"])
def api_backup_status():
    stats = backup_stats_lesen()
    year = str(datetime.now().year)
    year_data = stats.get(year, {})
    return jsonify({
        "last_run": year_data.get("last_run", ""),
        "runs_this_year": year_data.get("count", 0),
        "stats": stats,
    })


@bp.route("/api/backup/run", methods=["POST"])
def api_backup_run():
    global _ziele
    _ziele = [_backup_ziel_laden(1), _backup_ziel_laden(2)]
    result = run_all_backups(_ziele)
    return jsonify(result)
