"""Terminal-specific logging configuration."""

import logging
import os
from datetime import datetime
from pathlib import Path


def setup_terminal_logging(log_level: int = logging.DEBUG) -> logging.Logger:
    """Set up logging for terminal module with file output.
    
    Args:
        log_level: Logging level (default: DEBUG)
    
    Returns:
        Configured logger for terminal module
    """
    # Create logs directory
    log_dir = Path.home() / ".cache" / "crow-mcp" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Create timestamped log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"terminal_{timestamp}.log"
    
    # Create formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s.%(msecs)03d [%(levelname)8s] %(name)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler (always DEBUG level)
    file_handler = logging.FileHandler(log_file, mode='w')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    
    # Console handler (respects log_level)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    
    # Configure terminal logger
    logger = logging.getLogger('crow_mcp.terminal')
    logger.setLevel(logging.DEBUG)  # Capture everything
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.propagate = False  # Don't bubble up to root logger
    
    logger.info(f"Terminal logging initialized. Log file: {log_file}")
    
    return logger


def get_log_file_path() -> Path:
    """Get the most recent terminal log file path."""
    log_dir = Path.home() / ".cache" / "crow-mcp" / "logs"
    if not log_dir.exists():
        return None
    
    log_files = sorted(log_dir.glob("terminal_*.log"), reverse=True)
    return log_files[0] if log_files else None
