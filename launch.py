from __future__ import annotations

import sys
import traceback
from pathlib import Path

from image_opt.cli import main


def _crash_log() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).with_name("converter-error.log")
    return Path.cwd() / "converter-error.log"


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        try:
            _crash_log().write_text(traceback.format_exc(), encoding="utf-8")
        except OSError:
            pass
        raise
