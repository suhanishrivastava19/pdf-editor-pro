"""PDFService - all PDF operations, completely independent from the GUI.

The GUI (or any script / test) only talks to this class. Every method:

* validates its input,
* never modifies the source file (it always writes a *new* output file),
* raises a subclass of :class:`~pdfeditor.exceptions.PDFEditorError` on failure.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

import pymupdf
from PIL import Image, ImageOps, UnidentifiedImageError

from ..exceptions import (
    CorruptedPDFError,
    FileAccessError,
    InvalidPageRangeError,
    OperationError,
    PasswordRequiredError,
)
from ..logger import get_logger
from .utils import ensure_output_path, parse_page_ranges

log = get_logger(__name__)

PathLike = str | Path

A4_SIZE = (595.0, 842.0)  # points


@dataclass(slots=True)
class PDFInfo:
    """Lightweight description of an opened PDF."""

    path: Path
    page_count: int
    size_bytes: int
    encrypted: bool
    was_repaired: bool
    metadata: dict[str, str] = field(default_factory=dict)


class PDFService:
    """Facade exposing every PDF feature of the application."""

    # ------------------------------------------------------------------ open
    @staticmethod
    def open_document(path: PathLike, password: str | None = None) -> pymupdf.Document:
        """Open a PDF safely.

        Raises:
            FileAccessError: file missing / unreadable.
            CorruptedPDFError: not a PDF, empty or unrecoverable.
            PasswordRequiredError: encrypted and password missing / wrong.
        """
        p = Path(path)
        if not p.is_file():
            raise FileAccessError(f"File not found: {p}")
        if p.stat().st_size == 0:
            raise CorruptedPDFError(f"'{p.name}' is an empty file.")
        try:
            doc = pymupdf.open(str(p), filetype="pdf")
        except Exception as exc:  # pymupdf raises several distinct types
            log.warning("Could not open %s: %s", p, exc)
            raise CorruptedPDFError(
                f"'{p.name}' is not a valid PDF or is too damaged to open."
            ) from exc

        if doc.needs_pass:
            if not password:
                doc.close()
                raise PasswordRequiredError(f"'{p.name}' is password protected.")
            if not doc.authenticate(password):
                doc.close()
                raise PasswordRequiredError(f"Wrong password for '{p.name}'.")

        if doc.page_count == 0:
            doc.close()
            raise CorruptedPDFError(f"'{p.name}' contains no readable pages.")
        if doc.is_repaired:
            log.warning("%s was damaged and has been repaired in memory.", p.name)
        return doc

    @classmethod
    def get_info(cls, path: PathLike, password: str | None = None) -> PDFInfo:
        with cls.open_document(path, password) as doc:
            meta = {k: v for k, v in (doc.metadata or {}).items() if v}
            return PDFInfo(
                path=Path(path),
                page_count=doc.page_count,
                size_bytes=Path(path).stat().st_size,
                encrypted=doc.is_encrypted,
                was_repaired=doc.is_repaired,
                metadata=meta,
            )

    # --------------------------------------------------------------- helpers
    @staticmethod
    def _save(doc: pymupdf.Document, output: PathLike, **kwargs) -> Path:
        out = ensure_output_path(output, ".pdf")
        options = {"garbage": 3, "deflate": True}
        options.update(kwargs)
        try:
            doc.save(str(out), **options)
        except PermissionError as exc:
            raise FileAccessError(f"Permission denied writing '{out}'.") from exc
        except Exception as exc:
            raise OperationError(f"Could not save '{out.name}': {exc}") from exc
        log.info("Saved %s", out)
        return out

    @staticmethod
    def _check_distinct(source: PathLike, output: PathLike) -> None:
        try:
            same = Path(source).resolve() == Path(output).resolve()
        except OSError:
            same = False
        if same:
            raise OperationError(
                "Output must be a different file from the input (originals are never overwritten)."
            )

    @staticmethod
    def _copy_pages(src: pymupdf.Document, indexes: Sequence[int]) -> pymupdf.Document:
        """Build a new document from *indexes*, grouping consecutive runs for speed."""
        new = pymupdf.open()
        run_start = prev = None
        for idx in indexes:
            if run_start is None:
                run_start = prev = idx
            elif idx == prev + 1:
                prev = idx
            else:
                new.insert_pdf(src, from_page=run_start, to_page=prev)
                run_start = prev = idx
        if run_start is not None:
            new.insert_pdf(src, from_page=run_start, to_page=prev)
        return new

    # ----------------------------------------------------------------- merge
    @classmethod
    def merge(
        cls,
        inputs: Sequence[PathLike],
        output: PathLike,
        passwords: dict[str, str] | None = None,
    ) -> Path:
        """Concatenate several PDFs (in the given order) into one."""
        if len(inputs) < 2:
            raise OperationError("Select at least two PDF files to merge.")
        passwords = passwords or {}
        for src in inputs:
            cls._check_distinct(src, output)
        merged = pymupdf.open()
        try:
            for src in inputs:
                with cls.open_document(src, passwords.get(str(src))) as doc:
                    merged.insert_pdf(doc)
            return cls._save(merged, output)
        finally:
            merged.close()

    # ----------------------------------------------------------------- split
    @classmethod
    def split(
        cls,
        path: PathLike,
        out_dir: PathLike,
        mode: str = "each",
        value: str | int | None = None,
        password: str | None = None,
    ) -> list[Path]:
        """Split a PDF.

        ``mode``:
            * ``"each"``   - one file per page
            * ``"every_n"`` - a file per *value* pages (``value`` = int)
            * ``"ranges"`` - one file per group; groups separated by ``;``
              e.g. ``"1-3;4;5-9"``
        """
        out_dir = Path(out_dir)
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise FileAccessError(f"Cannot create folder '{out_dir}': {exc}") from exc

        stem = Path(path).stem
        results: list[Path] = []
        with cls.open_document(path, password) as src:
            total = src.page_count
            if mode == "each":
                groups = [[i] for i in range(total)]
            elif mode == "every_n":
                try:
                    n = int(value)  # type: ignore[arg-type]
                except (TypeError, ValueError) as exc:
                    raise InvalidPageRangeError("Enter a whole number of pages per file.") from exc
                if n < 1:
                    raise InvalidPageRangeError("Pages per file must be at least 1.")
                groups = [list(range(i, min(i + n, total))) for i in range(0, total, n)]
            elif mode == "ranges":
                parts = [p.strip() for p in str(value or "").split(";") if p.strip()]
                if not parts:
                    raise InvalidPageRangeError("Enter ranges such as 1-3;4;5-9.")
                groups = [parse_page_ranges(p, total) for p in parts]
            else:
                raise OperationError(f"Unknown split mode: {mode}")

            width = len(str(len(groups)))
            for n_file, indexes in enumerate(groups, start=1):
                part = cls._copy_pages(src, indexes)
                try:
                    label = (
                        f"page{indexes[0] + 1}" if len(indexes) == 1
                        else f"pages{indexes[0] + 1}-{indexes[-1] + 1}"
                    )
                    results.append(
                        cls._save(part, out_dir / f"{stem}_{str(n_file).zfill(width)}_{label}.pdf")
                    )
                finally:
                    part.close()
        return results

    # ---------------------------------------------------------------- rotate
    @classmethod
    def rotate(
        cls,
        path: PathLike,
        output: PathLike,
        angle: int,
        pages: str = "all",
        password: str | None = None,
    ) -> Path:
        """Rotate selected pages by a multiple of 90 degrees (clockwise)."""
        if angle % 90 != 0:
            raise OperationError("Rotation must be a multiple of 90 degrees.")
        cls._check_distinct(path, output)
        with cls.open_document(path, password) as doc:
            for i in parse_page_ranges(pages, doc.page_count):
                page = doc[i]
                page.set_rotation((page.rotation + angle) % 360)
            return cls._save(doc, output)

    # ---------------------------------------------------------------- delete
    @classmethod
    def delete_pages(
        cls, path: PathLike, output: PathLike, pages: str, password: str | None = None
    ) -> Path:
        cls._check_distinct(path, output)
        with cls.open_document(path, password) as doc:
            to_delete = set(parse_page_ranges(pages, doc.page_count))
            keep = [i for i in range(doc.page_count) if i not in to_delete]
            if not keep:
                raise OperationError("You cannot delete every page of the document.")
            doc.select(keep)
            return cls._save(doc, output)

    # --------------------------------------------------------------- reorder
    @classmethod
    def reorder_pages(
        cls,
        path: PathLike,
        output: PathLike,
        new_order: Sequence[int],
        password: str | None = None,
    ) -> Path:
        """Re-arrange pages. ``new_order`` holds 1-based page numbers, e.g. ``[3, 1, 2]``."""
        cls._check_distinct(path, output)
        with cls.open_document(path, password) as doc:
            order = [n - 1 for n in new_order]
            if sorted(order) != list(range(doc.page_count)):
                raise InvalidPageRangeError(
                    f"The new order must list each of the {doc.page_count} pages exactly once."
                )
            doc.select(order)
            return cls._save(doc, output)

    # ---------------------------------------------------------- extract text
    @classmethod
    def extract_text(
        cls,
        path: PathLike,
        output: PathLike | None = None,
        pages: str = "all",
        password: str | None = None,
    ) -> str:
        """Return (and optionally write to a .txt file) the text of the chosen pages."""
        chunks: list[str] = []
        with cls.open_document(path, password) as doc:
            for i in parse_page_ranges(pages, doc.page_count):
                chunks.append(f"--- Page {i + 1} ---\n{doc[i].get_text('text').strip()}\n")
        text = "\n".join(chunks)
        if not any(c.split("\n", 1)[1].strip() for c in chunks):
            log.info("No extractable text found in %s (scanned document?)", path)
        if output:
            out = ensure_output_path(output, ".txt")
            try:
                out.write_text(text, encoding="utf-8")
            except OSError as exc:
                raise FileAccessError(f"Cannot write '{out}': {exc}") from exc
        return text

    # ----------------------------------------------------- image <-> PDF
    @classmethod
    def images_to_pdf(
        cls,
        images: Iterable[PathLike],
        output: PathLike,
        page_size: str = "a4",
    ) -> Path:
        """Create a PDF with one page per image (``page_size``: ``"a4"`` or ``"original"``)."""
        paths = [Path(p) for p in images]
        if not paths:
            raise OperationError("Select at least one image.")
        doc = pymupdf.open()
        try:
            for p in paths:
                try:
                    with Image.open(p) as im:
                        im = ImageOps.exif_transpose(im).convert("RGB")
                        buf = io.BytesIO()
                        im.save(buf, format="JPEG", quality=92)
                        width_px, height_px = im.size
                except (UnidentifiedImageError, OSError) as exc:
                    raise OperationError(f"'{p.name}' is not a readable image.") from exc

                if page_size == "original":
                    w, h = width_px * 0.75, height_px * 0.75  # 96 dpi -> points
                    page = doc.new_page(width=w, height=h)
                    rect = page.rect
                else:
                    w, h = A4_SIZE
                    if width_px > height_px:  # landscape image -> landscape page
                        w, h = h, w
                    page = doc.new_page(width=w, height=h)
                    margin = 24
                    box = pymupdf.Rect(margin, margin, w - margin, h - margin)
                    scale = min(box.width / width_px, box.height / height_px)
                    iw, ih = width_px * scale, height_px * scale
                    x0, y0 = box.x0 + (box.width - iw) / 2, box.y0 + (box.height - ih) / 2
                    rect = pymupdf.Rect(x0, y0, x0 + iw, y0 + ih)
                page.insert_image(rect, stream=buf.getvalue())
            return cls._save(doc, output)
        finally:
            doc.close()

    @classmethod
    def pdf_to_images(
        cls,
        path: PathLike,
        out_dir: PathLike,
        fmt: str = "png",
        dpi: int = 150,
        pages: str = "all",
        password: str | None = None,
    ) -> list[Path]:
        """Render pages to PNG / JPG files."""
        fmt = fmt.lower().lstrip(".")
        if fmt not in {"png", "jpg", "jpeg"}:
            raise OperationError("Image format must be PNG or JPG.")
        if not 36 <= dpi <= 600:
            raise OperationError("DPI must be between 36 and 600.")
        out_dir = Path(out_dir)
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise FileAccessError(f"Cannot create folder '{out_dir}': {exc}") from exc

        results: list[Path] = []
        with cls.open_document(path, password) as doc:
            indexes = parse_page_ranges(pages, doc.page_count)
            width = len(str(doc.page_count))
            for i in indexes:
                pix = doc[i].get_pixmap(dpi=dpi, alpha=False)
                target = out_dir / f"{Path(path).stem}_page{str(i + 1).zfill(width)}.{fmt}"
                try:
                    pix.save(str(target))
                except Exception as exc:
                    raise OperationError(f"Could not write '{target.name}': {exc}") from exc
                results.append(target)
        log.info("Exported %d page(s) to %s", len(results), out_dir)
        return results

    # ------------------------------------------------------------- watermark
    @classmethod
    def add_text_watermark(
        cls,
        path: PathLike,
        output: PathLike,
        text: str,
        font_size: int = 54,
        opacity: float = 0.25,
        angle: int = 45,
        color: tuple[float, float, float] = (0.5, 0.5, 0.5),
        pages: str = "all",
        password: str | None = None,
    ) -> Path:
        """Stamp diagonal (or any angle) text in the centre of the chosen pages."""
        text = (text or "").strip()
        if not text:
            raise OperationError("Watermark text cannot be empty.")
        if not 0.02 <= opacity <= 1.0:
            raise OperationError("Opacity must be between 0.02 and 1.0.")
        cls._check_distinct(path, output)

        font = "helv"
        with cls.open_document(path, password) as doc:
            text_len = pymupdf.get_text_length(text, fontname=font, fontsize=font_size)
            for i in parse_page_ranges(pages, doc.page_count):
                page = doc[i]
                # Work in stored (un-rotated) page coordinates so rotated pages stay centred.
                centre_s = page.rect.tl + (page.rect.br - page.rect.tl) * 0.5
                centre_s = centre_s * page.derotation_matrix
                start_s = pymupdf.Point(centre_s.x - text_len / 2, centre_s.y + font_size * 0.3)
                morph_angle = angle + page.rotation  # keep the text angle visually constant
                page.insert_text(
                    start_s,
                    text,
                    fontname=font,
                    fontsize=font_size,
                    color=color,
                    fill_opacity=opacity,
                    rotate=0,
                    morph=(centre_s, pymupdf.Matrix(morph_angle)),
                    overlay=True,
                )
            return cls._save(doc, output)

    @classmethod
    def add_page_numbers(
        cls,
        path: PathLike,
        output: PathLike,
        font_size: int = 10,
        password: str | None = None,
    ) -> Path:
        """Add "Page X of Y" centred at the bottom of every page."""
        cls._check_distinct(path, output)
        with cls.open_document(path, password) as doc:
            total = doc.page_count
            for i, page in enumerate(doc):
                label = f"Page {i + 1} of {total}"
                w = pymupdf.get_text_length(label, fontname="helv", fontsize=font_size)
                visual = pymupdf.Point(page.rect.width / 2 - w / 2, page.rect.height - 20)
                page.insert_text(
                    visual * page.derotation_matrix,
                    label,
                    fontname="helv",
                    fontsize=font_size,
                    color=(0.25, 0.25, 0.25),
                    rotate=page.rotation,
                )
            return cls._save(doc, output)

    # -------------------------------------------------------------- security
    @classmethod
    def protect(
        cls,
        path: PathLike,
        output: PathLike,
        user_password: str,
        owner_password: str | None = None,
        allow_print: bool = True,
        allow_copy: bool = False,
        password: str | None = None,
    ) -> Path:
        """Encrypt with AES-256. ``user_password`` is needed to open the file."""
        if not user_password:
            raise OperationError("Please enter a password.")
        cls._check_distinct(path, output)
        perms = pymupdf.PDF_PERM_ACCESSIBILITY
        if allow_print:
            perms |= pymupdf.PDF_PERM_PRINT
        if allow_copy:
            perms |= pymupdf.PDF_PERM_COPY
        with cls.open_document(path, password) as doc:
            return cls._save(
                doc,
                output,
                encryption=pymupdf.PDF_ENCRYPT_AES_256,
                user_pw=user_password,
                owner_pw=owner_password or user_password + "#owner",
                permissions=perms,
            )

    @classmethod
    def unprotect(cls, path: PathLike, output: PathLike, password: str) -> Path:
        """Save an unencrypted copy of a password-protected PDF."""
        cls._check_distinct(path, output)
        with cls.open_document(path, password) as doc:
            return cls._save(doc, output, encryption=pymupdf.PDF_ENCRYPT_NONE)

    # -------------------------------------------------------------- optimise
    @classmethod
    def compress(cls, path: PathLike, output: PathLike, password: str | None = None) -> Path:
        """Rewrite the PDF with maximum clean-up. Also repairs many damaged files."""
        cls._check_distinct(path, output)
        with cls.open_document(path, password) as doc:
            return cls._save(doc, output, garbage=4, clean=True, deflate=True)

    # --------------------------------------------------------------- preview
    @classmethod
    def render_page(cls, doc: pymupdf.Document, index: int, zoom: float = 1.0) -> Image.Image:
        """Render one page as a PIL image for the preview pane."""
        if not 0 <= index < doc.page_count:
            raise InvalidPageRangeError(f"Page {index + 1} does not exist.")
        try:
            pix = doc[index].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        except Exception as exc:
            raise OperationError(f"Could not render page {index + 1}: {exc}") from exc
