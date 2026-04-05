"""
fix_covers.py — interactively fix missing or broken cover images in books.json.

Targets books where cover_image is null OR still pointing at the broken
duplicate "covers/image10.png" from a previous run.

For each book you'll be prompted:
  - Paste a local file path (e.g. /mnt/c/Users/username/Downloads/cover.png)
  - Press Enter to skip — leaves cover_image as null (no placeholder)

Images are saved to images/covers/ with a unique name. Progress is saved
after every book so you can Ctrl+C and resume later.

Run:
    python src/fix_covers.py
"""

import io
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data" / "books.json"
IMAGES_DIR = ROOT / "images" / "covers"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

TARGET_W, TARGET_H = 300, 450
BROKEN_COVER = "covers/image10.png"


def next_image_name() -> str:
    """Return the next available imageN.png filename (numerically sorted)."""
    nums = []
    for p in IMAGES_DIR.glob("image*.png"):
        try:
            nums.append(int(p.stem.replace("image", "")))
        except ValueError:
            pass
    n = max(nums) + 1 if nums else 1
    return f"image{n}.png"


def to_wsl_path(raw: str) -> Path:
    """Convert a Windows path to a WSL path if needed, strip surrounding quotes."""
    p = raw.strip().strip('"').strip("'")
    # Detect Windows path: starts with a drive letter e.g. C:\ or C:/
    if len(p) >= 3 and p[1] == ":" and p[2] in ("/", "\\"):
        drive = p[0].lower()
        rest = p[3:].replace("\\", "/")
        p = f"/mnt/{drive}/{rest}"
    else:
        p = p.replace("\\", "/")
    return Path(p).expanduser()


def save_cover(image_bytes: bytes, dest_path: Path):
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    img.thumbnail((TARGET_W, TARGET_H), Image.LANCZOS)
    background = Image.new("RGBA", (TARGET_W, TARGET_H), (255, 255, 255, 255))
    offset = ((TARGET_W - img.width) // 2, (TARGET_H - img.height) // 2)
    background.paste(img, offset, mask=img)
    background.convert("RGB").save(dest_path, "PNG", optimize=True)


def main():
    books = json.loads(DATA_FILE.read_text(encoding="utf-8"))

    targets = [
        (i, b) for i, b in enumerate(books)
        if not b.get("cover_image") or b.get("cover_image") == BROKEN_COVER
    ]

    total = len(targets)
    if not total:
        print("No books need fixing.")
        return

    print(f"\n{total} books to fix.")
    print("For each: paste a file path, or press Enter to skip (leaves cover empty).\n")

    for count, (idx, book) in enumerate(targets, 1):
        period = f"{book['month']} {book['year']}" if book["month"] else str(book["year"])
        print(f"[{count}/{total}] {book['title']}")
        print(f"        {book['author']}  ({period})")

        answer = input("  File path (or Enter to skip): ").strip()

        if not answer:
            # Explicitly null it out (clears any broken image10.png reference)
            books[idx]["cover_image"] = None
            print("  Skipped — cover set to null.\n")
        else:
            src = to_wsl_path(answer)
            if not src.exists():
                print(f"  File not found: {src} — skipping.\n")
                books[idx]["cover_image"] = None
            else:
                fname = next_image_name()
                dest = IMAGES_DIR / fname
                save_cover(src.read_bytes(), dest)
                books[idx]["cover_image"] = f"covers/{fname}"
                print(f"  Saved as {fname}\n")

        # Save after every book so Ctrl+C doesn't lose progress
        DATA_FILE.write_text(
            json.dumps(books, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    print("Done.")


if __name__ == "__main__":
    main()
