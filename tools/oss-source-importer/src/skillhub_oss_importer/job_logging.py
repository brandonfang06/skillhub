from __future__ import annotations

import json
import logging
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TextIO

LOGGER_NAME = "skillhub_oss_importer"


def job_value(value: object, *, limit: int = 512) -> str:
    if value is None:
        return "null"
    text = str(value)
    if len(text) > limit:
        text = f"{text[:limit]}..."
    return json.dumps(text, ensure_ascii=False)


@contextmanager
def configured_job_logging(stream: TextIO | None = None) -> Iterator[None]:
    logger = logging.getLogger(LOGGER_NAME)
    previous_handlers = list(logger.handlers)
    previous_level = logger.level
    previous_propagate = logger.propagate

    handler = logging.StreamHandler(stream or sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)sZ level=%(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    formatter.converter = time.gmtime
    handler.setFormatter(formatter)
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        yield
    finally:
        handler.flush()
        logger.handlers = previous_handlers
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate
