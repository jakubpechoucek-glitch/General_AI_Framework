"""Database engine and session handling.

SQLite is used by default (a single file under ./data). Set DATABASE_URL to use
PostgreSQL or another SQLAlchemy-supported database in production.
"""
import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB = f"sqlite:///{BASE_DIR / 'data' / 'app.db'}"
DATABASE_URL = os.environ.get("DATABASE_URL", DEFAULT_DB)
# Render / Heroku style URLs -> SQLAlchemy psycopg3 driver
for _prefix in ("postgres://", "postgresql://"):
    if DATABASE_URL.startswith(_prefix):
        DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len(_prefix):]

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_fk(dbapi_conn, _):  # enforce foreign keys in SQLite
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from . import models  # noqa: F401  (register models)

    if DATABASE_URL.startswith("sqlite"):
        Path(DATABASE_URL.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    bootstrap_admin()


def bootstrap_admin():
    """Create the first administrator from ADMIN_EMAIL / ADMIN_PASSWORD if no admin exists.

    Used for hosted deployments (e.g. Render) where the seed script is not run. The
    password is temporary: it must be changed at first sign-in.
    """
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not email or not password:
        return
    from .auth import hash_password
    from .models import User

    with SessionLocal() as db:
        if db.query(User).filter(User.is_admin.is_(True)).first():
            return
        db.add(User(employee_id="ADMIN-001", name="Administrator", email=email, is_admin=True,
                    password_hash=hash_password(password), must_change_password=True))
        db.commit()
