import sys
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _make_pdf(path: Path, pages: int, label: str = "Doc") -> Path:
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 100), f"{label} page {i + 1}", fontsize=24)
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def make_pdf(tmp_path):
    def factory(name="a.pdf", pages=5, label="Doc"):
        return _make_pdf(tmp_path / name, pages, label)
    return factory


@pytest.fixture
def sample_pdf(make_pdf):
    return make_pdf("sample.pdf", 5)


@pytest.fixture
def sample_images(tmp_path):
    paths = []
    for i, size in enumerate([(400, 300), (300, 500)]):
        p = tmp_path / f"img{i}.png"
        Image.new("RGB", size, (200 - i * 60, 100, 50 + i * 80)).save(p)
        paths.append(p)
    return paths
