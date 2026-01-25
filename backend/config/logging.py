"""
Centralized logging configuration
Import and call setup_logging() once at app startup.
Use get_logger(__name__) in any module to get a configured logger.
"""
import logging
import sys
from typing import Optional


# Default format for all logs
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str = "INFO") -> None:
    """
    Configure logging for the entire application.
    Call this once at startup (in main.py lifespan).
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Get the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    root_logger.addHandler(console_handler)
    
    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a logger instance for a module.
    
    Usage:
        from config.logging import get_logger
        logger = get_logger(__name__)
        logger.info("Something happened")
    
    Args:
        name: Logger name (typically __name__ of the calling module)
    
    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)
