from pathlib import Path
from typing import Protocol, TypeAlias, Callable
from io import StringIO
import itertools
import csv

from PIL import Image
from natsort import natsorted
from loguru import logger

import pcleaner.config as cfg
import pcleaner.structures as st
import pcleaner.helpers as hp
from pcleaner.ocr.ocr_mangaocr import MangaOcr
from pcleaner.ocr.ocr_tesseract import TesseractOcr
import pcleaner.ocr.supported_languages as osl


class OCRModel(Protocol):
    def __call__(self, img_or_path: Image.Image | Path | str, **kwargs) -> str: ...


OCREngineFactory: TypeAlias = Callable[[osl.LanguageCode], OCRModel]


def tesseract_ok(profile: cfg.Profile) -> bool:
    want_tess = profile.preprocessor.ocr_use_tesseract
    has_language_packs: bool = bool(TesseractOcr.langs())
    return not want_tess or (want_tess and has_language_packs)


def ocr_engines():
    return {
        cfg.OCREngine.MANGAOCR: MangaOcr(),
        cfg.OCREngine.TESSERACT: TesseractOcr(),
    }


def get_all_available_langs() -> set[osl.LanguageCode]:
    union_langs = set()
    for ocr in ocr_engines().values():
        union_langs |= ocr.langs()
    return union_langs


def build_ocr_engine_factory(
    tesseract_enabled: bool, ocr_engine_preference: cfg.OCREngine
) -> OCREngineFactory:
    """
    Create a factory function that returns the appropriate OCR engine for a given language.

    :param tesseract_enabled: Whether Tesseract should be considered for use.
    :param ocr_engine_preference: The preferred OCR engine.
    :return: The factory function.
    """
    # want_tess = profile.preprocessor.ocr_use_tesseract
    tess_langs: set[osl.LanguageCode] = TesseractOcr.langs()
    mocr_langs: set[osl.LanguageCode] = MangaOcr.langs()
    if tesseract_enabled and not tess_langs:
        logger.error(
            f"Tesseract OCR is not installed or not found. "
            "Please see the instructions in the README to install Tesseract correctly. Falling back to manga-ocr."
        )

    if not tesseract_enabled and ocr_engine_preference != cfg.OCREngine.AUTO:
        ocr_engine_preference = cfg.OCREngine.MANGAOCR

    def closure(lang: osl.LanguageCode) -> OCRModel:
        if ocr_engine_preference == cfg.OCREngine.AUTO:
            # Prefer MangaOCR for the languages it can do, which is only one, but it's
            # much better than Tesseract for it.
            if lang in mocr_langs:
                # The linter is being retarded here.
                # noinspection PyTypeChecker
                return MangaOcr()
            if lang in tess_langs:
                return TesseractOcr(lang)
        elif ocr_engine_preference == cfg.OCREngine.TESSERACT:
            if lang in tess_langs:
                return TesseractOcr(lang)
            logger.error(
                f"Tesseract language pack for '{lang}' is not installed or not found. "
                "Please see the instructions to install Tesseract correctly. Falling back to manga-ocr."
            )
        # Fall back to manga-ocr.
        # noinspection PyTypeChecker
        return MangaOcr()

    return closure


def format_output(
    ocr_analytics: list[st.OCRAnalytic],
    output_format: str,
    csv_column_names: tuple[str, str, str, str, str, str],
) -> str:
    """
    Format the output of the OCR process.

    :param ocr_analytics: A list of the OCR analytics per image.
    :param output_format: The format to output the data in (csv, json, plain).
    :param csv_column_names: The (localized) names of the columns in the CSV output:
        filename, startx, starty, endx, endy, text.
    :return: The formatted output.
    """
    # Build tuples of the form (path, text, box, translation) for the removed texts.
    path_texts_coords: list[tuple[Path, str, st.Box, str]] = []
    for analytic in ocr_analytics:
        data_to_format = analytic.all_box_data if analytic.all_box_data else analytic.removed_box_data
        for text, box, translation in data_to_format:
            path_texts_coords.append((analytic.path, text, box, translation))

    if path_texts_coords:
        paths, texts, boxes, translations = zip(*path_texts_coords)
        paths = hp.trim_prefix_from_paths(paths)
        path_texts_coords = list(zip(paths, texts, boxes, translations))
        # Sort by path.
        path_texts_coords = natsorted(path_texts_coords, key=lambda x: x[0])

    if output_format == "csv":
        return format_output_csv(path_texts_coords, csv_column_names)
    if output_format == "json":
        return format_output_json(path_texts_coords)
    return format_output_plain(path_texts_coords)


def format_output_csv(
    path_texts_coords: list[tuple[Path, str, st.Box, str]],
    csv_column_names: tuple[str, str, str, str, str, str],
) -> str:
    buffer = StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(csv_column_names)

    for path, bubble, box, _ in path_texts_coords:
        if "\n" in bubble:
            logger.warning(f"Detected newline in bubble: {path} {bubble} {box}")
            bubble = bubble.replace("\n", "\\n")
        writer.writerow([path, *box.as_tuple, bubble])

    return buffer.getvalue()


def format_output_json(path_texts_coords: list[tuple[Path, str, st.Box, str]]) -> str:
    results = []
    for _, text, box, translation in path_texts_coords:
        w = box.x2 - box.x1
        h = box.y2 - box.y1
        aspect_ratio = round(w / h, 2) if h > 0 else 1.0
        
        # Calculate line count from text
        lines = [l for l in text.split('\n') if l.strip()]
        lines_cnt = max(1, len(lines))
        
        # Calculate suggested shape
        if aspect_ratio >= 2.0:
            shape_opt = 6
        elif lines_cnt == 1:
            shape_opt = 7
        elif lines_cnt == 2:
            shape_opt = 1
        elif lines_cnt == 3:
            shape_opt = 2
        elif lines_cnt == 4:
            shape_opt = 3
        elif lines_cnt == 5:
            shape_opt = 4
        elif lines_cnt >= 6:
            shape_opt = 5
        else:
            shape_opt = 8

        results.append(
            {
                "x": box.x1,
                "y": box.y1,
                "width": w,
                "height": h,
                "text": text,
                "translation": translation,
                "bubble_type": "text",
                "lines_count": lines_cnt,
                "shapeOption": shape_opt,
                "aspect_ratio": aspect_ratio
            }
        )

    # Sort results by Y coordinate first (top to bottom),
    # then by X coordinate (right to left for manga/Arabic).
    # We use a small threshold for Y to group bubbles on the same line.
    Y_THRESHOLD = 15
    results.sort(key=lambda b: (b["y"] // Y_THRESHOLD, -b["x"]))

    import json

    return json.dumps(results, indent=4, ensure_ascii=False)


def format_output_plain(path_texts_coords: list[tuple[Path, str, st.Box, str]]) -> str:
    # Place the file path on it's own line, and only if it's different from the previous one.
    buffer = StringIO()
    current_path = ""
    for path, bubble, _, _ in path_texts_coords:
        if path != current_path:
            buffer.write(f"\n\n{path}: ")
            current_path = path
        buffer.write(f"\n{bubble}")
        if "\n" in bubble:
            logger.warning(f"Detected newline in bubble: {path} {bubble}")

    return buffer.getvalue()
