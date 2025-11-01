from prisma import Prisma
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import logging

logger = logging.getLogger(__name__)

# Global Prisma client instance
db = Prisma()


async def connect_db():
    """Connect to the database."""
    try:
        await db.connect()
        logger.info("Connected to database successfully")
    except Exception as e:
        logger.error(f"Failed to connect to database: {str(e)}")
        raise


async def disconnect_db():
    """Disconnect from the database."""
    try:
        await db.disconnect()
        logger.info("Disconnected from database successfully")
    except Exception as e:
        logger.error(f"Failed to disconnect from database: {str(e)}")
        raise


@asynccontextmanager
async def get_db() -> AsyncGenerator[Prisma, None]:
    """
    Dependency to get database session.
    Usage in FastAPI endpoints:
        async def endpoint(db: Prisma = Depends(get_db)):
            user = await db.user.find_first(...)
    """
    try:
        yield db
    except Exception as e:
        logger.error(f"Database session error: {str(e)}")
        raise


async def init_db():
    """Initialize database connection on startup."""
    await connect_db()
    logger.info("Database initialized")


async def close_db():
    """Close database connection on shutdown."""
    await disconnect_db()
    logger.info("Database closed")