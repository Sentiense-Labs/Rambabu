#!/usr/bin/env python3
"""
Mode state machine for AI RC Car
Manages AUTONOMOUS, MANUAL, and STOPPED modes
"""

import threading
from utils.logger import log_info, log_warning


class ModeManager:
    """Thread-safe mode state machine"""

    # Mode constants
    AUTONOMOUS = "AUTONOMOUS"
    MANUAL = "MANUAL"
    STOPPED = "STOPPED"

    def __init__(self):
        """Initialize mode manager"""
        self.current_mode = self.STOPPED
        self.lock = threading.Lock()
        log_info("Mode manager initialized in STOPPED mode")

    def set_mode(self, mode: str, source: str = "unknown") -> None:
        """Set the current mode (thread-safe)

        Args:
            mode: Target mode (AUTONOMOUS, MANUAL, STOPPED)
            source: Who triggered the change (API, navigator, voice, unknown)
        """
        valid_modes = [self.AUTONOMOUS, self.MANUAL, self.STOPPED]

        if mode not in valid_modes:
            log_warning(f"Invalid mode: {mode}. Valid modes: {valid_modes}")
            return

        with self.lock:
            old_mode = self.current_mode
            self.current_mode = mode
            if old_mode != mode:
                log_info(f"Mode changed: {old_mode} → {mode} (triggered by {source})")

    def get_mode(self) -> str:
        """Get current mode (thread-safe)"""
        with self.lock:
            return self.current_mode

    def is_auto(self) -> bool:
        """Check if in autonomous mode"""
        return self.get_mode() == self.AUTONOMOUS

    def is_manual(self) -> bool:
        """Check if in manual mode"""
        return self.get_mode() == self.MANUAL

    def is_stopped(self) -> bool:
        """Check if in stopped mode"""
        return self.get_mode() == self.STOPPED
