import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from database import init_db


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    old = config.DB_PATH
    config.DB_PATH = Path(path)
    yield config.DB_PATH
    config.DB_PATH = old
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def app(db_path):
    os.environ["KAPA_DEBUG"] = "false"
    os.environ["KAPA_SECRET_KEY"] = "test-secret"
    os.environ["KAPA_LOG_FILE"] = str(db_path.parent / "test_kapa.log")
    os.environ["KAPA_RATE_LIMIT"] = "9999"
    os.environ["KAPA_BACKUP_DIR"] = str(db_path.parent / "test_backups")

    from app import create_app
    app = create_app()
    app.config["TESTING"] = True

    with app.app_context():
        init_db()

    yield app

    # cleanup
    log = Path(os.environ["KAPA_LOG_FILE"])
    log.unlink(missing_ok=True)
    backup_dir = Path(os.environ["KAPA_BACKUP_DIR"])
    if backup_dir.exists():
        for f in backup_dir.glob("*"):
            f.unlink(missing_ok=True)
        backup_dir.rmdir()


@pytest.fixture
def client(app):
    return app.test_client()
