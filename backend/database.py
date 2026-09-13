import os
from pathlib import Path
from dotenv import load_dotenv
from sqlmodel import SQLModel, create_engine, Session
from .models import *  # Import models to register them

# Load only this checkout's optional .env. Real OS/container variables retain
# precedence, and no parent or sibling workspace configuration is consulted.
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

# Database URL — defaults to SQLite in platform-appropriate AppData
import sys
if sys.platform == "win32":
    _app_data_root = os.getenv("APPDATA", os.path.expanduser("~"))
elif sys.platform == "darwin":
    _app_data_root = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
else:
    _app_data_root = os.getenv("XDG_DATA_HOME", os.path.join(os.path.expanduser("~"), ".local", "share"))

app_data = os.path.join(_app_data_root, "Assay")
os.makedirs(app_data, exist_ok=True)
_default_db_path = os.path.join(app_data, "database.db")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_default_db_path}")

# SQLite-specific connection args
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(DATABASE_URL, connect_args=connect_args)


def create_db_and_tables():
    """Create all tables defined by SQLModel metadata, then apply schema migrations."""
    SQLModel.metadata.create_all(engine)
    # Run migrations to handle existing DBs with old schemas
    try:
        from .migrate import run_migrations
        run_migrations()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Migration warning: {e}")


def get_session():
    """Yield a database session for FastAPI dependency injection."""
    with Session(engine) as session:
        yield session
