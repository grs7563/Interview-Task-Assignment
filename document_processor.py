#!/usr/bin/env python3
"""
Multi-Format Document Processing System
=======================================
Accepts: PDF, JPG, PNG, TIFF, XLSX, XLS, CSV
- Digital PDFs  → text extraction (pdfplumber)
- Scanned PDFs / Images → OCR (Tesseract) with preprocessing
- Spreadsheets  → structured parsing (openpyxl / pandas)
Handles: multi-page PDFs, multi-sheet workbooks, poor image quality,
         corrupted files, mixed batches.

Author: Document Intelligence Module
"""

from __future__ import annotations

import os
import sys
import json
import logging
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Core libraries
import pdfplumber
from pdf2image import convert_from_path
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import pytesseract
import pandas as pd
from openpyxl import load_workbook

# ---------------------------------------------------------------------------
# Configuration & Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("DocProcessor")

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp",
    ".xlsx", ".xls", ".csv",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
SPREADSHEET_EXTENSIONS = {".xlsx", ".xls", ".csv"}

# OCR settings
OCR_LANG = "eng"
OCR_CONFIG = "--oem 3 --psm 6"          # LSTM + assume uniform block of text
MIN_CONFIDENCE = 30                     # filter very low-confidence words (optional)


# ---------------------------------------------------------------------------
# Result data structures
# ---------------------------------------------------------------------------

@dataclass
class PageResult:
    page_number: int
    text: str
    method: str                         # "digital" | "ocr"
    confidence: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    error: Optional[str] = None


@dataclass
class SheetResult:
    sheet_name: str
    headers: List[str]
    rows: List[List[Any]]
    row_count: int
    column_count: int
    error: Optional[str] = None


@dataclass
class FileResult:
    file_path: str
    file_name: str
    file_type: str
    success: bool
    processing_time_sec: float
    pages: List[PageResult] = field(default_factory=list)
    sheets: List[SheetResult] = field(default_factory=list)
    full_text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class BatchResult:
    processed_at: str
    total_files: int
    successful: int
    failed: int
    results: List[FileResult]
    summary: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Image preprocessing (helps with poor quality / scanned documents)
# ---------------------------------------------------------------------------

def preprocess_image(img: Image.Image, aggressive: bool = False) -> Image.Image:
    """
    Improve OCR accuracy on low-quality / scanned images.
    Uses only Pillow (no OpenCV dependency).
    """
    # Convert to grayscale
    if img.mode != "L":
        img = img.convert("L")

    # Auto-contrast
    img = ImageOps.autocontrast(img, cutoff=2)

    # Mild denoise
    img = img.filter(ImageFilter.MedianFilter(size=3))

    if aggressive:
        # Sharpen
        img = img.filter(ImageFilter.SHARPEN)
        # Increase contrast
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.5)
        # Slight brightness boost if very dark
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(1.1)

    return img


def ocr_image(img: Image.Image, preprocess: bool = True) -> Tuple[str, float]:
    """
    Run Tesseract OCR on a PIL Image.
    Returns (text, average_confidence).
    """
    if preprocess:
        # Try normal first, fall back to aggressive if text is very short
        processed = preprocess_image(img, aggressive=False)
        data = pytesseract.image_to_data(processed, lang=OCR_LANG, config=OCR_CONFIG, output_type=pytesseract.Output.DICT)
        text = pytesseract.image_to_string(processed, lang=OCR_LANG, config=OCR_CONFIG).strip()

        if len(text) < 30:  # probably bad quality → try aggressive
            processed = preprocess_image(img, aggressive=True)
            data = pytesseract.image_to_data(processed, lang=OCR_LANG, config=OCR_CONFIG, output_type=pytesseract.Output.DICT)
            text = pytesseract.image_to_string(processed, lang=OCR_LANG, config=OCR_CONFIG).strip()
    else:
        data = pytesseract.image_to_data(img, lang=OCR_LANG, config=OCR_CONFIG, output_type=pytesseract.Output.DICT)
        text = pytesseract.image_to_string(img, lang=OCR_LANG, config=OCR_CONFIG).strip()

    # Calculate average confidence of non-empty words
    confidences = [int(c) for c, t in zip(data["conf"], data["text"]) if t.strip() and int(c) >= 0]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

    return text, avg_conf


