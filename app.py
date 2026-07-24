import logging
import time
from collections import defaultdict
from functools import wraps
from logging.handlers import RotatingFileHandler

from flask import Flask, jsonify, request

import config
from database import close_db, init_db


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY

    # -----------------------------------------------------------------------
    # Logging
    # -----------------------------------------------------------------------
    config.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        str(config.LOG_FILE), maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    file_handler.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))
    app.logger.addHandler(file_handler)
    app.logger.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))
    app.logger.info("Kapa-Planung starting")

    # -----------------------------------------------------------------------
    # Datenbank
    # -----------------------------------------------------------------------
    app.teardown_appcontext(close_db)

    # -----------------------------------------------------------------------
    # Rate Limiting (einfach, in-memory)
    # -----------------------------------------------------------------------
    _rate_store = defaultdict(list)

    def rate_limit(max_req=None, window=None):
        max_req = max_req or config.RATE_LIMIT_REQUESTS
        window = window or config.RATE_LIMIT_WINDOW

        def decorator(f):
            @wraps(f)
            def wrapped(*args, **kwargs):
                ip = request.remote_addr or "127.0.0.1"
                now = time.time()
                bucket = _rate_store[ip]
                _rate_store[ip] = [t for t in bucket if now - t < window]
                if len(_rate_store[ip]) >= max_req:
                    app.logger.warning("Rate limit exceeded for %s", ip)
                    return jsonify({"error": "Zu viele Anfragen"}), 429
                _rate_store[ip].append(now)
                return f(*args, **kwargs)

            return wrapped

        return decorator

    # -----------------------------------------------------------------------
    # Error Handler
    # -----------------------------------------------------------------------
    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"error": "Ungueltige Anfrage"}), 400

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Nicht gefunden"}), 404

    @app.errorhandler(500)
    def server_error(e):
        app.logger.exception("Internal server error")
        return jsonify({"error": "Interner Serverfehler"}), 500

    # -----------------------------------------------------------------------
    # Blueprints registrieren
    # -----------------------------------------------------------------------
    from routes_allocations import bp as allocations_bp
    from routes_backup import bp as backup_bp
    from routes_history import bp as history_bp
    from routes_members import bp as members_bp
    from routes_pages import bp as pages_bp
    from routes_projects import bp as projects_bp
    from routes_steps import bp as steps_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(steps_bp)
    app.register_blueprint(members_bp)
    app.register_blueprint(allocations_bp)
    app.register_blueprint(backup_bp)
    app.register_blueprint(history_bp)

    # -----------------------------------------------------------------------
    # Cache-Buster fuer statische Dateien (haengt ?v=<mtime> an url_for)
    # -----------------------------------------------------------------------
    from pathlib import Path

    _static_root = Path(app.root_path) / "static"

    @app.url_defaults
    def _add_static_version(endpoint, values):  # type: ignore[unused-ignore]
        if endpoint == "static" and "filename" in values and "v" not in values:
            try:
                mtime = int((_static_root / values["filename"]).stat().st_mtime)
                values["v"] = mtime
            except OSError:
                pass

    # Rate-Limit auf API-Routen anwenden (vor der Registrierung als Decorator
    # ist nicht moeglich, also ueber before_request)
    @app.before_request
    def _rate_limit_api():
        if request.path.startswith("/api/"):
            ip = request.remote_addr or "127.0.0.1"
            now = time.time()
            bucket = _rate_store[ip]
            _rate_store[ip] = [t for t in bucket if now - t < config.RATE_LIMIT_WINDOW]
            if len(_rate_store[ip]) >= config.RATE_LIMIT_REQUESTS:
                return jsonify({"error": "Zu viele Anfragen"}), 429
            _rate_store[ip].append(now)

    return app


if __name__ == "__main__":
    init_db()
    app = create_app()
    app.logger.info(
        "Starting server on %s:%s (debug=%s)", config.HOST, config.PORT, config.DEBUG
    )
    app.run(debug=config.DEBUG, host=config.HOST, port=config.PORT)
