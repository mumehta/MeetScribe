#!/usr/bin/env python3
"""
Start the Meeting Transcriber API server.
This script provides a convenient way to start the FastAPI server.
"""

import uvicorn
import os
import sys
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

def main():
    """Start the FastAPI server"""
    print("🚀 Starting Meeting Transcriber API...")
    print("📝 Transcription endpoint: http://localhost:8000/api/v1/transcribe")
    print("📋 Meeting notes endpoint: http://localhost:8000/api/v1/generate-notes/{task_id}")
    print("📖 API docs: http://localhost:8000/docs")
    print("🔍 Health check: http://localhost:8000/")
    print()
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

if __name__ == "__main__":
    main()
