# backend/app/main.py
import os
os.environ.setdefault("MPLBACKEND", "Agg")

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import asyncio
import sys
import argparse

try:
    import matplotlib
    matplotlib.use("Agg")
except Exception:
    pass

from app.api.endpoints import transcribe, meeting_notes, audio_processing
from app.api.endpoints import recordings
from app.core.config import settings
from app.utils.logging_config import setup_logging, get_logger

# Setup logging with configuration priority
logger = setup_logging(service_name="main")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="API for transcribing audio files with speaker diarization"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(
    transcribe.router,
    prefix="/api/v1",
    tags=["transcription"]
)

app.include_router(
    meeting_notes.router,
    prefix="/api/v1",
    tags=["meeting-notes"]
)

app.include_router(
    audio_processing.router,
    prefix="/api/v1",
    tags=["audio-processing"]
)

app.include_router(
    recordings.router,
    prefix="/api/v1",
    tags=["recordings"]
)

@app.on_event("startup")
async def startup_event():
    """Initialize services on application startup"""
    try:
        # Lazy import to avoid heavy dependencies during module import
        from app.services.transcription_service import transcription_service
        logger.info("Initializing transcription service...")
        await transcription_service.initialize_models()
        logger.info("Transcription service initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize services: {str(e)}")
        raise

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION
    }

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

def parse_args():
    """Parse command line arguments for log level configuration"""
    parser = argparse.ArgumentParser(description="Meeting Transcriber API Server")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (overrides environment variables and .env file)"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind the server to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind the server to (default: 8000)"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development"
    )
    return parser.parse_args()

if __name__ == "__main__":
    import uvicorn
    
    # Parse command line arguments
    args = parse_args()
    
    # Reconfigure logging if CLI log level is provided
    if args.log_level:
        logger = setup_logging(log_level=args.log_level, service_name="main")
        logger.info(f"Log level set via CLI argument: {args.log_level}")
    
    logger.info(f"Starting Meeting Transcriber API server on {args.host}:{args.port}")
    logger.info(f"Reload mode: {args.reload}")
    
    uvicorn.run(
        "app.main:app", 
        host=args.host, 
        port=args.port, 
        reload=args.reload
    )
