from __future__ import annotations

import contextlib
import io
import logging
import warnings
from pathlib import Path
from typing import Callable, Iterable

from .core import BatchSummary, FileResult, Options, _unique_path, format_bytes

ProgressCb = Callable[[int, int, FileResult], None]


def collect_pdfs(inputs: Iterable[Path], recursive: bool) -> list[tuple[Path, Path]]:
    found: list[tuple[Path, Path]] = []
    seen: set[Path] = set()
    for raw in inputs:
        path = Path(raw).expanduser().resolve()
        if not path.exists():
            continue
        if path.is_file():
            if path.suffix.lower() == ".pdf" and path not in seen:
                found.append((path, path.parent))
                seen.add(path)
            continue
        pattern = "**/*" if recursive else "*"
        for child in sorted(path.glob(pattern)):
            if child.is_file() and child.suffix.lower() == ".pdf" and child not in seen:
                found.append((child, path))
                seen.add(child)
    return found


def convert_pdfs(
    inputs: Iterable[Path],
    output_dir: Path,
    options: Options,
    progress: ProgressCb | None = None,
    start_page: int | None = None,
    end_page: int | None = None,
    password: str | None = None,
) -> BatchSummary:
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    jobs = collect_pdfs(inputs, options.recursive)
    summary = BatchSummary()
    total = len(jobs)
    for index, (src, root) in enumerate(jobs, start=1):
        dest = _destination_for(src, root, output_dir, options)
        result = convert_pdf_file(
            src,
            dest,
            options,
            start_page=start_page,
            end_page=end_page,
            password=password,
        )
        summary.results.append(result)
        if progress:
            progress(index, total, result)
    return summary


def convert_pdf_file(
    src: Path,
    dest: Path,
    options: Options,
    start_page: int | None = None,
    end_page: int | None = None,
    password: str | None = None,
) -> FileResult:
    src = Path(src)
    dest = Path(dest)
    bytes_in = src.stat().st_size
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            from pdf2docx import Converter
    except ImportError:
        return FileResult(
            src=src,
            dest=None,
            status="error",
            bytes_in=bytes_in,
            error="не встановлено pdf2docx — виконайте pip install -r requirements.txt",
        )
    _quiet_pdf_libs()

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    if tmp.exists():
        tmp.unlink()

    kwargs: dict = {}
    if start_page is not None:
        kwargs["start"] = max(0, start_page - 1)
    if end_page is not None:
        kwargs["end"] = max(0, end_page)

    try:
        converter = Converter(str(src), password=password)
        try:
            converter.convert(str(tmp), **kwargs)
        finally:
            converter.close()

        if not tmp.exists() or tmp.stat().st_size == 0:
            tmp.unlink(missing_ok=True)
            return FileResult(
                src=src,
                dest=None,
                status="error",
                bytes_in=bytes_in,
                error="конвертація не створила файл",
            )

        bytes_out = tmp.stat().st_size
        if dest.exists():
            dest.unlink()
        tmp.replace(dest)

        if options.replace_original and dest.resolve() != src.resolve():
            src.unlink()

        note = _page_note(start_page, end_page)
        return FileResult(
            src=src,
            dest=dest,
            status="ok",
            bytes_in=bytes_in,
            bytes_out=bytes_out,
            note=note,
        )
    except Exception as exc:  # noqa: BLE001
        tmp.unlink(missing_ok=True)
        return FileResult(
            src=src,
            dest=None,
            status="error",
            bytes_in=bytes_in,
            error=_friendly_pdf_error(exc),
        )


def summarize_pdf(summary: BatchSummary) -> str:
    return (
        f"готово: {summary.ok} конвертовано, {summary.skipped} пропущено, "
        f"{summary.errors} помилок"
    )


def result_line(result: FileResult) -> str:
    name = result.src.name
    if result.status == "ok" and result.dest is not None:
        extra = f" ({result.note})" if result.note else ""
        return (
            f"{name} -> {result.dest.name}  "
            f"{format_bytes(result.bytes_in)} -> {format_bytes(result.bytes_out)}{extra}"
        )
    if result.status == "larger":
        return f"{name}: пропущено ({result.note})"
    return f"{name}: помилка - {result.error}"


def _destination_for(src: Path, root: Path, output_dir: Path, options: Options) -> Path:
    rel = src.relative_to(root)
    stem = rel.stem + (options.suffix or "")
    dest = output_dir / rel.with_name(stem + ".docx")
    if not options.overwrite and dest.exists() and dest.resolve() != src.resolve():
        dest = _unique_path(dest)
    return dest


def _page_note(start_page: int | None, end_page: int | None) -> str:
    if start_page is None and end_page is None:
        return ""
    start = start_page or 1
    end = str(end_page) if end_page is not None else "кінець"
    return f"сторінки {start}-{end}"


def _quiet_pdf_libs() -> None:
    warnings.filterwarnings("ignore", message=r".*`fitz` API is deprecated.*")
    logging.basicConfig(level=logging.ERROR, format="[%(levelname)s] %(message)s", force=True)
    logging.getLogger().setLevel(logging.ERROR)
    for name in ("pdf2docx", "pdf2docx.converter"):
        logging.getLogger(name).setLevel(logging.ERROR)


def _friendly_pdf_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    lowered = text.lower()
    if "password" in lowered or "encrypted" in lowered:
        return "PDF захищено паролем"
    return text
