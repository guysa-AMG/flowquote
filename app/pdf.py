"""PDF generation using Jinja2 and WeasyPrint (PLAN.md §6, §8).

Renders quotes and variation orders to PDF.
Documents rounding rule in footer:
line_total = round_half_up(qty * unit_price), subtotal = sum, vat = round_half_up(subtotal * vat_rate / 100).
"""
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

class PDFGenerator:
    def __init__(self, templates_dir: Path | None = None):
        self.templates_dir = templates_dir or TEMPLATES_DIR
        self.env = Environment(loader=FileSystemLoader(str(self.templates_dir)), autoescape=True)

    def render_quote_html(self, quote_data: dict[str, Any]) -> str:
        template = self.env.get_template("quote.html")
        return template.render(**quote_data)

    def render_variation_html(self, variation_data: dict[str, Any]) -> str:
        template = self.env.get_template("variation.html")
        return template.render(**variation_data)

    def generate_quote_pdf(self, quote_data: dict[str, Any], output_path: Path) -> Path:
        html_str = self.render_quote_html(quote_data)
        from weasyprint import HTML
        HTML(string=html_str).write_pdf(str(output_path))
        return output_path
