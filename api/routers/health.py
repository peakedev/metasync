"""
Health check API router
Provides health check endpoints for monitoring and service discovery
"""
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from typing import Dict, Any
from datetime import datetime

from api.core.logging import get_logger
from config import config
from utilities.cosmos_connector import get_mongo_client, ClientManager

logger = get_logger("api.routers.health")

router = APIRouter()


def check_database() -> Dict[str, Any]:
    """Check database connectivity"""
    try:
        client_manager = ClientManager()
        mongo_client = client_manager.get_client(config.db_connection_string)
        # Perform a simple operation to verify connectivity
        # Using admin command ping which is lightweight
        mongo_client.admin.command('ping')
        return {
            "status": "healthy",
            "database": "connected"
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e)
        }


@router.get("/health/ready", status_code=status.HTTP_200_OK)
async def readiness_check() -> Dict[str, Any]:
    """
    Readiness check endpoint
    Verifies that the service is ready to accept traffic by checking dependencies
    """
    logger.info("Readiness check requested")
    
    db_check = check_database()
    
    overall_status = "ready" if db_check["status"] == "healthy" else "not_ready"
    status_code = status.HTTP_200_OK if overall_status == "ready" else status.HTTP_503_SERVICE_UNAVAILABLE
    
    response_data = {
        "status": overall_status,
        "service": "metasync-api",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "checks": {
            "database": db_check
        }
    }
    
    return JSONResponse(content=response_data, status_code=status_code)


@router.get("/health/live", status_code=status.HTTP_200_OK)
async def liveness_check() -> Dict[str, Any]:
    """
    Liveness check endpoint
    Verifies that the application is running and responsive
    """
    logger.info("Liveness check requested")
    
    return {
        "status": "alive",
        "service": "metasync-api",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> Dict[str, Any]:
    """
    Basic health check endpoint
    Returns application status and basic service information
    """
    logger.info("Health check requested")
    
    return {
        "status": "healthy",
        "service": "metasync-api",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": "0.1.0"
    }

