#!/usr/bin/env python3
"""
SongSeeker Card Generator

Generates printable QR-code cards from a SongSeeker local CSV.
Supports double-sided printing, optional icon embedding, and optional colored backs.

Usage:
    python tools/generate_cards.py playlists/80s-local.csv cards/cards-80s.pdf
    python tools/generate_cards.py playlists/80s-local.csv cards/cards-80s.pdf --flip long --icon icons/icon-96x96.png --color
"""

import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
import qrcode
from qrcode.image.styledpil import StyledPilImage
import hashlib
import argparse
import textwrap
import os
import requests
from io import BytesIO


def generate_qr_code(url, file_path, icon_path, icon_image_cache=None):
    if icon_image_cache is None:
        icon_image_cache = {}
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    if icon_path is None:
        img = qr.make_image(fill_color="black", back_color="white")
    else:
        if icon_path.startswith('http'):
            if icon_path not in icon_image_cache:
                response = requests.get(icon_path)
                icon_image_cache[icon_path] = BytesIO(response.content)
            icon_image = icon_image_cache[icon_path]
            img = qr.make_image(image_factory=StyledPilImage, embeded_image_path=icon_image)
        else:
            img = qr.make_image(image_factory=StyledPilImage, embeded_image_path=icon_path)
    img.save(file_path)


def add_qr_code_with_border(c, url, position, box_size, icon_path):
    # Handle missing or invalid URLs gracefully
    if pd.isna(url) or not str(url).strip():
        return
    url = str(url).strip()
    hash_object = hashlib.sha256(url.encode())
    hex_dig = hash_object.hexdigest()

    qr_code_path = f"qr_{hex_dig}.png"  # Unique path for each QR code
    generate_qr_code(url, qr_code_path, icon_path)
    x, y = position
    c.drawImage(qr_code_path, x, y, width=box_size, height=box_size)
    os.remove(qr_code_path)


def add_text_box(c, info, position, box_size, use_color=True, set_name="",
                 font_artist="Helvetica-Bold", font_size_artist=14,
                 font_title="Helvetica", font_size_title=14,
                 font_year="Helvetica-Bold", font_size_year=50):
    x, y = position
    text_margin = 5
    text_indent = 8

    default_font_color = '0,0,0'  # Default color is black

    # Check if 'backcol' is in info and set the fill color
    if use_color and 'backcol' in info and not pd.isna(info['backcol']):
        try:
            backcol_str = str(info['backcol']).strip()
            r, g, b = tuple(float(x) for x in backcol_str.split(','))
            c.setFillColorRGB(r, g, b)
            c.rect(x, y, box_size, box_size, fill=1)
        except (ValueError, AttributeError):
            # backcol is malformed (e.g. a single number), just draw border
            c.rect(x, y, box_size, box_size)
    else:
        c.rect(x, y, box_size, box_size)

    r, g, b = tuple(float(x) for x in default_font_color.split(','))
    c.setFillColorRGB(r, g, b)

    # Calculate the centered position for each line of text
    if not pd.isna(info['Artist']):
        artist_text = f"{info['Artist']}"
        artist_x = x + (box_size - c.stringWidth(artist_text, font_artist, font_size_artist)) / 2
        artist_lines = textwrap.wrap(artist_text, width=int(len(artist_text) / c.stringWidth(artist_text, font_artist, font_size_artist) * (box_size - text_indent*2)))
        artist_y = y + box_size - (text_indent + font_size_artist)

        for line in artist_lines:
            artist_x = x + (box_size - c.stringWidth(line, font_artist, font_size_artist)) / 2
            c.setFont(font_artist, font_size_artist)
            c.drawString(artist_x, artist_y, line)
            artist_y -= text_margin + font_size_artist

    if not pd.isna(info['Title']):
        title_text = f"{info['Title']}"
        title_x = x + (box_size - c.stringWidth(title_text, font_title, font_size_title)) / 2
        title_lines = textwrap.wrap(title_text, width=int(len(title_text) / c.stringWidth(title_text, font_title, font_size_title) * (box_size - text_indent*2)))
        title_y = y + (len(title_lines) - 1) * (text_margin + font_size_title) + font_size_title / 2 + text_indent

        for line in title_lines:
            title_x = x + (box_size - c.stringWidth(line, font_title, font_size_title)) / 2
            c.setFont(font_title, font_size_title)
            c.drawString(title_x, title_y, line)
            title_y -= text_margin + font_size_title

    if not pd.isna(info['Year']):
        year_text = f"{info['Year']}"
        year_x = x + (box_size - c.stringWidth(year_text, font_year, font_size_year)) / 2
        year_y = y + box_size / 2 - (font_size_year / 2) / 2
        c.setFont(font_year, font_size_year)
        c.drawString(year_x, year_y, year_text)

    # Set name label in bottom-right corner
    if set_name:
        label_font = "Helvetica-Oblique"
        label_size = 7
        label_text = str(set_name)
        c.setFont(label_font, label_size)
        label_width = c.stringWidth(label_text, label_font, label_size)
        label_x = x + box_size - label_width - text_indent
        label_y = y + text_indent
        c.drawString(label_x, label_y, label_text)


