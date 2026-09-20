"""Reusable GUI building blocks: base dialog, password prompt, file-list editor."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING, Callable, Sequence

import customtkinter as ctk

from ..exceptions import PDFEditorError
from ..logger import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from .app import PDFEditorApp

log = get_logger(__name__)

# (light, dark) colour pairs used for plain-tk widgets that CustomTkinter does not theme.
LIST_BG = ("#ffffff", "#2b2b2b")
LIST_FG = ("#1a1a1a", "#e6e6e6")
LIST_SEL = ("#3b8ed0", "#1f6aa5")


def themed(pair: tuple[str, str]) -> str:
    """Pick the colour matching the current appearance mode."""
    return pair[1] if ctk.get_appearance_mode() == "Dark" else pair[0]


def make_listbox(master, height: int = 8, selectmode: str = tk.SINGLE) -> tk.Listbox:
    return tk.Listbox(
        master,
        height=height,
        selectmode=selectmode,
        activestyle="none",
        exportselection=False,
        bg=themed(LIST_BG),
        fg=themed(LIST_FG),
        selectbackground=themed(LIST_SEL),
        selectforeground="#ffffff",
        highlightthickness=1,
        highlightbackground="#8a8a8a",
        relief="flat",
        borderwidth=0,
        font=("Segoe UI", 11),
    )


class ToolDialog(ctk.CTkToplevel):
    """Modal dialog with a body frame and Cancel / Submit footer.

    Subclasses build widgets into ``self.body`` and implement :meth:`on_submit`.
    Errors deriving from :class:`PDFEditorError` are shown to the user instead of crashing.
    """

    def __init__(
        self,
        app: "PDFEditorApp",
        title: str,
        submit_text: str = "Apply",
        size: tuple[int, int] = (480, 420),
    ) -> None:
        super().__init__(app)
        self.app = app
        self.title(title)
        self.resizable(False, False)
        self.transient(app)
        self._center(*size)

        ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=18, weight="bold")).pack(
            anchor="w", padx=24, pady=(18, 4)
        )
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=24, pady=(4, 8))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=24, pady=(0, 18))
        ctk.CTkButton(
            footer, text="Cancel", width=90, fg_color="transparent", border_width=1,
            text_color=("gray20", "gray90"), command=self.destroy,
        ).pack(side="right", padx=(8, 0))
        self.submit_btn = ctk.CTkButton(footer, text=submit_text, width=120, command=self._submit)
        self.submit_btn.pack(side="right")

        self.bind("<Escape>", lambda _e: self.destroy())
        self.after(60, self._make_modal)

    # -- window helpers ---------------------------------------------------
    def _center(self, w: int, h: int) -> None:
        self.update_idletasks()
        x = self.app.winfo_rootx() + (self.app.winfo_width() - w) // 2
        y = self.app.winfo_rooty() + (self.app.winfo_height() - h) // 3
        self.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")

    def _make_modal(self) -> None:
        try:
            self.grab_set()
            self.focus_force()
        except tk.TclError:  # window closed before it became visible
            pass

    # -- form helpers -----------------------------------------------------
    def add_label(self, text: str, muted: bool = False, pady: tuple[int, int] = (8, 2)) -> ctk.CTkLabel:
        lbl = ctk.CTkLabel(
            self.body, text=text, anchor="w", justify="left", wraplength=420,
            text_color=("gray40", "gray65") if muted else None,
            font=ctk.CTkFont(size=12 if muted else 13),
        )
        lbl.pack(fill="x", pady=pady)
        return lbl

    def add_entry(self, label: str, default: str = "", placeholder: str = "", show: str | None = None) -> ctk.CTkEntry:
        self.add_label(label)
        entry = ctk.CTkEntry(self.body, placeholder_text=placeholder, show=show or "")
        entry.pack(fill="x")
        if default:
            entry.insert(0, default)
        return entry

    def add_slider(
        self, label: str, low: float, high: float, default: float, fmt: str = "{:.0f}", steps: int | None = None
    ) -> ctk.CTkSlider:
        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.pack(fill="x", pady=(8, 0))
        ctk.CTkLabel(row, text=label, anchor="w").pack(side="left")
        value_lbl = ctk.CTkLabel(row, text=fmt.format(default), anchor="e")
        value_lbl.pack(side="right")
        slider = ctk.CTkSlider(
            self.body, from_=low, to=high, number_of_steps=steps,
            command=lambda v: value_lbl.configure(text=fmt.format(v)),
        )
        slider.set(default)
        slider.pack(fill="x", pady=(2, 0))
        return slider

    # -- submit flow ------------------------------------------------------
    def _submit(self) -> None:
        try:
            self.on_submit()
        except PDFEditorError as exc:
            messagebox.showerror("Cannot continue", str(exc), parent=self)
        except Exception as exc:  # last-resort guard: never crash the GUI
            log.exception("Unexpected error in dialog")
            messagebox.showerror("Unexpected error", f"{type(exc).__name__}: {exc}", parent=self)

    def on_submit(self) -> None:  # pragma: no cover - abstract
        raise NotImplementedError


class PasswordPrompt(ctk.CTkToplevel):
    """Small modal window asking for a document password."""

    def __init__(self, parent, filename: str, wrong: bool = False) -> None:
        super().__init__(parent)
        self.password: str | None = None
        self.title("Password required")
        self.resizable(False, False)
        self.transient(parent)
        parent.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - 380) // 2
        y = parent.winfo_rooty() + 140
        self.geometry(f"380x{200 if wrong else 180}+{max(x, 0)}+{max(y, 0)}")

        ctk.CTkLabel(
            self, text=f"'{filename}' is protected.\nEnter the password to open it.",
            justify="left", anchor="w",
        ).pack(fill="x", padx=22, pady=(18, 6))
        if wrong:
            ctk.CTkLabel(self, text="Incorrect password, try again.", text_color="#d9534f").pack(
                anchor="w", padx=22
            )
        self.entry = ctk.CTkEntry(self, show="•", placeholder_text="Password")
        self.entry.pack(fill="x", padx=22, pady=8)
        self.entry.bind("<Return>", lambda _e: self._ok())
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=22)
        ctk.CTkButton(row, text="Open", width=90, command=self._ok).pack(side="right")
        ctk.CTkButton(
            row, text="Cancel", width=90, fg_color="transparent", border_width=1,
            text_color=("gray20", "gray90"), command=self.destroy,
        ).pack(side="right", padx=8)
        self.after(60, self._modal)

    def _modal(self) -> None:
        try:
            self.grab_set()
            self.entry.focus_force()
        except tk.TclError:
            pass

    def _ok(self) -> None:
        self.password = self.entry.get()
        self.destroy()

    @classmethod
    def ask(cls, parent, filename: str, wrong: bool = False) -> str | None:
        dlg = cls(parent, filename, wrong)
        parent.wait_window(dlg)
        return dlg.password or None


class FileListEditor(ctk.CTkFrame):
    """Ordered list of files with Add / Remove / Move up / Move down / Clear buttons."""

    def __init__(
        self,
        master,
        filetypes: Sequence[tuple[str, str]],
        dialog_title: str = "Select files",
        validator: Callable[[Path], str | None] | None = None,
        height: int = 8,
    ) -> None:
        """``validator(path)`` returns a display label, or ``None`` to reject the file."""
        super().__init__(master, fg_color="transparent")
        self.filetypes = list(filetypes)
        self.dialog_title = dialog_title
        self.validator = validator
        self.paths: list[Path] = []
        self.labels: list[str] = []

        self.listbox = make_listbox(self, height=height)
        self.listbox.pack(side="left", fill="both", expand=True)
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(side="left", fill="y", padx=(10, 0))
        for text, cmd in (
            ("Add…", self.add_dialog), ("Remove", self.remove_selected),
            ("Move up", lambda: self._move(-1)), ("Move down", lambda: self._move(1)),
            ("Clear", self.clear),
        ):
            ctk.CTkButton(buttons, text=text, width=96, height=28, command=cmd).pack(pady=3)

    # -- public --------------------------------------------------------
    def add_dialog(self) -> None:
        chosen = filedialog.askopenfilenames(
            parent=self.winfo_toplevel(), title=self.dialog_title, filetypes=self.filetypes
        )
        self.add_paths(Path(p) for p in chosen)

    def add_paths(self, paths) -> None:
        for p in paths:
            label = self.validator(p) if self.validator else p.name
            if label is None:
                continue  # validator already told the user why
            self.paths.append(p)
            self.labels.append(label)
        self._refresh()

    def clear(self) -> None:
        self.paths.clear()
        self.labels.clear()
        self._refresh()

    def remove_selected(self) -> None:
        sel = self.listbox.curselection()
        if sel:
            i = sel[0]
            del self.paths[i], self.labels[i]
            self._refresh(min(i, len(self.paths) - 1))

    # -- internals -----------------------------------------------------
    def _move(self, delta: int) -> None:
        sel = self.listbox.curselection()
        if not sel:
            return
        i, j = sel[0], sel[0] + delta
        if 0 <= j < len(self.paths):
            self.paths[i], self.paths[j] = self.paths[j], self.paths[i]
            self.labels[i], self.labels[j] = self.labels[j], self.labels[i]
            self._refresh(j)

    def _refresh(self, select: int | None = None) -> None:
        self.listbox.delete(0, tk.END)
        for n, label in enumerate(self.labels, start=1):
            self.listbox.insert(tk.END, f" {n}.  {label}")
        if select is not None and 0 <= select < len(self.paths):
            self.listbox.selection_set(select)
            self.listbox.see(select)
