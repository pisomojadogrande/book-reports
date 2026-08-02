"""
build.py — generate site/ from data/books.json and src/templates/.

Run:
    python src/build.py
"""

import json
import re
import shutil
from markupsafe import Markup, escape
from collections import defaultdict
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data" / "books.json"
TEMPLATES_DIR = Path(__file__).parent / "templates"
SITE_DIR = ROOT / "site"
IMAGES_SRC = ROOT / "images" / "covers"
IMAGES_DEST = SITE_DIR / "covers"

MONTH_ORDER = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}


_BOOK_TITLE_RE = re.compile(r'<book_title>(.*?)</book_title>', re.DOTALL)
_URL_RE = re.compile(r'https?://\S+')


def render_review(text):
    """Process review paragraph: <book_title> → <em>, bare URLs → <a>."""
    parts = _BOOK_TITLE_RE.split(text)
    out = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            escaped = str(escape(part))
            escaped = _URL_RE.sub(
                lambda m: f'<a href="{m.group()}" target="_blank" rel="noopener">{m.group()}</a>',
                escaped,
            )
            out.append(escaped)
        else:
            out.append(f'<em>{escape(part)}</em>')
    return Markup(''.join(out))


def slugify(text):
    text = text.lower()
    text = re.sub(r"['\u2018\u2019\u201c\u201d]", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def group_books(books):
    """
    Return a list of (year, [(period_label, [books])]) sorted newest first.
    period_label is "Month Year" for 2022+, or just the year string for earlier.
    """
    # Bucket by (year, month)
    buckets = defaultdict(list)
    for book in books:
        key = (book["year"], book.get("month"))
        buckets[key].append(book)

    # Sort keys: year desc, month desc
    def sort_key(k):
        year, month = k
        return (-year, -(MONTH_ORDER.get(month, 0)))

    sorted_keys = sorted(buckets.keys(), key=sort_key)

    # Group by year
    years_seen = []
    by_year = defaultdict(list)
    for year, month in sorted_keys:
        if year not in years_seen:
            years_seen.append(year)
        label = f"{month} {year}" if month else str(year)
        by_year[year].append((label, buckets[(year, month)]))

    return [(y, by_year[y]) for y in years_seen]


def main():
    books = json.loads(DATA_FILE.read_text(encoding="utf-8"))

    # Build grouped structure for template
    grouped = group_books(books)
    years = [y for y, _ in grouped]

    # Set up Jinja2
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    env.filters["slugify"] = slugify
    env.filters["render_review"] = render_review
    template = env.get_template("index.html.j2")

    # Render
    html = template.render(
        grouped=grouped,
        years=years,
        updated=date.today().strftime("%B %Y"),
    )

    # Write output
    SITE_DIR.mkdir(exist_ok=True)
    (SITE_DIR / "index.html").write_text(html, encoding="utf-8")

    # Copy CSS and favicons
    shutil.copy(TEMPLATES_DIR / "style.css", SITE_DIR / "style.css")
    shutil.copy(TEMPLATES_DIR / "favicon.png", SITE_DIR / "favicon.png")
    shutil.copy(TEMPLATES_DIR / "favicon.svg", SITE_DIR / "favicon.svg")

    # Copy cover images
    if IMAGES_SRC.exists():
        IMAGES_DEST.mkdir(exist_ok=True)
        for img in IMAGES_SRC.glob("*.png"):
            shutil.copy(img, IMAGES_DEST / img.name)

    print(f"Built {len(books)} books → {SITE_DIR / 'index.html'}")
    covers_copied = len(list(IMAGES_DEST.glob("*.png"))) if IMAGES_DEST.exists() else 0
    print(f"Copied {covers_copied} cover images")


if __name__ == "__main__":
    main()
