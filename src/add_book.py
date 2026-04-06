"""
add_book.py — add a new book to the reading journal, or fix a missing cover.

== ADDING A NEW BOOK ==

Minimal (month defaults to current month, year to current year):

    python src/add_book.py \\
        --title "The Name of the Wind" \\
        --author "Patrick Rothfuss" \\
        --review "Beautifully written fantasy..." \\
        --month April --year 2026

The review can be written in a plain text file first (recommended for longer
reviews), then passed with --review-file:

    python src/add_book.py \\
        --title "The Name of the Wind" \\
        --author "Patrick Rothfuss" \\
        --review-file review.txt \\
        --month April

Mark a book as a lasting impression (shows lime green accent on the site):

    python src/add_book.py ... --lasting-impression

== COVER IMAGES ==

By default the script tries Open Library then Google Books to find a cover.
Nothing else needed — it handles downloading and resizing automatically.

If auto-fetch doesn't find anything, or you want a specific image:

    python src/add_book.py ... --cover-file ~/Downloads/cover.jpg

Windows paths also work (WSL converts them automatically):

    python src/add_book.py ... --cover-file "C:\\Users\\username\\Downloads\\cover.jpg"

To skip the cover entirely (a placeholder tile with the book's first letter
will be shown on the site instead):

    python src/add_book.py ... --no-cover

== FIXING A COVER ON AN EXISTING BOOK ==

Some books from the original import are missing covers. Fix them with:

    python src/add_book.py --fix-cover --title "Going Infinite"

That tries the APIs automatically. To supply the image yourself:

    python src/add_book.py --fix-cover --title "Going Infinite" \\
        --cover-file ~/Downloads/cover.jpg

== DEPLOYING ==

By default the script rebuilds the site locally but does not deploy. Add
--deploy to push to S3 and invalidate CloudFront in one step:

    python src/add_book.py ... --deploy

Or rebuild and deploy separately:

    python src/build.py
    python src/deploy.py

== BOOKS WITH MISSING COVERS (as of initial import) ==

These 11 books lost their covers during the Google Docs → .docx export.
Run --fix-cover for each when you get a chance:

    Solutions and Other Problems — Allie Brosh (January 2025)
    The Talented Mrs. Mandelbaum (December 2024)
    Age of Revolutions (October 2024)
    How Adam Smith Can Change Your Life (July 2024)
    How To Know a Person (May 2024)
    Going Infinite — Michael Lewis (March 2024)
    Trust — Hernan Diaz (September 2023)
    We Don't Know Ourselves (April 2023)
    How the Other Half Eats (February 2023)
    The Profiteers (September 2022)
    Grasp (April 2022)
"""

import argparse
import io
import json
import logging
import random
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data" / "books.json"
IMAGES_DIR = ROOT / "images" / "covers"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

TARGET_W, TARGET_H = 300, 450

VALID_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

def next_image_name() -> str:
    nums = []
    for p in IMAGES_DIR.glob("image*.png"):
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


def to_wsl_path(raw: str) -> Path:
    p = raw.strip().strip('"').strip("'")
    if len(p) >= 3 and p[1] == ":" and p[2] in ("/", "\\"):
        drive = p[0].lower()
        rest = p[3:].replace("\\", "/")
        p = f"/mnt/{drive}/{rest}"
    else:
        p = p.replace("\\", "/")
    return Path(p).expanduser()


# ---------------------------------------------------------------------------
# Cover fetchers
# ---------------------------------------------------------------------------

def get_with_backoff(url, params=None, max_retries=6, initial_delay=2):
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            r = requests.get(url, params=params, timeout=15)
            if r.status_code == 429:
                wait = delay + random.uniform(0, delay * 0.2)
                log.info(f"  429 rate limit — waiting {wait:.1f}s (attempt {attempt+1}/{max_retries})")
                time.sleep(wait)
                delay = min(delay * 2, 120)
                continue
            return r
        except requests.RequestException as e:
            log.warning(f"  Request error: {e}")
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay = min(delay * 2, 120)
            else:
                raise
    raise RuntimeError(f"Gave up after {max_retries} attempts: {url}")


