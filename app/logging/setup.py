"""Standard application logging (errors, crashes, network issues) -> stdout.

Kept separate from the business event_log (app/logging/events.py), which is the
append-only audit trail used for /trace and dispute resolution.
"""

from __future__ import annotations

import logging
import sys


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root.handlers = [handler]
