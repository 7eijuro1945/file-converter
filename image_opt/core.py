from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from PIL import Image, ImageOps, UnidentifiedImageError

SUPPORTED_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".jfif",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".gif",
    ".ico",
}

FORMAT_TARGETS = {
    "webp": ("WEBP", ".webp"),
    "jpeg": ("JPEG", ".jpg"),
    "jpg": ("JPEG", ".jpg"),
    "png": ("PNG", ".png"),
}

ProgressCb = Callable[[int, int, "FileResult"], None]


@dataclass
class Options:
    format: str = "webp"
    quality: int = 80
    max_width: int | None = None
    max_height: int | None = None
    lossless: bool = False
    strip_metadata: bool = True
    skip_if_larger: bool = True
    recursive: bool = False
    overwrite: bool = False
    suffix: str = ""
    replace_original: bool = False


@dataclass
class FileResult:
    src: Path
    dest: Path | None
    status: str
    bytes_in: int = 0
    bytes_out: int = 0
    width: int = 0
    height: int = 0
    out_width: int = 0
    out_height: int = 0
    error: str | None = None
    note: str = ""


@dataclass
class BatchSummary:
    results: list[FileResult] = field(default_factory=list)

    @property
    def ok(self) -> int:
        return sum(1 for r in self.results if r.status == "ok")

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status in {"skipped", "larger"})

    @property
    def errors(self) -> int:
        return sum(1 for r in self.results if r.status == "error")

    @property
    def bytes_in(self) -> int:
        return sum(r.bytes_in for r in self.results if r.status == "ok")

    @property
    def bytes_out(self) -> int:
        return sum(r.bytes_out for r in self.results if r.status == "ok")

    @property
    def saved(self) -> int:
        return self.bytes_in - self.bytes_out

    @property
    def saved_pct(self) -> float:
        if self.bytes_in <= 0:
            return 0.0
        return (self.saved / self.bytes_in) * 100


def collect_images(inputs: Iterable[Path], recursive: bool) -> list[tuple[Path, Path]]:
    found: list[tuple[Path, Path]] = []
    seen: set[Path] = set()
    for raw in inputs:
        path = Path(raw).expanduser().resolve()
        if not path.exists():
            continue
        if path.is_file():
            if _is_image(path) and path not in seen:
                found.append((path, path.parent))
                seen.add(path)
            continue
        pattern = "**/*" if recursive else "*"
        for child in sorted(path.glob(pattern)):
            if child.is_file() and _is_image(child) and child not in seen:
                found.append((child, path))
                seen.add(child)
    return found


def destination_for(src: Path, root: Path, output_dir: Path, options: Options) -> Path:
    rel = src.relative_to(root)
    _, suffix = _target_format(src, options)
    stem = rel.stem + (options.suffix or "")
    dest = output_dir / rel.with_name(stem + suffix)
    if not options.overwrite and dest.exists() and dest.resolve() != src.resolve():
        dest = _unique_path(dest)
    return dest


def process_paths(
    inputs: Iterable[Path],
    output_dir: Path,
    options: Options,
    progress: ProgressCb | None = None,
) -> BatchSummary:
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    jobs = collect_images(inputs, options.recursive)
    summary = BatchSummary()
    total = len(jobs)
    for index, (src, root) in enumerate(jobs, start=1):
        dest = destination_for(src, root, output_dir, options)
        result = process_file(src, dest, options)
        summary.results.append(result)
        if progress:
            progress(index, total, result)
    return summary


