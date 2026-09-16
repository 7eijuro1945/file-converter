from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .core import Options, format_bytes, process_paths, summarize
from .pdf import convert_pdfs, result_line as pdf_result_line, summarize_pdf


def run_gui() -> None:
    App().mainloop()


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Конвертер файлів")
        self.minsize(560, 680)
        self.geometry("660x760")
        self.inputs: list[Path] = []
        self.pdf_inputs: list[Path] = []
        self._queue: queue.Queue = queue.Queue()
        self._busy = False

        self.output_var = tk.StringVar()
        self.format_var = tk.StringVar(value="webp")
        self.quality_var = tk.IntVar(value=80)
        self.max_width_var = tk.StringVar()
        self.max_height_var = tk.StringVar()
        self.recursive_var = tk.BooleanVar(value=True)
        self.lossless_var = tk.BooleanVar(value=False)
        self.strip_var = tk.BooleanVar(value=True)
        self.skip_larger_var = tk.BooleanVar(value=True)
        self.overwrite_var = tk.BooleanVar(value=False)
        self.pdf_output_var = tk.StringVar()
        self.pdf_recursive_var = tk.BooleanVar(value=True)
        self.pdf_overwrite_var = tk.BooleanVar(value=False)
        self.pdf_start_var = tk.StringVar()
        self.pdf_end_var = tk.StringVar()
        self.pdf_password_var = tk.StringVar()
        self.progress_var = tk.DoubleVar(value=0)
        self.status_var = tk.StringVar(value="Оберіть файли: зображення або PDF")

        self._build()
        self.after(80, self._poll_queue)

    def _build(self) -> None:
        pad = {"padx": 14, "pady": 6}
        root = ttk.Frame(self, padding=12)
        root.pack(fill=tk.BOTH, expand=True)

        ttk.Label(root, text="Локальний конвертер і оптимізатор", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(
            root,
            text="Стискає скріншоти, конвертує PNG/JPG у WebP і перетворює PDF на Word (DOCX).",
            wraplength=620,
        ).pack(anchor="w", pady=(0, 8))

        notebook = ttk.Notebook(root)
        notebook.pack(fill=tk.BOTH, expand=True)
        images = ttk.Frame(notebook, padding=8)
        pdfs = ttk.Frame(notebook, padding=8)
        notebook.add(images, text="Зображення")
        notebook.add(pdfs, text="PDF → Word")

        self._build_images_tab(images, pad)
        self._build_pdf_tab(pdfs)

        self.progress = ttk.Progressbar(root, variable=self.progress_var, maximum=100)
        self.progress.pack(fill=tk.X, padx=14, pady=(8, 4))
        ttk.Label(root, textvariable=self.status_var).pack(anchor="w", padx=14)

        log_frame = ttk.LabelFrame(root, text="Журнал", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=(4, 8))
        self.log = tk.Text(log_frame, height=8, wrap="word", state=tk.DISABLED)
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        try:
            self.tk.call("tk", "scaling", 1.2)
        except tk.TclError:
            pass

    def _build_images_tab(self, parent: ttk.Frame, pad: dict) -> None:
        io = ttk.LabelFrame(parent, text="Файли", padding=10)
        io.pack(fill=tk.X, **pad)

        btns = ttk.Frame(io)
        btns.pack(fill=tk.X)
        ttk.Button(btns, text="Додати файли…", command=self._add_files).pack(side=tk.LEFT)
        ttk.Button(btns, text="Додати папку…", command=self._add_folder).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Очистити", command=self._clear_inputs).pack(side=tk.LEFT)

        self.listbox = tk.Listbox(io, height=5, selectmode=tk.EXTENDED)
        self.listbox.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        out = ttk.Frame(io)
        out.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(out, text="Зберегти в:").pack(side=tk.LEFT)
        ttk.Entry(out, textvariable=self.output_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        ttk.Button(out, text="Огляд…", command=self._pick_output).pack(side=tk.LEFT)

        opts = ttk.LabelFrame(parent, text="Параметри", padding=10)
        opts.pack(fill=tk.X, **pad)

        row1 = ttk.Frame(opts)
        row1.pack(fill=tk.X)
        ttk.Label(row1, text="Формат").pack(side=tk.LEFT)
        ttk.Combobox(
            row1,
            textvariable=self.format_var,
            values=["webp", "jpeg", "png", "keep"],
            state="readonly",
            width=10,
        ).pack(side=tk.LEFT, padx=8)
        ttk.Label(row1, text="Якість").pack(side=tk.LEFT, padx=(12, 0))
        self.quality_label = ttk.Label(row1, text="80", width=4)
        self.quality_label.pack(side=tk.RIGHT)
        scale = ttk.Scale(row1, from_=1, to=100, variable=self.quality_var, command=self._on_quality)
        scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)

        row2 = ttk.Frame(opts)
        row2.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(row2, text="Макс. ширина").pack(side=tk.LEFT)
        ttk.Entry(row2, textvariable=self.max_width_var, width=8).pack(side=tk.LEFT, padx=6)
        ttk.Label(row2, text="Макс. висота").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Entry(row2, textvariable=self.max_height_var, width=8).pack(side=tk.LEFT, padx=6)
        ttk.Label(row2, text="px  (порожньо = без зміни)").pack(side=tk.LEFT)

        flags = ttk.Frame(opts)
        flags.pack(fill=tk.X, pady=(8, 0))
        ttk.Checkbutton(flags, text="Рекурсивно", variable=self.recursive_var).pack(side=tk.LEFT)
        ttk.Checkbutton(flags, text="WebP без втрат", variable=self.lossless_var).pack(side=tk.LEFT, padx=10)
        ttk.Checkbutton(flags, text="Прибрати метадані", variable=self.strip_var).pack(side=tk.LEFT)
        flags2 = ttk.Frame(opts)
        flags2.pack(fill=tk.X, pady=(4, 0))
        ttk.Checkbutton(flags2, text="Не зберігати, якщо більше за оригінал", variable=self.skip_larger_var).pack(side=tk.LEFT)
        ttk.Checkbutton(flags2, text="Перезаписувати", variable=self.overwrite_var).pack(side=tk.LEFT, padx=10)

        actions = ttk.Frame(parent)
        actions.pack(fill=tk.X, **pad)
        self.run_btn = ttk.Button(actions, text="Оптимізувати", command=self._start)
        self.run_btn.pack(side=tk.LEFT)
        ttk.Button(actions, text="Пресет: скріншоти", command=self._preset_screenshots).pack(side=tk.LEFT, padx=8)
        ttk.Button(actions, text="Пресет: агресивно", command=self._preset_aggressive).pack(side=tk.LEFT)

    def _build_pdf_tab(self, parent: ttk.Frame) -> None:
        io = ttk.LabelFrame(parent, text="PDF-файли", padding=10)
        io.pack(fill=tk.X, pady=6)

        btns = ttk.Frame(io)
        btns.pack(fill=tk.X)
        ttk.Button(btns, text="Додати PDF…", command=self._add_pdf_files).pack(side=tk.LEFT)
        ttk.Button(btns, text="Додати папку…", command=self._add_pdf_folder).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Очистити", command=self._clear_pdf_inputs).pack(side=tk.LEFT)

        self.pdf_listbox = tk.Listbox(io, height=6, selectmode=tk.EXTENDED)
        self.pdf_listbox.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        out = ttk.Frame(io)
        out.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(out, text="Зберегти в:").pack(side=tk.LEFT)
        ttk.Entry(out, textvariable=self.pdf_output_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        ttk.Button(out, text="Огляд…", command=self._pick_pdf_output).pack(side=tk.LEFT)

        opts = ttk.LabelFrame(parent, text="Параметри Word", padding=10)
        opts.pack(fill=tk.X, pady=6)

        pages = ttk.Frame(opts)
        pages.pack(fill=tk.X)
        ttk.Label(pages, text="Сторінки з").pack(side=tk.LEFT)
        ttk.Entry(pages, textvariable=self.pdf_start_var, width=6).pack(side=tk.LEFT, padx=6)
        ttk.Label(pages, text="по").pack(side=tk.LEFT)
        ttk.Entry(pages, textvariable=self.pdf_end_var, width=6).pack(side=tk.LEFT, padx=6)
        ttk.Label(pages, text="(порожньо = усі)").pack(side=tk.LEFT)

        pwd = ttk.Frame(opts)
        pwd.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(pwd, text="Пароль PDF").pack(side=tk.LEFT)
        ttk.Entry(pwd, textvariable=self.pdf_password_var, show="*", width=24).pack(side=tk.LEFT, padx=8)

        flags = ttk.Frame(opts)
        flags.pack(fill=tk.X, pady=(8, 0))
        ttk.Checkbutton(flags, text="Рекурсивно", variable=self.pdf_recursive_var).pack(side=tk.LEFT)
        ttk.Checkbutton(flags, text="Перезаписувати", variable=self.pdf_overwrite_var).pack(side=tk.LEFT, padx=10)

        ttk.Label(
            opts,
            text="Текстові PDF зберігають абзаци й таблиці краще. Скани без шару тексту вийдуть як зображення на сторінках.",
            wraplength=580,
        ).pack(anchor="w", pady=(8, 0))

        actions = ttk.Frame(parent)
        actions.pack(fill=tk.X, pady=6)
        self.pdf_run_btn = ttk.Button(actions, text="Конвертувати в Word", command=self._start_pdf)
        self.pdf_run_btn.pack(side=tk.LEFT)

    def _on_quality(self, _value: str) -> None:
        self.quality_label.configure(text=str(int(float(self.quality_var.get()))))

    def _add_files(self) -> None:
        files = filedialog.askopenfilenames(
            title="Оберіть зображення",
            filetypes=[
                ("Зображення", "*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.tif;*.tiff;*.gif"),
                ("Усі файли", "*.*"),
            ],
        )
        self._append_inputs([Path(p) for p in files], self.inputs, self.listbox, self.output_var, "optimized")

    def _add_folder(self) -> None:
        folder = filedialog.askdirectory(title="Оберіть папку")
        if folder:
            self._append_inputs([Path(folder)], self.inputs, self.listbox, self.output_var, "optimized")

    def _add_pdf_files(self) -> None:
        files = filedialog.askopenfilenames(
            title="Оберіть PDF",
            filetypes=[("PDF", "*.pdf"), ("Усі файли", "*.*")],
        )
        self._append_inputs([Path(p) for p in files], self.pdf_inputs, self.pdf_listbox, self.pdf_output_var, "converted")

    def _add_pdf_folder(self) -> None:
        folder = filedialog.askdirectory(title="Оберіть папку з PDF")
        if folder:
            self._append_inputs([Path(folder)], self.pdf_inputs, self.pdf_listbox, self.pdf_output_var, "converted")

    def _append_inputs(
        self,
        paths: list[Path],
        store: list[Path],
        listbox: tk.Listbox,
        output_var: tk.StringVar,
        folder: str,
    ) -> None:
        for path in paths:
            resolved = path.resolve()
            if resolved not in store:
                store.append(resolved)
                listbox.insert(tk.END, str(resolved))
        if store and not output_var.get():
            first = store[0]
            parent = first.parent if first.is_file() else first
            output_var.set(str(parent / folder))

    def _clear_inputs(self) -> None:
        self.inputs.clear()
        self.listbox.delete(0, tk.END)

    def _clear_pdf_inputs(self) -> None:
        self.pdf_inputs.clear()
        self.pdf_listbox.delete(0, tk.END)

    def _pick_output(self) -> None:
        folder = filedialog.askdirectory(title="Папка для збереження")
        if folder:
            self.output_var.set(folder)

    def _pick_pdf_output(self) -> None:
        folder = filedialog.askdirectory(title="Папка для Word-файлів")
        if folder:
            self.pdf_output_var.set(folder)

    def _preset_screenshots(self) -> None:
        self.format_var.set("webp")
        self.quality_var.set(82)
        self._on_quality("82")
        self.max_width_var.set("")
        self.max_height_var.set("")
        self.lossless_var.set(False)
        self.strip_var.set(True)
        self.skip_larger_var.set(True)

    def _preset_aggressive(self) -> None:
        self.format_var.set("webp")
        self.quality_var.set(68)
        self._on_quality("68")
        self.max_width_var.set("1920")
        self.max_height_var.set("1080")
        self.lossless_var.set(False)
        self.strip_var.set(True)
        self.skip_larger_var.set(True)

    def _options(self) -> Options:
        return Options(
            format=self.format_var.get(),
            quality=int(self.quality_var.get()),
            max_width=_parse_dim(self.max_width_var.get()),
            max_height=_parse_dim(self.max_height_var.get()),
            lossless=self.lossless_var.get(),
            strip_metadata=self.strip_var.get(),
            skip_if_larger=self.skip_larger_var.get(),
            recursive=self.recursive_var.get(),
            overwrite=self.overwrite_var.get(),
        )

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.run_btn.configure(state=state)
        self.pdf_run_btn.configure(state=state)

    def _start(self) -> None:
        if self._busy:
            return
        if not self.inputs:
            messagebox.showinfo("Немає файлів", "Додайте зображення або папку.")
            return
        output = self.output_var.get().strip()
        if not output:
            messagebox.showinfo("Немає папки", "Вкажіть папку для збереження.")
            return
        self._set_busy(True)
        self.progress_var.set(0)
        self.status_var.set("Обробка зображень…")
        self._append_log("Початок обробки зображень\n")
        options = self._options()
        inputs = list(self.inputs)
        output_dir = Path(output)

        def worker() -> None:
            def progress(index: int, total: int, result) -> None:
                self._queue.put(("progress", index, total, result, "image"))

            try:
                summary = process_paths(inputs, output_dir, options, progress=progress)
                self._queue.put(("done", summary, output_dir, "image"))
            except Exception as exc:  # noqa: BLE001
                self._queue.put(("fail", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _start_pdf(self) -> None:
        if self._busy:
            return
        if not self.pdf_inputs:
            messagebox.showinfo("Немає файлів", "Додайте PDF або папку.")
            return
        output = self.pdf_output_var.get().strip()
        if not output:
            messagebox.showinfo("Немає папки", "Вкажіть папку для Word-файлів.")
            return
        self._set_busy(True)
        self.progress_var.set(0)
        self.status_var.set("Конвертація PDF…")
        self._append_log("Початок конвертації PDF у Word\n")
        options = Options(
            recursive=self.pdf_recursive_var.get(),
            overwrite=self.pdf_overwrite_var.get(),
        )
        inputs = list(self.pdf_inputs)
        output_dir = Path(output)
        start_page = _parse_dim(self.pdf_start_var.get())
        end_page = _parse_dim(self.pdf_end_var.get())
        password = self.pdf_password_var.get() or None

        def worker() -> None:
            def progress(index: int, total: int, result) -> None:
                self._queue.put(("progress", index, total, result, "pdf"))

            try:
                summary = convert_pdfs(
                    inputs,
                    output_dir,
                    options,
                    progress=progress,
                    start_page=start_page,
                    end_page=end_page,
                    password=password,
                )
                self._queue.put(("done", summary, output_dir, "pdf"))
            except Exception as exc:  # noqa: BLE001
                self._queue.put(("fail", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_queue(self) -> None:
        try:
            while True:
                item = self._queue.get_nowait()
                kind = item[0]
                if kind == "progress":
                    _, index, total, result, mode = item
                    pct = 0 if total == 0 else (index / total) * 100
                    self.progress_var.set(pct)
                    self.status_var.set(f"{index}/{total}: {result.src.name}")
                    line = pdf_result_line(result) if mode == "pdf" else _result_line(result)
                    self._append_log(line + "\n")
                elif kind == "done":
                    _, summary, output_dir, mode = item
                    text = summarize_pdf(summary) if mode == "pdf" else summarize(summary)
                    self.status_var.set(text)
                    self._append_log(f"\n{text}\nЗбережено в: {output_dir}\n")
                    self._set_busy(False)
                    if summary.ok:
                        messagebox.showinfo("Готово", f"{text}\n\n{output_dir}")
                    elif summary.errors:
                        messagebox.showerror("Помилки", text)
                    else:
                        messagebox.showinfo("Готово", text)
                elif kind == "fail":
                    self.status_var.set("Помилка")
                    self._append_log(f"Помилка: {item[1]}\n")
                    self._set_busy(False)
                    messagebox.showerror("Помилка", item[1])
        except queue.Empty:
            pass
        self.after(80, self._poll_queue)

    def _append_log(self, text: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)


def _parse_dim(raw: str) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _result_line(result) -> str:
    name = result.src.name
    if result.status == "ok" and result.dest is not None:
        saved = format_bytes(result.bytes_in - result.bytes_out)
        extra = f" ({result.note})" if result.note else ""
        return f"{name} → {result.dest.name}  −{saved}{extra}"
    if result.status == "larger":
        return f"{name}: пропущено ({result.note})"
    return f"{name}: помилка — {result.error}"
