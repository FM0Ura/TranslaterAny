"""Motor de OCR paralelo com Tesseract, detecção de itálico via hOCR e desduplicação."""

import hashlib
import re
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from PIL import Image, ImageOps

from translaterany.media.ocr.models import SubtitleDisplaySet

TESSERACT_LANG_MAP: dict[str, str] = {
    "en": "eng",
    "eng": "eng",
    "ja": "jpn",
    "jpn": "jpn",
    "pt": "por",
    "por": "por",
    "es": "spa",
    "spa": "spa",
    "fr": "fra",
    "fra": "fra",
    "de": "deu",
    "deu": "deu",
    "it": "ita",
    "ita": "ita",
    "zh": "chi_sim",
    "chi": "chi_sim",
    "zho": "chi_sim",
    "ko": "kor",
    "kor": "kor",
    "ru": "rus",
    "rus": "rus",
}


def get_tesseract_lang(lang: object) -> str:
    """Mapeia um código ou objeto de idioma para o código esperado pelo Tesseract."""
    if hasattr(lang, "iso639_2") and lang.iso639_2:
        code = str(lang.iso639_2).lower()
        if code in TESSERACT_LANG_MAP:
            return TESSERACT_LANG_MAP[code]
    if hasattr(lang, "code") and lang.code:
        code = str(lang.code).lower().split("-")[0]
        if code in TESSERACT_LANG_MAP:
            return TESSERACT_LANG_MAP[code]
    if isinstance(lang, str):
        code = lang.lower().split("-")[0]
        return TESSERACT_LANG_MAP.get(code, code)
    return "eng"


@dataclass(frozen=True)
class OCRResultLine:
    start_ms: int
    end_ms: int
    x: int
    y: int
    w: int
    h: int
    video_w: int
    video_h: int
    text: str
    forced: bool = False


class _HOCRParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.pieces: list[str] = []
        self.in_italic = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        if tag_lower in ("em", "i"):
            if not self.in_italic:
                self.pieces.append("{\\i1}")
                self.in_italic = True
        elif tag_lower == "span":
            attr_dict = dict(attrs)
            if "ocr_line" in (attr_dict.get("class") or "") and self.pieces:
                if not self.pieces[-1].endswith("\\N") and not self.pieces[-1].endswith("\\N "):
                    self.pieces.append("\\N ")
        elif tag_lower == "br":
            self.pieces.append("\\N ")

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower in ("em", "i"):
            if self.in_italic:
                self.pieces.append("{\\i0}")
                self.in_italic = False

    def handle_data(self, data: str) -> None:
        if not data:
            return
        has_leading = data[0].isspace()
        has_trailing = data[-1].isspace()
        clean = data.strip()
        if not clean:
            if self.pieces and not self.pieces[-1].endswith(" "):
                self.pieces.append(" ")
            return
        if has_leading and self.pieces and not self.pieces[-1].endswith((" ", "\\N", "\\N ")):
            self.pieces.append(" ")
        self.pieces.append(clean)
        if has_trailing:
            self.pieces.append(" ")


def _parse_hocr(hocr: str) -> str:
    parser = _HOCRParser()
    parser.feed(hocr)
    if parser.in_italic:
        parser.pieces.append("{\\i0}")
    raw_text = "".join(parser.pieces).strip()
    raw_text = raw_text.replace("{\\i0}{\\i1}", "").replace("{\\i1}{\\i0}", "")
    raw_text = re.sub(r" +", " ", raw_text)
    raw_text = re.sub(r"\s*\\N\s*", lambda m: r"\N", raw_text)
    return raw_text


def _call_tesseract_hocr(image: Image.Image, lang: str) -> str:
    inv = ImageOps.invert(image)
    bbox = inv.getbbox()
    if bbox is None:
        return ""

    cropped = image.crop(bbox)
    bordered = ImageOps.expand(cropped, border=10, fill=255)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_name = tmp.name
        bordered.save(tmp_name, format="PNG")

    try:
        cmd = ["tesseract", tmp_name, "stdout", "--psm", "6", "--oem", "1", "-l", lang, "hocr"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15.0)
        return proc.stdout
    except FileNotFoundError as exc:
        raise RuntimeError(
            "tesseract não encontrado no PATH: instale via 'brew install tesseract tesseract-lang' "
            "ou pelo gerenciador de pacotes do sistema."
        ) from exc
    except Exception:
        return ""
    finally:
        Path(tmp_name).unlink(missing_ok=True)


def _deduplicate_displays(displays: list[SubtitleDisplaySet]) -> list[SubtitleDisplaySet]:
    if not displays:
        return []

    def get_hash(ds: SubtitleDisplaySet) -> str:
        return hashlib.sha256(ds.image.tobytes()).hexdigest()

    deduped: list[SubtitleDisplaySet] = []
    prev_ds: SubtitleDisplaySet | None = None
    prev_hash: str | None = None

    for ds in displays:
        h = get_hash(ds)
        if (
            prev_ds is not None
            and prev_hash == h
            and ds.x == prev_ds.x
            and ds.y == prev_ds.y
            and ds.start_ms <= prev_ds.end_ms + 100
        ):
            prev_ds = SubtitleDisplaySet(
                start_ms=prev_ds.start_ms,
                end_ms=max(prev_ds.end_ms, ds.end_ms),
                x=prev_ds.x,
                y=prev_ds.y,
                width=prev_ds.width,
                height=prev_ds.height,
                video_width=prev_ds.video_width,
                video_height=prev_ds.video_height,
                image=prev_ds.image,
                forced=prev_ds.forced or ds.forced,
            )
        else:
            if prev_ds is not None:
                deduped.append(prev_ds)
            prev_ds = ds
            prev_hash = h

    if prev_ds is not None:
        deduped.append(prev_ds)

    return deduped


def run_ocr(
    displays: list[SubtitleDisplaySet],
    lang: str = "eng",
    max_workers: int = 4,
) -> list[OCRResultLine]:
    cleaned = _deduplicate_displays(displays)
    if not cleaned:
        return []

    cache: dict[str, str] = {}
    lock = threading.Lock()

    def process_item(ds: SubtitleDisplaySet) -> OCRResultLine | None:
        h = hashlib.sha256(ds.image.tobytes()).hexdigest()
        with lock:
            if h in cache:
                cached_text = cache[h]
                if not cached_text:
                    return None
                return OCRResultLine(
                    start_ms=ds.start_ms,
                    end_ms=ds.end_ms,
                    x=ds.x,
                    y=ds.y,
                    w=ds.width,
                    h=ds.height,
                    video_w=ds.video_width,
                    video_h=ds.video_height,
                    text=cached_text,
                    forced=ds.forced,
                )

        hocr = _call_tesseract_hocr(ds.image, lang)
        text = _parse_hocr(hocr)
        with lock:
            cache[h] = text

        if not text:
            return None

        return OCRResultLine(
            start_ms=ds.start_ms,
            end_ms=ds.end_ms,
            x=ds.x,
            y=ds.y,
            w=ds.width,
            h=ds.height,
            video_w=ds.video_width,
            video_h=ds.video_height,
            text=text,
            forced=ds.forced,
        )

    if max_workers <= 1:
        results = [process_item(d) for d in cleaned]
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(process_item, cleaned))

    return [r for r in results if r is not None]
