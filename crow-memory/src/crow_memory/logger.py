"""Rotating file logger for crow-memory, mirroring crow-cli/crow-mcp convention.

Writes to ~/.crow/logs/crow-memory.log alongside crow-mcp.log, so all of crow's
logs live together. RotatingFileHandler: 5MB per file, 3 backups.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def get_log_path() -> Path:
    root = Path.home() / ".crow" / "logs"
    root.mkdir(parents=True, exist_ok=True)
    return root / "crow-memory.log"


logging_path = get_log_path()


def setup_logger(name="crow_memory_logger", log_file=logging_path, max_mb=5, max_files=3):
    """
    Sets up a rotating file logger.

    :param name: Name of the logger.
    :param log_file: Path object or string to the log file.
    :param max_mb: Maximum size in Megabytes before rotating.
    :param max_files: Maximum number of backup files to keep.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        file_handler = RotatingFileHandler(
            log_file, maxBytes=max_mb * 1024 * 1024, backupCount=max_files
        )
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


logger = setup_logger()
