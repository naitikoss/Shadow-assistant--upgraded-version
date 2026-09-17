import datetime as dt
from sqlalchemy import String, Text, DateTime, Boolean, Integer, Enum
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base
import enum


class ShortTermMemory(Base):
    """Rolling conversation context. Cheap, auto-saved, pruned to last N entries."""
    __tablename__ = "short_term_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(16))          # "user" | "assistant"
    channel: Mapped[str] = mapped_column(String(16))       # "telegram" | "orb"
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class LongTermMemory(Base):
    """Durable facts about Nai. Only written after user confirms (see PendingMemory)."""
    __tablename__ = "long_term_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fact: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(64), default="general")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class PendingMemory(Base):
    """A fact Shadow classified as long-term-worthy, awaiting a yes/no from Nai."""
    __tablename__ = "pending_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fact: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(64), default="general")
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class ReminderType(str, enum.Enum):
    message = "message"
    call = "call"
    both = "both"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    due_at: Mapped[dt.datetime] = mapped_column(DateTime)
    reminder_type: Mapped[ReminderType] = mapped_column(Enum(ReminderType), default=ReminderType.message)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    reminded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
