"""One dialog class per feature. Dialogs only collect input; work is done by PDFService."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ..core import PDFService, parse_page_ranges
from ..exceptions import InvalidPageRangeError, PDFEditorError, PasswordRequiredError
from .widgets import FileListEditor, PasswordPrompt, ToolDialog, make_listbox

PDF_TYPES = [("PDF files", "*.pdf")]
IMAGE_TYPES = [("Images", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.gif"), ("All files", "*.*")]


def _pages_hint(app) -> str:
    return f"Document has {app.page_count} page(s). Examples: 1-3,5   |   8-   |   all"


# ---------------------------------------------------------------------- merge
class MergeDialog(ToolDialog):
    def __init__(self, app) -> None:
        super().__init__(app, "Merge PDFs", "Merge", size=(620, 440))
        self._passwords: dict[str, str] = {}
        self.add_label("Add two or more PDFs. They are merged in the order listed.", muted=True)
        self.files = FileListEditor(
            self.body, PDF_TYPES, "Select PDFs to merge", validator=self._validate, height=10
        )
        self.files.pack(fill="both", expand=True, pady=6)
        if app.path:
            self.files.add_paths([app.path])

    def _validate(self, path: Path) -> str | None:
        """Pre-flight each file so corrupted / locked PDFs are reported immediately."""
        password = self.app.password if path == self.app.path else None
        while True:
            try:
                info = PDFService.get_info(path, password)
                break
            except PasswordRequiredError:
                password = PasswordPrompt.ask(self, path.name, wrong=password is not None)
                if password is None:
                    return None
            except PDFEditorError as exc:
                messagebox.showerror("Skipped file", str(exc), parent=self)
                return None
        if password:
            self._passwords[str(path)] = password
        note = "  (repaired)" if info.was_repaired else ""
        return f"{path.name}   -   {info.page_count} page(s){note}"

    def on_submit(self) -> None:
        if len(self.files.paths) < 2:
            raise InvalidPageRangeError("Add at least two PDF files to merge.")
        out = self.app.ask_output_pdf(self, "merged", initial_dir=self.files.paths[0].parent)
        if not out:
            return
        inputs, pw = list(self.files.paths), dict(self._passwords)
        self.destroy()
        self.app.run_job("Merging PDFs", lambda: PDFService.merge(inputs, out, pw), self.app.offer_open)


# ---------------------------------------------------------------------- split
class SplitDialog(ToolDialog):
    def __init__(self, app) -> None:
        super().__init__(app, "Split PDF", "Split", size=(480, 400))
        self.mode = ctk.StringVar(value="each")
        self.add_label(f"Document has {app.page_count} page(s).", muted=True)
        for text, value in (
            ("One file per page", "each"),
            ("Every N pages", "every_n"),
            ("Custom ranges", "ranges"),
        ):
            ctk.CTkRadioButton(
                self.body, text=text, variable=self.mode, value=value, command=self._update
            ).pack(anchor="w", pady=4)
        self.value = self.add_entry("Value", placeholder="")
        self.hint = self.add_label("", muted=True, pady=(2, 0))
        self._update()

    def _update(self) -> None:
        mode = self.mode.get()
        state = "disabled" if mode == "each" else "normal"
        self.value.configure(state=state, placeholder_text="")
        hints = {
            "each": "Creates a separate PDF for every page.",
            "every_n": "Enter how many pages each file should contain, e.g. 3.",
            "ranges": "Separate groups with ';' - e.g. 1-3;4;5-9 creates three files.",
        }
        self.hint.configure(text=hints[mode])

    def on_submit(self) -> None:
        mode = self.mode.get()
        value = self.value.get().strip() if mode != "each" else None
        if mode == "every_n" and (not value.isdigit() or int(value) < 1):
            raise InvalidPageRangeError("Enter a whole number of pages per file, e.g. 3.")
        if mode == "ranges":
            groups = [g for g in value.split(";") if g.strip()]
            if not groups:
                raise InvalidPageRangeError("Enter ranges such as 1-3;4;5-9.")
            for group in groups:
                parse_page_ranges(group, self.app.page_count)
        folder = filedialog.askdirectory(parent=self, title="Choose output folder")
        if not folder:
            return
        path, pw = self.app.path, self.app.password
        self.destroy()
        self.app.run_job(
            "Splitting PDF",
            lambda: PDFService.split(path, folder, mode, value, pw),
            lambda files: self.app.offer_folder(Path(folder), f"Created {len(files)} file(s)."),
        )


# --------------------------------------------------------------------- rotate
class RotateDialog(ToolDialog):
    ANGLES = {"90° right": 90, "180°": 180, "90° left": 270}

    def __init__(self, app) -> None:
        super().__init__(app, "Rotate pages", "Rotate", size=(480, 330))
        self.add_label("Direction")
        self.angle = ctk.CTkSegmentedButton(self.body, values=list(self.ANGLES))
        self.angle.set("90° right")
        self.angle.pack(fill="x")
        self.pages = self.add_entry("Pages", "all")
        self.add_label(_pages_hint(app), muted=True, pady=(2, 0))
        ctk.CTkButton(
            self.body, text="Use current page only", width=170, height=26,
            command=lambda: self._set_pages(str(app.current_index + 1)),
        ).pack(anchor="w", pady=8)

    def _set_pages(self, text: str) -> None:
        self.pages.delete(0, tk.END)
        self.pages.insert(0, text)

    def on_submit(self) -> None:
        angle, pages = self.ANGLES[self.angle.get()], self.pages.get()
        parse_page_ranges(pages, self.app.page_count)  # validate before closing the dialog
        out = self.app.ask_output_pdf(self, "rotated")
        if not out:
            return
        path, pw = self.app.path, self.app.password
        self.destroy()
        self.app.run_job(
            "Rotating pages", lambda: PDFService.rotate(path, out, angle, pages, pw), self.app.offer_open
        )


# --------------------------------------------------------------------- delete
class DeleteDialog(ToolDialog):
    def __init__(self, app) -> None:
        super().__init__(app, "Delete pages", "Delete", size=(480, 290))
        self.pages = self.add_entry("Pages to delete", str(app.current_index + 1))
        self.add_label(_pages_hint(app), muted=True, pady=(2, 0))
        self.add_label("Your original file is never changed - a new PDF is saved.", muted=True)

    def on_submit(self) -> None:
        pages = self.pages.get()
        selected = parse_page_ranges(pages, self.app.page_count)
        if len(selected) >= self.app.page_count:
            raise InvalidPageRangeError("You cannot delete every page of the document.")
        out = self.app.ask_output_pdf(self, "edited")
        if not out:
            return
        path, pw = self.app.path, self.app.password
        self.destroy()
        self.app.run_job(
            "Deleting pages", lambda: PDFService.delete_pages(path, out, pages, pw), self.app.offer_open
        )


# -------------------------------------------------------------------- reorder
class ReorderDialog(ToolDialog):
    def __init__(self, app) -> None:
        super().__init__(app, "Reorder pages", "Save reordered PDF", size=(700, 500))
        self.order = list(range(1, app.page_count + 1))
        self.add_label("Select a page, then move it - or drag items in the list.", muted=True)

        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.pack(fill="both", expand=True)
        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True)
        self.listbox = make_listbox(left, height=14)
        sb = ctk.CTkScrollbar(left, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

        mid = ctk.CTkFrame(row, fg_color="transparent")
        mid.pack(side="left", fill="y", padx=10)
        for text, cmd in (
            ("Move up", lambda: self._shift(-1)), ("Move down", lambda: self._shift(1)),
            ("To top", lambda: self._to(0)), ("To bottom", lambda: self._to(-1)),
            ("Reverse all", self._reverse), ("Reset", self._reset),
        ):
            ctk.CTkButton(mid, text=text, width=100, height=28, command=cmd).pack(pady=3)

        self.thumb = ctk.CTkLabel(row, text="", width=190)
        self.thumb.pack(side="left", padx=(4, 0))

        self.listbox.bind("<<ListboxSelect>>", lambda _e: self._show_thumb())
        self.listbox.bind("<B1-Motion>", self._drag)
        self._refresh(0)

    def _refresh(self, select: int | None = None) -> None:
        self.listbox.delete(0, tk.END)
        for pos, page in enumerate(self.order, start=1):
            moved = "" if pos == page else "   (moved)"
            self.listbox.insert(tk.END, f"  {pos:>3}.   Page {page}{moved}")
        if select is not None:
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(select)
            self.listbox.see(select)
            self._show_thumb()

    def _selected(self) -> int | None:
        sel = self.listbox.curselection()
        return sel[0] if sel else None

    def _show_thumb(self) -> None:
        idx = self._selected()
        if idx is None:
            return
        try:
            img = PDFService.render_page(self.app.doc, self.order[idx] - 1, 0.32)
            self._thumb_img = ctk.CTkImage(img, size=img.size)
            self.thumb.configure(image=self._thumb_img)
        except PDFEditorError:
            self.thumb.configure(image=None, text="No preview")

    def _shift(self, delta: int) -> None:
        i = self._selected()
        if i is None or not 0 <= i + delta < len(self.order):
            return
        self.order[i], self.order[i + delta] = self.order[i + delta], self.order[i]
        self._refresh(i + delta)

    def _to(self, target: int) -> None:
        i = self._selected()
        if i is None:
            return
        page = self.order.pop(i)
        j = 0 if target == 0 else len(self.order)
        self.order.insert(j, page)
        self._refresh(j)

    def _reverse(self) -> None:
        self.order.reverse()
        self._refresh(self._selected() or 0)

    def _reset(self) -> None:
        self.order = list(range(1, self.app.page_count + 1))
        self._refresh(0)

    def _drag(self, event) -> None:
        i, target = self._selected(), self.listbox.nearest(event.y)
        if i is not None and target != i:
            self.order.insert(target, self.order.pop(i))
            self._refresh(target)

    def on_submit(self) -> None:
        if self.order == sorted(self.order):
            raise InvalidPageRangeError("The page order has not been changed.")
        out = self.app.ask_output_pdf(self, "reordered")
        if not out:
            return
        path, pw, order = self.app.path, self.app.password, list(self.order)
        self.destroy()
        self.app.run_job(
            "Reordering pages",
            lambda: PDFService.reorder_pages(path, out, order, pw),
            self.app.offer_open,
        )


# --------------------------------------------------------------- extract text
class ExtractTextDialog(ToolDialog):
    def __init__(self, app) -> None:
        super().__init__(app, "Extract text", "Close", size=(680, 560))
        self.submit_btn.configure(command=self.destroy)
        top = ctk.CTkFrame(self.body, fg_color="transparent")
        top.pack(fill="x")
        self.pages = ctk.CTkEntry(top, placeholder_text="Pages, e.g. 1-3,5 (blank = all)")
        self.pages.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(top, text="Extract", width=90, command=self._extract).pack(side="left", padx=8)
        self.text = ctk.CTkTextbox(self.body, wrap="word", font=ctk.CTkFont(family="Consolas", size=12))
        self.text.pack(fill="both", expand=True, pady=10)
        bar = ctk.CTkFrame(self.body, fg_color="transparent")
        bar.pack(fill="x")
        ctk.CTkButton(bar, text="Copy to clipboard", width=140, command=self._copy).pack(side="left")
        ctk.CTkButton(bar, text="Save as .txt", width=120, command=self._save).pack(side="left", padx=8)
        self.status = ctk.CTkLabel(bar, text="", text_color=("gray40", "gray65"))
        self.status.pack(side="right")

    def _extract(self) -> None:
        pages, path, pw = self.pages.get(), self.app.path, self.app.password
        self.status.configure(text="Extracting…")
        self.app.run_job(
            "Extracting text",
            lambda: PDFService.extract_text(path, None, pages, pw),
            self._show,
        )

    def _show(self, text: str) -> None:
        if not self.winfo_exists():
            return
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", text)
        words = len(text.split())
        self.status.configure(text=f"{words:,} words")
        if not any(line.strip() and not line.startswith("--- Page") for line in text.splitlines()):
            messagebox.showinfo(
                "No text found",
                "This PDF has no selectable text - it may be a scanned document (image only).",
                parent=self,
            )

    def _copy(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.text.get("1.0", tk.END))
        self.status.configure(text="Copied")

    def _save(self) -> None:
        content = self.text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showinfo("Nothing to save", "Extract some text first.", parent=self)
            return
        target = filedialog.asksaveasfilename(
            parent=self, defaultextension=".txt", filetypes=[("Text", "*.txt")],
            initialfile=f"{Path(self.app.path).stem}.txt",
        )
        if target:
            try:
                Path(target).write_text(content, encoding="utf-8")
                self.status.configure(text="Saved")
            except OSError as exc:
                messagebox.showerror("Save failed", str(exc), parent=self)

    def on_submit(self) -> None:  # footer button is wired to destroy
        self.destroy()


# ------------------------------------------------------------- images -> PDF
class ImagesToPdfDialog(ToolDialog):
    def __init__(self, app) -> None:
        super().__init__(app, "Images → PDF", "Create PDF", size=(640, 440))
        self.add_label("Each image becomes one page, in the order listed.", muted=True)
        self.files = FileListEditor(
            self.body, IMAGE_TYPES, "Select images", validator=lambda p: p.name, height=9
        )
        self.files.pack(fill="both", expand=True, pady=6)
        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkLabel(row, text="Page size").pack(side="left")
        self.size = ctk.CTkSegmentedButton(row, values=["A4 (fit)", "Original size"])
        self.size.set("A4 (fit)")
        self.size.pack(side="left", padx=10)

    def on_submit(self) -> None:
        if not self.files.paths:
            raise InvalidPageRangeError("Add at least one image.")
        out = self.app.ask_output_pdf(self, "images", initial_dir=self.files.paths[0].parent)
        if not out:
            return
        paths = list(self.files.paths)
        size = "a4" if self.size.get().startswith("A4") else "original"
        self.destroy()
        self.app.run_job(
            "Creating PDF from images",
            lambda: PDFService.images_to_pdf(paths, out, size),
            self.app.offer_open,
        )


# ------------------------------------------------------------- PDF -> images
class PdfToImagesDialog(ToolDialog):
    def __init__(self, app) -> None:
        super().__init__(app, "PDF → Images", "Export", size=(480, 420))
        self.add_label("Format")
        self.fmt = ctk.CTkSegmentedButton(self.body, values=["PNG", "JPG"])
        self.fmt.set("PNG")
        self.fmt.pack(fill="x")
        self.dpi = self.add_slider("Resolution (DPI)", 72, 300, 150, "{:.0f}", steps=19)
        self.pages = self.add_entry("Pages", "all")
        self.add_label(_pages_hint(app), muted=True, pady=(2, 0))

    def on_submit(self) -> None:
        fmt, dpi, pages = self.fmt.get().lower(), int(self.dpi.get()), self.pages.get()
        parse_page_ranges(pages, self.app.page_count)
        folder = filedialog.askdirectory(parent=self, title="Choose output folder")
        if not folder:
            return
        path, pw = self.app.path, self.app.password
        self.destroy()
        self.app.run_job(
            "Exporting images",
            lambda: PDFService.pdf_to_images(path, folder, fmt, dpi, pages, pw),
            lambda files: self.app.offer_folder(Path(folder), f"Exported {len(files)} image(s)."),
        )


# ------------------------------------------------------------------ watermark
class WatermarkDialog(ToolDialog):
    COLORS = {
        "Gray": (0.5, 0.5, 0.5), "Red": (0.85, 0.1, 0.1),
        "Blue": (0.1, 0.3, 0.85), "Black": (0.0, 0.0, 0.0),
    }

    def __init__(self, app) -> None:
        super().__init__(app, "Add watermark", "Apply watermark", size=(480, 560))
        self.text = self.add_entry("Watermark text", "CONFIDENTIAL")
        self.size = self.add_slider("Font size", 20, 120, 54, "{:.0f} pt", steps=100)
        self.opacity = self.add_slider("Opacity", 0.05, 1.0, 0.25, "{:.0%}", steps=95)
        self.angle = self.add_slider("Angle", -90, 90, 45, "{:.0f}°", steps=36)
        self.add_label("Colour")
        self.color = ctk.CTkOptionMenu(self.body, values=list(self.COLORS))
        self.color.pack(anchor="w")
        self.pages = self.add_entry("Pages", "all")

    def on_submit(self) -> None:
        text, pages = self.text.get(), self.pages.get()
        size, opacity, angle = int(self.size.get()), round(self.opacity.get(), 2), int(self.angle.get())
        color = self.COLORS[self.color.get()]
        if not text.strip():
            raise InvalidPageRangeError("Enter the watermark text.")
        parse_page_ranges(pages, self.app.page_count)
        out = self.app.ask_output_pdf(self, "watermarked")
        if not out:
            return
        path, pw = self.app.path, self.app.password
        self.destroy()
        self.app.run_job(
            "Adding watermark",
            lambda: PDFService.add_text_watermark(path, out, text, size, opacity, angle, color, pages, pw),
            self.app.offer_open,
        )


# ------------------------------------------------------------- security
class ProtectDialog(ToolDialog):
    def __init__(self, app) -> None:
        super().__init__(app, "Protect with password", "Encrypt", size=(480, 440))
        self.pw1 = self.add_entry("Password", show="•")
        self.pw2 = self.add_entry("Confirm password", show="•")
        self.allow_print = ctk.CTkCheckBox(self.body, text="Allow printing")
        self.allow_print.select()
        self.allow_print.pack(anchor="w", pady=(14, 4))
        self.allow_copy = ctk.CTkCheckBox(self.body, text="Allow copying text")
        self.allow_copy.pack(anchor="w", pady=4)
        self.add_label("AES-256 encryption. Keep the password safe - it cannot be recovered.", muted=True)

    def on_submit(self) -> None:
        pw = self.pw1.get()
        if pw != self.pw2.get():
            raise InvalidPageRangeError("The two passwords do not match.")
        printing, copying = bool(self.allow_print.get()), bool(self.allow_copy.get())
        out = self.app.ask_output_pdf(self, "protected")
        if not out:
            return
        path, cur = self.app.path, self.app.password
        self.destroy()
        self.app.run_job(
            "Encrypting PDF",
            lambda: PDFService.protect(path, out, pw, None, printing, copying, cur),
            self.app.offer_open,
        )


class UnlockDialog(ToolDialog):
    def __init__(self, app) -> None:
        super().__init__(app, "Remove password", "Unlock", size=(480, 290))
        self.pw = self.add_entry("Current password", app.password or "", show="•")
        self.add_label("Saves an unprotected copy. Only do this for files you own.", muted=True)

    def on_submit(self) -> None:
        pw = self.pw.get()
        out = self.app.ask_output_pdf(self, "unlocked")
        if not out:
            return
        path = self.app.path
        self.destroy()
        self.app.run_job(
            "Removing password", lambda: PDFService.unprotect(path, out, pw), self.app.offer_open
        )
