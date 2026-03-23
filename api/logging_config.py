import logging
import os
from datetime import datetime, timezone, timedelta
from logging.handlers import TimedRotatingFileHandler

TW_TZ = timezone(timedelta(hours=8))


class TaiwanFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=TW_TZ)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()


class HealthCheckFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        return "GET /health" not in msg


def setup_logging(log_dir: str):
    os.makedirs(log_dir, exist_ok=True)
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    formatter = TaiwanFormatter(fmt, datefmt=datefmt)

    app_handler = TimedRotatingFileHandler(
        os.path.join(log_dir, "app.log"), when="midnight", backupCount=14
    )
    app_handler.setFormatter(formatter)

    app_logger = logging.getLogger("api")
    app_logger.setLevel(logging.INFO)
    app_logger.addHandler(app_handler)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    app_logger.addHandler(console)

    access_handler = TimedRotatingFileHandler(
        os.path.join(log_dir, "access.log"), when="midnight", backupCount=14
    )
    access_handler.setFormatter(formatter)
    access_handler.addFilter(HealthCheckFilter())

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.addHandler(access_handler)

    return app_logger
