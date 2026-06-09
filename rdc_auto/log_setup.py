from __future__ import annotations

import logging
from pathlib import Path

from .config import log_dir


def configure_logging(verbose: bool = False, directory: Path | None = None) -> Path:
    directory = directory or log_dir()
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / "rdc-auto.log"
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )
    return log_path
