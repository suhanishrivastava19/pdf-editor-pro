import pymupdf
import pytest

from pdfeditor.core import PDFService, parse_page_ranges
from pdfeditor.exceptions import (
    CorruptedPDFError,
    FileAccessError,
    InvalidPageRangeError,
    OperationError,
    PasswordRequiredError,
)


def page_count(path, password=None):
    with PDFService.open_document(path, password) as d:
        return d.page_count


def page_texts(path):
    with PDFService.open_document(path) as d:
        return [p.get_text().strip() for p in d]


# ---------------------------------------------------------- page range parser
@pytest.mark.parametrize(
    "spec,expected",
    [("1-3,5", [0, 1, 2, 4]), ("8-", [7, 8, 9]), ("all", list(range(10))),
     ("", list(range(10))), (" 2 , 2 ,4-5", [1, 3, 4]), ("-3", [0, 1, 2])],
)
def test_parse_ranges(spec, expected):
    assert parse_page_ranges(spec, 10) == expected


@pytest.mark.parametrize("spec", ["0", "11", "abc", "5-3", "1-99", "1,,x"])
def test_parse_ranges_invalid(spec):
    with pytest.raises(InvalidPageRangeError):
        parse_page_ranges(spec, 10)


# ------------------------------------------------------------------ open/info
def test_info(sample_pdf):
    info = PDFService.get_info(sample_pdf)
    assert info.page_count == 5 and not info.encrypted


def test_open_missing_file(tmp_path):
    with pytest.raises(FileAccessError):
        PDFService.open_document(tmp_path / "nope.pdf")


def test_open_empty_file(tmp_path):
    p = tmp_path / "empty.pdf"
    p.write_bytes(b"")
    with pytest.raises(CorruptedPDFError):
        PDFService.open_document(p)


def test_open_garbage_file(tmp_path):
    p = tmp_path / "junk.pdf"
    p.write_bytes(b"this is definitely not a pdf" * 50)
    with pytest.raises(CorruptedPDFError):
        PDFService.open_document(p)


