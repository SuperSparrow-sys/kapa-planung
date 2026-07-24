"""Datenbank-Backup: lokal + optional via SCP auf NAS.

Aufruf via CLI:  python backup.py
Aufruf via API:   POST /api/backup/run
Automatisch:      taeglich 02:00 + 22:00 (wenn KAPA_BACKUP_NAS_AUTO=true)
"""

import logging
import os
import shutil
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import config

logger = logging.getLogger(__name__)

# Bekannte Schluessel in backup.env
_BEKANNTE_SCHLUESSEL = {
    "BACKUP_LETZTER_LAUF", "BACKUP_LAEUFE_JAHR", "BACKUP_LAEUFE_ANZAHL",
    "KAPA_BACKUP_NAS_HOST", "KAPA_BACKUP_NAS_USER", "KAPA_BACKUP_NAS_BASE", "KAPA_BACKUP_NAS_KEY",
    "KAPA_NAS_AUTO", "KAPA_NAS_DAILY_KEEP",
}


# ---------------------------------------------------------------------------
# Stats-Persistenz (backup.env)
# ---------------------------------------------------------------------------

def _backup_env_lesen() -> dict:
    result = {}
    if not config.BACKUP_ENV_FILE.exists():
        return result
    with open(config.BACKUP_ENV_FILE, encoding="utf-8") as f:
        for zeile in f:
            zeile = zeile.strip()
            if not zeile or zeile.startswith("#") or "=" not in zeile:
                continue
            key, _, val = zeile.partition("=")
            result[key.strip()] = val.strip()
    return result