# ---------------------------------------------------------------------------
# PDF processing
# ---------------------------------------------------------------------------

def is_scanned_page(page) -> bool:
    """Heuristic: if almost no extractable text → treat as scanned."""
    text = page.extract_text() or ""
    return len(text.strip()) < 20


def process_pdf(file_path: Path) -> FileResult:
    start = datetime.now()
    result = FileResult(
        file_path=str(file_path),
        file_name=file_path.name,
        file_type="pdf",
        success=False,
        processing_time_sec=0.0,
    )

    try:
        with pdfplumber.open(file_path) as pdf:
            result.metadata["page_count"] = len(pdf.pages)
            result.metadata["is_encrypted"] = pdf.metadata.get("Encrypt") is not None if pdf.metadata else False

            for i, page in enumerate(pdf.pages, start=1):
                page_res = PageResult(page_number=i, text="", method="digital")

                try:
                    if is_scanned_page(page):
                        # Convert this page to image and OCR
                        logger.info(f"  Page {i}: low text → OCR")
                        images = convert_from_path(
                            file_path,
                            first_page=i,
                            last_page=i,
                            dpi=200,
                            fmt="png",
                        )
                        if images:
                            text, conf = ocr_image(images[0], preprocess=True)
                            page_res.text = text
                            page_res.method = "ocr"
                            page_res.confidence = round(conf, 1)
                            page_res.width, page_res.height = images[0].size
                        else:
                            page_res.error = "Failed to rasterize page"
                            result.warnings.append(f"Page {i}: rasterization failed")
                    else:
                        text = page.extract_text() or ""
                        page_res.text = text.strip()
                        page_res.method = "digital"
                        # Also try tables if present
                        tables = page.extract_tables()
                        if tables:
                            result.metadata.setdefault("tables_found", 0)
                            result.metadata["tables_found"] += len(tables)

                except Exception as e:
                    page_res.error = str(e)
                    result.errors.append(f"Page {i}: {e}")
                    logger.warning(f"  Page {i} error: {e}")

                result.pages.append(page_res)

            # Combine all page text
            result.full_text = "\n\n--- PAGE BREAK ---\n\n".join(
                p.text for p in result.pages if p.text
            )
            result.success = True

    except Exception as e:
        result.errors.append(f"PDF open/process failed: {e}")
        result.success = False
        logger.error(f"PDF error [{file_path.name}]: {e}")

    result.processing_time_sec = (datetime.now() - start).total_seconds()
    return result


# ---------------------------------------------------------------------------
# Image processing (JPG, PNG, TIFF, ...)
# ---------------------------------------------------------------------------

def process_image(file_path: Path) -> FileResult:
    start = datetime.now()
    result = FileResult(
        file_path=str(file_path),
        file_name=file_path.name,
        file_type=file_path.suffix.lower().lstrip("."),
        success=False,
        processing_time_sec=0.0,
    )

    try:
        with Image.open(file_path) as img:
            # Handle multi-frame TIFF
            n_frames = getattr(img, "n_frames", 1)
            result.metadata["frame_count"] = n_frames
            result.metadata["original_mode"] = img.mode
            result.metadata["original_size"] = img.size

            frames_text = []
            for frame_idx in range(n_frames):
                try:
                    if n_frames > 1:
                        img.seek(frame_idx)
                    # Work on a copy
                    frame = img.copy()
                    text, conf = ocr_image(frame, preprocess=True)

                    page_res = PageResult(
                        page_number=frame_idx + 1,
                        text=text,
                        method="ocr",
                        confidence=round(conf, 1),
                        width=frame.width,
                        height=frame.height,
                    )
                    result.pages.append(page_res)
                    frames_text.append(text)

                except Exception as e:
                    result.errors.append(f"Frame {frame_idx + 1}: {e}")
                    result.pages.append(PageResult(
                        page_number=frame_idx + 1,
                        text="",
                        method="ocr",
                        error=str(e),
                    ))

            result.full_text = "\n\n--- FRAME BREAK ---\n\n".join(frames_text)
            result.success = len(result.errors) == 0 or any(p.text for p in result.pages)

    except Exception as e:
        result.errors.append(f"Image open/process failed: {e}")
        result.success = False
        logger.error(f"Image error [{file_path.name}]: {e}")

    result.processing_time_sec = (datetime.now() - start).total_seconds()
    return result


