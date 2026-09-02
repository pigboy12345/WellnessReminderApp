import logging
import os
import sys


def setup_logging(log_file: str, log_level: str = "INFO") -> logging.Logger:
    """Configure logging to a file (always) and console (when one exists)."""
    level = getattr(logging, str(log_level).upper(), logging.INFO)

    log_dir = os.path.dirname(os.path.abspath(log_file))
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger("WellnessReminder")
    logger.setLevel(level)
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    # PyInstaller --noconsole builds have no stdout/stderr; guard against that.
    if sys.stdout is not None:
        try:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(fmt)
            logger.addHandler(console_handler)
        except Exception:
            pass

    return logger
