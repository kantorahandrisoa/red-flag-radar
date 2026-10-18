"""Screening, match and decision storage (SQLite). Sanctions are written by the pipeline."""
from datetime import datetime, timezone

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from pipeline.paths import DB_PATH

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Base(DeclarativeBase):
    pass


class Screening(Base):
    __tablename__ = "screenings"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[str] = mapped_column(String(32), default=now)
    created_by: Mapped[str] = mapped_column(String(100), default="")
    model_version: Mapped[str] = mapped_column(String(64))
    data_version: Mapped[str] = mapped_column(String(128))
    thresholds: Mapped[dict] = mapped_column(JSON)
    seconds: Mapped[float] = mapped_column(Float, default=0.0)
    candidates: Mapped[list["Candidate"]] = relationship(back_populates="screening", cascade="all, delete-orphan")


class Candidate(Base):
    __tablename__ = "candidates"
    id: Mapped[int] = mapped_column(primary_key=True)
    screening_id: Mapped[int] = mapped_column(ForeignKey("screenings.id"), index=True)
    row: Mapped[int] = mapped_column(Integer)
    external_id: Mapped[str] = mapped_column(String(64), default="")
    raw: Mapped[dict] = mapped_column(JSON)          # the uploaded row, as given
    normalized: Mapped[dict] = mapped_column(JSON)   # what the matcher compared
    best_score: Mapped[float] = mapped_column(Float, default=0.0)
    zone: Mapped[str] = mapped_column(String(16), default="cleared")
    screening: Mapped[Screening] = relationship(back_populates="candidates")
    matches: Mapped[list["Match"]] = relationship(back_populates="candidate", cascade="all, delete-orphan",
                                                  order_by="desc(Match.score)")


class Match(Base):
    __tablename__ = "matches"
    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), index=True)
    sanction_id: Mapped[str] = mapped_column(String(32))
    score: Mapped[float] = mapped_column(Float)
    zone: Mapped[str] = mapped_column(String(16))
    features: Mapped[dict] = mapped_column(JSON)     # kept so every explanation can be replayed
    first_seen_at: Mapped[str] = mapped_column(String(32), default=now)
    candidate: Mapped[Candidate] = relationship(back_populates="matches")


class Decision(Base):
    """Append-only audit trail: who decided what, when, on which model and list versions."""
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), index=True)
    sanction_id: Mapped[str] = mapped_column(String(32), default="")
    decision: Mapped[str] = mapped_column(String(16))   # confirmed | dismissed
    comment: Mapped[str] = mapped_column(Text)
    reviewer: Mapped[str] = mapped_column(String(100))
    decided_at: Mapped[str] = mapped_column(String(32), default=now)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    model_version: Mapped[str] = mapped_column(String(64))
    data_version: Mapped[str] = mapped_column(String(128))


def init_db() -> None:
    Base.metadata.create_all(engine)
