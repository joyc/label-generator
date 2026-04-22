from __future__ import annotations

from pathlib import Path

import typer

from .config import load_layout
from .data_loader import load_data, validate_columns
from .renderer import LabelRenderer

app = typer.Typer(add_completion=False)

_ROOT = Path(__file__).resolve().parents[2]


@app.command()
def generate(
    data: Path = typer.Option(
        _ROOT / "data" / "products.csv", help="CSV or Excel input"
    ),
    template: Path = typer.Option(
        _ROOT / "config" / "template.png", help="Template image"
    ),
    layout: Path = typer.Option(
        _ROOT / "config" / "layout.json", help="Layout config JSON"
    ),
    output: Path = typer.Option(_ROOT / "output", help="Output directory"),
    font: Path = typer.Option(
        _ROOT / "fonts" / "NotoSansCJK-Regular.otf", help="CJK regular font file"
    ),
    bold_font: Path = typer.Option(
        _ROOT / "fonts" / "NotoSansCJK-Bold.otf", help="CJK bold font file (optional)"
    ),
) -> None:
    # --- fail-fast checks ---
    missing_files = [p for p in (template, layout, font) if not p.exists()]
    if missing_files:
        for p in missing_files:
            typer.echo(f"ERROR: file not found: {p.resolve()}", err=True)
        raise typer.Exit(1)

    bold_font_path = bold_font if bold_font.exists() else None
    if not bold_font_path:
        typer.echo(
            f"  [warn] bold font not found, falling back to regular: {bold_font}",
            err=True,
        )

    layout_cfg = load_layout(layout)
    records = load_data(data)

    missing_cols = validate_columns(records, layout_cfg)
    if missing_cols:
        typer.echo(
            f"ERROR: CSV is missing columns required by layout: {missing_cols}",
            err=True,
        )
        raise typer.Exit(1)

    renderer = LabelRenderer(template, layout_cfg, font, bold_font_path=bold_font_path)

    output.mkdir(parents=True, exist_ok=True)
    failed: list[str] = []
    generated = 0

    typer.echo(f"Processing {len(records)} records → {output}/")
    for i, record in enumerate(records):
        sku = (
            record.get("sku")
            or record.get("sku_code")
            or record.get("jan")
            or f"row_{i}"
        )
        try:
            dest = renderer.render_to_file(record, output, index=i)
            typer.echo(f"  ✓ {dest.name}")
            generated += 1
        except Exception as e:
            typer.echo(f"  ✗ {sku}: {e}", err=True)
            failed.append(str(sku))

    typer.echo(f"\nDone: {generated} generated, {len(failed)} failed.")
    if failed:
        typer.echo(f"Failed SKUs: {failed}", err=True)
        raise typer.Exit(2)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
