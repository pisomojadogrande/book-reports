from pathlib import Path
from PIL import Image

def save_natural(src, dest, max_dim=600):
    img = Image.open(src).convert('RGB')
    img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    img.save(dest, 'PNG', optimize=True)
    print('Saved', dest, img.size)

def to_path(raw):
    p = raw.strip().strip('"').strip("'")
    if len(p) > 2 and p[1] == ':':
        p = '/mnt/' + p[0].lower() + '/' + p[3:].replace('\\', '/')
    return Path(p)

for name, dest in [('Torah', 'images/covers/image83.png'),
                   ('Mayer July', 'images/covers/image80.png')]:
    raw = input(f'Path to {name} image: ')
    src = to_path(raw)
    if not src.exists():
        print(f'Not found: {src}')
    else:
        save_natural(src, dest)
