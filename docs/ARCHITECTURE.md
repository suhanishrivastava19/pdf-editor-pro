# Architecture

## Goals
1. **Separation of concerns** – PDF logic knows nothing about the GUI.
2. **Never crash on bad input** – every failure becomes a typed, user-friendly error.
3. **Never destroy user data** – originals are never overwritten.
4. **Responsive UI** – long operations run on a worker thread.

## Layers

```
┌────────────────────────────────────────────────────────────┐
│ GUI  (customtkinter)                                       │
│  app.py  ── main window, run_job(), open/close, status     │
│  dialogs.py ─ one ToolDialog subclass per feature          │
│  preview.py ─ PreviewPanel (canvas, zoom, navigation)      │
│  widgets.py ─ ToolDialog base, PasswordPrompt, FileList    │
└───────────────▲────────────────────────────────────────────┘
                │ calls (only public API)
┌───────────────┴────────────────────────────────────────────┐
│ Core  (PyMuPDF + Pillow)                                   │
│  service.PDFService  ── static/class methods per feature   │
│  utils               ── parse_page_ranges(), ensure_output │
└───────────────▲────────────────────────────────────────────┘
                │ raises
┌───────────────┴────────────────────────────────────────────┐
│ exceptions.py                                              │
│  PDFEditorError                                            │
│   ├─ FileAccessError        ├─ PasswordRequiredError       │
│   ├─ CorruptedPDFError      ├─ InvalidPageRangeError       │
│   └─ OperationError                                        │
└────────────────────────────────────────────────────────────┘
```

## Key design decisions

### Object-oriented structure
* `PDFService` – facade with one method per feature; shared helpers (`_save`, `_copy_pages`,
  `_check_distinct`) remove duplication.
* `ToolDialog` – template-method base class: subclasses build widgets and implement
  `on_submit()`; the base class supplies layout, modal handling and central error handling.
* `PreviewPanel`, `FileListEditor`, `PasswordPrompt` – self-contained reusable widgets.
* `PDFEditorApp` – composes everything and owns application state (open document, password).

### Error handling
`PDFService.open_document()` is the single entry point for reading files. It converts every
low-level failure into one of the custom exceptions:

| Situation | Exception | What the user sees |
|---|---|---|
| Missing file | `FileAccessError` | "File not found" |
| Empty / not a PDF / unrecoverable | `CorruptedPDFError` | "not a valid PDF or too damaged" |
| Encrypted, no/wrong password | `PasswordRequiredError` | Password prompt (retry loop) |
| Partially damaged but repairable | *(opens, `was_repaired=True`)* | Warning + "Compress / repair" hint |
| Bad page range / bad input | `InvalidPageRangeError` | Message; dialog stays open |
| Anything else | `OperationError` | Message; details in the log |

The GUI catches `PDFEditorError` at three choke points (`ToolDialog._submit`, `PDFEditorApp._guarded`,
`run_job`) and has a last-resort `Exception` handler that logs a full traceback.

### Page-range mini-language
`parse_page_ranges("1-3,5,8-", total)` → 0-based indexes. Used by rotate, delete, extract,
watermark, split and export. Dialogs call it **before** closing so mistakes are fixed in place.

### Threading model
`PDFEditorApp.run_job(description, work, on_success)`:
1. disables re-entry, shows an indeterminate progress bar,
2. runs `work()` on a daemon thread (each operation opens its *own* document handle),
3. polls with `after(80, …)` and invokes `on_success` / shows the error **on the UI thread**.

Tkinter is never touched from the worker thread.

### Rotated pages
Watermarks and page numbers are computed in the page's *stored* coordinate space using
`page.derotation_matrix`, and the morph angle is compensated by `page.rotation`, so text is
centred and keeps the requested visual angle on 0/90/180/270° pages (covered by unit tests).

### Logging
`logger.setup_logging()` installs a console handler and a rotating file handler
(`~/.pdf_editor_pro/logs/`). Modules use `get_logger(__name__)`.

## Testing strategy
| Layer | Approach |
|---|---|
| `core` | Pure unit tests with generated PDFs (`tests/test_service.py`) |
| GUI | Real Tk windows under Xvfb; native dialogs mocked (`tests/test_gui.py`) |
| Packaging | Frozen binary smoke-tested at build time |

## Extending
Add a feature in three steps:
1. Add a method to `PDFService` (+ unit test).
2. Add a `ToolDialog` subclass in `gui/dialogs.py`.
3. Register a button in the `sections` list in `PDFEditorApp._build_sidebar`.
