"""Console logging: one line per step, time-stamped (no log files; the SD timelines are the record)."""

import logging
import sys


def setup_logging(level=logging.INFO) -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)-5s %(message)s", datefmt="%H:%M:%S",
                        stream=sys.stdout, force=True)
