
from fastapi import APIRouter, status
from datetime import datetime
import logging

from app.config import settings
from app.database import db
from app.models import HealthCheckResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Health Check",
    description="Check if the application and database are healthy"
)
async def health_check():
    try:
        # Test database connection
        await db.query_raw("SELECT 1")
        db_status = "connected"
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        db_status = "disconnected"
    
    return HealthCheckResponse(
        status="healthy" if db_status == "connected" else "unhealthy",
        version=settings.VERSION,
        database=db_status,
        timestamp=datetime.now()
    )


@router.get(
    "/",
    summary="Root Endpoint",
    description="API information and available endpoints"
)
async def root():
    """Root endpoint with API information."""
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "description": settings.DESCRIPTION,
        "environment": settings.ENVIRONMENT,
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "redoc": "/redoc",
            "auth": "/auth",
            "documents": "/documents",
            "chat": "/chat"
        }
    }