# ---------------------------------------------------------------------------
# Spreadsheet processing (XLSX, XLS, CSV)
# ---------------------------------------------------------------------------

def process_spreadsheet(file_path: Path) -> FileResult:
    start = datetime.now()
    ext = file_path.suffix.lower()
    result = FileResult(
        file_path=str(file_path),
        file_name=file_path.name,
        file_type=ext.lstrip("."),
        success=False,
        processing_time_sec=0.0,
    )

    try:
        if ext == ".csv":
            # Robust CSV reading – handle irregular / mixed-structure CSVs
            encoding_used = None
            df = None
            for encoding in ("utf-8", "latin-1", "cp1252", "utf-16"):
                try:
                    # First try normal parse
                    df = pd.read_csv(
                        file_path,
                        encoding=encoding,
                        dtype=str,
                        keep_default_na=False,
                        on_bad_lines="warn",   # pandas >= 1.3
                    )
                    encoding_used = encoding
                    break
                except TypeError:
                    # older pandas – fallback
                    try:
                        df = pd.read_csv(
                            file_path,
                            encoding=encoding,
                            dtype=str,
                            keep_default_na=False,
                            error_bad_lines=False,
                            warn_bad_lines=True,
                        )
                        encoding_used = encoding
                        break
                    except Exception:
                        continue
                except UnicodeDecodeError:
                    continue
                except Exception:
                    # Last resort: read as pure text lines
                    try:
                        with open(file_path, "r", encoding=encoding, errors="replace") as f:
                            lines = [line.rstrip("\n") for line in f]
                        result.full_text = "\n".join(lines)
                        result.sheets.append(SheetResult(
                            sheet_name="Sheet1 (raw)",
                            headers=["raw_line"],
                            rows=[[ln] for ln in lines],
                            row_count=len(lines),
                            column_count=1,
                        ))
                        result.metadata["encoding_used"] = encoding
                        result.metadata["parse_mode"] = "raw_lines"
                        result.success = True
                        result.warnings.append("CSV had irregular structure – stored as raw lines")
                        break
                    except Exception:
                        continue
            else:
                if not result.success:
                    raise ValueError("Could not decode or parse CSV with common encodings")

            if df is not None and not result.success:
                headers = list(df.columns.astype(str))
                rows = df.values.tolist()
                sheet = SheetResult(
                    sheet_name="Sheet1",
                    headers=headers,
                    rows=rows,
                    row_count=len(rows),
                    column_count=len(headers),
                )
                result.sheets.append(sheet)
                result.full_text = df.to_string(index=False)
                result.metadata["encoding_used"] = encoding_used
                result.success = True

        elif ext == ".xlsx":
            wb = load_workbook(file_path, data_only=True, read_only=True)
            result.metadata["sheet_names"] = wb.sheetnames

            for sheet_name in wb.sheetnames:
                try:
                    ws = wb[sheet_name]
                    data = list(ws.values)
                    if not data:
                        result.sheets.append(SheetResult(
                            sheet_name=sheet_name,
                            headers=[],
                            rows=[],
                            row_count=0,
                            column_count=0,
                        ))
                        continue

                    headers = [str(c) if c is not None else "" for c in data[0]]
                    rows = []
                    for row in data[1:]:
                        rows.append(["" if c is None else c for c in row])

                    result.sheets.append(SheetResult(
                        sheet_name=sheet_name,
                        headers=headers,
                        rows=rows,
                        row_count=len(rows),
                        column_count=len(headers),
                    ))
                except Exception as e:
                    result.errors.append(f"Sheet '{sheet_name}': {e}")
                    result.sheets.append(SheetResult(
                        sheet_name=sheet_name,
                        headers=[],
                        rows=[],
                        row_count=0,
                        column_count=0,
                        error=str(e),
                    ))

            # Full text representation
            texts = []
            for s in result.sheets:
                texts.append(f"=== Sheet: {s.sheet_name} ===")
                if s.headers:
                    texts.append(" | ".join(s.headers))
                for row in s.rows[:50]:  # limit preview
                    texts.append(" | ".join(str(c) for c in row))
                if s.row_count > 50:
                    texts.append(f"... ({s.row_count - 50} more rows)")
            result.full_text = "\n".join(texts)
            result.success = True
            wb.close()

        elif ext == ".xls":
            # Legacy .xls – try pandas with xlrd if available, else clear error
            try:
                xls = pd.ExcelFile(file_path, engine="xlrd")
                result.metadata["sheet_names"] = xls.sheet_names
                for sheet_name in xls.sheet_names:
                    df = pd.read_excel(xls, sheet_name=sheet_name, dtype=str, keep_default_na=False)
                    headers = list(df.columns.astype(str))
                    rows = df.values.tolist()
                    result.sheets.append(SheetResult(
                        sheet_name=sheet_name,
                        headers=headers,
                        rows=rows,
                        row_count=len(rows),
                        column_count=len(headers),
                    ))
                result.full_text = "\n\n".join(
                    f"=== {s.sheet_name} ===\n" + "\n".join(
                        [" | ".join(s.headers)] + [" | ".join(str(c) for c in r) for r in s.rows[:30]]
                    )
                    for s in result.sheets
                )
                result.success = True
            except ImportError:
                result.errors.append(
                    "Legacy .xls support requires 'xlrd'. "
                    "Please convert to .xlsx or install xlrd."
                )
                result.warnings.append("Skipped .xls file – engine not available")
            except Exception as e:
                result.errors.append(f".xls parse failed: {e}")

    except Exception as e:
        result.errors.append(f"Spreadsheet process failed: {e}")
        result.success = False
        logger.error(f"Spreadsheet error [{file_path.name}]: {e}")

    result.processing_time_sec = (datetime.now() - start).total_seconds()
    return result


