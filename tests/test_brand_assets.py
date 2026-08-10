# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Validate shipped Hospitable brand image assets."""

from __future__ import annotations

import binascii
import struct
import zlib
from pathlib import Path

from PIL import Image

BRAND_DIR = Path(__file__).resolve().parents[1] / "custom_components/hospitable/brand"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
EXPECTED_SIZES = {
    "icon.png": (256, 256),
    "icon@2x.png": (512, 512),
}


def _brand_png_paths() -> list[Path]:
    """Return every PNG shipped in the brand directory."""
    return sorted(BRAND_DIR.glob("*.png"))


def _assert_png_chunks_valid(path: Path) -> None:
    """Assert every PNG chunk has a valid CRC and IDAT stream."""
    data = path.read_bytes()
    assert data.startswith(PNG_SIGNATURE), f"{path.name} is missing the PNG signature"

    offset = len(PNG_SIGNATURE)
    idat = bytearray()
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data = data[offset + 8 : offset + 8 + length]
        stored_crc_bytes = data[offset + 8 + length : offset + 12 + length]
        stored_crc = struct.unpack(">I", stored_crc_bytes)[0]
        computed_crc = binascii.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        assert stored_crc == computed_crc, (
            f"{path.name} {chunk_type.decode('ascii')} CRC mismatch: "
            f"stored 0x{stored_crc:08x}, computed 0x{computed_crc:08x}"
        )
        if chunk_type == b"IDAT":
            idat.extend(chunk_data)
        offset += 12 + length
        if chunk_type == b"IEND":
            break

    assert idat, f"{path.name} has no IDAT payload"
    zlib.decompress(bytes(idat))


def test_brand_png_payloads_are_valid() -> None:
    """Every shipped brand PNG has valid chunks and decodes with Pillow."""
    for path in _brand_png_paths():
        _assert_png_chunks_valid(path)
        with Image.open(path) as image:
            image.load()
        with Image.open(path) as image:
            image.verify()


def test_brand_assets_are_icon_only() -> None:
    """The brand directory ships only correctly sized square icons."""
    assert not (BRAND_DIR / "logo.png").exists()
    assert {path.name for path in _brand_png_paths()} == set(EXPECTED_SIZES)

    for path in _brand_png_paths():
        with Image.open(path) as image:
            assert image.size == EXPECTED_SIZES[path.name]
            assert image.width == image.height
