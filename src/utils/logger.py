from typing import Any, Dict, Optional
from functools import lru_cache
import logging
import json
from dotenv import load_dotenv
import os

load_dotenv()


LOG_TO_FILE = os.getenv("LOG_TO_FILE", "false").lower() == "true"
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "app.log")

# LOG_LEVEL = DEBUG -- INFO -- WARNING -- ERROR -- CRITICAL


class CustomJsonFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging, excluding unnecessary fields.
    """

    EXCLUDED_FIELDS = {
        "levelno",
        "pathname",
        "filename",
        "module",
        "lineno",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "created",
        "exc_info",
        "exc_text",
        "stack_info",
        "taskName",
        "args",
        "funcName",
        "msg",
        "levelname",
    }

    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "name": record.name,
            "function": record.funcName,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key not in log_record and key not in self.EXCLUDED_FIELDS:
                log_record[key] = value

        return json.dumps(log_record, ensure_ascii=False)


class CustomLoggerAdapter(logging.LoggerAdapter):
    """
    Custom logger adapter to handle extra attributes correctly.
    """

    def process(self, msg, kwargs):
        if "extra" not in kwargs:
            kwargs["extra"] = {}

        kwargs["extra"].update(self.extra)
        return msg, kwargs


class CustomLogger:
    """
    Singleton Logger implementation with proper support for extra fields.

    - Allows only logger names that start with `app.` or `service.`
    - Ensures extra attributes are included in JSON logs.
    """

    _instances: dict = {}

    @staticmethod
    def get_logger(
        name: str = "app",
        default_extra: Dict[str, Any] = {},
    ) -> logging.LoggerAdapter:
        # if not name.startswith(("app.", "service.")):
        #     raise ValueError("Logger name must start with 'app.' or 'service.'")

        if name in CustomLogger._instances:
            return CustomLogger._instances[name]

        logger = logging.getLogger(name)

        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        logger.setLevel(getattr(logging, log_level, logging.INFO))

        formatter = CustomJsonFormatter()

        if not logger.hasHandlers():
            if LOG_TO_FILE:
                file_handler = logging.FileHandler(LOG_FILE_PATH)
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
            else:
                console_handler = logging.StreamHandler()
                console_handler.setFormatter(formatter)
                logger.addHandler(console_handler)

        logger_adapter = CustomLoggerAdapter(logger, default_extra or {})
        CustomLogger._instances[name] = logger_adapter

        return logger_adapter


@lru_cache(maxsize=10)
def get_logger(
    name: str = "app",
    default_extra: Optional[Dict[str, Any]] = None,
) -> logging.LoggerAdapter:
    """
    Returns a pre-configured logger as a Singleton.

    Args:
        name (str): Logger name.
        default_extra (dict): Default additional attributes.

    Returns:
        logging.LoggerAdapter: Logger instance.
    """

    if default_extra is None:
        default_extra = {}

    return CustomLogger.get_logger(name, default_extra)
