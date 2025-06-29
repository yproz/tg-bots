"""Асинхронный движок + фабрика сессий, одно место на весь проект."""
import os, asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from .models import Base

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://pricebot:pricebot@db/pricebot",
)

# Асинхронный engine для основного приложения
engine = create_async_engine(DATABASE_URL, echo=False)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

# Синхронный engine для Celery задач
SYNC_DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
sync_engine = create_engine(SYNC_DATABASE_URL, echo=False)
sync_session_factory = sessionmaker(sync_engine, expire_on_commit=False)

def get_sync_session():
    """Получить синхронную сессию для работы с БД"""
    return sync_session_factory()

async def create_tables():
    """Создаёт все таблицы, если их ещё нет."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # ensure optional columns exist (idempotent)
        await conn.execute(
            text(
                "ALTER TABLE accounts "
                "ADD COLUMN IF NOT EXISTS ozon_client_id TEXT"
            )
        )
    # Добавляем constraint в отдельной транзакции, чтобы не портить основную
    async with engine.begin() as conn:
        try:
            await conn.execute(
                text(
                    "ALTER TABLE raw_prices "
                    "ADD CONSTRAINT uq_raw_price "
                    "UNIQUE (client_id, product_id, collected_at)"
                )
            )
        except Exception:
            pass
    # убедимся в наличии базовых индекс-/констрейнтов
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))