def _backup_env_schreiben(daten: dict) -> None:
    zeilen = []
    if config.BACKUP_ENV_FILE.exists():
        with open(config.BACKUP_ENV_FILE, encoding="utf-8") as f:
            zeilen = f.readlines()
    neue = []
    gesehen = set()
    for zeile in zeilen:
        stripped = zeile.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            neue.append(zeile)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in _BEKANNTE_SCHLUESSEL:
            neue.append(f"{key}={daten.get(key, '')}\n")
            gesehen.add(key)
        else:
            neue.append(zeile)
    for key in sorted(_BEKANNTE_SCHLUESSEL):
        if key not in gesehen:
            neue.append(f"{key}={daten.get(key, '')}\n")
    config.BACKUP_ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(config.BACKUP_ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(neue)


def backup_stats_lesen() -> dict:
    env = _backup_env_lesen()
    return {
        "last_run": env.get("BACKUP_LETZTER_LAUF", ""),
        "laeufe_anzahl": int(env.get("BACKUP_LAEUFE_ANZAHL", "0") or 0),
        "laeufe_jahr": int(env.get("BACKUP_LAEUFE_JAHR", "0") or 0),
    }


def _backup_stats_schreiben(zeitstempel: str, anzahl: int, jahr: int) -> None:
    env = _backup_env_lesen()
    env["BACKUP_LETZTER_LAUF"] = zeitstempel
    env["BACKUP_LAEUFE_ANZAHL"] = str(anzahl)
    env["BACKUP_LAEUFE_JAHR"] = str(jahr)
    _backup_env_schreiben(env)


# ---------------------------------------------------------------------------
# NAS Backup via SCP
# ---------------------------------------------------------------------------

@dataclass
class NasConfig:
    host: str = ""
    user: str = ""
    base: str = ""
    key_path: str = ""


def _nas_configured() -> bool:
    env = _backup_env_lesen()
    host = os.environ.get("KAPA_BACKUP_NAS_HOST", env.get("KAPA_BACKUP_NAS_HOST", ""))
    user = os.environ.get("KAPA_BACKUP_NAS_USER", env.get("KAPA_BACKUP_NAS_USER", ""))
    base = os.environ.get("KAPA_BACKUP_NAS_BASE", env.get("KAPA_BACKUP_NAS_BASE", ""))
    return bool(host and user and base)


def _nas_config() -> NasConfig:
    env = _backup_env_lesen()
    return NasConfig(
        host=os.environ.get("KAPA_BACKUP_NAS_HOST", env.get("KAPA_BACKUP_NAS_HOST", "")),
        user=os.environ.get("KAPA_BACKUP_NAS_USER", env.get("KAPA_BACKUP_NAS_USER", "")),
        base=os.environ.get("KAPA_BACKUP_NAS_BASE", env.get("KAPA_BACKUP_NAS_BASE", "")),
        key_path=os.environ.get("KAPA_BACKUP_NAS_KEY", env.get("KAPA_BACKUP_NAS_KEY", "")),
    )


def nas_config_export() -> NasConfig:
    return _nas_config()


def _ssh_key_option(cfg: NasConfig) -> list[str]:
    if cfg.key_path:
        return ["-i", cfg.key_path]
    return []


def _ssh_cmd(cfg: NasConfig, *args) -> subprocess.CompletedProcess:
    cmd = ["ssh"]
    cmd.extend(_ssh_key_option(cfg))
    cmd.extend([
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=20",
        "-o", "BatchMode=yes",
        f"{cfg.user}@{cfg.host}",
        *args,
    ])
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


def _scp_transfer(cfg: NasConfig, local: Path, remote: str) -> bool:
    cmd = ["scp", "-O"]
    cmd.extend(_ssh_key_option(cfg))
    cmd.extend([
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=20",
        str(local),
        f"{cfg.user}@{cfg.host}:{remote}",
    ])
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        logger.warning("SCP-Fehler (rc=%d): %s", r.returncode, r.stderr.strip()[:200])
    return r.returncode == 0


# ---------------------------------------------------------------------------
# Backup-Logik
# ---------------------------------------------------------------------------

def _backup_sqlite(src: Path, dst: Path) -> bool:
    try:
        con_src = sqlite3.connect(str(src))
        con_dst = sqlite3.connect(str(dst))
        con_src.backup(con_dst)
        con_src.close()
        con_dst.close()
        return True
    except Exception as exc:
        logger.warning("SQLite .backup fehlgeschlagen (%s), fallback copy: %s", src.name, exc)
        try:
            shutil.copy2(src, dst)
            return dst.exists()
        except Exception as exc2:
            logger.error("Copy fallback fehlgeschlagen: %s", exc2)
            return False


def run_backup(nas: NasConfig | None = None) -> dict:
    errors = []
    files_ok = 0
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    src = config.DB_PATH

    if not src.exists():
        return {"success": False, "message": "Datenbank nicht gefunden", "files": 0, "errors": ["kapa.db existiert nicht"]}

    # ── 1. Lokales Backup ────────────────────────────────────────────
    config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    local_dst = config.BACKUP_DIR / f"kapa_backup_{timestamp}.db"

    if _backup_sqlite(src, local_dst):
        files_ok += 1
        logger.info("Lokales Backup OK: %s", local_dst.name)
        # Rotation
        backups = sorted(config.BACKUP_DIR.glob("kapa_backup_*.db"))
        while len(backups) > config.BACKUP_MAX_COUNT:
            oldest = backups.pop(0)
            oldest.unlink()
    else:
        errors.append("Lokales Backup fehlgeschlagen")

    # ── 2. NAS-Backup (optional) ─────────────────────────────────────
    if nas is None and _nas_configured():
        nas = _nas_config()

    if nas and nas.host:
        logger.info("Starte NAS-Backup %s@%s", nas.user, nas.host)

        r = _ssh_cmd(nas, "echo", "ok")
        if r.returncode != 0 or r.stdout.strip() != "ok":
            msg = r.stderr.strip() or "SSH-Verbindung fehlgeschlagen"
            errors.append(f"SSH-Fehler: {msg}")
        else:
            tmp_dir = Path(tempfile.mkdtemp(prefix="kapa_nas_"))
            try:
                tmp_file = tmp_dir / "kapa.db"
                if _backup_sqlite(src, tmp_file):
                    remote_dir = f"{nas.base}/daily/{today}"
                    r2 = _ssh_cmd(nas, "mkdir", "-p", remote_dir)
                    if r2.returncode != 0:
                        errors.append("NAS mkdir fehlgeschlagen")
                    elif _scp_transfer(nas, tmp_file, f"{remote_dir}/kapa.db"):
                        files_ok += 1
                        size_kb = tmp_file.stat().st_size // 1024
                        logger.info("NAS-Backup OK: %s/daily/%s/kapa.db (%d KB)", nas.base, today, size_kb)
                    else:
                        errors.append("NAS-Upload fehlgeschlagen")
                else:
                    errors.append("NAS lokale Kopie fehlgeschlagen")
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

            # Alte daily-Verzeichnisse aufräumen
            try:
                r = _ssh_cmd(nas, "ls", "-1d", f"{nas.base}/daily/????-??-??")
                if r.returncode == 0 and r.stdout.strip():
                    dirs = sorted(d.strip() for d in r.stdout.splitlines() if d.strip())
                    for d in dirs[:-config.NAS_DAILY_KEEP]:
                        _ssh_cmd(nas, "rm", "-rf", d)
            except Exception as exc:
                logger.warning("NAS-Cleanup daily fehlgeschlagen: %s", exc)

    if not errors and files_ok > 0:
        msg = f"{files_ok} Datei(en) gesichert"
        success = True
        logger.info("Backup erfolgreich: %s", msg)
    else:
        msg = "Backup-Fehler: " + ("; ".join(errors) if errors else "keine Dateien gesichert")
        success = files_ok > 0
        if errors:
            logger.warning(msg)

    # ── Statistiken aktualisieren ────────────────────────────────────
    zeitstempel = now.strftime("%Y-%m-%dT%H:%M:%S")
    aktuelles_jahr = now.year
    stats = backup_stats_lesen()
    anzahl = (stats["laeufe_anzahl"] if stats["laeufe_jahr"] == aktuelles_jahr else 0) + 1
    _backup_stats_schreiben(zeitstempel, anzahl, aktuelles_jahr)

    return {
        "success": success,
        "message": msg,
        "files": files_ok,
        "errors": errors,
        "last_run": zeitstempel,
        "runs_this_year": anzahl,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from database import init_db
    init_db()
    result = run_backup()
    print(result["message"])
    if result["errors"]:
        for e in result["errors"]:
            print(f"  - {e}")
