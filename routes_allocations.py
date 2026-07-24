"""Allokations-Routen"""

from flask import Blueprint, jsonify, request

from database import get_db, member_exists, project_exists
from history import record_action

bp = Blueprint("allocations", __name__)


def _escape_sql(val) -> str:
    if val is None:
        return "NULL"
    if isinstance(val, str):
        return "'" + val.replace("'", "''") + "'"
    return str(val)


@bp.route("/api/allocations", methods=["POST"])
def save_allocation():
    data = request.get_json(force=True)

    try:
        project_id = int(data["project_id"])
        year = int(data["year"])
        quarter = int(data["quarter"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Ungueltige Eingabe: project_id, year, quarter erforderlich"}), 400

    values = data.get("values")
    if not isinstance(values, dict):
        return jsonify({"error": "values muss ein Objekt sein"}), 400

    db = get_db()
    if not project_exists(db, project_id):
        return jsonify({"error": "Projekt nicht gefunden"}), 404
    if quarter not in (1, 2, 3, 4):
        return jsonify({"error": "Quartal muss 1-4 sein"}), 400

    # Capture old values for undo
    old_allocs = {}
    existing = db.execute(
        "SELECT team_member_id, stunden FROM allocations "
        "WHERE project_id = ? AND year = ? AND quarter = ?",
        (project_id, year, quarter),
    ).fetchall()
    for r in existing:
        old_allocs[r["team_member_id"]] = r["stunden"]

    try:
        db.execute("BEGIN IMMEDIATE")
        for member_id_str, wert in values.items():
            try:
                member_id = int(member_id_str)
            except (TypeError, ValueError):
                db.rollback()
                return jsonify({"error": f"Ungueltige Mitarbeiter-ID: {member_id_str}"}), 400

            if not member_exists(db, member_id):
                db.rollback()
                return jsonify({"error": f"Mitarbeiter {member_id} nicht gefunden"}), 400

            try:
                stunden_val = float(wert or 0)
            except (TypeError, ValueError):
                stunden_val = 0.0

            if stunden_val < 0:
                db.rollback()
                return jsonify({"error": "Stunden duerfen nicht negativ sein"}), 400

            db.execute(
                """
                INSERT INTO allocations (project_id, year, quarter, team_member_id, stunden)
                VALUES (?,?,?,?,?)
                ON CONFLICT(project_id, year, quarter, team_member_id)
                DO UPDATE SET stunden = excluded.stunden
                """,
                (project_id, year, quarter, member_id, stunden_val),
            )
        db.commit()
    except Exception:
        db.rollback()
        raise

    # Build undo/redo SQL
    undo_parts = []
    redo_parts = []
    for member_id_str, wert in values.items():
        mid = int(member_id_str)
        neue = float(wert or 0)
        alte = old_allocs.get(mid, 0)
        if alte == 0:
            undo_parts.append(
                f"DELETE FROM allocations WHERE project_id = {project_id} AND year = {year} "
                f"AND quarter = {quarter} AND team_member_id = {mid}"
            )
        else:
            undo_parts.append(
                f"UPDATE allocations SET stunden = {alte} WHERE project_id = {project_id} "
                f"AND year = {year} AND quarter = {quarter} AND team_member_id = {mid}"
            )
        if neue == 0:
            redo_parts.append(
                f"DELETE FROM allocations WHERE project_id = {project_id} AND year = {year} "
                f"AND quarter = {quarter} AND team_member_id = {mid}"
            )
        else:
            redo_parts.append(
                f"INSERT INTO allocations (project_id, year, quarter, team_member_id, stunden) "
                f"VALUES ({project_id}, {year}, {quarter}, {mid}, {neue}) "
                f"ON CONFLICT(project_id, year, quarter, team_member_id) "
                f"DO UPDATE SET stunden = {neue}"
            )
    record_action(
        f"Stunden Q{quarter}/{year} Projekt #{project_id}",
        ";\n".join(undo_parts),
        ";\n".join(redo_parts),
    )
    return jsonify({"ok": True})