def test_truncated_pdf_is_handled(sample_pdf, tmp_path):
    data = sample_pdf.read_bytes()
    bad = tmp_path / "truncated.pdf"
    bad.write_bytes(data[: len(data) // 2])
    try:  # either repaired or reported cleanly - never a raw crash
        PDFService.open_document(bad).close()
    except CorruptedPDFError:
        pass


# ---------------------------------------------------------------------- merge
def test_merge(make_pdf, tmp_path):
    a, b = make_pdf("a.pdf", 2, "A"), make_pdf("b.pdf", 3, "B")
    out = PDFService.merge([a, b], tmp_path / "out" / "m.pdf")
    assert page_count(out) == 5
    assert "A page 1" in page_texts(out)[0] and "B page 1" in page_texts(out)[2]


def test_merge_needs_two(sample_pdf, tmp_path):
    with pytest.raises(OperationError):
        PDFService.merge([sample_pdf], tmp_path / "m.pdf")


def test_merge_never_overwrites_input(make_pdf):
    a, b = make_pdf("a.pdf", 1), make_pdf("b.pdf", 1)
    with pytest.raises(OperationError):
        PDFService.merge([a, b], a)


# ---------------------------------------------------------------------- split
def test_split_each(sample_pdf, tmp_path):
    files = PDFService.split(sample_pdf, tmp_path / "s", "each")
    assert len(files) == 5 and all(page_count(f) == 1 for f in files)


def test_split_every_n(sample_pdf, tmp_path):
    files = PDFService.split(sample_pdf, tmp_path / "s", "every_n", 2)
    assert [page_count(f) for f in files] == [2, 2, 1]


def test_split_ranges(sample_pdf, tmp_path):
    files = PDFService.split(sample_pdf, tmp_path / "s", "ranges", "1-2;4,5")
    assert [page_count(f) for f in files] == [2, 2]
    assert "Doc page 4" in page_texts(files[1])[0]


def test_split_bad_input(sample_pdf, tmp_path):
    with pytest.raises(InvalidPageRangeError):
        PDFService.split(sample_pdf, tmp_path / "s", "every_n", 0)
    with pytest.raises(InvalidPageRangeError):
        PDFService.split(sample_pdf, tmp_path / "s", "ranges", "1-9")


# --------------------------------------------------------------------- rotate
def test_rotate_selected_pages(sample_pdf, tmp_path):
    out = PDFService.rotate(sample_pdf, tmp_path / "r.pdf", 90, "1,3")
    with PDFService.open_document(out) as d:
        assert [p.rotation for p in d] == [90, 0, 90, 0, 0]


def test_rotate_accumulates_and_wraps(sample_pdf, tmp_path):
    once = PDFService.rotate(sample_pdf, tmp_path / "r1.pdf", 270)
    twice = PDFService.rotate(once, tmp_path / "r2.pdf", 180)
    with PDFService.open_document(twice) as d:
        assert d[0].rotation == 90


def test_rotate_invalid_angle(sample_pdf, tmp_path):
    with pytest.raises(OperationError):
        PDFService.rotate(sample_pdf, tmp_path / "r.pdf", 45)


# --------------------------------------------------------------------- delete
def test_delete(sample_pdf, tmp_path):
    out = PDFService.delete_pages(sample_pdf, tmp_path / "d.pdf", "2-3")
    assert page_count(out) == 3
    assert "Doc page 4" in page_texts(out)[1]


def test_delete_all_rejected(sample_pdf, tmp_path):
    with pytest.raises(OperationError):
        PDFService.delete_pages(sample_pdf, tmp_path / "d.pdf", "all")


# -------------------------------------------------------------------- reorder
def test_reorder(sample_pdf, tmp_path):
    out = PDFService.reorder_pages(sample_pdf, tmp_path / "o.pdf", [5, 4, 3, 2, 1])
    assert "Doc page 5" in page_texts(out)[0]


def test_reorder_must_be_permutation(sample_pdf, tmp_path):
    with pytest.raises(InvalidPageRangeError):
        PDFService.reorder_pages(sample_pdf, tmp_path / "o.pdf", [1, 1, 2, 3, 4])


# -------------------------------------------------------------- extract text
def test_extract_text(sample_pdf, tmp_path):
    txt = tmp_path / "t.txt"
    text = PDFService.extract_text(sample_pdf, txt, pages="2-3")
    assert "Doc page 2" in text and "Doc page 3" in text and "Doc page 1" not in text
    assert txt.read_text(encoding="utf-8") == text


# -------------------------------------------------------------- image <-> pdf
@pytest.mark.parametrize("size", ["a4", "original"])
def test_images_to_pdf(sample_images, tmp_path, size):
    out = PDFService.images_to_pdf(sample_images, tmp_path / "i.pdf", size)
    with PDFService.open_document(out) as d:
        assert d.page_count == 2
        assert len(d[0].get_images()) == 1


def test_images_to_pdf_bad_image(tmp_path):
    bad = tmp_path / "x.png"
    bad.write_bytes(b"not an image")
    with pytest.raises(OperationError):
        PDFService.images_to_pdf([bad], tmp_path / "i.pdf")


@pytest.mark.parametrize("fmt", ["png", "jpg"])
def test_pdf_to_images(sample_pdf, tmp_path, fmt):
    files = PDFService.pdf_to_images(sample_pdf, tmp_path / "img", fmt, 72, "1-2")
    assert len(files) == 2 and all(f.exists() and f.stat().st_size > 0 for f in files)


def test_pdf_to_images_bad_dpi(sample_pdf, tmp_path):
    with pytest.raises(OperationError):
        PDFService.pdf_to_images(sample_pdf, tmp_path / "img", "png", 5)


# ------------------------------------------------------------------ watermark
def test_watermark_adds_text_and_angle(sample_pdf, tmp_path):
    out = PDFService.add_text_watermark(sample_pdf, tmp_path / "w.pdf", "CONFIDENTIAL", angle=45)
    with PDFService.open_document(out) as d:
        for page in d:
            assert "CONFIDENTIAL" in page.get_text()
        line = next(
            l for b in d[0].get_text("dict")["blocks"] if "lines" in b
            for l in b["lines"] if "CONFIDENTIAL" in "".join(s["text"] for s in l["spans"])
        )
        dx, dy = line["dir"]
        assert dx > 0.5 and dy < -0.5  # rises to the right (45 deg, counter-clockwise)


def test_watermark_on_rotated_page_is_centred_and_horizontal(sample_pdf, tmp_path):
    rotated = PDFService.rotate(sample_pdf, tmp_path / "r.pdf", 90, "1")
    out = PDFService.add_text_watermark(rotated, tmp_path / "w.pdf", "DRAFT", angle=0)
    with PDFService.open_document(out) as d:
        page = d[0]
        hits = page.search_for("DRAFT")  # stored (un-rotated) coordinates
        assert hits
        c = hits[0].tl + (hits[0].br - hits[0].tl) * 0.5
        visual_c = c * page.rotation_matrix
        assert abs(visual_c.x - page.rect.width / 2) < 20
        assert abs(visual_c.y - page.rect.height / 2) < 20
        line = next(
            l for b in page.get_text("dict")["blocks"] if "lines" in b
            for l in b["lines"] if "DRAFT" in "".join(s["text"] for s in l["spans"])
        )
        vx, vy = pymupdf.Point(*line["dir"]) * pymupdf.Matrix(page.rotation_matrix.a, page.rotation_matrix.b,
                                                            page.rotation_matrix.c, page.rotation_matrix.d, 0, 0)
        assert vx > 0.99 and abs(vy) < 0.05  # reads left-to-right, upright on screen


def test_watermark_validation(sample_pdf, tmp_path):
    with pytest.raises(OperationError):
        PDFService.add_text_watermark(sample_pdf, tmp_path / "w.pdf", "  ")
    with pytest.raises(OperationError):
        PDFService.add_text_watermark(sample_pdf, tmp_path / "w.pdf", "x", opacity=5)


def test_page_numbers(sample_pdf, tmp_path):
    out = PDFService.add_page_numbers(sample_pdf, tmp_path / "n.pdf")
    assert "Page 3 of 5" in page_texts(out)[2]


# ------------------------------------------------------------------- security
def test_protect_and_unprotect(sample_pdf, tmp_path):
    enc = PDFService.protect(sample_pdf, tmp_path / "e.pdf", "secret")
    with pytest.raises(PasswordRequiredError):
        PDFService.open_document(enc)
    with pytest.raises(PasswordRequiredError):
        PDFService.open_document(enc, "wrong")
    assert page_count(enc, "secret") == 5
    plain = PDFService.unprotect(enc, tmp_path / "p.pdf", "secret")
    assert page_count(plain) == 5  # opens without a password


def test_protect_requires_password(sample_pdf, tmp_path):
    with pytest.raises(OperationError):
        PDFService.protect(sample_pdf, tmp_path / "e.pdf", "")


def test_operation_on_encrypted_input_with_password(sample_pdf, tmp_path):
    enc = PDFService.protect(sample_pdf, tmp_path / "e.pdf", "pw")
    out = PDFService.rotate(enc, tmp_path / "r.pdf", 90, password="pw")
    assert page_count(out) == 5


# ------------------------------------------------------------ compress/render
def test_compress(sample_pdf, tmp_path):
    assert page_count(PDFService.compress(sample_pdf, tmp_path / "c.pdf")) == 5


def test_render_page(sample_pdf):
    with PDFService.open_document(sample_pdf) as d:
        img = PDFService.render_page(d, 0, 1.0)
        assert img.size == (595, 842)
        with pytest.raises(InvalidPageRangeError):
            PDFService.render_page(d, 99)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_watermark_angle_is_visually_constant(sample_pdf, tmp_path, rotation):
    src = PDFService.rotate(sample_pdf, tmp_path / "r.pdf", rotation, "1") if rotation else sample_pdf
    out = PDFService.add_text_watermark(src, tmp_path / "w.pdf", "HELLO", angle=45)
    with PDFService.open_document(out) as d:
        page = d[0]
        line = next(
            l for b in page.get_text("dict")["blocks"] if "lines" in b
            for l in b["lines"] if "HELLO" in "".join(s["text"] for s in l["spans"])
        )
        m = page.rotation_matrix
        v = pymupdf.Point(*line["dir"]) * pymupdf.Matrix(m.a, m.b, m.c, m.d, 0, 0)
        assert v.x > 0.6 and v.y < -0.6


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_page_numbers_upright_on_rotated_pages(sample_pdf, tmp_path, rotation):
    src = PDFService.rotate(sample_pdf, tmp_path / "r.pdf", rotation, "1")
    out = PDFService.add_page_numbers(src, tmp_path / "n.pdf")
    with PDFService.open_document(out) as d:
        page = d[0]
        line = next(
            l for b in page.get_text("dict")["blocks"] if "lines" in b
            for l in b["lines"] if "Page 1 of 5" in "".join(s["text"] for s in l["spans"])
        )
        m = page.rotation_matrix
        v = pymupdf.Point(*line["dir"]) * pymupdf.Matrix(m.a, m.b, m.c, m.d, 0, 0)
        assert v.x > 0.99
        bbox = pymupdf.Rect(line["bbox"]) * m
        assert bbox.y0 > page.rect.height * 0.9  # sits at the visual bottom
