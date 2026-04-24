from __future__ import annotations

import io
import json
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

import ttkbootstrap as ttk
from PIL import Image, ImageTk
from tkinter.ttk import PanedWindow

# Support both `python -m label_generator.gui` and direct script execution
if __package__ is None:
    _SCRIPT_DIR = Path(__file__).resolve().parent
    sys.path.insert(0, str(_SCRIPT_DIR))
    from config import load_layout
    from data_loader import load_data, validate_columns
    from renderer import LabelRenderer
else:
    from .config import load_layout
    from .data_loader import load_data, validate_columns
    from .renderer import LabelRenderer

_ROOT = Path(__file__).resolve().parents[2]

# Marker colours for layout editor
_MARKER_TEXT_FILL = "#4dabf7"
_MARKER_TEXT_OUTLINE = "#1971c2"
_MARKER_BARCODE_FILL = "#51cf66"
_MARKER_BARCODE_OUTLINE = "#2f9e44"
_MARKER_SIZE = 14


class LabelGeneratorGUI:
    def __init__(self, root: ttk.Window) -> None:
        self.root = root
        self.root.title("Label Generator")
        self.root.geometry("1280x900")
        self.root.minsize(1000, 750)

        # --- state ---
        self.records: list[dict[str, Any]] = []
        self.layout_cfg: dict[str, Any] = {}
        self.renderer: LabelRenderer | None = None
        self.preview_image_tk: ImageTk.PhotoImage | None = None
        self._is_generating = False

        # Layout editor state
        self._edit_mode = False
        self._layout_markers: dict[str, dict] = {}
        self._drag_data: dict[str, Any] = {"field": None, "x": 0, "y": 0}
        self._template_image_tk: ImageTk.PhotoImage | None = None
        self._template_size: tuple[int, int] = (0, 0)
        self._canvas_scale: float = 1.0
        self._canvas_offset: tuple[float, float] = (0.0, 0.0)

        self._load_btn: ttk.Button | None = None
        self._generate_btn: ttk.Button | None = None
        self._edit_btn: ttk.Button | None = None
        self._edit_toolbar: ttk.Frame | None = None
        self._coord_label: ttk.Label | None = None
        self._field_label: ttk.Label | None = None

        self._build_ui()
        self._set_defaults()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        # === Header ===
        header = ttk.Frame(main)
        header.pack(fill=tk.X, pady=(0, 15))
        ttk.Label(
            header,
            text="Label Generator",
            font=("Helvetica", 22, "bold"),
        ).pack(side=tk.LEFT)
        ttk.Label(
            header,
            text="批量吊牌标签生成工具",
            font=("Helvetica", 12),
            bootstyle="secondary",
        ).pack(side=tk.LEFT, padx=(12, 0), pady=(6, 0))

        ttk.Separator(main, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 15))

        # === Configuration ===
        config_lf = ttk.Labelframe(main, text=" 文件配置 ", padding=15)
        config_lf.pack(fill=tk.X, pady=(0, 15))

        self._path_vars: dict[str, tk.StringVar] = {}
        self._path_entries: dict[str, ttk.Entry] = {}

        fields = [
            ("data", "数据文件 (CSV/Excel)", _ROOT / "data" / "products.csv"),
            ("template", "模板图片", _ROOT / "config" / "template1.png"),
            ("layout", "布局 JSON", _ROOT / "config" / "layout.json"),
            ("output", "输出目录", _ROOT / "output"),
            ("font", "常规字体", _ROOT / "fonts" / "NotoSansCJK-Regular.otf"),
            ("bold_font", "粗体字体 (可选)", _ROOT / "fonts" / "NotoSansCJK-Bold.otf"),
        ]

        for row, (key, label, default) in enumerate(fields):
            ttk.Label(config_lf, text=label + ":", width=20, anchor=tk.E).grid(
                row=row, column=0, sticky=tk.E, padx=(0, 10), pady=5
            )
            var = tk.StringVar(value=str(default))
            self._path_vars[key] = var
            entry = ttk.Entry(config_lf, textvariable=var, bootstyle="secondary")
            entry.grid(row=row, column=1, sticky=tk.EW, padx=(0, 10), pady=5)
            self._path_entries[key] = entry

            is_dir = key == "output"
            btn = ttk.Button(
                config_lf,
                text="浏览…",
                width=8,
                command=lambda k=key, d=is_dir: self._browse(k, d),
                bootstyle="secondary-outline",
            )
            btn.grid(row=row, column=2, pady=5)

        config_lf.columnconfigure(1, weight=1)

        # === Actions ===
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(0, 15))

        self._load_btn = ttk.Button(
            btn_frame,
            text="加载数据",
            command=self._load_data,
            bootstyle="primary",
            width=12,
        )
        self._load_btn.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(
            btn_frame,
            text="预览选中行",
            command=self._preview_selected,
            bootstyle="info",
            width=12,
        ).pack(side=tk.LEFT, padx=10)

        self._generate_btn = ttk.Button(
            btn_frame,
            text="生成全部标签",
            command=self._generate_all,
            bootstyle="success",
            width=14,
        )
        self._generate_btn.pack(side=tk.LEFT, padx=10)

        self._edit_btn = ttk.Button(
            btn_frame,
            text="编辑布局",
            command=self._toggle_edit_mode,
            bootstyle="warning",
            width=12,
        )
        self._edit_btn.pack(side=tk.LEFT, padx=10)

        # === Edit toolbar (hidden by default) ===
        self._edit_toolbar = ttk.Frame(main)
        self._edit_toolbar.pack(fill=tk.X, pady=(0, 10))
        self._edit_toolbar.pack_forget()

        self._field_label = ttk.Label(
            self._edit_toolbar, text="未选中", font=("Helvetica", 10, "bold")
        )
        self._field_label.pack(side=tk.LEFT, padx=(0, 15))

        self._coord_label = ttk.Label(self._edit_toolbar, text="")
        self._coord_label.pack(side=tk.LEFT, padx=(0, 15))

        ttk.Button(
            self._edit_toolbar,
            text="保存布局",
            command=self._save_layout,
            bootstyle="success-outline",
            width=10,
        ).pack(side=tk.RIGHT, padx=(10, 0))

        ttk.Button(
            self._edit_toolbar,
            text="退出编辑",
            command=self._toggle_edit_mode,
            bootstyle="secondary-outline",
            width=10,
        ).pack(side=tk.RIGHT)

        ttk.Label(
            self._edit_toolbar,
            text="提示: 拖动标记调整坐标",
            bootstyle="secondary",
        ).pack(side=tk.RIGHT, padx=(0, 15))

        # === Content (paned) ===
        paned = PanedWindow(main, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # Left: Data table
        tree_lf = ttk.Labelframe(paned, text=" 数据预览 ", padding=10)
        paned.add(tree_lf, weight=3)

        self.tree = ttk.Treeview(
            tree_lf,
            show="headings",
            bootstyle="primary",
        )
        vsb = ttk.Scrollbar(
            tree_lf, orient=tk.VERTICAL, command=self.tree.yview, bootstyle="round"
        )
        hsb = ttk.Scrollbar(
            tree_lf, orient=tk.HORIZONTAL, command=self.tree.xview, bootstyle="round"
        )
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky=tk.NSEW)
        vsb.grid(row=0, column=1, sticky=tk.NS)
        hsb.grid(row=1, column=0, sticky=tk.EW)
        tree_lf.rowconfigure(0, weight=1)
        tree_lf.columnconfigure(0, weight=1)

        # Right: Preview
        preview_lf = ttk.Labelframe(paned, text=" 标签预览 / 布局编辑 ", padding=10)
        paned.add(preview_lf, weight=2)

        self.preview_canvas = tk.Canvas(
            preview_lf,
            bg=str(self.root.style.colors.bg),
            highlightthickness=0,
        )
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)

        # Bind canvas resize for editor redraw
        self.preview_canvas.bind("<Configure>", self._on_canvas_configure)

        # === Status Bar ===
        ttk.Separator(main, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(15, 8))

        bottom = ttk.Frame(main)
        bottom.pack(fill=tk.X)

        self.progress = ttk.Progressbar(
            bottom,
            orient=tk.HORIZONTAL,
            mode="determinate",
            bootstyle="success-striped",
            length=300,
        )
        self.progress.pack(fill=tk.X, pady=(0, 8))

        status_frame = ttk.Frame(bottom)
        status_frame.pack(fill=tk.X)

        self.status_dot = tk.Label(
            status_frame, text="●", font=("Helvetica", 10), fg="#adb5bd"
        )
        self.status_dot.pack(side=tk.LEFT, padx=(0, 6))

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(status_frame, textvariable=self.status_var, anchor=tk.W).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )

        self._set_status("就绪", "secondary")

    # ------------------------------------------------------------------
    # Defaults & helpers
    # ------------------------------------------------------------------
    def _set_defaults(self) -> None:
        for key, var in self._path_vars.items():
            p = Path(var.get())
            if not p.exists():
                if key == "template":
                    for candidate in (_ROOT / "config").glob("template*.png"):
                        var.set(str(candidate))
                        break
                elif key == "data":
                    for candidate in (_ROOT / "data").glob("*.csv"):
                        var.set(str(candidate))
                        break
                elif key == "layout":
                    for candidate in (_ROOT / "config").glob("*.json"):
                        var.set(str(candidate))
                        break

    def _color(self, bootstyle: str) -> str:
        return str(getattr(self.root.style.colors, bootstyle, "#4dabf7"))

    def _set_status(self, text: str, bootstyle: str = "primary") -> None:
        self.status_var.set(text)
        self.status_dot.configure(fg=self._color(bootstyle))
        self.root.update_idletasks()

    def _browse(self, key: str, is_dir: bool) -> None:
        if is_dir:
            path = filedialog.askdirectory(title="选择目录")
        elif key == "data":
            path = filedialog.askopenfilename(
                title="选择数据文件",
                filetypes=[("CSV", "*.csv"), ("Excel", "*.xlsx *.xls"), ("All", "*")],
            )
        elif key in ("template",):
            path = filedialog.askopenfilename(
                title="选择图片",
                filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg *.jpeg"), ("All", "*")],
            )
        elif key == "layout":
            path = filedialog.askopenfilename(
                title="选择布局 JSON",
                filetypes=[("JSON", "*.json"), ("All", "*")],
            )
        else:
            path = filedialog.askopenfilename(
                title="选择字体",
                filetypes=[("OpenType", "*.otf"), ("TrueType", "*.ttf"), ("All", "*")],
            )
        if path:
            self._path_vars[key].set(path)

    def _get_path(self, key: str) -> Path:
        return Path(self._path_vars[key].get())

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------
    def _load_data(self) -> None:
        if self._is_generating:
            messagebox.showinfo("提示", "正在生成标签中，请等待完成后再加载数据。")
            return

        data_path = self._get_path("data")
        layout_path = self._get_path("layout")
        template_path = self._get_path("template")
        font_path = self._get_path("font")
        bold_font_path = self._get_path("bold_font")

        missing = [
            p for p in (data_path, layout_path, template_path, font_path) if not p.exists()
        ]
        if missing:
            messagebox.showerror(
                "文件缺失",
                "以下文件不存在:\n" + "\n".join(str(p) for p in missing),
            )
            return

        try:
            self.layout_cfg = load_layout(layout_path)
        except Exception as e:
            messagebox.showerror("加载布局失败", str(e))
            return

        try:
            self.records = load_data(data_path)
        except Exception as e:
            messagebox.showerror("加载数据失败", str(e))
            return

        missing_cols = validate_columns(self.records, self.layout_cfg)
        if missing_cols:
            messagebox.showwarning(
                "列缺失",
                f"数据缺少布局要求的列: {missing_cols}",
            )

        self.tree.delete(*self.tree.get_children())
        if not self.records:
            self._set_status("数据文件为空", "warning")
            return

        columns = list(self.records[0].keys())
        self.tree["columns"] = columns
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=100, anchor=tk.W)

        for record in self.records:
            values = [str(record.get(col, "")) for col in columns]
            self.tree.insert("", tk.END, values=values)

        if bold_font_path and not bold_font_path.exists():
            messagebox.showwarning(
                "字体文件不存在",
                f"粗体字体文件不存在，将使用普通字体替代:\n{bold_font_path}",
            )
            bold_font = None
        else:
            bold_font = bold_font_path if bold_font_path.exists() else None

        try:
            self.renderer = LabelRenderer(
                template_path, self.layout_cfg, font_path, bold_font_path=bold_font
            )
        except Exception as e:
            messagebox.showerror("初始化渲染器失败", str(e))
            self.renderer = None
            return

        self._set_status(f"已加载 {len(self.records)} 条记录", "success")

        # If in edit mode, refresh editor
        if self._edit_mode:
            self._draw_layout_editor()

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------
    def _preview_selected(self) -> None:
        if self._edit_mode:
            messagebox.showinfo("提示", "当前处于布局编辑模式，请先退出编辑。")
            return
        if not self.renderer:
            messagebox.showwarning("提示", "请先加载数据")
            return

        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请在表格中选中一行")
            return

        item = self.tree.item(selection[0])
        values = item["values"]
        columns = self.tree["columns"]
        record = {col: val for col, val in zip(columns, values)}

        try:
            img = self.renderer.render(record)
            self._show_preview(img)
            self._set_status(f"预览: SKU {record.get('sku', '?')}", "info")
        except Exception as e:
            messagebox.showerror("渲染失败", str(e))

    def _show_preview(self, img: Image.Image) -> None:
        canvas_w = self.preview_canvas.winfo_width()
        canvas_h = self.preview_canvas.winfo_height()
        if canvas_w < 10 or canvas_h < 10:
            canvas_w, canvas_h = 400, 300

        img_w, img_h = img.size
        scale = min(canvas_w / img_w, canvas_h / img_h, 1.0)
        new_w, new_h = int(img_w * scale), int(img_h * scale)

        preview = img.resize((new_w, new_h), Image.LANCZOS)
        self.preview_image_tk = ImageTk.PhotoImage(preview)

        self.preview_canvas.delete("all")
        x = (canvas_w - new_w) // 2
        y = (canvas_h - new_h) // 2
        self.preview_canvas.create_image(x, y, anchor=tk.NW, image=self.preview_image_tk)

    # ------------------------------------------------------------------
    # Layout Editor
    # ------------------------------------------------------------------
    def _toggle_edit_mode(self) -> None:
        if not self.layout_cfg:
            messagebox.showwarning("提示", "请先加载数据以初始化布局。")
            return

        self._edit_mode = not self._edit_mode

        if self._edit_mode:
            self._edit_btn.configure(text="退出编辑", bootstyle="danger")
            self._edit_toolbar.pack(fill=tk.X, pady=(0, 10))
            self._set_status("布局编辑模式", "warning")
            self._draw_layout_editor()
        else:
            self._edit_btn.configure(text="编辑布局", bootstyle="warning")
            self._edit_toolbar.pack_forget()
            self.preview_canvas.delete("all")
            self._set_status("已退出编辑模式", "secondary")

    def _on_canvas_configure(self, _event: Any = None) -> None:
        if self._edit_mode:
            self._draw_layout_editor()

    def _get_template_size(self) -> tuple[int, int]:
        meta = self.layout_cfg.get("_meta", {})
        ts = meta.get("template_size")
        if ts and len(ts) == 2:
            return int(ts[0]), int(ts[1])

        template_path = self._get_path("template")
        if template_path.exists():
            with Image.open(template_path) as img:
                return img.size
        return 591, 354

    def _calc_canvas_transform(self) -> tuple[float, float, float]:
        canvas_w = self.preview_canvas.winfo_width()
        canvas_h = self.preview_canvas.winfo_height()
        if canvas_w < 10 or canvas_h < 10:
            canvas_w, canvas_h = 400, 300

        tw, th = self._template_size
        scale = min(canvas_w / tw, canvas_h / th, 1.0)
        offset_x = (canvas_w - tw * scale) / 2
        offset_y = (canvas_h - th * scale) / 2
        return scale, offset_x, offset_y

    def _template_to_canvas(self, tx: float, ty: float) -> tuple[float, float]:
        scale, ox, oy = self._canvas_scale, self._canvas_offset[0], self._canvas_offset[1]
        return tx * scale + ox, ty * scale + oy

    def _canvas_to_template(self, cx: float, cy: float) -> tuple[float, float]:
        scale, ox, oy = self._canvas_scale, self._canvas_offset[0], self._canvas_offset[1]
        return (cx - ox) / scale, (cy - oy) / scale

    def _draw_layout_editor(self) -> None:
        self.preview_canvas.delete("all")
        self._layout_markers.clear()

        self._template_size = self._get_template_size()
        scale, ox, oy = self._calc_canvas_transform()
        self._canvas_scale = scale
        self._canvas_offset = (ox, oy)

        # Draw template background
        template_path = self._get_path("template")
        if template_path.exists():
            img = Image.open(template_path).convert("RGBA")
            tw, th = self._template_size
            display_w, display_h = int(tw * scale), int(th * scale)
            resized = img.resize((display_w, display_h), Image.LANCZOS)
            self._template_image_tk = ImageTk.PhotoImage(resized)
            self.preview_canvas.create_image(ox, oy, anchor=tk.NW, image=self._template_image_tk)

        # Draw field markers
        for field, spec in self.layout_cfg.items():
            if field.startswith("_"):
                continue
            self._draw_field_marker(field, spec)

        # Bind drag events
        self.preview_canvas.tag_bind("marker", "<ButtonPress-1>", self._on_marker_press)
        self.preview_canvas.tag_bind("marker", "<B1-Motion>", self._on_marker_drag)
        self.preview_canvas.tag_bind("marker", "<ButtonRelease-1>", self._on_marker_release)

    def _draw_field_marker(self, field: str, spec: dict) -> None:
        xy = spec.get("xy", [0, 0])
        kind = spec.get("type", "text")
        anchor = spec.get("anchor", "lt")

        cx, cy = self._template_to_canvas(xy[0], xy[1])
        cx, cy = int(cx), int(cy)

        size = _MARKER_SIZE
        half = size // 2

        # Determine rect corners based on anchor
        if anchor in ("mm", "mt", "mb"):
            x1, x2 = cx - half, cx + half
        elif anchor in ("rt", "rb", "rm"):
            x1, x2 = cx - size, cx
        else:  # lt, lb, lm
            x1, x2 = cx, cx + size

        if anchor in ("mm", "lm", "rm"):
            y1, y2 = cy - half, cy + half
        elif anchor in ("lb", "mb", "rb"):
            y1, y2 = cy - size, cy
        else:  # lt, mt, rt
            y1, y2 = cy, cy + size

        fill = _MARKER_TEXT_FILL if kind == "text" else _MARKER_BARCODE_FILL
        outline = _MARKER_TEXT_OUTLINE if kind == "text" else _MARKER_BARCODE_OUTLINE

        rect = self.preview_canvas.create_rectangle(
            x1, y1, x2, y2, fill=fill, outline=outline, width=2, tags=("marker", field)
        )
        text = self.preview_canvas.create_text(
            x1, y1 - 4, text=field, anchor=tk.SW, fill=outline, font=("Helvetica", 9, "bold"), tags=("marker", field)
        )

        self._layout_markers[field] = {
            "rect": rect,
            "text": text,
            "anchor": anchor,
            "kind": kind,
        }

    def _on_marker_press(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        item = self.preview_canvas.find_closest(event.x, event.y)[0]
        tags = self.preview_canvas.gettags(item)
        field = None
        for tag in tags:
            if tag != "marker" and not tag.startswith("("):
                field = tag
                break

        if not field or field not in self._layout_markers:
            return

        self._drag_data["field"] = field
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

        marker = self._layout_markers[field]
        spec = self.layout_cfg[field]
        xy = spec.get("xy", [0, 0])

        self._field_label.configure(text=f"字段: {field}")
        self._coord_label.configure(text=f"坐标: ({xy[0]}, {xy[1]})")

        # Highlight selected
        self.preview_canvas.itemconfig(marker["rect"], width=3)
        for other, m in self._layout_markers.items():
            if other != field:
                self.preview_canvas.itemconfig(m["rect"], width=2)

    def _on_marker_drag(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        field = self._drag_data.get("field")
        if not field:
            return

        dx = event.x - self._drag_data["x"]
        dy = event.y - self._drag_data["y"]
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

        marker = self._layout_markers[field]
        self.preview_canvas.move(marker["rect"], dx, dy)
        self.preview_canvas.move(marker["text"], dx, dy)

        # Update underlying layout coordinate
        rect_coords = self.preview_canvas.coords(marker["rect"])
        if not rect_coords:
            return

        anchor = marker["anchor"]
        x1, y1 = rect_coords[0], rect_coords[1]

        # Map canvas corner back to template coordinate based on anchor
        size = _MARKER_SIZE
        if anchor in ("mm", "mt", "mb"):
            cx = x1 + size / 2
        elif anchor in ("rt", "rb", "rm"):
            cx = x1 + size
        else:
            cx = x1

        if anchor in ("mm", "lm", "rm"):
            cy = y1 + size / 2
        elif anchor in ("lb", "mb", "rb"):
            cy = y1 + size
        else:
            cy = y1

        tx, ty = self._canvas_to_template(cx, cy)
        tx, ty = round(tx), round(ty)

        self.layout_cfg[field]["xy"] = [tx, ty]
        self._coord_label.configure(text=f"坐标: ({tx}, {ty})")

    def _on_marker_release(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        self._drag_data["field"] = None

    def _save_layout(self) -> None:
        layout_path = self._get_path("layout")
        try:
            with open(layout_path, "w", encoding="utf-8") as f:
                json.dump(self.layout_cfg, f, ensure_ascii=False, indent=2)
            self._set_status(f"布局已保存: {layout_path.name}", "success")
            messagebox.showinfo("保存成功", f"布局已保存到:\n{layout_path}")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    def _generate_all(self) -> None:
        if self._edit_mode:
            messagebox.showinfo("提示", "当前处于布局编辑模式，请先退出编辑。")
            return
        if self._is_generating:
            messagebox.showinfo("提示", "正在生成中，请稍候完成后再操作。")
            return
        if not self.renderer:
            messagebox.showwarning("提示", "请先加载数据")
            return

        self._is_generating = True
        if self._load_btn:
            self._load_btn.state(["disabled"])
        if self._generate_btn:
            self._generate_btn.state(["disabled"])

        output_dir = self._get_path("output")
        output_dir.mkdir(parents=True, exist_ok=True)

        total = len(self.records)
        self.progress["maximum"] = total
        self.progress["value"] = 0
        self._set_status(f"开始生成 {total} 个标签…", "warning")

        thread = threading.Thread(
            target=self._generate_worker, args=(output_dir, total), daemon=True
        )
        thread.start()

    def _generate_worker(self, output_dir: Path, total: int) -> None:
        generated = 0
        failed: list[str] = []

        for i, record in enumerate(self.records):
            sku = (
                record.get("sku")
                or record.get("sku_code")
                or record.get("jan")
                or f"row_{i}"
            )
            try:
                self.renderer.render_to_file(record, output_dir, index=i)
                generated += 1
            except Exception as e:
                failed.append(f"{sku}: {e}")

            self.root.after(0, self._update_progress, i + 1)

        self.root.after(
            0,
            self._generation_done,
            generated,
            failed,
            output_dir,
        )

    def _update_progress(self, value: int) -> None:
        self.progress["value"] = value
        self._set_status(f"生成中… {value} / {self.progress['maximum']}", "warning")

    def _generation_done(
        self, generated: int, failed: list[str], output_dir: Path
    ) -> None:
        self._is_generating = False
        if self._load_btn:
            self._load_btn.state(["!disabled"])
        if self._generate_btn:
            self._generate_btn.state(["!disabled"])

        self.progress["value"] = self.progress["maximum"]
        if failed:
            self._set_status(f"完成: {generated} 成功, {len(failed)} 失败", "danger")
            msg = "\n".join(failed[:10])
            if len(failed) > 10:
                msg += f"\n… 还有 {len(failed) - 10} 个错误"
            messagebox.showwarning(
                "生成完成（有错误）",
                f"成功: {generated}\n失败: {len(failed)}\n\n{msg}",
            )
        else:
            self._set_status(f"完成: 成功生成 {generated} 个标签", "success")
            messagebox.showinfo(
                "生成完成",
                f"成功生成 {generated} 个标签。\n输出目录: {output_dir}",
            )


def main() -> None:
    root = ttk.Window(themename="flatly")
    app = LabelGeneratorGUI(root)

    def on_close() -> None:
        if app._is_generating:
            if not messagebox.askyesno("确认退出", "当前仍在生成标签，确认要退出吗？"):
                return
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
