"""Shared Octanode-style proposal theme for customer documentation PDFs."""

from __future__ import annotations

import math
from pathlib import Path

from fpdf import FPDF

# Brand palette sampled from the Octanode proposal reference
TEAL = (13, 93, 111)
TEAL_DEEP = (11, 70, 85)
TEAL_MID = (15, 105, 124)
ORANGE = (200, 138, 42)
INK = (40, 48, 52)
MUTED = (100, 110, 115)
LINE = (220, 226, 228)
CALLOUT_BG = (247, 241, 232)
WHITE = (255, 255, 255)


def ascii(text: str) -> str:
	replacements = {
		"\u2014": "-",
		"\u2013": "-",
		"\u2018": "'",
		"\u2019": "'",
		"\u201c": '"',
		"\u201d": '"',
		"\u2022": "-",
		"\u2192": "->",
		"\u00a0": " ",
		"\u2026": "...",
		"\u00b7": " | ",  # middle dot
		"\u2219": " | ",
		"\u2027": " | ",
	}
	for a, b in replacements.items():
		text = text.replace(a, b)
	return text.encode("ascii", "replace").decode("ascii")


class ProposalPDF(FPDF):
	def __init__(self, doc_title: str, brand: str = "Hiraal", *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.doc_title = doc_title
		self.brand = brand
		self._in_cover = False

	def header(self):
		if self.page_no() <= 2 or self._in_cover:
			return
		self.set_font("Helvetica", "", 8)
		self.set_text_color(*MUTED)
		self.cell(0, 6, ascii(self.doc_title), align="L")
		self.ln(8)

	def footer(self):
		if self._in_cover or self.page_no() == 1:
			return
		self.set_y(-14)
		self.set_font("Helvetica", "", 8)
		self.set_text_color(*MUTED)
		self.cell(0, 8, f"{self.brand}  |  Page {self.page_no()}", align="C")


def draw_cover(
	pdf: ProposalPDF,
	*,
	brand: str,
	pill: str,
	title: str,
	subtitle: str,
	prepared_for: tuple[str, str],
	prepared_by: tuple[str, str],
	scope: tuple[str, str],
):
	pdf._in_cover = True
	pdf.add_page()
	# Teal full-bleed background
	pdf.set_fill_color(*TEAL_MID)
	pdf.rect(0, 0, pdf.w, pdf.h, style="F")
	# Subtle concentric arcs
	pdf.set_draw_color(18, 120, 142)
	pdf.set_line_width(0.4)
	cx, cy = pdf.w * 0.78, pdf.h * 0.42
	for r in range(40, 220, 28):
		pdf.ellipse(cx - r, cy - r, r * 2, r * 2, style="D")

	pdf.set_xy(22, 28)
	pdf.set_font("Helvetica", "", 11)
	pdf.set_text_color(*WHITE)
	pdf.cell(0, 8, "  ".join(list(brand.upper())), ln=1)

	# Pill
	pdf.set_xy(22, 48)
	pdf.set_draw_color(*WHITE)
	pdf.set_line_width(0.5)
	pill_text = ascii(pill).upper()
	pdf.set_font("Helvetica", "", 8)
	tw = pdf.get_string_width(pill_text) + 14
	y = pdf.get_y()
	# Simple rounded pill (fallback if rounded_rect unavailable)
	try:
		pdf.rounded_rect(22, y, tw, 8, 4, style="D")
	except Exception:
		pdf.rect(22, y, tw, 8, style="D")
	pdf.set_xy(22, y + 1.5)
	pdf.cell(tw, 5, pill_text, align="C")

	pdf.set_xy(22, 72)
	pdf.set_font("Helvetica", "B", 28)
	pdf.set_text_color(*WHITE)
	pdf.multi_cell(pdf.w - 50, 12, ascii(title))
	pdf.set_x(22)
	pdf.set_font("Helvetica", "", 14)
	pdf.multi_cell(pdf.w - 50, 8, ascii(subtitle))

	# Footer meta bar
	meta_y = pdf.h - 52
	pdf.set_draw_color(*WHITE)
	pdf.set_line_width(0.3)
	pdf.line(22, meta_y, pdf.w - 22, meta_y)

	cols = [
		("PREPARED FOR", prepared_for[0], prepared_for[1]),
		("PREPARED BY", prepared_by[0], prepared_by[1]),
		("SCOPE", scope[0], scope[1]),
	]
	col_w = (pdf.w - 44) / 3
	for i, (label, a, b) in enumerate(cols):
		x = 22 + i * col_w
		pdf.set_xy(x, meta_y + 6)
		pdf.set_font("Helvetica", "", 7)
		pdf.set_text_color(200, 220, 225)
		pdf.cell(col_w - 6, 5, label)
		pdf.set_xy(x, meta_y + 14)
		pdf.set_font("Helvetica", "B", 10)
		pdf.set_text_color(*WHITE)
		pdf.cell(col_w - 6, 5, ascii(a))
		pdf.set_xy(x, meta_y + 21)
		pdf.set_font("Helvetica", "", 8)
		pdf.set_text_color(210, 225, 230)
		pdf.multi_cell(col_w - 6, 4, ascii(b))

	pdf._in_cover = False


def draw_contents(pdf: ProposalPDF, entries: list[tuple[str, str, int | None]]):
	"""entries: (number, title, page_hint or None)"""
	pdf.add_page()
	add_section_title(pdf, "Contents")
	pdf.ln(4)
	for num, title, page in entries:
		y = pdf.get_y()
		if y > pdf.h - 30:
			pdf.add_page()
			y = pdf.get_y()
		pdf.set_font("Helvetica", "B", 12)
		pdf.set_text_color(*TEAL)
		pdf.set_xy(pdf.l_margin, y)
		pdf.cell(14, 10, num)
		pdf.set_font("Helvetica", "", 12)
		pdf.set_text_color(*INK)
		pdf.cell(pdf.epw - 28, 10, ascii(title))
		if page is not None:
			pdf.set_text_color(*TEAL)
			pdf.cell(14, 10, str(page), align="R")
		pdf.ln(10)
		pdf.set_draw_color(*LINE)
		pdf.set_line_width(0.2)
		pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
		pdf.ln(2)


def add_section_title(pdf: ProposalPDF, text: str, kicker: str | None = None):
	pdf.set_x(pdf.l_margin)
	if kicker:
		pdf.set_font("Helvetica", "", 8)
		pdf.set_text_color(*TEAL)
		pdf.cell(0, 5, ascii(kicker).upper().replace(" ", "  "), ln=1)
		pdf.set_x(pdf.l_margin)
	pdf.set_font("Helvetica", "B", 18)
	pdf.set_text_color(*TEAL)
	pdf.multi_cell(0, 9, ascii(text))
	pdf.set_x(pdf.l_margin)
	# Orange accent bar
	y = pdf.get_y() + 1
	pdf.set_fill_color(*ORANGE)
	pdf.rect(pdf.l_margin, y, 28, 1.6, style="F")
	pdf.ln(8)


def add_kicker_block(pdf: ProposalPDF, label: str):
	pdf.set_x(pdf.l_margin)
	pdf.set_font("Helvetica", "B", 9)
	pdf.set_text_color(*TEAL)
	pdf.cell(0, 6, ascii(label).upper().replace(" ", "  "), ln=1)
	pdf.set_x(pdf.l_margin)


def add_para(pdf: ProposalPDF, text: str, size: int = 10):
	pdf.set_x(pdf.l_margin)
	pdf.set_font("Helvetica", "", size)
	pdf.set_text_color(*INK)
	pdf.multi_cell(0, 5.5, ascii(text))
	pdf.set_x(pdf.l_margin)
	pdf.ln(2)


def add_bullet(pdf: ProposalPDF, text: str):
	pdf.set_x(pdf.l_margin + 2)
	pdf.set_font("Helvetica", "", 10)
	pdf.set_text_color(*INK)
	pdf.multi_cell(0, 5.5, ascii(f"-  {text}"))
	pdf.set_x(pdf.l_margin)


def add_callout(pdf: ProposalPDF, title: str, body: str):
	pdf.ln(2)
	# Estimate height
	pdf.set_font("Helvetica", "", 10)
	lines = pdf.multi_cell(pdf.epw - 10, 5.5, ascii(body), dry_run=True, output="LINES")
	h = 12 + len(lines) * 5.5 + 6
	if pdf.get_y() + h > pdf.h - pdf.b_margin:
		pdf.add_page()
	x, y = pdf.l_margin, pdf.get_y()
	pdf.set_fill_color(*CALLOUT_BG)
	pdf.rect(x, y, pdf.epw, h, style="F")
	pdf.set_fill_color(*ORANGE)
	pdf.rect(x, y, 2.2, h, style="F")
	pdf.set_xy(x + 6, y + 4)
	pdf.set_font("Helvetica", "B", 10)
	pdf.set_text_color(*INK)
	pdf.cell(0, 5, ascii(title), ln=1)
	pdf.set_x(x + 6)
	pdf.set_font("Helvetica", "", 10)
	pdf.multi_cell(pdf.epw - 10, 5.5, ascii(body))
	pdf.set_y(y + h + 3)
	pdf.set_x(pdf.l_margin)


def add_table(
	pdf: ProposalPDF,
	headers: list[str],
	rows: list[list[str]],
	col_widths: list[float] | None = None,
	caption: str | None = None,
):
	if caption:
		pdf.set_font("Helvetica", "I", 8)
		pdf.set_text_color(*MUTED)
		pdf.multi_cell(0, 4, ascii(caption))
		pdf.set_x(pdf.l_margin)
		pdf.ln(1)

	n = len(headers)
	if not col_widths:
		col_widths = [pdf.epw / n] * n

	def header_row():
		pdf.set_font("Helvetica", "B", 8)
		pdf.set_fill_color(*TEAL)
		pdf.set_text_color(*WHITE)
		for i, h in enumerate(headers):
			pdf.cell(col_widths[i], 7, ascii(h)[:48], border=0, fill=True)
		pdf.ln()
		pdf.set_text_color(*INK)

	if pdf.get_y() + 20 > pdf.h - pdf.b_margin:
		pdf.add_page()
	header_row()

	pdf.set_font("Helvetica", "", 8)
	line_h = 4.5
	for ri, row in enumerate(rows):
		# Compute row height
		max_lines = 1
		cell_lines = []
		for i, cell in enumerate(row):
			lines = pdf.multi_cell(
				col_widths[i] - 2, line_h, ascii(str(cell)), dry_run=True, output="LINES"
			)
			cell_lines.append(lines)
			max_lines = max(max_lines, len(lines))
		row_h = max(line_h * max_lines + 3, 8)
		if pdf.get_y() + row_h > pdf.h - pdf.b_margin:
			pdf.add_page()
			header_row()
			pdf.set_font("Helvetica", "", 8)
		x0, y0 = pdf.l_margin, pdf.get_y()
		if ri % 2 == 1:
			pdf.set_fill_color(248, 250, 251)
			pdf.rect(x0, y0, pdf.epw, row_h, style="F")
		for i, lines in enumerate(cell_lines):
			pdf.set_xy(x0 + sum(col_widths[:i]) + 1, y0 + 1.5)
			pdf.multi_cell(col_widths[i] - 2, line_h, "\n".join(lines))
		pdf.set_xy(pdf.l_margin, y0 + row_h)
		pdf.set_draw_color(*LINE)
		pdf.set_line_width(0.2)
		pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
	pdf.ln(4)


def add_image(pdf: ProposalPDF, path: Path, caption: str, max_h: float = 95):
	if not path.exists():
		add_para(pdf, f"[Missing figure: {path.name}]")
		return
	pdf.ln(2)
	if pdf.get_y() + max_h + 16 > pdf.h - pdf.b_margin:
		pdf.add_page()
	pdf.image(str(path), w=pdf.epw, h=max_h, keep_aspect_ratio=True)
	pdf.set_x(pdf.l_margin)
	pdf.set_font("Helvetica", "I", 8)
	pdf.set_text_color(*MUTED)
	pdf.multi_cell(0, 4.5, ascii(caption), align="C")
	pdf.set_x(pdf.l_margin)
	pdf.set_text_color(*INK)
	pdf.ln(3)


def add_code(pdf: ProposalPDF, text: str):
	pdf.set_x(pdf.l_margin)
	pdf.set_fill_color(245, 247, 248)
	pdf.set_font("Courier", "", 8)
	pdf.set_text_color(40, 40, 40)
	pdf.multi_cell(0, 4.5, ascii(text), fill=True)
	pdf.set_x(pdf.l_margin)
	pdf.ln(3)


def add_steps(pdf: ProposalPDF, steps: list[tuple[str, str]]):
	"""Numbered flow steps like the Octanode proposal."""
	for i, (title, body) in enumerate(steps, start=1):
		pdf.set_x(pdf.l_margin)
		pdf.set_font("Helvetica", "B", 11)
		pdf.set_text_color(*TEAL)
		pdf.cell(8, 6, str(i))
		pdf.set_text_color(*INK)
		pdf.multi_cell(0, 6, ascii(title))
		pdf.set_x(pdf.l_margin + 8)
		pdf.set_font("Helvetica", "", 10)
		pdf.multi_cell(pdf.epw - 8, 5.2, ascii(body))
		pdf.set_x(pdf.l_margin)
		if i < len(steps):
			pdf.set_text_color(*ORANGE)
			pdf.set_font("Helvetica", "B", 10)
			pdf.cell(0, 5, "v", align="C", ln=1)
			pdf.set_text_color(*INK)
		pdf.ln(1)
