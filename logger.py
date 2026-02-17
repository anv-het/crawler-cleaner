"""
Logger module - Configurable logging to file and console.
"""

import logging
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

_logger_instance = None

def setup_logger(name="Ranker_Crawler"):
    """
    Set up and return a configured logger based on settings.
    """
    global _logger_instance

    if _logger_instance is not None:
        return _logger_instance

    # Settings
    log_level = os.getenv("LOG_LEVEL", "INFO")
    log_enabled = os.getenv("LOG_ENABLED", "true").lower() == "true"
    log_to_console = os.getenv("LOG_TO_CONSOLE", "true").lower() == "true"
    log_to_file = os.getenv("LOG_TO_FILE", "true").lower() == "true"
    log_file_path = os.getenv("LOG_FILE_PATH", "logs/")

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    logger.handlers.clear()

    if not log_enabled:
        logger.addHandler(logging.NullHandler())
        _logger_instance = logger
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console Handler
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # File Handler
    if log_to_file:
        full_log_path = os.path.join(os.getcwd(), log_file_path)
        os.makedirs(full_log_path, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(full_log_path, f"{name.lower()}_{timestamp}.log")

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # Log creation message
        # logger.info(f"Log file created: {log_file}")

    _logger_instance = logger
    return logger

def get_logger(name="Ranker_Crawler"):
    """Get the existing logger instance, or create a default one."""
    global _logger_instance
    if _logger_instance is None:
        return setup_logger(name)
    return _logger_instance
