"""Helpers para criação de fluxos binários sintéticos PGS (.sup) e VobSub (.sub/.idx)."""

import struct
from pathlib import Path


def _pg_segment(seg_type: int, pts: int, dts: int, payload: bytes) -> bytes:
    """Monta um segmento PGS com cabeçalho PG (0x50, 0x47)."""
    header = struct.pack(">2sIIBH", b"PG", pts, dts, seg_type, len(payload))
    return header + payload


def make_synthetic_sup(
    dest: Path,
    width: int = 100,
    height: int = 30,
    text_color: int = 1,
    start_pts: int = 90000,  # 1000 ms
    end_pts: int = 180000,  # 2000 ms
    video_w: int = 1920,
    video_h: int = 1080,
    x: int = 100,
    y: int = 900,
) -> Path:
    """Gera um arquivo .sup sintético válido contendo uma legenda."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    chunks = []

    # 1. PCS (Presentation Composition Segment) - Início do display set
    # video_w(2B), video_h(2B), fps(1B), comp_num(2B), state(1B)=0x80(Epoch start),
    # pal_update(1B)=0, pal_id(1B)=0, obj_count(1B)=1
    # obj_id(2B)=0, win_id(1B)=0, cropped_forced(1B)=0, obj_x(2B), obj_y(2B)
    pcs_payload = struct.pack(">HHBHBBBB", video_w, video_h, 0x10, 1, 0x80, 0, 0, 1) + struct.pack(
        ">HBBHH", 0, 0, 0, x, y
    )
    chunks.append(_pg_segment(0x16, start_pts, 0, pcs_payload))

    # 2. WDS (Window Definition Segment)
    wds_payload = struct.pack(">BBHHHH", 1, 0, x, y, width, height)
    chunks.append(_pg_segment(0x17, start_pts, 0, wds_payload))

    # 3. PDS (Palette Definition Segment)
    # pal_id(1B)=0, pal_version(1B)=0
    # entries: entry_id(1B), Y(1B), Cr(1B), Cb(1B), Alpha(1B)
    # entry 0: transparent (alpha=0), entry text_color: opaque (alpha=255)
    pds_payload = (
        struct.pack(">BB", 0, 0)
        + struct.pack(">BBBBB", 0, 0, 128, 128, 0)
        + struct.pack(">BBBBB", text_color, 255, 128, 128, 255)
    )
    chunks.append(_pg_segment(0x14, start_pts, 0, pds_payload))

    # 4. ODS (Object Definition Segment)
    # obj_id(2B)=0, obj_ver(1B)=0, seq_flag(1B)=0xC0 (first & last)
    # data_len(3B), w(2B), h(2B), rle_data...
    # RLE para cada linha: run de 'width' pixels da cor text_color -> 0x00, (0x80 | (count & 0x3F) ou 0xC0...), color
    rle_line = bytearray()
    remaining = width
    while remaining > 0:
        run = min(remaining, 63)
        rle_line.extend([0x00, 0x80 | run, text_color])
        remaining -= run
    rle_line.extend([0x00, 0x00])  # End of line
    rle_data = bytes(rle_line) * height

    data_len = len(rle_data) + 4
    ods_header = struct.pack(">HBB", 0, 0, 0xC0)
    len_bytes = struct.pack(">I", data_len)[1:]  # 3 bytes
    ods_payload = ods_header + len_bytes + struct.pack(">HH", width, height) + rle_data
    chunks.append(_pg_segment(0x15, start_pts, 0, ods_payload))

    # 5. EDS (End of Display Set)
    chunks.append(_pg_segment(0x80, start_pts, 0, b""))

    # 6. PCS de fechamento (obj_count = 0) em end_pts
    pcs_clear = struct.pack(">HHBHBBBB", video_w, video_h, 0x10, 2, 0x00, 0, 0, 0)
    chunks.append(_pg_segment(0x16, end_pts, 0, pcs_clear))
    chunks.append(_pg_segment(0x80, end_pts, 0, b""))

    dest.write_bytes(b"".join(chunks))
    return dest
