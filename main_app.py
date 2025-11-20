#!/usr/bin/env python3
"""
Main FastAPI application
"""

import uuid
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from starlette.middleware.base import BaseHTTPMiddleware

from api.core.logging import (
    configure_logging,
    get_logger,
    RequestLogger
)
from api.core.docs_auth import docs_auth_dependency
from api.routers import (
    clients,
    health,
    prompts,
    jobs,
    workers,
    prompt_flows,
    models,
    stream,
    runs
)
from api.services.worker_manager import get_worker_manager
from api.services.run_orchestrator import get_run_orchestrator

# Configure logging
configure_logging()
logger = get_logger("api.main")
request_logger = RequestLogger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown."""
    # Startup
    try:
        print("\n" + "="*60)
        print("🚀 MetaSync API Starting...")
        print("="*60)
        
        # Start worker manager
        manager = get_worker_manager()
        manager.load_workers_from_db()
        
        # Start run orchestrator
        orchestrator = get_run_orchestrator()
        orchestrator.start()
        
        print("="*60)
        print("✅ MetaSync API Ready")
        print("="*60 + "\n")
    except Exception as e:
        print(f"\n❌ Startup error: {str(e)}\n")
    
    yield  # Application runs here
    
    # Shutdown
    try:
        from utilities.cosmos_connector import ClientManager
        
        print("\n" + "="*60)
        print("🛑 MetaSync API Shutting Down...")
        print("="*60)
        
        # Stop orchestrator FIRST
        orchestrator = get_run_orchestrator()
        orchestrator.stop()
        
        # Stop workers
        manager = get_worker_manager()
        
        # Run stop_all_workers in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, manager.stop_all_workers),
                timeout=5.0  # 5 second timeout total
            )
        except asyncio.TimeoutError:
            print("⚠️  Some workers may still be running")
        
        # NOW close MongoDB connections (after workers and orchestrator are stopped)
        try:
            client_manager = ClientManager()
            client_manager.close_all()
            print("🔌 Database connections closed")
        except Exception as e:
            print(f"⚠️  Error closing database: {str(e)}")
        
        print("="*60)
        print("👋 MetaSync API Stopped")
        print("="*60 + "\n")
            
    except Exception as e:
        print(f"\n❌ Shutdown error: {str(e)}\n")


# Initialize FastAPI app
app = FastAPI(
    title="MetaSync API",
    description="API for MetaSync LLM processing",
    version="0.1.0",
    docs_url=None,  # Disable automatic /docs endpoint
    redoc_url=None,  # Disable automatic /redoc endpoint
    openapi_url=None,  # Disable automatic /openapi.json endpoint
    lifespan=lifespan
)

# Add correlation ID middleware
class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Middleware to add correlation ID to requests."""
    
    async def dispatch(self, request: Request, call_next):
        # Generate or extract correlation ID
        correlation_id = request.headers.get(
            "X-Correlation-ID", str(uuid.uuid4())
        )
        
        # Add to request state
        request.state.correlation_id = correlation_id
        
        # Log request
        request_logger.log_request(
            method=request.method,
            path=request.url.path,
            correlation_id=correlation_id,
            client_ip=request.client.host if request.client else None
        )
        
        try:
            # Process request
            response = await call_next(request)
            
            # Add correlation ID to response headers
            response.headers["X-Correlation-ID"] = correlation_id
            
            # Log response
            request_logger.log_response(
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                correlation_id=correlation_id
            )
            
            return response
            
        except Exception as e:
            # Log error
            request_logger.log_error(
                method=request.method,
                path=request.url.path,
                error=str(e),
                correlation_id=correlation_id
            )
            raise

app.add_middleware(CorrelationIDMiddleware)

# Include routers
app.include_router(clients.router, prefix="/clients", tags=["clients"])
app.include_router(health.router, tags=["health"])
app.include_router(prompts.router, prefix="/prompts", tags=["prompts"])
app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
app.include_router(workers.router, prefix="/workers", tags=["workers"])
app.include_router(
    prompt_flows.router, prefix="/prompt-flows", tags=["prompt-flows"]
)
app.include_router(models.router, prefix="/models", tags=["models"])
app.include_router(stream.router, prefix="/stream", tags=["stream"])
app.include_router(runs.router, prefix="/runs", tags=["runs"])

# Protected documentation endpoints
@app.get("/docs", dependencies=[Depends(docs_auth_dependency)])
async def protected_docs():
    """Protected Swagger UI documentation."""
    from fastapi.openapi.docs import get_swagger_ui_html
    return get_swagger_ui_html(
        openapi_url="/openapi.json", title="MetaSync API"
    )

@app.get("/redoc", dependencies=[Depends(docs_auth_dependency)])
async def protected_redoc():
    """Protected ReDoc documentation."""
    from fastapi.openapi.docs import get_redoc_html
    return get_redoc_html(
        openapi_url="/openapi.json", title="MetaSync API"
    )

@app.get("/openapi.json", dependencies=[Depends(docs_auth_dependency)])
async def protected_openapi():
    """Protected OpenAPI schema."""
    return app.openapi()


if __name__ == "__main__":
    import uvicorn
    import subprocess
    
    # Kill any existing processes on port 8001
    try:
        result = subprocess.run(
            ['lsof', '-ti:8001'], capture_output=True, text=True
        )
        if result.stdout.strip():
            print(
                "⚠️  Found existing processes on port 8001, killing them..."
            )
            subprocess.run(
                ['kill', '-9'] + result.stdout.strip().split('\n'),
                check=False
            )
            import time
            time.sleep(2)
            print("✅ Cleaned up existing processes")
    except Exception as e:
        print(f"ℹ️  No existing processes found on port 8001: {e}")
    
    print("🚀 Starting FastAPI server on http://0.0.0.0:8001")
    uvicorn.run(app, host="0.0.0.0", port=8001)

