"""Parser e decodificador de legendas PGS Blu-ray (.sup)."""

import struct
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from translaterany.media.ocr.models import SubtitleDisplaySet


def decode_rle(raw: bytes, width: int | None = None) -> list[int]:
    """Decodifica o fluxo RLE padrão Blu-ray PGS em uma lista de índices de paleta."""
    pixels: list[int] = []
    i = 0
    n = len(raw)
    while i < n:
        b = raw[i]
        i += 1
        if b != 0:
            pixels.append(b)
        else:
            if i >= n:
                break
            flag = raw[i]
            i += 1
            if flag == 0x00:
                # End of line
                continue
            flag_type = flag & 0xC0
            if flag_type == 0x00:
                # 1 byte: run de cor 0
                count = flag & 0x3F
                pixels.extend([0] * count)
            elif flag_type == 0x40:
                # 2 bytes: run longo de cor 0
                if i >= n:
                    break
                next_b = raw[i]
                i += 1
                count = ((flag & 0x3F) << 8) | next_b
                pixels.extend([0] * count)
            elif flag_type == 0x80:
                # 2 bytes: run curto de cor específica
                if i >= n:
                    break
                color = raw[i]
                i += 1
                count = flag & 0x3F
                pixels.extend([color] * count)
            elif flag_type == 0xC0:
                # 3 bytes: run longo de cor específica
                if i + 1 >= n:
                    break
                next1 = raw[i]
                color = raw[i + 1]
                i += 2
                count = ((flag & 0x3F) << 8) | next1
                pixels.extend([color] * count)
    return pixels


@dataclass
class _PCSObject:
    object_id: int
    window_id: int
    forced: bool
    x: int
    y: int


@dataclass
class _PCSData:
    video_width: int
    video_height: int
    pts: int
    objects: list[_PCSObject] = field(default_factory=list)


@dataclass
class _ODSData:
    object_id: int
    width: int = 0
    height: int = 0
    rle_data: bytearray = field(default_factory=bytearray)


