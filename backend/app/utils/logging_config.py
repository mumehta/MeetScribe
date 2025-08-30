"""
Centralized logging configuration for the Meeting Transcriber API.

This module provides logging configuration with priority:
1. Command line arguments (if applicable)
2. Environment variables
3. .env file settings
4. Default values
"""

import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.core.config import settings


def get_log_level(cli_log_level: Optional[str] = None) -> str:
    """
    Get log level with priority: CLI arg > ENV var > .env file > default
    
    Args:
        cli_log_level: Optional command line log level override
        
    Returns:
        Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Priority 1: Command line argument
    if cli_log_level:
        return cli_log_level.upper()
    
    # Priority 2: Environment variable
    env_log_level = os.environ.get('LOG_LEVEL')
    if env_log_level:
        return env_log_level.upper()
    
    # Priority 3: .env file (loaded via settings)
    if settings.LOG_LEVEL:
        return settings.LOG_LEVEL.upper()
    
    # Priority 4: Default
    return 'INFO'


def setup_logging(log_level: Optional[str] = None, service_name: str = "api") -> logging.Logger:
    """
    Setup comprehensive logging to both console and file.
    
    Args:
        log_level: Optional log level override
        service_name: Name of the service for log file naming
        
    Returns:
        Configured logger instance
    """
    # Get effective log level
    effective_log_level = get_log_level(log_level)
    numeric_level = getattr(logging, effective_log_level, logging.INFO)
    
    # Ensure logs directory exists
    logs_dir = settings.logs_folder_path
    logs_dir.mkdir(exist_ok=True)
    
    # Create log filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_filename = f"{service_name}_{timestamp}.log"
    log_file = logs_dir / log_filename
    
    # Clear any existing handlers to avoid duplicates
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    
    # Create formatters
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(name)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(file_formatter)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(console_formatter)
    
    # Configure root logger
    root_logger.setLevel(numeric_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # Create service-specific logger
    logger = logging.getLogger(f"meeting_transcriber.{service_name}")
    
    # Log the logging configuration
    logger.info(f"Logging initialized - Level: {effective_log_level}, File: {log_file}")
    logger.debug(f"Log level sources checked: CLI -> ENV -> .env -> default")
    logger.debug(f"Logs directory: {logs_dir}")
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a specific module.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Logger instance
    """
    return logging.getLogger(f"meeting_transcriber.{name}")