def main(csv_file_path, output_pdf_path, icon_path=None, flip_mode="short", use_color=True, set_name=""):
    data = pd.read_csv(csv_file_path)
    # Remove leading and trailing whitespaces (compatible with old and new pandas)
    try:
        data = data.map(lambda x: x.strip() if isinstance(x, str) else x)
    except AttributeError:
        data = data.applymap(lambda x: x.strip() if isinstance(x, str) else x)

    c = canvas.Canvas(output_pdf_path, pagesize=A4)
    page_width, page_height = A4
    box_size = 6.5 * cm
    boxes_per_row = int(page_width // box_size)
    boxes_per_column = int(page_height // box_size)
    boxes_per_page = boxes_per_row * boxes_per_column
    vpageindent = 0.8 * cm
    hpageindent = (page_width - (box_size * boxes_per_row)) / 2

    for i in range(0, len(data), boxes_per_page):
        # Generate QR codes
        for index in range(i, min(i + boxes_per_page, len(data))):
            row = data.iloc[index]
            position_index = index % (boxes_per_row * boxes_per_column)
            column_index = position_index % boxes_per_row
            row_index = position_index // boxes_per_row
            x = hpageindent + (column_index * box_size)
            y = page_height - vpageindent - (row_index + 1) * box_size
            add_qr_code_with_border(c, row['URL'], (x, y), box_size, icon_path)

        c.showPage()

        # Add text information
        for index in range(i, min(i + boxes_per_page, len(data))):
            row = data.iloc[index]
            position_index = index % boxes_per_page

            # Calculate column/row based on flip mode for double-sided printing
            if flip_mode == "short":
                # Flip on short edge: mirror horizontally (left ↔ right)
                column_index = (boxes_per_row - 1) - (position_index % boxes_per_row)
                row_index = position_index // boxes_per_row
            elif flip_mode == "long":
                # Flip on long edge: mirror vertically (top ↔ bottom)
                column_index = position_index % boxes_per_row
                row_index = (boxes_per_column - 1) - (position_index // boxes_per_row)
            else:
                # No flip / manual alignment: same positions as QR
                column_index = position_index % boxes_per_row
                row_index = position_index // boxes_per_row

            x = hpageindent + (column_index * box_size)
            y = page_height - vpageindent - (row_index + 1) * box_size
            add_text_box(c, row, (x, y), box_size, use_color=use_color, set_name=set_name)

        c.showPage()

    c.save()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate printable QR-code cards for SongSeeker.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Double-sided printing:
  Most printers default to "flip on long edge" (like a calendar).
  If your cards don't align back-to-back, try:
    --flip long    (mirror top↔bottom)
    --flip short   (mirror left↔right, like a book page)
    --flip none    (same layout, for manual alignment)

Examples:
  python tools/generate_cards.py songs.csv cards.pdf
  python tools/generate_cards.py songs.csv cards.pdf --flip long --icon icon.png --color
        """
    )
    parser.add_argument("csv_file", help="Path to the CSV file")
    parser.add_argument("output_pdf", help="Path to the output PDF file")
    parser.add_argument("--icon", help="Path to icon to embed in QR Code (should not exceed 300x300px, transparent background)", required=False)
    parser.add_argument("--flip", choices=["short", "long", "none"], default="short",
                        help="Double-sided flip direction: short=book-style horizontal flip (default), long=calendar-style vertical flip, none=no mirror")
    parser.add_argument("--color", action="store_true", default=False,
                        help="Use backcol values from CSV for colored card backs (default: no color)")
    parser.add_argument("--set-name", default="",
                        help="Set name printed in the corner of each card (e.g. 80s-90s)")
    args = parser.parse_args()
    main(args.csv_file, args.output_pdf, args.icon, args.flip, use_color=args.color, set_name=args.set_name)
