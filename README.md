# reading

A personal reading journal — static website generated from a JSON data file, hosted on S3 + CloudFront, with a small CLI for adding new books.

**What it does:**
- Renders ~170 books (2019–present) as a card layout with cover images, reviews, and year navigation
- Marks select books as "lasting impressions" with a visual accent
- Fetches cover images automatically from Open Library or Google Books
- Deploys to S3 and invalidates CloudFront in one command

**Stack:** Python, Jinja2, AWS CDK (Python), S3, CloudFront, ACM, IAM Identity Center

---

## Repository layout

```
src/
  add_book.py     # CLI: add a new book or fix a missing cover
  build.py        # render books.json → site/
  deploy.py       # sync site/ to S3 + CloudFront invalidation
  parse_docx.py   # one-time: convert .docx → books.json
  templates/      # Jinja2 template + CSS + favicon
infra/
  app.py
  cert_stack.py   # ACM certificate (us-east-1)
  reading_stack.py # S3 bucket + CloudFront distribution
  .env.example    # copy to .env and fill in
```

`data/`, `images/`, and `site/` are gitignored — they live only on the machine that builds and deploys.

---

## Setup

You probably need these packages installed:
```bash
apt install zlib1g-dev libjpeg-dev python3-dev build-essential
```

And then

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Adding a book

```bash
# Auto-fetch cover from Open Library / Google Books:
python src/add_book.py \
    --title "The Name of the Wind" \
    --author "Patrick Rothfuss" \
    --review-file review.txt \
    --month April --year 2026 \
    --deploy

# Mark as a lasting impression:
python src/add_book.py ... --lasting-impression

# Supply a cover image manually:
python src/add_book.py ... --cover-file ~/Downloads/cover.jpg

# Fix a missing cover on an existing book:
python src/add_book.py --fix-cover --title "Going Infinite"
```

`--deploy` rebuilds the site and pushes to S3 + CloudFront in one step. Without it, the site is rebuilt locally but not published.

See `python src/add_book.py --help` for the full reference.

---

## Build and deploy separately

```bash
python src/build.py    # writes to site/
python src/deploy.py   # syncs site/ to S3 and invalidates CloudFront
python src/deploy.py --dry-run  # show what would be uploaded
```

`deploy.py` reads the S3 bucket name and CloudFront distribution ID from CloudFormation stack outputs — no identifiers need to be hardcoded anywhere.

---

## Infrastructure (AWS CDK)

See `infra/.env.example` for required environment variables. Copy it to `infra/.env` (gitignored) and fill in your AWS account ID and domain.

```bash
cd infra
pip install -r requirements.txt

# One-time bootstrap:
cdk bootstrap aws://ACCOUNT/us-east-1 --profile books-admin

# Deploy:
cdk deploy CertStack --profile books-admin    # ACM cert (must validate via DNS first)
cdk deploy ReadingStack --profile books-admin # S3 + CloudFront
```

After deploying `ReadingStack`, add a CNAME from your domain to the CloudFront domain name shown in the stack outputs.

Credentials use IAM Identity Center (short-lived tokens, no long-lived keys stored anywhere).
