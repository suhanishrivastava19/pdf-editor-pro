"""Main application window."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Callable

import customtkinter as ctk
import pymupdf

from .. import __app_name__, __version__
from ..core import PDFService
from ..exceptions import PDFEditorError, PasswordRequiredError
from ..logger import get_logger
from . import dialogs
from .preview import PreviewPanel
from .widgets import PasswordPrompt

log = get_logger(__name__)

ACCENT = "#2f6fed"


class PDFEditorApp(ctk.CTk):
    """Top-level window: sidebar of tools + live preview + status bar."""

    def __init__(self, initial_file: str | None = None) -> None:
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")
        super().__init__()
        self.title(f"{__app_name__}")
        self.geometry("1200x780")
        self.minsize(1000, 640)
        self._set_icon()

        # -- document state (read by the dialogs) ------------------------
        self.path: Path | None = None
        self.password: str | None = None
        self.doc: pymupdf.Document | None = None
        self._busy = False
        self._doc_buttons: list[ctk.CTkButton] = []

        self._build_layout()
        self._bind_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        if initial_file:
            self.after(200, lambda: self.open_path(Path(initial_file)))

    def _set_icon(self) -> None:
        """Best-effort window icon (works from source and from a PyInstaller bundle)."""
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
        try:
            if sys.platform.startswith("win"):
                self.iconbitmap(str(base / "assets" / "icon.ico"))
            else:
                from PIL import ImageTk, Image
                self._icon = ImageTk.PhotoImage(Image.open(base / "assets" / "icon.png"))
                self.iconphoto(True, self._icon)
        except Exception as exc:  # cosmetic only
            log.debug("Icon not set: %s", exc)

    # ------------------------------------------------------------ properties
    @property
    def page_count(self) -> int:
        return self.doc.page_count if self.doc else 0

    @property
    def current_index(self) -> int:
        return self.preview.index

    # ---------------------------------------------------------------- layout
    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_main()
        self._build_statusbar()

    def _build_sidebar(self) -> None:
        side = ctk.CTkFrame(self, width=250, corner_radius=0)
        side.grid(row=0, column=0, rowspan=2, sticky="nsew")
        side.grid_propagate(False)
        side.grid_rowconfigure(2, weight=1)

        head = ctk.CTkFrame(side, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=18, pady=(20, 6))
        ctk.CTkLabel(head, text="PDF Editor Pro", font=ctk.CTkFont(size=21, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(
            head, text=f"v{__version__}  ·  Algoryx Internship", text_color=("gray40", "gray65"),
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w")

        ctk.CTkButton(
            side, text="Open PDF…", height=38, font=ctk.CTkFont(size=14, weight="bold"),
            command=self.open_dialog,
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=(10, 8))

        tools = ctk.CTkScrollableFrame(side, fg_color="transparent")
        tools.grid(row=2, column=0, sticky="nsew", padx=6)
        sections = [
            ("ORGANIZE", [
                ("Merge PDFs", self.merge, False),
                ("Split PDF", lambda: dialogs.SplitDialog(self), True),
                ("Rotate pages", lambda: dialogs.RotateDialog(self), True),
                ("Delete pages", lambda: dialogs.DeleteDialog(self), True),
                ("Reorder pages", lambda: dialogs.ReorderDialog(self), True),
            ]),
            ("CONVERT", [
                ("Extract text", lambda: dialogs.ExtractTextDialog(self), True),
                ("Images → PDF", lambda: dialogs.ImagesToPdfDialog(self), False),
                ("PDF → Images", lambda: dialogs.PdfToImagesDialog(self), True),
            ]),
            ("ENHANCE & SECURE", [
                ("Add watermark", lambda: dialogs.WatermarkDialog(self), True),
                ("Add page numbers", self.add_page_numbers, True),
                ("Protect with password", lambda: dialogs.ProtectDialog(self), True),
                ("Remove password", lambda: dialogs.UnlockDialog(self), True),
                ("Compress / repair", self.compress, True),
            ]),
        ]
        for title, items in sections:
            ctk.CTkLabel(
                tools, text=title, anchor="w", text_color=("gray40", "gray60"),
                font=ctk.CTkFont(size=11, weight="bold"),
            ).pack(fill="x", padx=12, pady=(14, 4))
            for text, command, needs_doc in items:
                btn = ctk.CTkButton(
                    tools, text=text, anchor="w", height=34, fg_color="transparent",
                    text_color=("gray10", "gray92"), hover_color=("gray82", "gray25"),
                    command=lambda c=command: self._guarded(c),
                )
                btn.pack(fill="x", padx=6, pady=1)
                if needs_doc:
                    self._doc_buttons.append(btn)

        foot = ctk.CTkFrame(side, fg_color="transparent")
        foot.grid(row=3, column=0, sticky="ew", padx=18, pady=14)
        ctk.CTkLabel(foot, text="Theme", text_color=("gray40", "gray65")).pack(side="left")
        ctk.CTkOptionMenu(
            foot, values=["System", "Light", "Dark"], width=110, command=self._set_theme
        ).pack(side="right")
        self._set_tools_enabled(False)

    def _build_main(self) -> None:
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=16, pady=(14, 6))
        main.grid_rowconfigure(1, weight=1)
        main.grid_columnconfigure(0, weight=1)

        self.info_title = ctk.CTkLabel(main, text="No document open", anchor="w",
                                       font=ctk.CTkFont(size=16, weight="bold"))
        self.info_title.grid(row=0, column=0, sticky="w")
        self.info_sub = ctk.CTkLabel(main, text="", anchor="e", text_color=("gray40", "gray65"))
        self.info_sub.grid(row=0, column=1, sticky="e")
        self.preview = PreviewPanel(main, on_error=lambda m: self.set_status(m))
        self.preview.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(8, 0))

    def _build_statusbar(self) -> None:
        bar = ctk.CTkFrame(self, height=30, corner_radius=0)
        bar.grid(row=1, column=1, sticky="ew")
        self.status = ctk.CTkLabel(bar, text="Ready", anchor="w")
        self.status.pack(side="left", padx=14, pady=4)
        self.progress = ctk.CTkProgressBar(bar, mode="indeterminate", width=160, height=8)

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-o>", lambda _e: self.open_dialog())
        canvas = self.preview.canvas
        canvas.bind("<Left>", lambda _e: self.preview.prev_page())
        canvas.bind("<Right>", lambda _e: self.preview.next_page())
        canvas.bind("<Prior>", lambda _e: self.preview.prev_page())
        canvas.bind("<Next>", lambda _e: self.preview.next_page())
        self.bind("<Control-plus>", lambda _e: self.preview.change_zoom(1.25))
        self.bind("<Control-equal>", lambda _e: self.preview.change_zoom(1.25))
        self.bind("<Control-minus>", lambda _e: self.preview.change_zoom(0.8))

    # ---------------------------------------------------------------- helpers
    def _set_theme(self, mode: str) -> None:
        ctk.set_appearance_mode(mode)
        self.after(50, self.preview.refresh_theme)

    def _set_tools_enabled(self, enabled: bool) -> None:
        for btn in self._doc_buttons:
            btn.configure(state="normal" if enabled else "disabled")

    def set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def _guarded(self, command: Callable[[], Any]) -> None:
        """Run a sidebar action and turn any failure into a friendly message."""
        if self._busy:
            self.set_status("Please wait - another task is still running.")
            return
        try:
            command()
        except PDFEditorError as exc:
            messagebox.showerror("Cannot continue", str(exc), parent=self)
        except Exception as exc:
            log.exception("Unexpected error")
            messagebox.showerror("Unexpected error", f"{type(exc).__name__}: {exc}", parent=self)

    # ------------------------------------------------------------ open / close
    def open_dialog(self) -> None:
        chosen = filedialog.askopenfilename(
            parent=self, title="Open PDF", filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        if chosen:
            self.open_path(Path(chosen))

    def open_path(self, path: Path) -> None:
        """Open *path*, prompting for a password if needed. Never raises."""
        password: str | None = None
        while True:
            try:
                doc = PDFService.open_document(path, password)
                break
            except PasswordRequiredError:
                password = PasswordPrompt.ask(self, path.name, wrong=password is not None)
                if password is None:
                    self.set_status("Open cancelled.")
                    return
            except PDFEditorError as exc:
                log.warning("Open failed: %s", exc)
                messagebox.showerror("Cannot open file", str(exc), parent=self)
                self.set_status(f"Could not open {path.name}")
                return

        if self.doc:
            self.doc.close()
        self.doc, self.path, self.password = doc, path, password
        self.preview.set_document(doc)
        self._set_tools_enabled(True)

        size_mb = path.stat().st_size / 1_048_576
        flags = []
        if doc.is_encrypted:
            flags.append("encrypted")
        if doc.is_repaired:
            flags.append("repaired in memory")
        self.title(f"{path.name} - {__app_name__}")
        self.info_title.configure(text=path.name)
        self.info_sub.configure(
            text=f"{doc.page_count} pages  ·  {size_mb:.2f} MB" + (f"  ·  {', '.join(flags)}" if flags else "")
        )
        self.set_status(f"Opened {path}")
        if doc.is_repaired:
            messagebox.showwarning(
                "Damaged file",
                "This PDF was damaged but could be repaired in memory.\n"
                "Use 'Compress / repair' to save a clean copy.",
                parent=self,
            )

    def on_close(self) -> None:
        if self.doc:
            self.doc.close()
        self.destroy()

    # ------------------------------------------------------------ background jobs
    def run_job(self, description: str, work: Callable[[], Any], on_success: Callable[[Any], None]) -> None:
        """Run *work* on a thread so the UI stays responsive; call *on_success* on the UI thread."""
        self._busy = True
        self.set_status(f"{description}…")
        self.progress.pack(side="right", padx=14)
        self.progress.start()
        outcome: dict[str, Any] = {}

        def target() -> None:
            try:
                outcome["result"] = work()
            except BaseException as exc:  # noqa: BLE001 - reported on the UI thread
                outcome["error"] = exc

        thread = threading.Thread(target=target, daemon=True)
        thread.start()

        def poll() -> None:
            if thread.is_alive():
                self.after(80, poll)
                return
            self.progress.stop()
            self.progress.pack_forget()
            self._busy = False
            error = outcome.get("error")
            if error is None:
                self.set_status(f"{description} - done.")
                on_success(outcome.get("result"))
            elif isinstance(error, PDFEditorError):
                log.warning("%s failed: %s", description, error)
                self.set_status(f"{description} - failed.")
                messagebox.showerror("Operation failed", str(error), parent=self)
            else:
                log.error("%s crashed", description, exc_info=error)
                self.set_status(f"{description} - failed.")
                messagebox.showerror("Unexpected error", f"{type(error).__name__}: {error}", parent=self)

        poll()

    # ---------------------------------------------------- shared dialog helpers
    def ask_output_pdf(self, parent, suffix: str, initial_dir: Path | None = None) -> str:
        stem = self.path.stem if self.path else "document"
        folder = initial_dir or (self.path.parent if self.path else Path.home())
        return filedialog.asksaveasfilename(
            parent=parent, title="Save PDF as", defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")], initialdir=str(folder), initialfile=f"{stem}_{suffix}.pdf",
        )

    def offer_open(self, result: Path) -> None:
        if messagebox.askyesno("Done", f"Saved:\n{result}\n\nOpen the new file now?", parent=self):
            self.open_path(Path(result))

    def offer_folder(self, folder: Path, message: str) -> None:
        if messagebox.askyesno("Done", f"{message}\n\n{folder}\n\nOpen the folder?", parent=self):
            self._reveal(folder)

    @staticmethod
    def _reveal(folder: Path) -> None:
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError as exc:
            log.warning("Could not open folder: %s", exc)

    # ------------------------------------------------------------ direct actions
    def merge(self) -> None:
        dialogs.MergeDialog(self)

    def add_page_numbers(self) -> None:
        out = self.ask_output_pdf(self, "numbered")
        if out:
            path, pw = self.path, self.password
            self.run_job("Adding page numbers", lambda: PDFService.add_page_numbers(path, out, 10, pw), self.offer_open)

    def compress(self) -> None:
        out = self.ask_output_pdf(self, "compressed")
        if not out:
            return
        path, pw = self.path, self.password

        def done(result: Path) -> None:
            before, after = path.stat().st_size, Path(result).stat().st_size
            saved = (1 - after / before) * 100 if before else 0
            messagebox.showinfo(
                "Compression result",
                f"Before: {before / 1024:.0f} KB\nAfter:  {after / 1024:.0f} KB\n"
                f"Saved:  {saved:.1f}%",
                parent=self,
            )
            self.offer_open(result)

        self.run_job("Compressing PDF", lambda: PDFService.compress(path, out, pw), done)
