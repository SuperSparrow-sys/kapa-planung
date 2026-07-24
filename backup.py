"""Backup: lokal + via SCP auf NAS (bis zu 2 Ziele).

Konfiguration: backup.env (Laufzeit, gitignored)
Stats:         backup_stats.json
API:            POST /api/backup/run, GET /api/backup/status
"""

import json
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

_BASIS = os.path.dirname(os.path.abspath(__file__))
_ENV_PFAD = os.path.join(_BASIS, "backup.env")
_STATS_PFAD = os.path.join(_BASIS, "backup_stats.json")

_SSH_BIN = shutil.which("ssh") or "/usr/bin/ssh"
_SCP_BIN = shutil.which("scp") or "/usr/bin/scp"


def _env_lesen() -> dict:
    result = {}
    if not os.path.exists(_ENV_PFAD):
        return result
    with open(_ENV_PFAD, encoding="utf-8-sig") as f:
        for zeile in f:
            zeile = zeile.strip()
            if not zeile or zeile.startswith("#") or "=" not in zeile:
                continue
            key, _, val = zeile.partition("=")
            result[key.strip()] = val.strip()
    return result


def _env_schreiben(daten: dict) -> None:
    bekannte_schluessel = {
        "BACKUP_UNLOCK_PASSWORD",
        "BACKUP_1_HOST", "BACKUP_1_USER", "BACKUP_1_BASE", "BACKUP_1_SSH_KEY",
        "BACKUP_2_HOST", "BACKUP_2_USER", "BACKUP_2_BASE", "BACKUP_2_SSH_KEY",
    }
    zeilen = []
    if os.path.exists(_ENV_PFAD):
        with open(_ENV_PFAD, encoding="utf-8-sig") as f:
            zeilen = f.readlines()
    neue_zeilen = []
    gesehen = set()
    for zeile in zeilen:
        stripped = zeile.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            neue_zeilen.append(zeile)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in bekannte_schluessel:
            wert = daten.get(key, "")
            neue_zeilen.append(f"{key}={wert}\n")
            gesehen.add(key)
        else:
            neue_zeilen.append(zeile)
    for key in bekannte_schluessel:
        if key not in gesehen:
            wert = daten.get(key, "")
            neue_zeilen.append(f"{key}={wert}\n")
    with open(_ENV_PFAD, "w", encoding="utf-8") as f:
        f.writelines(neue_zeilen)


