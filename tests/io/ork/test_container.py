import gzip
import io
import zipfile

import pytest

from stressaero.io.ork.container import read_container
from stressaero.io.ork.errors import OrkFormatError
from tests.oracle_data import find

MINIMAL = b'<?xml version="1.0" encoding="utf-8"?>\n<openrocket version="1.10" creator="test"><rocket/></openrocket>'


def test_zip_container():
    c = read_container(find("Dual parachute"))
    assert c.kind == "zip"
    assert c.entries[0] == "rocket.ork"
    assert c.xml.lstrip().startswith(b"<?xml")


def test_gzip_container():
    c = read_container(find("simplerocket", "v2412"))
    assert c.kind == "gzip"
    assert b"<openrocket" in c.xml[:300]


def test_plain_xml_container():
    c = read_container(find("asimple", "v2412"))
    assert c.kind == "xml"


def test_leading_slash_entries_load():
    c = read_container(find("Parallel booster"))
    assert c.kind == "zip"
    assert any(e.startswith("/") for e in c.entries)


def test_accepts_bytes():
    assert read_container(MINIMAL).kind == "xml"
    assert read_container(gzip.compress(MINIMAL)).kind == "gzip"


def test_ork_entry_not_first():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("decals/a.png", b"png")
        z.writestr("rocket.ork", MINIMAL)
    assert read_container(buf.getvalue()).xml == MINIMAL


def test_oversized_entry_rejected(tmp_path):
    path = tmp_path / "bomb.ork"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("rocket.ork", b"<openrocket>" + b"\0" * (65 * 2**20))
    with pytest.raises(OrkFormatError, match="too large"):
        read_container(path)


def test_oversized_gzip_rejected():
    with pytest.raises(OrkFormatError, match="too large"):
        read_container(gzip.compress(b"<openrocket>" + b"\0" * (2 * 2**20)), max_bytes=2**20)


def test_garbage_rejected():
    with pytest.raises(OrkFormatError, match="not an OpenRocket file"):
        read_container(b"\x00\x01garbage" * 50)


def test_zip_without_ork_entry_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("readme.txt", b"hi")
    with pytest.raises(OrkFormatError, match="no .ork"):
        read_container(buf.getvalue())
