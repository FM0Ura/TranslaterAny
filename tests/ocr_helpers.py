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


def make_synthetic_vobsub(
    sub_path: Path,
    idx_path: Path,
    start_ms: int = 1000,
    end_ms: int = 3000,
    width: int = 100,
    height: int = 30,
    video_w: int = 720,
    video_h: int = 480,
    x: int = 50,
    y: int = 400,
) -> None:
    """Gera arquivos .idx e .sub sintéticos válidos contendo uma legenda DVD."""
    sub_path.parent.mkdir(parents=True, exist_ok=True)
    idx_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Gerar .idx
    start_s = start_ms // 1000
    start_rem = start_ms % 1000
    h_val = start_s // 3600
    m_val = (start_s % 3600) // 60
    s_val = start_s % 60
    ts_str = f"{h_val:02d}:{m_val:02d}:{s_val:02d}:{start_rem:03d}"

    idx_content = (
        f"# VobSub index file\n"
        f"size: {video_w}x{video_h}\n"
        f"palette: 000000, 111111, 222222, ffffff, 000000, 000000, 000000, 000000, "
        f"000000, 000000, 000000, 000000, 000000, 000000, 000000, 000000\n"
        f"timestamp: {ts_str}, filepos: 000000000\n"
    )
    idx_path.write_text(idx_content, encoding="utf-8")

    # 2. Gerar .sub com SPU
    # Coordinates: x1 = x, x2 = x + width - 1, y1 = y, y2 = y + height - 1
    x1, x2 = x, x + width - 1
    y1, y2 = y, y + height - 1

    # RLE dummy: para cada linha, 2 bytes 0x0000 (end of line code)
    # Total de linhas no top field = (height + 1) // 2, bottom field = height // 2
    top_lines = (height + 1) // 2
    bot_lines = height // 2
    top_rle = b"\x00\x00" * top_lines
    bot_rle = b"\x00\x00" * bot_lines
    pixel_data = top_rle + bot_rle

    top_offset = 4
    bot_offset = 4 + len(top_rle)
    dcsq_offset = 4 + len(pixel_data)

    # DCSQ 1: Start display at t=0
    delay_units = max(1, end_ms - start_ms)

    # DCSQ 1 commands
    # 0x01 (start)
    # 0x03 (colors: 0x3210 -> c3=3, c2=2, c1=1, c0=0)
    # 0x04 (contrast: 0xFFF0 -> a3=15, a2=15, a1=15, a0=0)
    # 0x05 (coords: 6 bytes)
    # 0x06 (top/bot offsets: 4 bytes)
    # 0xFF
    coord_bytes = bytes(
        [
            (x1 >> 4) & 0xFF,
            ((x1 & 0x0F) << 4) | ((x2 >> 8) & 0x0F),
            x2 & 0xFF,
            (y1 >> 4) & 0xFF,
            ((y1 & 0x0F) << 4) | ((y2 >> 8) & 0x0F),
            y2 & 0xFF,
        ]
    )

    dcsq1_cmds = (
        b"\x01"
        + b"\x03\x32\x10"
        + b"\x04\xff\xf0"
        + b"\x05"
        + coord_bytes
        + struct.pack(">BHH", 0x06, top_offset, bot_offset)
        + b"\xff"
    )

    # Next seq offset:
    dcsq2_offset = dcsq_offset + 4 + len(dcsq1_cmds)
    dcsq1_header = struct.pack(">HH", 0, dcsq2_offset)
    dcsq1 = dcsq1_header + dcsq1_cmds

    # DCSQ 2: Stop display at delay_units
    dcsq2_cmds = b"\x02\xff"
    dcsq2_header = struct.pack(">HH", delay_units, dcsq2_offset)  # points to self
    dcsq2 = dcsq2_header + dcsq2_cmds

    spu_payload = pixel_data + dcsq1 + dcsq2
    spu_size = 4 + len(spu_payload)
    spu_header = struct.pack(">HH", spu_size, dcsq_offset)
    sub_path.write_bytes(spu_header + spu_payload)