# ---------------------------------------------------------------------------
# Main dispatcher & batch processor
# ---------------------------------------------------------------------------

def process_file(file_path: Union[str, Path]) -> FileResult:
    """Process a single file of any supported type."""
    path = Path(file_path)
    if not path.exists():
        return FileResult(
            file_path=str(path),
            file_name=path.name,
            file_type="unknown",
            success=False,
            processing_time_sec=0.0,
            errors=[f"File not found: {path}"],
        )

    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return FileResult(
            file_path=str(path),
            file_name=path.name,
            file_type=ext.lstrip(".") or "unknown",
            success=False,
            processing_time_sec=0.0,
            errors=[f"Unsupported file type: {ext}"],
        )

    logger.info(f"Processing: {path.name}")

    try:
        if ext == ".pdf":
            return process_pdf(path)
        elif ext in IMAGE_EXTENSIONS:
            return process_image(path)
        elif ext in SPREADSHEET_EXTENSIONS:
            return process_spreadsheet(path)
        else:
            return FileResult(
                file_path=str(path),
                file_name=path.name,
                file_type=ext.lstrip("."),
                success=False,
                processing_time_sec=0.0,
                errors=[f"No handler for {ext}"],
            )
    except Exception as e:
        logger.exception(f"Unexpected error on {path.name}")
        return FileResult(
            file_path=str(path),
            file_name=path.name,
            file_type=ext.lstrip("."),
            success=False,
            processing_time_sec=0.0,
            errors=[f"Unexpected error: {e}", traceback.format_exc()],
        )