def _stats_laden() -> dict:
    if os.path.exists(_STATS_PFAD):
        try:
            with open(_STATS_PFAD, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _stats_speichern(stats: dict) -> None:
    try:
        Path(_STATS_PFAD).parent.mkdir(parents=True, exist_ok=True)
        with open(_STATS_PFAD, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning("Backup-Statistik konnte nicht gespeichert werden: %s", e)


def backup_stats_lesen() -> dict:
    return _stats_laden()


def _backup_stats_schreiben(zeitstempel: str, anzahl: int, jahr: int) -> None:
    stats = _stats_laden()
    year_key = str(jahr)
    if year_key not in stats:
        stats[year_key] = {}
    stats[year_key]["count"] = anzahl
    stats[year_key]["last_run"] = zeitstempel
    _stats_speichern(stats)


@dataclass
class BackupConfig:
    nas_host: str = ""
    nas_user: str = ""
    nas_base: str = ""
    nas_key_path: str = ""


def _backup_ziel_laden(idx: int) -> BackupConfig:
    env = _env_lesen()
    p = str(idx)
    return BackupConfig(
        nas_host=env.get(f"BACKUP_{p}_HOST", ""),
        nas_user=env.get(f"BACKUP_{p}_USER", ""),
        nas_base=env.get(f"BACKUP_{p}_BASE", ""),
        nas_key_path=env.get(f"BACKUP_{p}_SSH_KEY", ""),
    )


def _backup_ziel_speichern(idx: int, z: BackupConfig) -> None:
    p = str(idx)
    data = _env_lesen()
    data[f"BACKUP_{p}_HOST"] = z.nas_host
    data[f"BACKUP_{p}_USER"] = z.nas_user
    data[f"BACKUP_{p}_BASE"] = z.nas_base
    data[f"BACKUP_{p}_SSH_KEY"] = z.nas_key_path
    _env_schreiben(data)


def _ssh_key_option(cfg: BackupConfig) -> list[str]:
    if cfg.nas_key_path:
        return ["-i", cfg.nas_key_path]
    return []


def _ssh_cmd(cfg: BackupConfig, *args) -> subprocess.CompletedProcess:
    cmd = [_SSH_BIN]
    cmd.extend(_ssh_key_option(cfg))
    cmd.extend([
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=20",
        "-o", "BatchMode=yes",
        f"{cfg.nas_user}@{cfg.nas_host}",
        *args,
    ])
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


def _scp_transfer(cfg: BackupConfig, local: Path, remote: str) -> bool:
    cmd = [_SCP_BIN, "-O"]
    cmd.extend(_ssh_key_option(cfg))
    cmd.extend([
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=20",
        str(local),
        f"{cfg.nas_user}@{cfg.nas_host}:{remote}",
    ])
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        logger.warning("SCP-Fehler (rc=%d): %s", r.returncode, r.stderr.strip()[:200])
    return r.returncode == 0


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
            logger.error("Copy fallback auch fehlgeschlagen: %s", exc2)
            return False


def run_backup(cfg: BackupConfig, label: str = "") -> dict:
    result = {"success": False, "message": "", "files": 0, "errors": [], "label": label}
    src = config.DB_PATH
    if not src.exists():
        result["message"] = "kapa.db nicht gefunden"
        return result

    r = _ssh_cmd(cfg, "echo", "ok")
    if r.returncode != 0 or r.stdout.strip() != "ok":
        err = r.stderr.strip() or "SSH-Verbindung fehlgeschlagen"
        result["message"] = f"SSH-Fehler: {err}"
        return result

    tmp_dir = Path(tempfile.mkdtemp(prefix="kapa_backup_"))
    errors = []
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    try:
        tmp_file = tmp_dir / "kapa.db"
        if not _backup_sqlite(src, tmp_file):
            errors.append("Lokale Kopie fehlgeschlagen")
        else:
            size = tmp_file.stat().st_size
            remote_dir = f"{cfg.nas_base}/daily/{today}"
            r2 = _ssh_cmd(cfg, "mkdir", "-p", remote_dir)
            if r2.returncode != 0:
                errors.append("NAS mkdir fehlgeschlagen")
            elif _scp_transfer(cfg, tmp_file, f"{remote_dir}/kapa.db"):
                result["files"] += 1
                logger.info("Backup OK (%s): kapa.db -> %s/daily/%s/ (%d KB)",
                            label or cfg.nas_host, cfg.nas_base, today, size // 1024)
            else:
                errors.append("NAS-Upload fehlgeschlagen")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # ── Aufräumen: letzte 7 daily behalten ─────────────────────────
    try:
        r = _ssh_cmd(cfg, "ls", "-1d", f"{cfg.nas_base}/daily/????-??-??")
        if r.returncode == 0 and r.stdout.strip():
            dirs = sorted(d.strip() for d in r.stdout.splitlines() if d.strip())
            for d in dirs[:-7]:
                _ssh_cmd(cfg, "rm", "-rf", d)
    except Exception as exc:
        logger.warning("Cleanup daily fehlgeschlagen: %s", exc)

    if not errors and result["files"] > 0:
        result["success"] = True
        result["message"] = f"{result['files']} Datei(en) gesichert ({label or cfg.nas_host})"
        logger.info("Backup %s erfolgreich", label or cfg.nas_host)
    else:
        err_text = "; ".join(errors) if errors else "Keine Dateien gesichert"
        result["message"] = err_text
        logger.warning("Backup %s fehlgeschlagen: %s", label or cfg.nas_host, err_text)

    if errors:
        result["errors"] = errors
    return result


def run_all_backups(cfgs: list[BackupConfig]) -> dict:
    ergebnisse = []
    gesamt_dateien = 0
    gesamt_fehler = []

    for i, cfg in enumerate(cfgs, 1):
        label = f"Ziel-{i}"
        logger.info("Starte Backup %s (%s@%s)", label, cfg.nas_user, cfg.nas_host)
        try:
            res = run_backup(cfg, label=label)
        except Exception as exc:
            res = {"success": False, "message": str(exc), "files": 0, "errors": [str(exc)], "label": label}
        ergebnisse.append(res)
        if res["success"]:
            gesamt_dateien += res["files"]
        if res["errors"]:
            gesamt_fehler.extend(res["errors"])

    erfolgreich = sum(1 for r in ergebnisse if r["success"])
    fehlgeschlagen = sum(1 for r in ergebnisse if not r["success"])

    msg_parts = []
    if erfolgreich:
        msg_parts.append(f"{erfolgreich}/{len(cfgs)} Ziel(e) OK ({gesamt_dateien} Dateien)")
    if fehlgeschlagen:
        fail_details = " | ".join(
            f"FAIL {r['label']}: {r['message']}" for r in ergebnisse if not r["success"]
        )
        fail_msg = f"{fehlgeschlagen} Ziel(e) fehlgeschlagen"
        if fail_details:
            fail_msg += f" ({fail_details})"
        msg_parts.append(fail_msg)

    jetzt = datetime.now()
    zeitstempel = jetzt.isoformat()
    aktuelles_jahr = jetzt.year
    stats = _stats_laden()
    year_key = str(aktuelles_jahr)
    year_data = stats.get(year_key, {})
    anzahl = year_data.get("count", 0) + 1
    _backup_stats_schreiben(zeitstempel, anzahl, aktuelles_jahr)

    return {
        "success": erfolgreich > 0,
        "message": ", ".join(msg_parts) if msg_parts else "Alle fehlgeschlagen",
        "files": gesamt_dateien,
        "errors": gesamt_fehler,
        "ergebnisse": ergebnisse,
        "last_run": zeitstempel,
        "runs_this_year": anzahl,
    }