def parse_pgs(sup_path: Path) -> list[SubtitleDisplaySet]:
    """Lê um arquivo .sup e retorna os conjuntos de exibição com imagens binarizadas."""
    data = sup_path.read_bytes()
    offset = 0
    total_len = len(data)

    current_pcs: _PCSData | None = None
    palettes: dict[int, dict[int, int]] = {}  # pal_id -> {entry_id: alpha}
    current_pal_id = 0
    current_ods: dict[int, _ODSData] = {}

    display_sets: list[SubtitleDisplaySet] = []
    pending_ds: SubtitleDisplaySet | None = None

    while offset + 13 <= total_len:
        magic = data[offset : offset + 2]
        if magic != b"PG":
            offset += 1
            continue

        pts, dts, seg_type, seg_len = struct.unpack_from(">IIBH", data, offset + 2)
        offset += 13
        if offset + seg_len > total_len:
            break

        payload = data[offset : offset + seg_len]
        offset += seg_len

        pts_ms = pts // 90

        if seg_type == 0x16:  # PCS (Presentation Composition Segment)
            if len(payload) >= 11:
                v_w, v_h, fps, comp_num, comp_state, pal_up, pal_id, obj_count = struct.unpack_from(
                    ">HHBHBBBB", payload, 0
                )
                current_pal_id = pal_id
                pcs_objs: list[_PCSObject] = []
                pos = 11
                for _ in range(obj_count):
                    if pos + 8 <= len(payload):
                        obj_id, win_id, crop_flag, ox, oy = struct.unpack_from(">HBBHH", payload, pos)
                        pos += 8
                        if crop_flag & 0x80:
                            pos += 8
                        pcs_objs.append(
                            _PCSObject(
                                object_id=obj_id,
                                window_id=win_id,
                                forced=bool(crop_flag & 0x40),
                                x=ox,
                                y=oy,
                            )
                        )
                current_pcs = _PCSData(video_width=v_w, video_height=v_h, pts=pts_ms, objects=pcs_objs)

                # Se obj_count == 0, encerra o display set anterior
                if obj_count == 0 and pending_ds is not None:
                    closed = SubtitleDisplaySet(
                        start_ms=pending_ds.start_ms,
                        end_ms=pts_ms,
                        x=pending_ds.x,
                        y=pending_ds.y,
                        width=pending_ds.width,
                        height=pending_ds.height,
                        video_width=pending_ds.video_width,
                        video_height=pending_ds.video_height,
                        image=pending_ds.image,
                        forced=pending_ds.forced,
                    )
                    display_sets.append(closed)
                    pending_ds = None

        elif seg_type == 0x14:  # PDS (Palette Definition Segment)
            if len(payload) >= 2:
                pal_id, pal_ver = struct.unpack_from(">BB", payload, 0)
                pal = palettes.setdefault(pal_id, {})
                entries_data = payload[2:]
                for e_idx in range(0, len(entries_data) - 4, 5):
                    eid, y, cr, cb, alpha = struct.unpack_from(">BBBBB", entries_data, e_idx)
                    pal[eid] = (y, alpha)

        elif seg_type == 0x15:  # ODS (Object Definition Segment)
            if len(payload) >= 4:
                obj_id, obj_ver, seq_flag = struct.unpack_from(">HBB", payload, 0)
                ods = current_ods.setdefault(obj_id, _ODSData(object_id=obj_id))
                if seq_flag & 0x80:  # Primeiro segmento
                    if len(payload) >= 11:
                        w, h = struct.unpack_from(">HH", payload, 7)
                        ods.width = w
                        ods.height = h
                        ods.rle_data = bytearray(payload[11:])
                else:
                    ods.rle_data.extend(payload[4:])

        elif seg_type == 0x80:  # EDS (End of Display Set)
            if current_pcs and current_pcs.objects and current_ods:
                # Constrói o DisplaySet para o objeto atual
                pcs_obj = current_pcs.objects[0]
                ods_obj = current_ods.get(pcs_obj.object_id)
                if ods_obj and ods_obj.width > 0 and ods_obj.height > 0:
                    raw_pixels = decode_rle(bytes(ods_obj.rle_data), ods_obj.width)
                    pal = palettes.get(current_pal_id, {})

                    # Binarização: Alpha > 64 -> texto preto (0); fundo -> branco (255)
                    expected_len = ods_obj.width * ods_obj.height
                    if len(raw_pixels) < expected_len:
                        raw_pixels.extend([0] * (expected_len - len(raw_pixels)))
                    elif len(raw_pixels) > expected_len:
                        raw_pixels = raw_pixels[:expected_len]

                    has_bright_text = any(isinstance(v, tuple) and v[1] > 64 and v[0] >= 80 for v in pal.values())

                    bin_bytes = bytearray(expected_len)
                    for idx, c in enumerate(raw_pixels):
                        val = pal.get(c, (0, 0))
                        y_val, alpha = val if isinstance(val, tuple) else (0, val)
                        if alpha <= 64:
                            bin_bytes[idx] = 255
                        elif has_bright_text:
                            bin_bytes[idx] = 0 if y_val >= 80 else 255
                        else:
                            bin_bytes[idx] = 0

                    img = Image.frombytes("L", (ods_obj.width, ods_obj.height), bytes(bin_bytes))

                    if pending_ds is not None:
                        # Fecha o anterior no tempo inicial deste
                        closed = SubtitleDisplaySet(
                            start_ms=pending_ds.start_ms,
                            end_ms=current_pcs.pts,
                            x=pending_ds.x,
                            y=pending_ds.y,
                            width=pending_ds.width,
                            height=pending_ds.height,
                            video_width=pending_ds.video_width,
                            video_height=pending_ds.video_height,
                            image=pending_ds.image,
                            forced=pending_ds.forced,
                        )
                        display_sets.append(closed)

                    pending_ds = SubtitleDisplaySet(
                        start_ms=current_pcs.pts,
                        end_ms=current_pcs.pts + 2500,  # Provisório até ser fechado por PCS clear
                        x=pcs_obj.x,
                        y=pcs_obj.y,
                        width=ods_obj.width,
                        height=ods_obj.height,
                        video_width=current_pcs.video_width,
                        video_height=current_pcs.video_height,
                        image=img,
                        forced=pcs_obj.forced,
                    )

            current_ods.clear()

    if pending_ds is not None:
        display_sets.append(pending_ds)

    return display_sets
