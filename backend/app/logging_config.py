"""Central logging setup.

Configures the root logger so every module's ``logging.getLogger(__name__)``
call is captured both to the console and to a rotating file at
``backend/logs/app.log``. Call :func:`setup_logging` once at process start
(see ``backend/main.py``).

Level is controlled by the ``LOG_LEVEL`` env var (default ``INFO``).
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CONFIGURED = False

# backend/logs/  (this file lives at backend/app/logging_config.py)
LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_FILE = LOG_DIR / "app.log"


def setup_logging() -> Path:
    """Attach a console + rotating-file handler to the root logger (idempotent)."""
    global _CONFIGURED
    if _CONFIGURED:
        return LOG_FILE

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 5 MB per file, keep 5 rotations (~25 MB of history).
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)
    # Drop any handlers we added on a previous call (e.g. uvicorn --reload in the
    # same process) so logs aren't duplicated, then attach fresh ones.
    root.handlers = [h for h in root.handlers if not getattr(h, "_pf_managed", False)]
    for handler in (file_handler, console_handler):
        handler._pf_managed = True  # type: ignore[attr-defined]
        root.addHandler(handler)

    logging.getLogger(__name__).info(
        "[LOG] logging initialised -> %s (level=%s)", LOG_FILE, level_name
    )
    _CONFIGURED = True
    return LOG_FILE
