"""Build a standalone Windows GUI executable."""

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.__main__ import run

ROOT = Path(__file__).resolve().parent


def main() -> int:
    run(
        [
            str(ROOT / "Converter.spec"),
            "--noconfirm",
            "--clean",
            f"--distpath={ROOT / 'dist'}",
            f"--workpath={ROOT / 'build'}",
        ]
    )
    exe = ROOT / "dist" / "Converter.exe"
    if not exe.exists():
        print("build failed: Converter.exe not found", file=sys.stderr)
        return 1
    print(f"built {exe} ({exe.stat().st_size / 1024 / 1024:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
