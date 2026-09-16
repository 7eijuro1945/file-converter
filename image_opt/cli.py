from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core import Options, format_bytes, process_paths, summarize
from .pdf import convert_pdfs, result_line as pdf_result_line, summarize_pdf


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv == ["--gui"] or argv == ["-g"]:
        from .gui import run_gui

        run_gui()
        return 0

    parser = argparse.ArgumentParser(
        prog="image_opt",
        description="Пакетне стискання зображень і конвертація PDF у Word.",
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="Файли або папки")
    parser.add_argument("-o", "--output", type=Path, help="Папка для результатів")
    parser.add_argument(
        "-f",
        "--format",
        choices=["webp", "jpeg", "png", "keep"],
        default="webp",
        help="Цільовий формат зображень (типово webp)",
    )
    parser.add_argument("-q", "--quality", type=int, default=80, help="Якість 1–100")
    parser.add_argument("--max-width", type=int, help="Максимальна ширина, px")
    parser.add_argument("--max-height", type=int, help="Максимальна висота, px")
    parser.add_argument("-r", "--recursive", action="store_true", help="Обходити вкладені папки")
    parser.add_argument("--lossless", action="store_true", help="WebP без втрат")
    parser.add_argument("--keep-metadata", action="store_true", help="Зберегти EXIF/ICC")
    parser.add_argument("--overwrite", action="store_true", help="Перезаписувати існуючі файли")
    parser.add_argument("--always-write", action="store_true", help="Зберігати навіть якщо файл більший")
    parser.add_argument("--suffix", default="", help="Суфікс до імені, наприклад _opt")
    parser.add_argument("--replace", action="store_true", help="Видалити оригінал після успішної обробки")
    parser.add_argument("--pdf-to-word", action="store_true", help="Конвертувати PDF у DOCX")
    parser.add_argument("--start-page", type=int, help="Перша сторінка PDF (з 1)")
    parser.add_argument("--end-page", type=int, help="Остання сторінка PDF (включно)")
    parser.add_argument("--password", help="Пароль до PDF")
    parser.add_argument("--gui", "-g", action="store_true", help="Відкрити вікно")
    args = parser.parse_args(argv)

    if args.gui:
        from .gui import run_gui

        run_gui()
        return 0

    if args.pdf_to_word:
        return _run_pdf(args)

    output = args.output or _default_output(args.inputs)
    options = Options(
        format=args.format,
        quality=args.quality,
        max_width=args.max_width,
        max_height=args.max_height,
        lossless=args.lossless,
        strip_metadata=not args.keep_metadata,
        skip_if_larger=not args.always_write,
        recursive=args.recursive,
        overwrite=args.overwrite,
        suffix=args.suffix,
        replace_original=args.replace,
    )

    def on_progress(index: int, total: int, result) -> None:
        name = result.src.name
        if result.status == "ok" and result.dest is not None:
            saved = format_bytes(result.bytes_in - result.bytes_out)
            print(f"[{index}/{total}] {name} -> {result.dest.name}  -{saved}")
        elif result.status == "larger":
            print(f"[{index}/{total}] {name}: пропущено ({result.note})")
        else:
            print(f"[{index}/{total}] {name}: помилка - {result.error}")

    summary = process_paths(args.inputs, output, options, progress=on_progress)
    if not summary.results:
        print("не знайдено зображень у вказаних шляхах")
        return 1
    print(summarize(summary))
    print(f"вихід: {output}")
    return 1 if summary.errors else 0


def _run_pdf(args: argparse.Namespace) -> int:
    output = args.output or _default_output(args.inputs, folder="converted")
    options = Options(
        recursive=args.recursive,
        overwrite=args.overwrite,
        suffix=args.suffix,
        replace_original=args.replace,
    )

    def on_progress(index: int, total: int, result) -> None:
        print(f"[{index}/{total}] {pdf_result_line(result)}")

    summary = convert_pdfs(
        args.inputs,
        output,
        options,
        progress=on_progress,
        start_page=args.start_page,
        end_page=args.end_page,
        password=args.password,
    )
    if not summary.results:
        print("не знайдено PDF у вказаних шляхах")
        return 1
    print(summarize_pdf(summary))
    print(f"вихід: {output}")
    return 1 if summary.errors else 0


def _default_output(inputs: list[Path], folder: str = "optimized") -> Path:
    first = Path(inputs[0]).expanduser().resolve()
    parent = first.parent if first.is_file() else first
    return parent / folder


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
