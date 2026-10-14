"""Persist each successful translation call."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, create_engine, delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


@dataclass(frozen=True)
class TranslationRecord:
    original_text: str
    source_language: str
    target_language: str
    translation: str
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    cached: bool


class TranslationStore(Protocol):
    def prepare(self) -> None:
        """Create tables. Called once when the API process starts."""

    def save(self, record: TranslationRecord) -> None:
        """Store one successful call."""

    def find_by_original_text(self, original_text: str) -> list[TranslationRecord]:
        """Return saved calls for this original text, oldest first."""


class MemoryTranslationStore:
    """Test double. Production uses PostgresTranslationStore."""

    def __init__(self) -> None:
        self.records: list[TranslationRecord] = []

    def prepare(self) -> None:
        return None

    def save(self, record: TranslationRecord) -> None:
        self.records.append(record)

    def find_by_original_text(self, original_text: str) -> list[TranslationRecord]:
        return [record for record in self.records if record.original_text == original_text]


class Base(DeclarativeBase):
    pass


class TranslationRow(Base):
    __tablename__ = "translations"

    id: Mapped[int] = mapped_column(primary_key=True)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_language: Mapped[str] = mapped_column(String(8), nullable=False)
    target_language: Mapped[str] = mapped_column(String(8), nullable=False)
    translation: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    cached: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PostgresTranslationStore:
    def __init__(self, database_url: str) -> None:
        self.engine: Engine = create_engine(_sqlalchemy_url(database_url), pool_pre_ping=True)

    def prepare(self) -> None:
        Base.metadata.create_all(self.engine)

    def save(self, record: TranslationRecord) -> None:
        with Session(self.engine) as session:
            session.add(
                TranslationRow(
                    original_text=record.original_text,
                    source_language=record.source_language,
                    target_language=record.target_language,
                    translation=record.translation,
                    model=record.model,
                    latency_ms=record.latency_ms,
                    input_tokens=record.input_tokens,
                    output_tokens=record.output_tokens,
                    estimated_cost_usd=Decimal(str(record.estimated_cost_usd)),
                    cached=record.cached,
                )
            )
            session.commit()

    def find_by_original_text(self, original_text: str) -> list[TranslationRecord]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(TranslationRow)
                .where(TranslationRow.original_text == original_text)
                .order_by(TranslationRow.id)
            ).all()
            return [_record(row) for row in rows]

    def delete_by_original_text(self, original_text: str) -> None:
        with Session(self.engine) as session:
            session.execute(
                delete(TranslationRow).where(TranslationRow.original_text == original_text)
            )
            session.commit()


def _sqlalchemy_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
    return database_url


def _record(row: TranslationRow) -> TranslationRecord:
    return TranslationRecord(
        original_text=row.original_text,
        source_language=row.source_language,
        target_language=row.target_language,
        translation=row.translation,
        model=row.model,
        latency_ms=row.latency_ms,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        estimated_cost_usd=float(row.estimated_cost_usd),
        cached=row.cached,
    )
