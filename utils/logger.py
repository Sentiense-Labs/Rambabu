#!/usr/bin/env python3
"""
Logging utility for AI RC Car
Provides timestamped logging to console and file
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Log levels
DEBUG = 0
INFO = 1
WARNING = 2
ERROR = 3

# Current log level (can be set via config)
LOG_LEVEL = INFO

# Log file path
LOG_FILE = Path("logs/runtime.log")


def _ensure_log_dir():
    """Create logs directory if it doesn't exist"""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def _get_timestamp() -> str:
    """Get formatted timestamp [YYYY-MM-DD HH:MM:SS]"""
    return datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")


def _log(level: int, level_name: str, msg: str) -> None:
    """Internal logging function"""
    if level < LOG_LEVEL:
        return

    timestamp = _get_timestamp()
    log_msg = f"{timestamp} {level_name}: {msg}"

    # Output to console
    print(log_msg)

    # Output to file
    try:
        _ensure_log_dir()
        with open(LOG_FILE, "a") as f:
            f.write(log_msg + "\n")
    except Exception as e:
        print(f"Failed to write to log file: {e}")


def log_debug(msg: str) -> None:
    """Log debug message"""
    _log(DEBUG, "DEBUG", msg)


def log_info(msg: str) -> None:
    """Log info message"""
    _log(INFO, "INFO", msg)


def log_warning(msg: str) -> None:
    """Log warning message"""
    _log(WARNING, "WARNING", msg)


def log_error(msg: str) -> None:
    """Log error message"""
    _log(ERROR, "ERROR", msg)


def set_log_level(level: int) -> None:
    """Set minimum log level"""
    global LOG_LEVEL
    LOG_LEVEL = level
