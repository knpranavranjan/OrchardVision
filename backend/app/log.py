import logging
import logging.config
import time


def configure_logging(level: str = "INFO") -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "plain": {
                    "format": "%(asctime)s.%(msecs)03dZ %(levelname)-7s %(name)s: %(message)s",
                    "datefmt": "%Y-%m-%dT%H:%M:%S",
                }
            },
            "handlers": {
                "console": {"class": "logging.StreamHandler", "formatter": "plain"},
            },
            "root": {"level": level.upper(), "handlers": ["console"]},
            "loggers": {
                "uvicorn.access": {"level": "WARNING"},
                "sqlalchemy.engine": {"level": "WARNING"},
            },
        }
    )
    # Timestamps are UTC everywhere, logs included.
    logging.Formatter.converter = time.gmtime
