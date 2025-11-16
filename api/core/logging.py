"""
Structured logging configuration for the API
"""

import logging
import sys
from typing import Any, Dict
import structlog
from structlog.stdlib import LoggerFactory


def configure_logging() -> None:
    """Configure structured logging for the application"""
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger instance"""
    return structlog.get_logger(name)


class RequestLogger:
    """Logger for HTTP requests and responses"""
    
    def __init__(self):
        self.logger = get_logger("api.request")
    
    def log_request(self, method: str, path: str, correlation_id: str, **kwargs) -> None:
        """Log incoming HTTP request"""
        self.logger.info(
            "HTTP request received",
            method=method,
            path=path,
            correlation_id=correlation_id,
            **kwargs
        )
    
    def log_response(self, method: str, path: str, status_code: int, correlation_id: str, **kwargs) -> None:
        """Log HTTP response"""
        self.logger.info(
            "HTTP response sent",
            method=method,
            path=path,
            status_code=status_code,
            correlation_id=correlation_id,
            **kwargs
        )
    
    def log_error(self, method: str, path: str, error: str, correlation_id: str, **kwargs) -> None:
        """Log HTTP error"""
        self.logger.error(
            "HTTP error occurred",
            method=method,
            path=path,
            error=error,
            correlation_id=correlation_id,
            **kwargs
        )


class DatabaseLogger:
    """Logger for database operations"""
    
    def __init__(self):
        self.logger = get_logger("api.database")
    
    def log_operation(self, operation: str, collection: str, **kwargs) -> None:
        """Log database operation"""
        self.logger.info(
            "Database operation",
            operation=operation,
            collection=collection,
            **kwargs
        )
    
    def log_error(self, operation: str, collection: str, error: str, **kwargs) -> None:
        """Log database error"""
        self.logger.error(
            "Database error",
            operation=operation,
            collection=collection,
            error=error,
            **kwargs
        )


class BusinessLogger:
    """Logger for business logic operations"""
    
    def __init__(self):
        self.logger = get_logger("api.business")
    
    def log_operation(self, service: str, operation: str, **kwargs) -> None:
        """Log business operation"""
        self.logger.info(
            "Business operation",
            service=service,
            operation=operation,
            **kwargs
        )
    
    def log_error(self, service: str, operation: str, error: str, **kwargs) -> None:
        """Log business error"""
        self.logger.error(
            "Business error",
            service=service,
            operation=operation,
            error=error,
            **kwargs
        )



