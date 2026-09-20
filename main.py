"""Entry point:  python main.py [optional.pdf]"""

from __future__ import annotations

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):  # running from source: make ``src`` importable
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from pdfeditor.logger import get_logger, setup_logging  # noqa: E402


def main() -> int:
    setup_logging()
    log = get_logger("pdfeditor")
    try:
        from pdfeditor.gui import PDFEditorApp
    except ImportError as exc:  # missing dependency / tkinter
        print(f"Missing dependency: {exc}\nInstall with: pip install -r requirements.txt", file=sys.stderr)
        return 1

    initial = sys.argv[1] if len(sys.argv) > 1 else None
    log.info("Starting PDF Editor Pro")
    app = PDFEditorApp(initial_file=initial)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
