"""Allokations-Routen"""

from flask import Blueprint, jsonify, request

from database import get_db, member_exists, project_exists

bp = Blueprint("allocations", __name__)


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
    return jsonify({"ok": True})
