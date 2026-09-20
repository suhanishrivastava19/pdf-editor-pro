"""Build a standalone executable with PyInstaller.

Usage:
    python build_exe.py            # creates dist/PDFEditorPro(.exe)

Run it on the operating system you want to target (Windows -> .exe,
macOS -> .app bundle, Linux -> ELF binary).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEP = ";" if sys.platform.startswith("win") else ":"


def main() -> int:
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed", "--onefile",
        "--name", "PDFEditorPro",
        "--paths", str(ROOT / "src"),
        "--collect-all", "customtkinter",
        "--hidden-import", "PIL._tkinter_finder",  # Pillow <-> Tk bridge (preview images)
        "--collect-submodules", "PIL",
        "--add-data", f"{ROOT / 'assets'}{SEP}assets",
        "--icon", str(ROOT / "assets" / "icon.ico"),
        str(ROOT / "main.py"),
    ]
    print("Running:", " ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
