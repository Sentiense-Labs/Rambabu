#!/usr/bin/env python3
"""
Logging utility for AI RC Car
Provides timestamped logging to console and file
"""

import sys
from datetime import datetime
from pathlib import Path

# Log levels
DEBUG = 0
INFO = 1
WARNING = 2
ERROR = 3

# Read from config — import deferred to avoid circular imports
_LOG_LEVEL_MAP = {"DEBUG": DEBUG, "INFO": INFO, "WARNING": WARNING, "ERROR": ERROR}


def _get_config_value(attr: str, default):
    """Safely read a config attribute, falling back if config isn't available yet."""
    try:
        import config

        return getattr(config, attr, default)
    except Exception:
        return default


def _get_log_level() -> int:
    level_str = _get_config_value("LOG_LEVEL", "INFO")
    return _LOG_LEVEL_MAP.get(level_str, INFO)


def _get_log_file() -> Path:
    return Path(_get_config_value("LOG_FILE", "logs/runtime.log"))


def _ensure_log_dir(log_file: Path):
    """Create logs directory if it doesn't exist"""
    log_file.parent.mkdir(parents=True, exist_ok=True)


def _get_timestamp() -> str:
    """Get formatted timestamp [YYYY-MM-DD HH:MM:SS]"""
    return datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")


def _log(level: int, level_name: str, msg: str) -> None:
    """Internal logging function"""
    if level < _get_log_level():
        return

    timestamp = _get_timestamp()
    log_msg = f"{timestamp} {level_name}: {msg}"

    # Output to console
    print(log_msg)

    # Output to file
    try:
        log_file = _get_log_file()
        _ensure_log_dir(log_file)
        with open(log_file, "a") as f:
            f.write(log_msg + "\n")
    except Exception as e:
        print(f"Failed to write to log file: {e}", file=sys.stderr)


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
    """Set minimum log level (runtime override)"""
    # This is a no-op now — log level comes from config
    # Kept for backwards compatibility
    pass
