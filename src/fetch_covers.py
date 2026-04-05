"""
fetch_covers.py — unattended cover fetcher for books with missing or broken covers.

Targets books where cover_image is null OR cover_image == "covers/image10.png"
(image10.png was a known duplicate caused by a sort bug in fix_covers.py).

Tries Open Library first, then Google Books with exponential backoff on 429s.
Writes a summary at the end showing what succeeded and what was not found.

Run:
    python src/fetch_covers.py [--dry-run]
"""

import argparse
import io
import json
import logging
import random
import time
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data" / "books.json"
IMAGES_DIR = ROOT / "images" / "covers"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

TARGET_W, TARGET_H = 300, 450
BROKEN_COVER = "covers/image10.png"

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

def next_image_name() -> str:
    """Return the next available imageN.png filename (numerically sorted)."""
    existing = IMAGES_DIR.glob("image*.png")
    nums = []
    for p in existing:
        try:
            nums.append(int(p.stem.replace("image", "")))
        except ValueError:
            pass
    n = max(nums) + 1 if nums else 1
    return f"image{n}.png"


def save_cover(image_bytes: bytes, dest_path: Path):
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    img.thumbnail((TARGET_W, TARGET_H), Image.LANCZOS)
    background = Image.new("RGBA", (TARGET_W, TARGET_H), (255, 255, 255, 255))
    offset = ((TARGET_W - img.width) // 2, (TARGET_H - img.height) // 2)
    background.paste(img, offset, mask=img)
    background.convert("RGB").save(dest_path, "PNG", optimize=True)


# ---------------------------------------------------------------------------
# API fetchers with backoff
# ---------------------------------------------------------------------------

def get_with_backoff(url, params=None, max_retries=6, initial_delay=2):
    """GET with exponential backoff on 429. Returns Response or raises."""
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            r = requests.get(url, params=params, timeout=15)
            if r.status_code == 429:
                wait = delay + random.uniform(0, delay * 0.2)
                log.info(f"    429 rate limit — waiting {wait:.1f}s (attempt {attempt+1}/{max_retries})")
                time.sleep(wait)
                delay = min(delay * 2, 120)
                continue
            return r
        except requests.RequestException as e:
            log.warning(f"    Request error: {e}")
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay = min(delay * 2, 120)
            else:
                raise
    raise RuntimeError(f"Gave up after {max_retries} attempts: {url}")


def fetch_open_library(title: str, author: str):
    """Return image bytes from Open Library, or None."""
    try:
        r = get_with_backoff(
            "https://openlibrary.org/search.json",
            params={"title": title, "author": author, "limit": 5,
                    "fields": "cover_i,title,author_name"},
        )
        r.raise_for_status()
        for doc in r.json().get("docs", []):
            cover_id = doc.get("cover_i")
            if cover_id:
                img_r = get_with_backoff(
                    f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
                )
                img_r.raise_for_status()
                if len(img_r.content) > 2000:
                    return img_r.content
    except Exception as e:
        log.warning(f"    Open Library error: {e}")
    return None


def fetch_google_books(title: str, author: str):
    """Return image bytes from Google Books, or None."""
    try:
        r = get_with_backoff(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": f"intitle:{title} inauthor:{author}", "maxResults": 3},
        )
        r.raise_for_status()
        for item in r.json().get("items", []):
            links = item.get("volumeInfo", {}).get("imageLinks", {})
            thumb = links.get("thumbnail") or links.get("smallThumbnail")
            if thumb:
                thumb = thumb.replace("zoom=1", "zoom=3").replace("http://", "https://")
                img_r = get_with_backoff(thumb)
                img_r.raise_for_status()
                if len(img_r.content) > 2000:
                    return img_r.content
    except Exception as e:
        log.warning(f"    Google Books error: {e}")
    return None


def fetch_cover(title: str, author: str):
    """Try Open Library then Google Books. Return bytes or None."""
    log.info(f"  Trying Open Library...")
    result = fetch_open_library(title, author)
    if result:
        return result
    log.info(f"  Trying Google Books...")
    result = fetch_google_books(title, author)
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be fetched without saving anything")
    args = parser.parse_args()

    books = json.loads(DATA_FILE.read_text(encoding="utf-8"))

    targets = [
        (i, b) for i, b in enumerate(books)
        if not b.get("cover_image") or b.get("cover_image") == BROKEN_COVER
    ]

    log.info(f"\n{len(targets)} books to fix.\n")

    succeeded = []
    not_found = []
    errors = []

    for count, (idx, book) in enumerate(targets, 1):
        period = f"{book['month']} {book['year']}" if book["month"] else str(book["year"])
        log.info(f"[{count}/{len(targets)}] {book['title']} — {book['author']} ({period})")

        if args.dry_run:
            log.info("  (dry run — skipping fetch)\n")
            continue

        try:
            image_bytes = fetch_cover(book["title"], book["author"])
        except Exception as e:
            log.error(f"  ERROR: {e}")
            errors.append(book["title"])
            continue

        if image_bytes:
            fname = next_image_name()
            dest = IMAGES_DIR / fname
            save_cover(image_bytes, dest)
            books[idx]["cover_image"] = f"covers/{fname}"
            log.info(f"  Saved as {fname}\n")
            succeeded.append(book["title"])
            # Save after every successful fetch so progress isn't lost
            DATA_FILE.write_text(json.dumps(books, indent=2, ensure_ascii=False),
                                 encoding="utf-8")
        else:
            log.info(f"  Not found in any source.\n")
            not_found.append(book["title"])

        # Polite delay between books
        time.sleep(1.0)

    # Summary
    log.info("\n" + "=" * 60)
    log.info(f"Done. {len(succeeded)} fetched, {len(not_found)} not found, {len(errors)} errors.")
    if not_found:
        log.info("\nNot found (will keep placeholder cover):")
        for t in not_found:
            log.info(f"  - {t}")
    if errors:
        log.info("\nErrors (may be worth retrying):")
        for t in errors:
            log.info(f"  - {t}")


if __name__ == "__main__":
    main()
