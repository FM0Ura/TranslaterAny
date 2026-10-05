"""Etapa ocr: converte legendas gráficas (PGS/VobSub) em .ocr.ass ou faz bypass se for texto."""

import pysubs2
from pydantic import BaseModel

from translaterany.media.ocr.engine import OCRResultLine, run_ocr
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.util.fs import file_sha256


class OCRArtifact(BaseModel):
    bypassed: bool
    path: str
    lines_count: int = 0
    duration_ms: int = 0
    sha256: str = ""


def _build_ass_event(line: OCRResultLine) -> pysubs2.SSAEvent:
    ev = pysubs2.SSAEvent(start=line.start_ms, end=line.end_ms, text=line.text)
    vh = line.video_h or 1080
    y_ratio = line.y / vh if vh > 0 else 1.0

    if y_ratio < 0.25:
        ev.style = "Top"
        if "\\an8" not in ev.text:
            ev.text = "{\\an8}" + ev.text
    elif 0.25 <= y_ratio <= 0.65:
        ev.style = "Sign"
        if "\\an5" not in ev.text:
            ev.text = "{\\an5}" + ev.text
    else:
        ev.style = "Default"

    return ev


@register_stage
class OCRStage(Stage):
    name = "ocr"
    version = "1"
    scope = StageScope.EPISODE
    inputs = ("extract",)

    def run(self, ctx: StageContext) -> None:
        extract_path = ctx.inputs.path("extract")
        ext = extract_path.suffix.lower()

        if ext in (".ass", ".ssa", ".srt"):
            art = OCRArtifact(
                bypassed=True,
                path=str(extract_path),
                lines_count=0,
                sha256=file_sha256(extract_path) if extract_path.exists() else "",
            )
            ctx.output.json(art)
            return

        import shutil

        if shutil.which("tesseract") is None:
            raise RuntimeError(
                "tesseract não encontrado no PATH: necessário para OCR de legendas gráficas. "
                "Instale via 'brew install tesseract tesseract-lang' ou pelo gerenciador de pacotes do sistema."
            )

        from translaterany.languages.registry import LanguageRegistry
        from translaterany.media.ocr.engine import get_tesseract_lang
        from translaterany.media.ocr.pgs import parse_pgs
        from translaterany.media.ocr.vobsub import parse_vobsub

        source_lang_info = getattr(ctx, "source_language", None) or LanguageRegistry.resolve("en")
        tess_lang = get_tesseract_lang(source_lang_info)

        if ext == ".sup":
            displays = parse_pgs(extract_path)
        elif ext == ".sub":
            idx_path = extract_path.with_suffix(".idx")
            displays = parse_vobsub(extract_path, idx_path)
        else:
            displays = []

        lines = run_ocr(displays, lang=tess_lang)

        doc = pysubs2.SSAFile()
        doc.info["PlayResX"] = 1920
        doc.info["PlayResY"] = 1080
        doc.info["WrapStyle"] = "0"
        doc.info["ScaledBorderAndShadow"] = "yes"

        doc.styles["Default"] = pysubs2.SSAStyle(fontname="Arial", fontsize=48)
        doc.styles["Top"] = pysubs2.SSAStyle(fontname="Arial", fontsize=48, alignment=pysubs2.Alignment.TOP_CENTER)
        doc.styles["Sign"] = pysubs2.SSAStyle(fontname="Arial", fontsize=44, alignment=pysubs2.Alignment.MIDDLE_CENTER)

        for line in lines:
            doc.events.append(_build_ass_event(line))

        out_dir = getattr(ctx.output, "_directory", None) or extract_path.parent
        out_ass_path = out_dir / f"{extract_path.stem}.ocr.ass"
        doc.save(str(out_ass_path))

        duration_ms = max((ev.end for ev in doc.events), default=0)
        art = OCRArtifact(
            bypassed=False,
            path=str(out_ass_path),
            lines_count=len(doc.events),
            duration_ms=duration_ms,
            sha256=file_sha256(out_ass_path),
        )
        ctx.output.json(art)