def process_file(src: Path, dest: Path, options: Options) -> FileResult:
    src = Path(src)
    dest = Path(dest)
    bytes_in = src.stat().st_size
    try:
        with Image.open(src) as img:
            img.load()
            img = ImageOps.exif_transpose(img) or img
            width, height = img.size
            note = ""
            if getattr(img, "n_frames", 1) > 1:
                img.seek(0)
                note = "лише перший кадр анімації"
                img = img.copy()

            img = _prepare_mode(img, src, options)
            img = _resize(img, options)
            dest.parent.mkdir(parents=True, exist_ok=True)

            tmp = dest.with_name(dest.name + ".tmp")
            _save(img, tmp, src, options)
            bytes_out = tmp.stat().st_size

            if options.skip_if_larger and bytes_out >= bytes_in:
                tmp.unlink(missing_ok=True)
                return FileResult(
                    src=src,
                    dest=None,
                    status="larger",
                    bytes_in=bytes_in,
                    bytes_out=bytes_in,
                    width=width,
                    height=height,
                    out_width=img.width,
                    out_height=img.height,
                    note="результат не менший за оригінал",
                )

            if dest.exists():
                dest.unlink()
            tmp.replace(dest)

            if options.replace_original and dest.resolve() != src.resolve():
                src.unlink()

            return FileResult(
                src=src,
                dest=dest,
                status="ok",
                bytes_in=bytes_in,
                bytes_out=bytes_out,
                width=width,
                height=height,
                out_width=img.width,
                out_height=img.height,
                note=note,
            )
    except UnidentifiedImageError:
        return FileResult(src=src, dest=None, status="error", bytes_in=bytes_in, error="не вдалося прочитати зображення")
    except Exception as exc:  # noqa: BLE001 — surface any encoder failure to the UI
        return FileResult(src=src, dest=None, status="error", bytes_in=bytes_in, error=str(exc))


def summarize(summary: BatchSummary) -> str:
    saved = format_bytes(summary.saved)
    pct = f"{summary.saved_pct:.1f}%"
    return (
        f"готово: {summary.ok} збережено, {summary.skipped} пропущено, "
        f"{summary.errors} помилок; економія {saved} ({pct})"
    )


def format_bytes(size: int) -> str:
    value = float(abs(size))
    units = ["B", "KB", "MB", "GB"]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            sign = "-" if size < 0 else ""
            if unit == "B":
                return f"{sign}{int(value)} {unit}"
            return f"{sign}{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def _is_image(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_SUFFIXES


def _unique_path(path: Path) -> Path:
    index = 1
    while True:
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _target_format(src: Path, options: Options) -> tuple[str, str]:
    key = options.format.lower().strip()
    if key != "keep":
        return FORMAT_TARGETS.get(key, FORMAT_TARGETS["webp"])

    suffix = src.suffix.lower()
    if suffix in {".jpg", ".jpeg", ".jfif"}:
        return "JPEG", ".jpg"
    if suffix == ".png":
        return "PNG", ".png"
    if suffix == ".webp":
        return "WEBP", ".webp"
    if suffix in {".tif", ".tiff"}:
        return "TIFF", suffix
    if suffix == ".bmp":
        return "BMP", ".bmp"
    if suffix == ".gif":
        return "GIF", ".gif"
    if suffix == ".ico":
        return "ICO", ".ico"
    return "PNG", suffix or ".png"


def _prepare_mode(img: Image.Image, src: Path, options: Options) -> Image.Image:
    fmt, _ = _target_format(src, options)

    if fmt == "JPEG":
        if img.mode in {"RGBA", "LA"} or (img.mode == "P" and "transparency" in img.info):
            rgba = img.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.split()[-1])
            return background
        return img.convert("RGB")

    if img.mode == "P":
        return img.convert("RGBA" if "transparency" in img.info else "RGB")
    if img.mode == "CMYK":
        return img.convert("RGB")
    return img


def _resize(img: Image.Image, options: Options) -> Image.Image:
    max_w = options.max_width or img.width
    max_h = options.max_height or img.height
    if max_w <= 0 or max_h <= 0:
        return img
    if img.width <= max_w and img.height <= max_h:
        return img
    clone = img.copy()
    clone.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    return clone


def _save(img: Image.Image, dest: Path, src: Path, options: Options) -> None:
    fmt, _ = _target_format(src, options)
    quality = max(1, min(100, options.quality))
    save_kwargs: dict = {"format": fmt}

    if not options.strip_metadata:
        for key in ("exif", "icc_profile"):
            if key in img.info:
                save_kwargs[key] = img.info[key]

    if fmt == "WEBP":
        save_kwargs.update(
            quality=quality,
            method=6,
            lossless=options.lossless,
        )
    elif fmt == "JPEG":
        save_kwargs.update(
            quality=quality,
            optimize=True,
            progressive=True,
            subsampling=0 if quality >= 90 else 2,
        )
    elif fmt == "PNG":
        save_kwargs.update(optimize=True, compress_level=9)

    if options.strip_metadata:
        clean = img.copy()
        clean.info.pop("exif", None)
        clean.save(dest, **save_kwargs)
        return
    img.save(dest, **save_kwargs)
