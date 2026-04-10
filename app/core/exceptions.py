# app/core/exceptions.py
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError
import logging

logger = logging.getLogger(__name__)


class AnthroException(Exception):
    """Base exception for Anthro application"""
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class ValidationException(AnthroException):
    """Custom validation exception"""
    def __init__(self, message: str):
        super().__init__(message, 422)
        
class PaymentException(AnthroException):
    """Custom validation exception"""
    def __init__(self, message: str):
        super().__init__(message, 422)

class AuthenticationException(AnthroException):
    """Authentication failed exception"""
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, 401)


class AuthorizationException(AnthroException):
    """Authorization failed exception"""
    def __init__(self, message: str = "Not authorized"):
        super().__init__(message, 403)


class NotFoundException(AnthroException):
    """Resource not found exception"""
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, 404)


class ConflictException(AnthroException):
    """Resource conflict exception"""
    def __init__(self, message: str = "Resource conflict"):
        super().__init__(message, 409)


class FileProcessingException(AnthroException):
    """File processing failed exception"""
    def __init__(self, message: str = "File processing failed"):
        super().__init__(message, 422)


class SubscriptionException(AnthroException):
    """Subscription related exception"""
    def __init__(self, message: str = "Subscription error"):
        super().__init__(message, 402)


async def custom_exception_handler(request: Request, exc: AnthroException):
    """Custom exception handler for Anthro exceptions"""
    logger.error(f"AnthroException: {exc.message} - Status: {exc.status_code}")
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "message": exc.message,
            "status_code": exc.status_code,
            "path": str(request.url)
        }
    )


async def validation_exception_handler(request: Request, exc: ValidationError):
    """Handle FastAPI validation errors"""
    logger.error(f"ValidationError: {exc.errors()}")
    
    return JSONResponse(
        status_code=422,
        content={
            "error": True,
            "message": "Validation error",
            "status_code": 422,
            "details": exc.errors(),
            "path": str(request.url)
        }
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle FastAPI HTTP exceptions"""
    logger.error(f"HTTPException: {exc.detail} - Status: {exc.status_code}")
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "message": exc.detail,
            "status_code": exc.status_code,
            "path": str(request.url)
        }
    )