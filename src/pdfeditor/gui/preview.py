"""Scrollable page preview with navigation and zoom controls."""

from __future__ import annotations

import tkinter as tk
from typing import Callable

import customtkinter as ctk
import pymupdf
from PIL import ImageTk

from ..core import PDFService
from ..exceptions import PDFEditorError
from ..logger import get_logger

log = get_logger(__name__)

CANVAS_BG = ("#dfe3ea", "#1b1c1f")
SCREEN_SCALE = 96 / 72  # zoom 1.0 == 100 % at 96 dpi
MIN_ZOOM, MAX_ZOOM = 0.25, 4.0


class PreviewPanel(ctk.CTkFrame):
    """Shows one page at a time, with prev/next, page jump, zoom and fit-to-width."""

    def __init__(self, master, on_error: Callable[[str], None] | None = None) -> None:
        super().__init__(master, fg_color="transparent")
        self.doc: pymupdf.Document | None = None
        self.index = 0
        self.zoom = 1.0
        self.fit_mode = True
        self._photo: ImageTk.PhotoImage | None = None
        self._on_error = on_error or (lambda msg: None)

        # canvas + scrollbars
        area = ctk.CTkFrame(self, fg_color="transparent")
        area.pack(fill="both", expand=True)
        area.grid_rowconfigure(0, weight=1)
        area.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(area, highlightthickness=0, bg=self._bg())
        self.vbar = ctk.CTkScrollbar(area, command=self.canvas.yview)
        self.hbar = ctk.CTkScrollbar(area, orientation="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vbar.set, xscrollcommand=self.hbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar.grid(row=1, column=0, sticky="ew")

        # controls
        bar = ctk.CTkFrame(self, corner_radius=10)
        bar.pack(fill="x", pady=(8, 0))
        self.prev_btn = ctk.CTkButton(bar, text="◀", width=36, command=self.prev_page)
        self.prev_btn.pack(side="left", padx=(10, 4), pady=8)
        self.page_entry = ctk.CTkEntry(bar, width=52, justify="center")
        self.page_entry.pack(side="left")
        self.page_entry.bind("<Return>", self._jump)
        self.total_lbl = ctk.CTkLabel(bar, text="/ 0", width=44)
        self.total_lbl.pack(side="left")
        self.next_btn = ctk.CTkButton(bar, text="▶", width=36, command=self.next_page)
        self.next_btn.pack(side="left", padx=4)

        ctk.CTkButton(bar, text="Fit width", width=76, command=self.fit_width).pack(side="right", padx=(4, 10))
        ctk.CTkButton(bar, text="+", width=34, command=lambda: self.change_zoom(1.25)).pack(side="right", padx=2)
        self.zoom_lbl = ctk.CTkLabel(bar, text="100%", width=52)
        self.zoom_lbl.pack(side="right")
        ctk.CTkButton(bar, text="−", width=34, command=lambda: self.change_zoom(0.8)).pack(side="right", padx=2)

        self._bind_events()
        self._show_placeholder()

    # -- theming -------------------------------------------------------
    @staticmethod
    def _bg() -> str:
        return CANVAS_BG[1] if ctk.get_appearance_mode() == "Dark" else CANVAS_BG[0]

    def refresh_theme(self) -> None:
        self.canvas.configure(bg=self._bg())
        if self.doc:
            self.render()
        else:
            self._show_placeholder()

    # -- events --------------------------------------------------------
    def _bind_events(self) -> None:
        self.canvas.bind("<Configure>", lambda _e: self._on_resize())
        self.canvas.bind("<MouseWheel>", self._on_wheel)  # Windows / macOS
        self.canvas.bind("<Button-4>", lambda e: self._on_wheel(e, 1))  # Linux
        self.canvas.bind("<Button-5>", lambda e: self._on_wheel(e, -1))
        self.canvas.bind("<Enter>", lambda _e: self.canvas.focus_set())

    def _on_resize(self) -> None:
        if self.doc and self.fit_mode:
            self._debounced_render()
        elif not self.doc:
            self._show_placeholder()

    def _debounced_render(self) -> None:
        if getattr(self, "_after_id", None):
            self.after_cancel(self._after_id)
        self._after_id = self.after(120, self.render)

    def _on_wheel(self, event, direction: int | None = None) -> str:
        if direction is None:
            direction = 1 if event.delta > 0 else -1
        if event.state & 0x4:  # Ctrl held -> zoom
            self.change_zoom(1.1 if direction > 0 else 1 / 1.1)
        elif event.state & 0x1:  # Shift -> horizontal
            self.canvas.xview_scroll(-direction * 3, "units")
        else:
            self.canvas.yview_scroll(-direction * 3, "units")
        return "break"

    # -- public API ----------------------------------------------------
    def set_document(self, doc: pymupdf.Document | None) -> None:
        self.doc = doc
        self.index = 0
        self.fit_mode = True
        if doc is None:
            self.total_lbl.configure(text="/ 0")
            self._show_placeholder()
            return
        self.total_lbl.configure(text=f"/ {doc.page_count}")
        self.render()

    def go_to(self, index: int) -> None:
        if self.doc and 0 <= index < self.doc.page_count:
            self.index = index
            self.render()
            self.canvas.yview_moveto(0)

    def prev_page(self) -> None:
        self.go_to(self.index - 1)

    def next_page(self) -> None:
        self.go_to(self.index + 1)

    def change_zoom(self, factor: float) -> None:
        if not self.doc:
            return
        self.fit_mode = False
        self.zoom = min(MAX_ZOOM, max(MIN_ZOOM, self.zoom * factor))
        self.render()

    def fit_width(self) -> None:
        self.fit_mode = True
        self.render()

    # -- rendering -----------------------------------------------------
    def _jump(self, _event=None) -> None:
        try:
            self.go_to(int(self.page_entry.get()) - 1)
        except ValueError:
            pass
        self._sync_controls()

    def _sync_controls(self) -> None:
        self.page_entry.delete(0, tk.END)
        self.page_entry.insert(0, str(self.index + 1) if self.doc else "")
        self.zoom_lbl.configure(text=f"{self.zoom:.0%}")
        has = self.doc is not None
        self.prev_btn.configure(state="normal" if has and self.index > 0 else "disabled")
        self.next_btn.configure(
            state="normal" if has and self.index < self.doc.page_count - 1 else "disabled"
        )

    def render(self) -> None:
        if not self.doc:
            return
        try:
            page = self.doc[self.index]
            if self.fit_mode:
                avail = max(self.canvas.winfo_width() - 64, 200)
                self.zoom = min(MAX_ZOOM, max(MIN_ZOOM, avail / (page.rect.width * SCREEN_SCALE)))
            image = PDFService.render_page(self.doc, self.index, self.zoom * SCREEN_SCALE)
        except PDFEditorError as exc:
            log.warning("Preview failed: %s", exc)
            self._on_error(str(exc))
            self._show_placeholder("This page could not be displayed.")
            return
        self._photo = ImageTk.PhotoImage(image)
        self.canvas.delete("all")
        pad = 24
        cw = max(self.canvas.winfo_width(), image.width + 2 * pad)
        x = (cw - image.width) // 2
        shadow = "#0d0e10" if ctk.get_appearance_mode() == "Dark" else "#c2c8d2"
        self.canvas.create_rectangle(x + 3, pad + 3, x + image.width + 3, pad + image.height + 3,
                                     fill=shadow, outline="")  # drop shadow
        self.canvas.create_image(x, pad, anchor="nw", image=self._photo)
        self.canvas.configure(scrollregion=(0, 0, cw, image.height + 2 * pad))
        if image.width + 2 * pad > self.canvas.winfo_width() + 2:
            self.hbar.grid()
        else:
            self.hbar.grid_remove()
        self._sync_controls()

    def _show_placeholder(self, text: str = "Open a PDF to get started\n(Ctrl+O)") -> None:
        self.canvas.delete("all")
        w, h = max(self.canvas.winfo_width(), 300), max(self.canvas.winfo_height(), 200)
        colour = "#8b93a1" if ctk.get_appearance_mode() == "Dark" else "#6b7280"
        self.canvas.create_text(w // 2, h // 2, text=text, fill=colour, font=("Segoe UI", 16), justify="center")
        self.canvas.configure(scrollregion=(0, 0, w, h))
        self._sync_controls()
