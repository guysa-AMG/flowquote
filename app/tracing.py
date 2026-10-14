"""Local, privacy-safe stage timing without exporting data over the network."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter

logger = logging.getLogger("talkquote.pipeline")


@contextmanager
def local_stage(name: str) -> Iterator[None]:
    """Log stage name and duration only; never include transcript or customer data."""
    started = perf_counter()
    try:
        yield
    finally:
        logger.info(
            "pipeline_stage_complete",
            extra={"stage": name, "duration_ms": round((perf_counter() - started) * 1000, 2)},
        )
