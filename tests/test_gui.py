"""End-to-end GUI tests (need a display; run headless with:  xvfb-run -a pytest)."""

import os
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

tk = pytest.importorskip("tkinter")
ctk = pytest.importorskip("customtkinter")

if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no display available", allow_module_level=True)

from pdfeditor.core import PDFService  # noqa: E402
from pdfeditor.gui import PDFEditorApp, dialogs  # noqa: E402


@pytest.fixture
def app():
    try:
        application = PDFEditorApp()
    except tk.TclError:
        pytest.skip("cannot open a display")
    application.update()
    yield application
    application.on_close()


def pump(app, seconds=3.0):
    """Process Tk events until background jobs finish."""
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        if not app._busy:
            app.update()
            return
        time.sleep(0.02)
    raise AssertionError("job did not finish")


@pytest.fixture(autouse=True)
def quiet_messageboxes():
    with mock.patch("tkinter.messagebox.askyesno", return_value=False), \
         mock.patch("tkinter.messagebox.showinfo"), \
         mock.patch("tkinter.messagebox.showwarning"), \
         mock.patch("tkinter.messagebox.showerror") as err:
        yield err


def test_tools_disabled_until_document_open(app, sample_pdf):
    assert all(b.cget("state") == "disabled" for b in app._doc_buttons)
    app.open_path(sample_pdf)
    assert all(b.cget("state") == "normal" for b in app._doc_buttons)
    assert app.page_count == 5 and app.current_index == 0


def test_page_navigation(app, sample_pdf):
    app.open_path(sample_pdf)
    app.preview.next_page(); app.preview.next_page()
    assert app.current_index == 2
    app.preview.go_to(99)  # out of range is ignored
    assert app.current_index == 2


def test_corrupted_file_shows_error_and_app_survives(app, tmp_path, quiet_messageboxes):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"garbage" * 100)
    app.open_path(bad)
    quiet_messageboxes.assert_called_once()
    assert app.doc is None


def test_encrypted_file_prompts_for_password(app, sample_pdf, tmp_path):
    enc = PDFService.protect(sample_pdf, tmp_path / "enc.pdf", "s3cret")
    with mock.patch("pdfeditor.gui.app.PasswordPrompt.ask", side_effect=["wrong", "s3cret"]):
        app.open_path(enc)
    assert app.doc is not None and app.password == "s3cret"


def test_rotate_dialog_end_to_end(app, sample_pdf, tmp_path):
    app.open_path(sample_pdf)
    out = tmp_path / "rotated_out.pdf"
    dlg = dialogs.RotateDialog(app)
    dlg.pages.delete(0, "end"); dlg.pages.insert(0, "1-2")
    with mock.patch.object(app, "ask_output_pdf", return_value=str(out)):
        dlg._submit()
    pump(app)
    with PDFService.open_document(out) as d:
        assert [p.rotation for p in d][:3] == [90, 90, 0]


def test_reorder_dialog_end_to_end(app, sample_pdf, tmp_path):
    app.open_path(sample_pdf)
    out = tmp_path / "reordered.pdf"
    dlg = dialogs.ReorderDialog(app)
    dlg._reverse()
    with mock.patch.object(app, "ask_output_pdf", return_value=str(out)):
        dlg._submit()
    pump(app)
    with PDFService.open_document(out) as d:
        assert "page 5" in d[0].get_text()


def test_invalid_input_reports_error_without_crash(app, sample_pdf, quiet_messageboxes):
    app.open_path(sample_pdf)
    dlg = dialogs.DeleteDialog(app)
    dlg.pages.delete(0, "end"); dlg.pages.insert(0, "99")
    with mock.patch.object(app, "ask_output_pdf", return_value="/tmp/never.pdf"):
        dlg._submit()
    quiet_messageboxes.assert_called_once()
    assert dlg.winfo_exists()  # dialog stays open so the user can fix the input


def test_extract_text_dialog(app, sample_pdf):
    app.open_path(sample_pdf)
    dlg = dialogs.ExtractTextDialog(app)
    dlg.pages.insert(0, "2")
    dlg._extract()
    pump(app)
    assert "Doc page 2" in dlg.text.get("1.0", "end")
