from __future__ import annotations

"""NEAPP05 UI asset limits and canonical path validation."""

from dataclasses import dataclass
import neapp_v5_native as fmt

RECORD_FIXED_LEN = 2 + 4 + 32

MAX_MANIFEST_LEN = 16384
MIN_ASSET_PAYLOAD_LEN = 1
MAX_ASSET_PAYLOAD_LEN = 2_097_152
MIN_FILE_COUNT = 1
MAX_FILE_COUNT = 64
MIN_PATH_LEN = 1
MAX_PATH_LEN = 160
MIN_FILE_LEN = 1
MAX_FILE_LEN = 1_048_576
HOST_UI_ABI_V1 = 1
INDEX_PATH = "index.html"

PATH_FIRST = frozenset(range(0x41, 0x5B)) | frozenset(range(0x61, 0x7B)) | frozenset(range(0x30, 0x3A))
PATH_REST = PATH_FIRST | {0x2E, 0x5F, 0x2D}


@dataclass
class AssetRecord:
    path: str
    file_len: int
    sha256: bytes

def validate_asset_path(path: bytes) -> str:
    if not path:
        raise fmt.BadPackage("asset path is empty")
    if len(path) > MAX_PATH_LEN:
        raise fmt.BadPackage(f"asset path is {len(path)} bytes, above the {MAX_PATH_LEN}-byte cap")
    for i, b in enumerate(path):
        if b == 0:
            raise fmt.BadPackage(f"asset path contains a NUL byte at offset {i}")
        if b < 0x20 or b > 0x7E:
            raise fmt.BadPackage(
                f"asset path byte {b:#04x} at offset {i} is non-ASCII or a control byte")
    if b"\\" in path:
        raise fmt.BadPackage("asset path contains a backslash separator")
    if b"%" in path:
        raise fmt.BadPackage("asset path contains a percent escape")
    if b":" in path:
        raise fmt.BadPackage("asset path contains a colon")
    if b"?" in path:
        raise fmt.BadPackage("asset path contains a query separator")
    if b"#" in path:
        raise fmt.BadPackage("asset path contains a fragment separator")
    if path.startswith(b"/"):
        raise fmt.BadPackage("asset path is absolute (leading '/')")
    if path.endswith(b"/"):
        raise fmt.BadPackage("asset path ends with '/'")
    segments = path.split(b"/")
    for seg in segments:
        if not seg:
            raise fmt.BadPackage("asset path contains an empty segment ('//')")
        if seg == b"." or seg == b"..":
            raise fmt.BadPackage(f"asset path contains the dot segment {seg.decode('ascii')!r}")
        if seg[0] not in PATH_FIRST:
            raise fmt.BadPackage(
                f"asset path segment {seg.decode('ascii', 'replace')!r} does not start with "
                "[A-Za-z0-9]")
        for b in seg[1:]:
            if b not in PATH_REST:
                raise fmt.BadPackage(
                    f"asset path segment {seg.decode('ascii', 'replace')!r} has a byte outside "
                    "[A-Za-z0-9._-]")
    return path.decode("ascii")
