"""Fragmented MP4 (DASH) with FLAC inside -> a plain .flac file, in pure Python.

Tidal's LOSSLESS stream arrives as a DASH init segment plus media segments
(fragmented MP4 whose samples are FLAC frames). A .flac file is just the
"fLaC" marker, the metadata blocks kept in the init segment's dfLa box, and
those frames one after another - so no ffmpeg is needed on the phone.
No Kivy in here.
"""
import struct


class NotFlacError(Exception):
    """The segments do not carry FLAC (for example AAC) - keep them as .m4a."""


def _boxes(data, start=0, end=None):
    """Yields (type, payload_start, box_end, box_start) for the boxes in a range."""
    end = len(data) if end is None else end
    pos = start
    while pos + 8 <= end:
        size, kind = struct.unpack(">I4s", data[pos:pos + 8])
        header = 8
        if size == 1:
            if pos + 16 > end:
                return
            size = struct.unpack(">Q", data[pos + 8:pos + 16])[0]
            header = 16
        elif size == 0:
            size = end - pos
        if size < header or pos + size > end:
            return
        yield kind, pos + header, pos + size, pos
        pos += size


def flac_header(init: bytes) -> bytes:
    """b'fLaC' + the metadata blocks from the init segment's dfLa box."""
    index = init.find(b"dfLa")
    if index < 4:
        raise NotFlacError("no dfLa box in the init segment")
    size = struct.unpack(">I", init[index - 4:index])[0]
    payload = init[index + 4:index - 4 + size][4:]          # skip version + flags
    blocks, pos = [], 0
    while pos + 4 <= len(payload):
        head = payload[pos]
        length = int.from_bytes(payload[pos + 1:pos + 4], "big")
        data = payload[pos + 4:pos + 4 + length]
        if len(data) < length:
            break
        blocks.append((head & 0x7F, data))
        pos += 4 + length
        if head & 0x80:
            break
    if not blocks or blocks[0][0] != 0:
        raise NotFlacError("no STREAMINFO block")
    out = bytearray(b"fLaC")
    for i, (kind, data) in enumerate(blocks):
        last = 0x80 if i == len(blocks) - 1 else 0
        out += bytes([last | kind]) + len(data).to_bytes(3, "big") + data
    return bytes(out)


def _tfhd_default_size(data, start, end):
    flags = int.from_bytes(data[start + 1:start + 4], "big")
    pos = start + 8                                         # version/flags + track id
    if flags & 0x1:
        pos += 8
    if flags & 0x2:
        pos += 4
    if flags & 0x8:
        pos += 4
    if flags & 0x10:
        return struct.unpack(">I", data[pos:pos + 4])[0]
    return None


def _trun(data, start, end, default_size):
    """(data_offset or None, [sample sizes]) of one trun box."""
    flags = int.from_bytes(data[start + 1:start + 4], "big")
    count = struct.unpack(">I", data[start + 4:start + 8])[0]
    pos = start + 8
    offset = None
    if flags & 0x1:
        offset = struct.unpack(">i", data[pos:pos + 4])[0]
        pos += 4
    if flags & 0x4:
        pos += 4
    sizes = []
    for _ in range(count):
        if flags & 0x100:
            pos += 4
        if flags & 0x200:
            sizes.append(struct.unpack(">I", data[pos:pos + 4])[0])
            pos += 4
        elif default_size is not None:
            sizes.append(default_size)
        else:
            raise NotFlacError("trun without sample sizes")
        if flags & 0x400:
            pos += 4
        if flags & 0x800:
            pos += 4
    return offset, sizes


def frames(segment: bytes):
    """Yields the FLAC frames (bytes) of one media segment (moof + mdat)."""
    pending = []                                            # (moof_start, offset, sizes)
    for kind, start, end, box_start in _boxes(segment):
        if kind == b"moof":
            for k2, s2, e2, _b2 in _boxes(segment, start, end):
                if k2 != b"traf":
                    continue
                default_size, runs = None, []
                for k3, s3, e3, _b3 in _boxes(segment, s2, e2):
                    if k3 == b"tfhd":
                        default_size = _tfhd_default_size(segment, s3, e3)
                    elif k3 == b"trun":
                        runs.append(_trun(segment, s3, e3, default_size))
                for offset, sizes in runs:
                    pending.append((box_start, offset, sizes))
        elif kind == b"mdat":
            cursor = start
            for moof_start, offset, sizes in pending:
                pos = moof_start + offset if offset is not None else cursor
                for size in sizes:
                    yield segment[pos:pos + size]
                    pos += size
                cursor = pos
            pending = []


def assemble(init_path, segment_paths, out_path) -> None:
    """Writes out_path as a .flac. Raises NotFlacError when the stream is not FLAC."""
    with open(init_path, "rb") as f:
        header = flac_header(f.read())
    first = True
    with open(out_path, "wb") as out:
        out.write(header)
        for path in segment_paths:
            with open(path, "rb") as f:
                data = f.read()
            for frame in frames(data):
                if first:
                    if len(frame) < 2 or frame[0] != 0xFF or (frame[1] & 0xFC) != 0xF8:
                        raise NotFlacError("the first sample is not a FLAC frame")
                    first = False
                out.write(frame)
    if first:
        raise NotFlacError("no audio frames found")