def fetch_open_library(title: str, author: str):
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
                img_r = get_with_backoff(f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg")
                img_r.raise_for_status()
                if len(img_r.content) > 2000:
                    return img_r.content
    except Exception as e:
        log.warning(f"  Open Library error: {e}")
    return None


def fetch_google_books(title: str, author: str):
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
        log.warning(f"  Google Books error: {e}")
    return None


def acquire_cover(title: str, author: str, cover_file=None, no_cover=False):
    """
    Return (cover_image_value, saved_path_or_None).
    cover_image_value is e.g. "covers/image72.png" or None.
    """
    if no_cover:
        return None, None

    if cover_file:
        src = to_wsl_path(cover_file)
        if not src.exists():
            log.error(f"Cover file not found: {src}")
            sys.exit(1)
        fname = next_image_name()
        dest = IMAGES_DIR / fname
        save_cover(src.read_bytes(), dest)
        log.info(f"Cover saved from file: {fname}")
        return f"covers/{fname}", dest

    # Try APIs
    log.info("Fetching cover from Open Library...")
    image_bytes = fetch_open_library(title, author)
    if not image_bytes:
        log.info("Trying Google Books...")
        image_bytes = fetch_google_books(title, author)

    if image_bytes:
        fname = next_image_name()
        dest = IMAGES_DIR / fname
        save_cover(image_bytes, dest)
        log.info(f"Cover fetched and saved: {fname}")
        return f"covers/{fname}", dest
    else:
        log.info("No cover found — will show placeholder tile.")
        return None, None


# ---------------------------------------------------------------------------
# books.json helpers
# ---------------------------------------------------------------------------

def load_books():
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def save_books(books):
    DATA_FILE.write_text(json.dumps(books, indent=2, ensure_ascii=False), encoding="utf-8")


def find_book(books, title: str):
    title_lower = title.lower()
    matches = [b for b in books if b["title"].lower() == title_lower]
    if not matches:
        # Partial match fallback
        matches = [b for b in books if title_lower in b["title"].lower()]
    return matches


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def mode_fix_cover(args):
    books = load_books()
    matches = find_book(books, args.title)

    if not matches:
        log.error(f"No book found matching title: {args.title!r}")
        sys.exit(1)
    if len(matches) > 1:
        log.error(f"Ambiguous title — {len(matches)} matches:")
        for b in matches:
            log.error(f"  {b['title']} — {b['author']}")
        sys.exit(1)

    book = matches[0]
    idx = books.index(book)
    log.info(f"Fixing cover for: {book['title']} — {book['author']}")

    cover_value, _ = acquire_cover(
        book["title"], book["author"],
        cover_file=args.cover_file,
        no_cover=args.no_cover,
    )
    books[idx]["cover_image"] = cover_value
    save_books(books)
    log.info("books.json updated.")

    rebuild_and_deploy(args.deploy)


def mode_add_book(args):
    # Validate required fields
    if not args.title:
        log.error("--title is required")
        sys.exit(1)
    if not args.author:
        log.error("--author is required")
        sys.exit(1)

    # Review text
    if args.review_file:
        review_path = to_wsl_path(args.review_file)
        if not review_path.exists():
            log.error(f"Review file not found: {review_path}")
            sys.exit(1)
        review = review_path.read_text(encoding="utf-8").strip()
    elif args.review:
        review = args.review.strip()
    else:
        log.error("Provide a review via --review or --review-file")
        sys.exit(1)

    # Month / year
    month = args.month
    if month and month not in VALID_MONTHS:
        # Case-insensitive fix
        matched = [m for m in VALID_MONTHS if m.lower() == month.lower()]
        if matched:
            month = matched[0]
        else:
            log.error(f"Unknown month: {month!r}. Use full name, e.g. April")
            sys.exit(1)

    year = args.year or date.today().year

    # Cover
    cover_value, _ = acquire_cover(
        args.title, args.author,
        cover_file=args.cover_file,
        no_cover=args.no_cover,
    )

    entry = {
        "title": args.title,
        "author": args.author,
        "review": review,
        "year": year,
        "month": month,
        "cover_image": cover_value,
        "lasting_impression": args.lasting_impression,
    }

    books = load_books()

    # Insert at the front (newest first)
    books.insert(0, entry)
    save_books(books)

    log.info(f"\nAdded: {entry['title']} — {entry['author']}")
    log.info(f"  Period: {month or '(no month)'} {year}")
    log.info(f"  Cover:  {cover_value or 'none (placeholder)'}")
    log.info(f"  Lasting impression: {entry['lasting_impression']}")

    rebuild_and_deploy(args.deploy)


def rebuild_and_deploy(deploy: bool):
    log.info("\nRebuilding site...")
    subprocess.run([sys.executable, str(ROOT / "src" / "build.py")], check=True)
    log.info("Build complete.")

    if deploy:
        log.info("\nDeploying...")
        subprocess.run([sys.executable, str(ROOT / "src" / "deploy.py")], check=True)
    else:
        log.info("Run 'python src/deploy.py' to publish.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Add a new book to the reading journal, or fix a missing cover on an existing one.\n"
            "After updating books.json the site is rebuilt automatically.\n"
            "Run with --deploy to also push to S3 + CloudFront in one step."
        ),
        epilog=(
            "Examples:\n"
            "  # Add a book, let the script find the cover automatically:\n"
            "  python src/add_book.py --title \"Demon Copperhead\" --author \"Barbara Kingsolver\"\n"
            "      --review-file review.txt --month April --deploy\n"
            "\n"
            "  # Add a book you want to mark as a lasting impression:\n"
            "  python src/add_book.py --title \"Demon Copperhead\" --author \"Barbara Kingsolver\"\n"
            "      --review-file review.txt --lasting-impression --deploy\n"
            "\n"
            "  # Fix a missing cover (auto-fetch from API):\n"
            "  python src/add_book.py --fix-cover --title \"Going Infinite\"\n"
            "\n"
            "  # Fix a missing cover with a local file (Windows path works too):\n"
            "  python src/add_book.py --fix-cover --title \"Going Infinite\"\n"
            "      --cover-file \"C:\\\\Users\\\\username\\\\Downloads\\\\cover.jpg\"\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--fix-cover", action="store_true",
        help=(
            "Fix the cover for an existing book rather than adding a new one. "
            "Requires --title. Optionally use --cover-file to supply an image; "
            "otherwise the script tries Open Library then Google Books."
        ),
    )

    # Book fields
    parser.add_argument("--title", help="Book title (required)")
    parser.add_argument("--author", help="Author name (required for new books)")
    parser.add_argument(
        "--review",
        help="Review text, written inline. Use --review-file for longer reviews.",
    )
    parser.add_argument(
        "--review-file", metavar="PATH",
        help=(
            "Path to a plain text file containing the review. "
            "Windows paths like C:\\\\Users\\\\username\\\\review.txt are converted automatically."
        ),
    )
    parser.add_argument(
        "--month",
        help="Month you finished the book, e.g. April. Defaults to no month if omitted.",
    )
    parser.add_argument(
        "--year", type=int,
        help="Year you finished the book. Defaults to the current year.",
    )
    parser.add_argument(
        "--lasting-impression", action="store_true",
        help=(
            "Mark this book as a lasting impression. "
            "It will appear with a lime green accent and a memorable badge on the site."
        ),
    )

    # Cover options
    cover_group = parser.add_mutually_exclusive_group()
    cover_group.add_argument(
        "--cover-file", metavar="PATH",
        help=(
            "Local image file to use as the cover (JPG, PNG, etc.). "
            "The image is resized and letterboxed automatically. "
            "If not provided, the script tries Open Library then Google Books."
        ),
    )
    cover_group.add_argument(
        "--no-cover", action="store_true",
        help=(
            "Skip the cover entirely. The site will show a placeholder tile "
            "with the book's first letter instead."
        ),
    )

    parser.add_argument(
        "--deploy", action="store_true",
        help=(
            "After rebuilding the site, sync to S3 and invalidate CloudFront. "
            "Equivalent to running python src/deploy.py afterwards."
        ),
    )

    args = parser.parse_args()

    if args.fix_cover:
        if not args.title:
            log.error("--fix-cover requires --title")
            sys.exit(1)
        mode_fix_cover(args)
    else:
        mode_add_book(args)


if __name__ == "__main__":
    main()
