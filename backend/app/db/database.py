import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///./clinical.db"

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()


def init_db() -> None:
    """Create tables if they do not exist yet."""
    from backend.app.db import models  # noqa: F401  (registers the models)

    Base.metadata.create_all(bind=engine)
