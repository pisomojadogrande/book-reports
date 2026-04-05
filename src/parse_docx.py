"""
parse_docx.py — one-time conversion of the reading journal .docx to books.json.

Run:
    python src/parse_docx.py --docx "/path/to/file.docx"

Outputs:
    data/books.json       — all book entries
    images/covers/        — extracted cover images (as imageN.png)
"""

import argparse
import io
import json
import re
import sys
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from PIL import Image


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
IMAGES_DIR = ROOT / "images" / "covers"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MONTH_NAMES = {
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
}


def parse_heading(text: str):
    """
    Parse a Heading 3 text into (year, month_or_None).
    "March 2026" -> (2026, "March")
    "2021"       -> (2021, None)
    Returns None if not a date heading.
    """
    text = text.strip()
    if re.fullmatch(r"\d{4}", text):
        return (int(text), None)
    m = re.fullmatch(r"([A-Za-z]+)\s+(\d{4})", text)
    if m and m.group(1).lower() in MONTH_NAMES:
        return (int(m.group(2)), m.group(1).capitalize())
    return None


def paragraph_has_image(para):
    return para._p.find(".//" + qn("w:drawing")) is not None


def is_title_paragraph(para):
    """A title paragraph is normal-style with a bold+italic first non-empty run."""
    if para.style.name.lower() != "normal":
        return False
    for run in para.runs:
        if run.text.strip():
            return bool(run.font.bold and run.font.italic)
    return False


def extract_title_and_rest(para):
    """
    Return (title, lasting_impression, rest_text) from a title paragraph.
    Title = text of leading bold+italic runs.
    lasting_impression = True if any title run is also underlined.
    rest_text = all remaining run text on the same paragraph.
    """
    title_parts = []
    rest_parts = []
    in_title = True
    lasting = False

    for run in para.runs:
        if in_title and run.font.bold and run.font.italic:
            title_parts.append(run.text)
            if run.font.underline:
                lasting = True
        else:
            in_title = False
            rest_parts.append(run.text)

    title = "".join(title_parts).strip().rstrip(",").strip()
    rest = "".join(rest_parts).strip()
    return title, lasting, rest


def split_author_review(rest_text: str):
    """
    rest_text is everything after the bold+italic title on the title line,
    typically: ", Author Name. Review sentence..."
    Returns (author, review_start).
    """
    rest_text = rest_text.lstrip(",").strip()
    m = re.search(r"\.\s+", rest_text)
    if m:
        author = rest_text[: m.start()].strip()
        review_start = rest_text[m.end():].strip()
        return author, review_start
    return rest_text.strip(), ""


def extract_image_bytes(para, doc):
    """Return raw image bytes from the first inline drawing, or None."""
    drawing = para._p.find(".//" + qn("w:drawing"))
    if drawing is None:
        return None
    blip = drawing.find(".//" + qn("a:blip"))
    if blip is None:
        return None
    embed = blip.get(qn("r:embed"))
    if not embed:
        return None
    part = doc.part.related_parts.get(embed)
    if part is None:
        return None
    return part.blob


def save_cover(image_bytes: bytes, dest_path: Path):
    """
    Save cover image normalized to 300×450px with letterboxing (white background).
    """
    TARGET_W, TARGET_H = 300, 450
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    img.thumbnail((TARGET_W, TARGET_H), Image.LANCZOS)
    background = Image.new("RGBA", (TARGET_W, TARGET_H), (255, 255, 255, 255))
    offset = ((TARGET_W - img.width) // 2, (TARGET_H - img.height) // 2)
    background.paste(img, offset, mask=img)
    background.convert("RGB").save(dest_path, "PNG", optimize=True)


# ---------------------------------------------------------------------------
# Main parsing logic
# ---------------------------------------------------------------------------

def parse_document(docx_path: Path):
    doc = Document(str(docx_path))
    paragraphs = doc.paragraphs

    # --- Pass 1: split document into sections ---
    # Each section = {"year": int, "month": str|None, "paras": [para, ...]}
    sections = []
    current_section = None

    for para in paragraphs:
        if para.style.name == "Heading 3":
            parsed = parse_heading(para.text)
            if parsed:
                current_section = {"year": parsed[0], "month": parsed[1], "paras": []}
                sections.append(current_section)
                # Note: some heading paragraphs contain a stray embedded image
                # (export artifact from Google Docs float layout). We do NOT
                # include these — images always belong to book entries.
            # Empty/unparseable headings are ignored
        else:
            if current_section is not None:
                current_section["paras"].append(para)

    # --- Pass 2: extract books from each section ---
    image_counter = [0]
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    books = []

    for section in sections:
        year = section["year"]
        month = section["month"]
        paras = section["paras"]

        # Find indices of title paragraphs
        title_indices = [i for i, p in enumerate(paras) if is_title_paragraph(p)]

        for n, ti in enumerate(title_indices):
            title_para = paras[ti]
            title, lasting, rest = extract_title_and_rest(title_para)
            if not title:
                continue

            author, review_start = split_author_review(rest)

            # Slice out the paragraphs "belonging" to this book:
            # from just before the title (to catch pre-title images) to just
            # before the next title (exclusive).
            block_start = ti - 1 if ti > 0 else ti
            block_end = title_indices[n + 1] if n + 1 < len(title_indices) else len(paras)
            block_paras = paras[block_start:block_end]

            # Find cover image: check title_para itself first (image embedded
            # alongside title text), then scan the rest of the block.
            cover_path = None
            review_parts = [review_start] if review_start else []

            if paragraph_has_image(title_para):
                image_bytes = extract_image_bytes(title_para, doc)
                if image_bytes:
                    image_counter[0] += 1
                    fname = f"image{image_counter[0]}.png"
                    save_cover(image_bytes, IMAGES_DIR / fname)
                    cover_path = f"covers/{fname}"

            for para in block_paras:
                if para is title_para:
                    continue
                if paragraph_has_image(para):
                    if cover_path is None:
                        image_bytes = extract_image_bytes(para, doc)
                        if image_bytes:
                            image_counter[0] += 1
                            fname = f"image{image_counter[0]}.png"
                            dest = IMAGES_DIR / fname
                            save_cover(image_bytes, dest)
                            cover_path = f"covers/{fname}"
                else:
                    text = para.text.strip()
                    if text and para in paras[ti:block_end]:
                        review_parts.append(text)

            review = "\n\n".join(p for p in review_parts if p).strip()

            books.append({
                "title": title,
                "author": author,
                "review": review,
                "year": year,
                "month": month,
                "cover_image": cover_path,
                "lasting_impression": lasting,
            })

    return books


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Convert reading journal .docx to books.json")
    parser.add_argument("--docx", required=True, help="Path to the .docx file")
    args = parser.parse_args()

    docx_path = Path(args.docx)
    if not docx_path.exists():
        print(f"Error: file not found: {docx_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing {docx_path} ...")
    books = parse_document(docx_path)

    out_path = DATA_DIR / "books.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(books, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(books)} books to {out_path}")
    print(f"Cover images saved to {IMAGES_DIR}")

    with_covers = sum(1 for b in books if b["cover_image"])
    with_lasting = sum(1 for b in books if b["lasting_impression"])
    print(f"  {with_covers} books with cover images")
    print(f"  {with_lasting} lasting impression books")
    years = sorted(set(b["year"] for b in books if b["year"]))
    print(f"  Years: {years[0]}–{years[-1]}")


if __name__ == "__main__":
    main()
