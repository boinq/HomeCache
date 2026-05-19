import os
from collections.abc import Generator
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{DATA_DIR / 'inventory.db'}",
)


def _get_connect_args() -> dict:
    if DATABASE_URL.startswith("sqlite"):
        return {"check_same_thread": False}

    return {}


engine = create_engine(
    DATABASE_URL,
    connect_args=_get_connect_args(),
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session