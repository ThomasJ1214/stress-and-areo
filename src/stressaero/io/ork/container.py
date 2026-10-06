"""Detect and unpack the OpenRocket ``.ork`` container (ZIP, GZIP or plain XML).

OpenRocket 13.04+ writes a ZIP whose first entry is ``rocket.ork`` (followed by decal images); files from
before 13.04 are GZIP-compressed XML; plain XML is also accepted by OpenRocket. Nothing is extracted to disk
(entry names may be absolute, e.g. ``/datafiles/textures/balsa.jpg``) and decompressed size is capped.
"""

from __future__ import annotations

import gzip
import io
import re
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from stressaero.io.ork.errors import OrkFormatError

DEFAULT_MAX_BYTES = 64 * 2**20
_ORK_ENTRY = re.compile(r"\.(ork|rkt|cdx1)$", re.IGNORECASE)
_CHUNK = 1 << 20


@dataclass(frozen=True)
class Container:
    kind: Literal["zip", "gzip", "xml"]
    xml: bytes
    entries: tuple[str, ...] = ()


def _too_large(limit: int) -> OrkFormatError:
    return OrkFormatError(f"OpenRocket document is too large (> {limit // 2**20} MiB uncompressed)")


def _read_capped(stream, limit: int) -> bytes:
    out = bytearray()
    while True:
        chunk = stream.read(_CHUNK)
        if not chunk:
            return bytes(out)
        out += chunk
        if len(out) > limit:
            raise _too_large(limit)


def read_container(source: Path | str | bytes, *, max_bytes: int = DEFAULT_MAX_BYTES) -> Container:
    raw = source if isinstance(source, bytes | bytearray) else Path(source).read_bytes()
    raw = bytes(raw)
    if raw[:2] == b"PK":
        try:
            zf = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile as e:
            raise OrkFormatError(f"corrupt ZIP container: {e}") from e
        names = tuple(i.filename for i in zf.infolist())
        main = next((n for n in names if _ORK_ENTRY.search(n.lstrip("/"))), None)
        if main is None:
            raise OrkFormatError("ZIP container has no .ork entry")
        try:
            with zf.open(main) as fh:
                xml = _read_capped(fh, max_bytes)
        except (zipfile.BadZipFile, zlib.error, EOFError) as e:
            raise OrkFormatError(f"corrupt ZIP entry {main!r}: {e}") from e
        return Container("zip", xml, names)
    if raw[:2] == b"\x1f\x8b":
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as fh:
                xml = _read_capped(fh, max_bytes)
        except (OSError, EOFError, zlib.error) as e:
            raise OrkFormatError(f"corrupt GZIP container: {e}") from e
        return Container("gzip", xml)
    if len(raw) > max_bytes:
        raise _too_large(max_bytes)
    if b"<openrocket" not in raw[:300]:
        raise OrkFormatError("not an OpenRocket file (no <openrocket> root element)")
    return Container("xml", raw)
