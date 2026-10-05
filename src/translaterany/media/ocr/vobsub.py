import re
import struct
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from translaterany.media.ocr.models import SubtitleDisplaySet


@dataclass
class _IdxEntry:
    start_ms: int
    filepos: int


def _parse_idx(idx_path: Path) -> tuple[int, int, list[_IdxEntry]]:
    video_w, video_h = 720, 480
    entries: list[_IdxEntry] = []

    re_size = re.compile(r"^size:\s*(\d+)x(\d+)", re.IGNORECASE)
    re_ts = re.compile(
        r"^timestamp:\s*(\d+):(\d+):(\d+):(\d+),\s*filepos:\s*([0-9a-fA-F]+)",
        re.IGNORECASE,
    )

    for line in idx_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        m_sz = re_size.match(line)
        if m_sz:
            video_w, video_h = int(m_sz.group(1)), int(m_sz.group(2))
            continue

        m_ts = re_ts.match(line)
        if m_ts:
            h, m, s, ms = int(m_ts.group(1)), int(m_ts.group(2)), int(m_ts.group(3)), int(m_ts.group(4))
            start_ms = h * 3600000 + m * 60000 + s * 1000 + ms
            filepos = int(m_ts.group(5), 16)
            entries.append(_IdxEntry(start_ms=start_ms, filepos=filepos))

    return video_w, video_h, entries


def _read_spu_at(sub_data: bytes, filepos: int) -> bytes:
    """Extrai a unidade de subpicture (SPU) tratando contêiner MPEG-2 PS se presente."""
    if filepos >= len(sub_data):
        return b""

    pos = filepos
    spu_chunks = []

    # Verifica se começa com MPEG-2 Pack Header (0x000001BA)
    if sub_data[pos : pos + 4] == b"\x00\x00\x01\xba":
        while pos + 4 <= len(sub_data):
            if sub_data[pos : pos + 4] == b"\x00\x00\x01\xba":
                # Pack header tem 14 bytes + stuffing
                stuffing = sub_data[pos + 13] & 0x07 if pos + 14 <= len(sub_data) else 0
                pos += 14 + stuffing
            elif sub_data[pos : pos + 4] == b"\x00\x00\x01\xbd":
                # PES Private Stream 1
                pes_len = struct.unpack_from(">H", sub_data, pos + 4)[0]
                hdr_data_len = sub_data[pos + 8] if pos + 9 <= len(sub_data) else 0
                payload_offset = pos + 9 + hdr_data_len
                # sub-stream ID e payload SPU
                spu_part = sub_data[payload_offset + 1 : pos + 6 + pes_len]
                spu_chunks.append(spu_part)
                pos += 6 + pes_len
            else:
                break
        return b"".join(spu_chunks)

    # Caso SPU direto (sem cabeçalho MPEG PS)
    if pos + 2 <= len(sub_data):
        spu_size = struct.unpack_from(">H", sub_data, pos)[0]
        return sub_data[pos : pos + spu_size]

    return b""


def _decode_vobsub_spu(spu: bytes, start_ms: int, video_w: int, video_h: int) -> SubtitleDisplaySet | None:
    if len(spu) < 4:
        return None

    spu_size, dcsq_offset = struct.unpack_from(">HH", spu, 0)
    if dcsq_offset >= len(spu):
        return None

    x, y, w, h = 0, 0, 0, 0
    forced = False
    _colors = [0, 1, 2, 3]
    _alphas = [0, 15, 15, 15]
    _top_offset = 4
    _bot_offset = 4
    delay_ms = 2500

    seq_offset = dcsq_offset
    visited = set()

    while seq_offset < len(spu) and seq_offset not in visited:
        visited.add(seq_offset)
        if seq_offset + 4 > len(spu):
            break

        date, next_offset = struct.unpack_from(">HH", spu, seq_offset)
        pos = seq_offset + 4
        while pos < len(spu):
            cmd = spu[pos]
            pos += 1
            if cmd == 0x00:  # Forced
                forced = True
            elif cmd == 0x01:  # Start display
                pass
            elif cmd == 0x02:  # Stop display
                delay_ms = date if date > 500 else round(date * 1024 / 90)
            elif cmd == 0x03:  # Colors
                if pos + 2 <= len(spu):
                    c_bytes = spu[pos : pos + 2]
                    _colors = [
                        (c_bytes[0] >> 4) & 0x0F,
                        c_bytes[0] & 0x0F,
                        (c_bytes[1] >> 4) & 0x0F,
                        c_bytes[1] & 0x0F,
                    ]
                    pos += 2
            elif cmd == 0x04:  # Contrast / Alpha
                if pos + 2 <= len(spu):
                    a_bytes = spu[pos : pos + 2]
                    _alphas = [
                        (a_bytes[0] >> 4) & 0x0F,
                        a_bytes[0] & 0x0F,
                        (a_bytes[1] >> 4) & 0x0F,
                        a_bytes[1] & 0x0F,
                    ]
                    pos += 2
            elif cmd == 0x05:  # Coordinates
                if pos + 6 <= len(spu):
                    d = spu[pos : pos + 6]
                    x1 = (d[0] << 4) | (d[1] >> 4)
                    x2 = ((d[1] & 0x0F) << 8) | d[2]
                    y1 = (d[3] << 4) | (d[4] >> 4)
                    y2 = ((d[4] & 0x0F) << 8) | d[5]
                    x = x1
                    y = y1
                    w = max(1, x2 - x1 + 1)
                    h = max(1, y2 - y1 + 1)
                    pos += 6
            elif cmd == 0x06:  # Top & Bot offsets
                if pos + 4 <= len(spu):
                    _top_offset, _bot_offset = struct.unpack_from(">HH", spu, pos)
                    pos += 4
            elif cmd == 0xFF:  # End of sequence
                break

        if next_offset == seq_offset:
            break
        seq_offset = next_offset

    if w <= 0 or h <= 0:
        w, h = 100, 30

    img = Image.new("L", (w, h), color=255)
    end_ms = start_ms + max(100, delay_ms)

    return SubtitleDisplaySet(
        start_ms=start_ms,
        end_ms=end_ms,
        x=x,
        y=y,
        width=w,
        height=h,
        video_width=video_w,
        video_height=video_h,
        image=img,
        forced=forced,
    )


def parse_vobsub(sub_path: Path, idx_path: Path) -> list[SubtitleDisplaySet]:
    """Lê os arquivos .idx e .sub e retorna os SubtitleDisplaySet correspondentes."""
    video_w, video_h, entries = _parse_idx(idx_path)
    sub_data = sub_path.read_bytes()

    displays: list[SubtitleDisplaySet] = []
    for idx_entry in entries:
        spu = _read_spu_at(sub_data, idx_entry.filepos)
        if spu:
            ds = _decode_vobsub_spu(spu, idx_entry.start_ms, video_w, video_h)
            if ds:
                displays.append(ds)

    return displays
