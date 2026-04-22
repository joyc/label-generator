# Label Generator

Batch apparel label PNG generator. Reads a CSV/Excel file and outputs one print-ready PNG per row, overlaying text and a JAN-13 barcode onto a template image.

## Requirements

- Python 3.11+
- Dependencies listed in `requirements.txt`

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Or install as an editable package:

```bash
pip install -e .
```

## Usage

```bash
# Using PYTHONPATH (no install required)
PYTHONPATH=src python -m label_generator.cli

# With explicit paths
PYTHONPATH=src python -m label_generator.cli \
  --data data/products.csv \
  --template config/template.png \
  --layout config/layout.json \
  --output output/
```

Output PNGs are written to `output/{sku}.png`.

## Project Structure

```
label-generator/
├── config/
│   ├── template.png       # Background template image (591×354 px)
│   └── layout.json        # Field coordinates, font sizes, barcode settings
├── data/
│   └── products.csv       # Input data (CSV or Excel)
├── fonts/
│   ├── NotoSansCJK-Regular.otf
│   └── NotoSansCJK-Bold.otf
├── output/                # Generated PNGs (git-ignored)
└── src/label_generator/
    ├── cli.py             # CLI entry point
    ├── renderer.py        # LabelRenderer class
    ├── barcode_gen.py     # JAN-13 barcode generation
    ├── config.py          # layout.json loader
    └── data_loader.py     # CSV/Excel reader
```

## CSV Columns

| Column | Description |
|--------|-------------|
| `sku` | Product ID — used as output filename |
| `size` | Size (S / M / L / XL …) |
| `category` | Category label shown in rounded box |
| `sku_code` | Product code (e.g. J25011BLM) |
| `color_name` | Color / style description |
| `jan` | JAN code — 12 digits (check digit auto-added) or 13 digits (validated) |

## layout.json

Each key maps to a CSV column. `_meta` keys are metadata and skipped during rendering.

```json
{
  "_meta": {
    "template_size": [591, 354],
    "font": "fonts/NotoSansCJK-Regular.otf",
    "bold_font": "fonts/NotoSansCJK-Bold.otf"
  },
  "size": {
    "type": "text",
    "xy": [220, 114],
    "font_size": 64,
    "anchor": "rt",
    "bold": true
  },
  "jan": {
    "type": "barcode",
    "xy": [498, 214],
    "anchor": "mm",
    "width": 210,
    "height": 130,
    "rotation": -90,
    "show_text": true
  }
}
```

**Text fields:** `type`, `xy`, `font_size`, `anchor`, `color`, `bold`, `max_width`

**Barcode fields:** `type`, `xy`, `anchor`, `width`, `height`, `rotation`, `show_text`

Anchor values follow PIL convention: `"lt"` (left-top), `"mm"` (center), `"rt"` (right-top), etc.
