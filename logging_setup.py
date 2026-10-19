import json
import logging
from datetime import UTC, datetime
from logging.config import dictConfig
from traceback import extract_tb


class JsonFormatter(logging.Formatter):
    def format(self, record):
        data = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "method", "route", "status", "duration_ms"):
            if hasattr(record, key):
                data[key] = getattr(record, key)
        if record.exc_info:
            # SQL/SMTP exception messages can contain credentials or user data.
            # Keep the error type and frame locations, without messages or locals.
            data["error_type"] = record.exc_info[0].__name__
            data["traceback"] = [
                {"file": frame.filename, "line": frame.lineno, "function": frame.name}
                for frame in extract_tb(record.exc_info[2])
            ]
        return json.dumps(data, ensure_ascii=False)


def configure_logging(level):
    dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"json": {"()": JsonFormatter}},
        "handlers": {"console": {
            "class": "logging.StreamHandler", "stream": "ext://sys.stdout", "formatter": "json",
        }},
        "root": {"level": level, "handlers": ["console"]},
        "loggers": {
            "uvicorn": {"handlers": [], "propagate": True, "level": level},
            "uvicorn.error": {"handlers": [], "propagate": True, "level": level},
            # Our access log omits raw URLs, query strings and client credentials.
            "uvicorn.access": {"handlers": [], "propagate": False},
            "sqlalchemy.engine": {"level": "WARNING"},
        },
    })
