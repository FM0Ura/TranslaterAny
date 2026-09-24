"""Conversão de SRT (qualquer codificação) para ASS."""

import charset_normalizer
import pysubs2

from translaterany.subtitles.ass import AssError


def decode_text(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        best = charset_normalizer.from_bytes(data).best()
        if best is None:
            raise AssError("legenda com codificação desconhecida") from None
        return str(best)


def srt_to_ass(data: bytes) -> bytes:
    subs = pysubs2.SSAFile.from_string(decode_text(data), format_="srt")
    return subs.to_string("ass").encode("utf-8")