def process_batch(
    file_paths: List[Union[str, Path]],
    max_workers: int = 4,
) -> BatchResult:
    """
    Process multiple files (optionally in parallel).
    Returns a BatchResult with all individual results + summary.
    """
    start = datetime.now()
    results: List[FileResult] = []

    # Sequential is safer for memory (large PDFs / images); parallel optional
    if max_workers <= 1:
        for fp in file_paths:
            results.append(process_file(fp))
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(process_file, fp): fp for fp in file_paths}
            for future in as_completed(future_map):
                results.append(future.result())

    # Sort back to original order
    name_order = {Path(p).name: i for i, p in enumerate(file_paths)}
    results.sort(key=lambda r: name_order.get(r.file_name, 999))

    successful = sum(1 for r in results if r.success)
    failed = len(results) - successful

    summary = {
        "total_pages_or_frames": sum(len(r.pages) for r in results),
        "total_sheets": sum(len(r.sheets) for r in results),
        "ocr_pages": sum(1 for r in results for p in r.pages if p.method == "ocr"),
        "digital_pages": sum(1 for r in results for p in r.pages if p.method == "digital"),
        "total_processing_sec": round((datetime.now() - start).total_seconds(), 2),
        "file_types": {},
    }
    for r in results:
        summary["file_types"][r.file_type] = summary["file_types"].get(r.file_type, 0) + 1

    return BatchResult(
        processed_at=datetime.now().isoformat(timespec="seconds"),
        total_files=len(results),
        successful=successful,
        failed=failed,
        results=results,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def result_to_dict(obj) -> Any:
    """Convert dataclasses to plain dicts for JSON serialization."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: result_to_dict(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [result_to_dict(i) for i in obj]
    if isinstance(obj, dict):
        return {k: result_to_dict(v) for k, v in obj.items()}
    return obj


def save_results(batch: BatchResult, output_dir: Path) -> Dict[str, str]:
    """
    Save:
      - full JSON report
      - one .txt per successful file (extracted text)
      - summary CSV
    Returns dict of created file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    created = {}

    # 1. Full JSON
    json_path = output_dir / "batch_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result_to_dict(batch), f, indent=2, ensure_ascii=False, default=str)
    created["json"] = str(json_path)

    # 2. Individual text extracts
    texts_dir = output_dir / "extracted_texts"
    texts_dir.mkdir(exist_ok=True)
    for r in batch.results:
        if r.success and r.full_text.strip():
            safe_name = Path(r.file_name).stem + "_extracted.txt"
            txt_path = texts_dir / safe_name
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(f"Source: {r.file_name}\n")
                f.write(f"Type: {r.file_type} | Method summary: ")
                methods = {p.method for p in r.pages} if r.pages else {"spreadsheet"}
                f.write(", ".join(methods) + "\n")
                f.write("=" * 60 + "\n\n")
                f.write(r.full_text)
            created[f"text_{r.file_name}"] = str(txt_path)

    # 3. Summary CSV
    summary_rows = []
    for r in batch.results:
        summary_rows.append({
            "file_name": r.file_name,
            "file_type": r.file_type,
            "success": r.success,
            "pages_or_frames": len(r.pages),
            "sheets": len(r.sheets),
            "processing_sec": round(r.processing_time_sec, 2),
            "error_count": len(r.errors),
            "warnings": "; ".join(r.warnings) if r.warnings else "",
            "primary_errors": "; ".join(r.errors[:2]) if r.errors else "",
        })
    df = pd.DataFrame(summary_rows)
    csv_path = output_dir / "batch_summary.csv"
    df.to_csv(csv_path, index=False)
    created["summary_csv"] = str(csv_path)

    return created


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None):
    import argparse

    parser = argparse.ArgumentParser(
        description="Multi-format document text/OCR/spreadsheet extractor"
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="One or more PDF / image / spreadsheet files",
    )
    parser.add_argument(
        "-o", "--output",
        default="./output",
        help="Output directory for results (default: ./output)",
    )
    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=2,
        help="Parallel workers (1 = sequential, safer for large files)",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Only write the full JSON report",
    )

    args = parser.parse_args(argv)

    print("=" * 60)
    print("  Multi-Format Document Processor")
    print("=" * 60)
    print(f"Files to process : {len(args.files)}")
    print(f"Output directory : {args.output}")
    print(f"Workers          : {args.workers}")
    print("-" * 60)

    batch = process_batch(args.files, max_workers=args.workers)

    print(f"\nProcessed : {batch.total_files}")
    print(f"Successful: {batch.successful}")
    print(f"Failed    : {batch.failed}")
    print(f"Time      : {batch.summary.get('total_processing_sec', 0)} s")
    print(f"OCR pages : {batch.summary.get('ocr_pages', 0)}")
    print(f"Digital   : {batch.summary.get('digital_pages', 0)}")

    out_dir = Path(args.output)
    created = save_results(batch, out_dir)

    print("\nCreated files:")
    for k, v in created.items():
        print(f"  • {v}")

    # Also print short per-file status
    print("\nPer-file status:")
    for r in batch.results:
        status = "✓" if r.success else "✗"
        extra = f"({len(r.pages)} pages)" if r.pages else f"({len(r.sheets)} sheets)"
        print(f"  {status} {r.file_name:40s} {extra:15s} {r.processing_time_sec:.1f}s")
        if r.errors:
            for e in r.errors[:2]:
                print(f"      ⚠ {e[:80]}")

    return 0 if batch.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
