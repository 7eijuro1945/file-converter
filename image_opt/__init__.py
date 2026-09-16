"""Local batch file converter and image optimizer."""

from .core import FileResult, Options, process_paths, summarize
from .pdf import convert_pdfs, summarize_pdf

__all__ = [
    "FileResult",
    "Options",
    "process_paths",
    "summarize",
    "convert_pdfs",
    "summarize_pdf",
]
