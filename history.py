"""Undo/Redo-Logik. Speichert SQL-Anweisungen in action_history."""

import logging

from database import get_db

logger = logging.getLogger(__name__)


def _get_pointer(db) -> int:
    row = db.execute("SELECT current_position FROM undo_pointer WHERE id = 1").fetchone()
    return row["current_position"] if row else 0


def _set_pointer(db, pos: int):
    db.execute("UPDATE undo_pointer SET current_position = ? WHERE id = 1", (pos,))


def record_action(description: str, undo_sql: str, redo_sql: str):
    """Neue Aktion aufzeichnen. Löscht den Redo-Stack (alles nach Pointer)."""
    db = get_db()
    pos = _get_pointer(db)

    # Alles nach aktueller Position löschen (Redo-Stack clearen)
    db.execute("DELETE FROM action_history WHERE id > ?", (pos,))

    # Neue Aktion anhängen
    db.execute(
        "INSERT INTO action_history (description, undo_sql, redo_sql) VALUES (?, ?, ?)",
        (description, undo_sql, redo_sql),
    )
    new_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.execute("UPDATE undo_pointer SET current_position = ? WHERE id = 1", (new_id,))
    db.commit()


def undo() -> dict:
    """Letzte Aktion rückgängig machen."""
    db = get_db()
    pos = _get_pointer(db)
    if pos <= 0:
        return {"success": False, "message": "Nichts rückgängig zu machen"}

    row = db.execute(
        "SELECT id, description, undo_sql FROM action_history WHERE id = ?", (pos,)
    ).fetchone()
    if not row:
        return {"success": False, "message": "Aktion nicht gefunden"}

    try:
        for stmt in row["undo_sql"].split(";\n"):
            stmt = stmt.strip()
            if stmt:
                db.execute(stmt)
        db.execute("UPDATE undo_pointer SET current_position = ? WHERE id = 1", (pos - 1,))
        db.commit()
        logger.info("Undo OK: %s", row["description"])
        return {"success": True, "message": f"Rückgängig: {row['description']}"}
    except Exception as e:
        db.rollback()
        logger.error("Undo fehlgeschlagen: %s", e)
        return {"success": False, "message": str(e)}


def redo() -> dict:
    """Nächste rückgängig gemachte Aktion wiederherstellen."""
    db = get_db()
    pos = _get_pointer(db)
    row = db.execute(
        "SELECT id, description, redo_sql FROM action_history WHERE id = ?", (pos + 1,)
    ).fetchone()
    if not row:
        return {"success": False, "message": "Nichts wiederherzustellen"}

    try:
        for stmt in row["redo_sql"].split(";\n"):
            stmt = stmt.strip()
            if stmt:
                db.execute(stmt)
        db.execute("UPDATE undo_pointer SET current_position = ? WHERE id = 1", (pos + 1,))
        db.commit()
        logger.info("Redo OK: %s", row["description"])
        return {"success": True, "message": f"Wiederhergestellt: {row['description']}"}
    except Exception as e:
        db.rollback()
        logger.error("Redo fehlgeschlagen: %s", e)
        return {"success": False, "message": str(e)}


def history_status() -> dict:
    """Status: wie viele Undo/Redo-Schritte verfügbar."""
    db = get_db()
    pos = _get_pointer(db)
    total = db.execute("SELECT COUNT(*) c FROM action_history").fetchone()["c"]
    can_undo = pos > 0
    can_redo = pos < total
    last_desc = None
    next_desc = None
    if can_undo:
        r = db.execute("SELECT description FROM action_history WHERE id = ?", (pos,)).fetchone()
        last_desc = r["description"] if r else None
    if can_redo:
        r = db.execute("SELECT description FROM action_history WHERE id = ?", (pos + 1,)).fetchone()
        next_desc = r["description"] if r else None
    return {
        "can_undo": can_undo,
        "can_redo": can_redo,
        "undo_description": last_desc,
        "redo_description": next_desc,
        "position": pos,
        "total": total,
    }
