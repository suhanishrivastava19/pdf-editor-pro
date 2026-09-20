"""Small helpers shared by the core layer."""

from __future__ import annotations

from pathlib import Path

from ..exceptions import FileAccessError, InvalidPageRangeError


def parse_page_ranges(spec: str, total: int) -> list[int]:
    """Convert a human page spec into a sorted, de-duplicated list of 0-based indexes.

    Examples (``total=10``)::

        "1-3,5"  -> [0, 1, 2, 4]
        "8-"     -> [7, 8, 9]
        "all"    -> [0, ..., 9]
    """
    spec = (spec or "").strip().lower()
    if not spec or spec == "all":
        return list(range(total))

    pages: set[int] = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            if "-" in chunk:
                start_s, end_s = (part.strip() for part in chunk.split("-", 1))
                start = int(start_s) if start_s else 1
                end = int(end_s) if end_s else total
            else:
                start = end = int(chunk)
        except ValueError as exc:
            raise InvalidPageRangeError(f"Invalid page range: '{chunk}'") from exc
        if start < 1 or end > total or start > end:
            raise InvalidPageRangeError(
                f"Range '{chunk}' is outside the document (1-{total})."
            )
        pages.update(range(start - 1, end))
    if not pages:
        raise InvalidPageRangeError("No pages selected.")
    return sorted(pages)


def ensure_output_path(path: str | Path, suffix: str | None = None) -> Path:
    """Validate an output path and create its parent folder."""
    out = Path(path)
    if suffix and out.suffix.lower() != suffix:
        out = out.with_suffix(suffix)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise FileAccessError(f"Cannot create folder '{out.parent}': {exc}") from exc
    return out
