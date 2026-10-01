#!/usr/bin/env python3
"""Validate repository assets, local Markdown links, and immutable Action pins."""

from pathlib import Path
import re
import struct
import subprocess
import sys
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET
import zlib


def check_png(data):
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("invalid PNG signature")
    offset, chunks = 8, []
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("truncated PNG chunk")
        size = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + size
        if end > len(data):
            raise ValueError("truncated PNG data")
        payload = data[offset + 8:offset + 8 + size]
        checksum = struct.unpack(">I", data[end - 4:end])[0]
        if zlib.crc32(kind + payload) & 0xffffffff != checksum:
            raise ValueError("PNG checksum mismatch")
        if not chunks:
            if kind != b"IHDR" or size != 13:
                raise ValueError("missing PNG header")
            width, height = struct.unpack(">II", payload[:8])
            if width == 0 or height == 0:
                raise ValueError("empty PNG dimensions")
        chunks.append(kind)
        offset = end
        if kind == b"IEND":
            if size != 0 or offset != len(data):
                raise ValueError("invalid PNG end")
            break
    if not chunks or chunks[-1] != b"IEND" or b"IDAT" not in chunks:
        raise ValueError("incomplete PNG")


def check_markdown(path, content):
    for destination in re.findall(r"\]\(([^)\n]+)\)", content):
        destination = destination.split(" ", 1)[0].strip("<>")
        url = urlsplit(destination)
        if url.scheme or url.netloc or destination.startswith(("/", "#")):
            continue
        if url.path and not (path.parent / unquote(url.path)).exists():
            raise ValueError(f"missing local link: {destination}")


def check_actions(content):
    for action in re.findall(r"uses:\s*([^\s]+)", content):
        if not action.startswith("./") and not re.fullmatch(r"[^@]+@[0-9a-f]{40}", action):
            raise ValueError(f"Action must use immutable SHA: {action}")


def check_file(path):
    if path.suffix.lower() == ".png":
        check_png(path.read_bytes())
    elif path.suffix.lower() == ".svg":
        content = path.read_text(encoding="utf-8")
        if "<!DOCTYPE" in content or "<!ENTITY" in content:
            raise ValueError("SVG document declarations are not allowed")
        if ET.fromstring(content).tag.split("}")[-1] != "svg":
            raise ValueError("invalid SVG root")
    elif path.suffix.lower() == ".md":
        check_markdown(path, path.read_text(encoding="utf-8"))
    elif path.parent == Path(".github/workflows") and path.suffix in (".yml", ".yaml"):
        check_actions(path.read_text(encoding="utf-8"))


def main():
    paths = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
    ).decode().split("\0")
    for name in sorted(set(paths) - {""}):
        try:
            check_file(Path(name))
        except (OSError, UnicodeError, ValueError, ET.ParseError) as error:
            print(f"{name}: {error}", file=sys.stderr)
            return 1
    print("Repository asset, documentation, and Action-pin checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
