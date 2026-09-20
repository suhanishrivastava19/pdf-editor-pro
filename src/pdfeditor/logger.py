"""Central logging configuration (console + rotating file)."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path.home() / ".pdf_editor_pro" / "logs"
_CONFIGURED = False


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root logger once. Safe to call multiple times."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    root = logging.getLogger()
    root.setLevel(level)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            LOG_DIR / "pdf_editor.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError:  # read-only home dir etc. - console logging is enough
        root.warning("File logging disabled (cannot write to %s)", LOG_DIR)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
