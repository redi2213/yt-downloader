"""Writes Vorbis-comment tags and a cover picture into a .flac file, in pure Python.

A FLAC file is "fLaC", metadata blocks, then audio frames. This rewrites the
metadata blocks (the old VORBIS_COMMENT / PICTURE / PADDING blocks are replaced) and
copies the frames unchanged, so the audio is bit-identical. No Kivy in here.
"""
import os
import shutil
import struct

STREAMINFO, PADDING, APPLICATION, SEEKTABLE, VORBIS_COMMENT, CUESHEET, PICTURE = range(7)


class FlacTagError(Exception):
    pass


def _read_blocks(f):
    if f.read(4) != b"fLaC":
        raise FlacTagError("not a FLAC file")
    blocks = []
    while True:
        head = f.read(4)
        if len(head) < 4:
            raise FlacTagError("truncated metadata")
        length = int.from_bytes(head[1:4], "big")
        data = f.read(length)
        if len(data) < length:
            raise FlacTagError("truncated metadata block")
        blocks.append((head[0] & 0x7F, data))
        if head[0] & 0x80:
            return blocks


def vorbis_comment(tags: dict, vendor: str = "YT Bridge") -> bytes:
    entries = []
    for key, value in tags.items():
        value = str(value if value is not None else "").strip()
        if value and key:
            entries.append(("%s=%s" % (str(key).upper(), value)).encode("utf-8"))
    vendor_bytes = vendor.encode("utf-8")
    out = struct.pack("<I", len(vendor_bytes)) + vendor_bytes + struct.pack("<I", len(entries))
    for entry in entries:
        out += struct.pack("<I", len(entry)) + entry
    return out


def _image_info(data: bytes):
    """(mime, width, height) of a JPEG or PNG; width/height 0 when unknown."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return "image/png", width, height
    if data[:2] == b"\xff\xd8":
        pos = 2
        while pos + 9 < len(data):
            if data[pos] != 0xFF:
                pos += 1
                continue
            marker = data[pos + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB):
                height, width = struct.unpack(">HH", data[pos + 5:pos + 9])
                return "image/jpeg", width, height
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                pos += 2
                continue
            pos += 2 + struct.unpack(">H", data[pos + 2:pos + 4])[0]
        return "image/jpeg", 0, 0
    return "", 0, 0


def picture_block(data: bytes) -> bytes:
    """A front-cover PICTURE block, or b'' when the data is not a JPEG/PNG."""
    mime, width, height = _image_info(data)
    if not mime:
        return b""
    mime_bytes = mime.encode("ascii")
    return (struct.pack(">I", 3) + struct.pack(">I", len(mime_bytes)) + mime_bytes
            + struct.pack(">I", 0)                                  # no description
            + struct.pack(">IIII", width, height, 24, 0)            # depth 24, not indexed
            + struct.pack(">I", len(data)) + data)


def tag_file(path: str, tags: dict = None, cover: bytes = None) -> None:
    """Replaces the tags (and the cover, when given) of the FLAC file at path."""
    with open(path, "rb") as f:
        blocks = _read_blocks(f)
        frames_at = f.tell()
        keep = [b for b in blocks if b[0] not in (PADDING, VORBIS_COMMENT, PICTURE)]
        if cover is None:       # keep the cover that is already there
            keep += [b for b in blocks if b[0] == PICTURE]
        if not keep or keep[0][0] != STREAMINFO:
            raise FlacTagError("no STREAMINFO block")
        new = list(keep)
        if tags:
            new.append((VORBIS_COMMENT, vorbis_comment(tags)))
        else:
            new += [b for b in blocks if b[0] == VORBIS_COMMENT]
        if cover:
            picture = picture_block(cover)
            if picture:
                new.append((PICTURE, picture))
        tmp = path + ".tagging"
        try:
            with open(tmp, "wb") as out:
                out.write(b"fLaC")
                for i, (kind, data) in enumerate(new):
                    last = 0x80 if i == len(new) - 1 else 0
                    out.write(bytes([last | kind]) + len(data).to_bytes(3, "big") + data)
                f.seek(frames_at)
                shutil.copyfileobj(f, out, 1024 * 1024)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
