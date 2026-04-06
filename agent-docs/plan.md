# reading.example.com — Project Plan

> **Note to agents:** This document is the authoritative project plan. As each task or sub-task is completed, check it off by changing `[ ]` to `[x]`. Do not mark something complete until it has been verified working. Do not skip ahead — complete and check off items in order within each phase.

---

## Overview

Convert a Google Doc (.docx) reading journal into a clean, hosted static website at
`reading.example.com`, with a minimal CLI tool for adding new books going forward.

---

## Source Material

- **File:** `What I have read, ~2019-present.docx`
- **~170 books** spanning 2019–present
- **Structure:**
  - 2019–2021: year-only headings, no month breakdown, few/no cover images
  - 2022–present: monthly headings, embedded PNG cover images (69 total)
- **Per-book fields:** title, author, prose review, cover image (2022+), month/year read
- **Special flag:** underlined titles = "lasting impression" books (29 of them)

---

## Project Repository Structure

```
reading/
├── agent-docs/
│   └── plan.md               # this file
├── data/
│   └── books.json            # canonical data source (all books + metadata)
├── images/
│   └── covers/               # extracted cover images + future additions
├── src/
│   ├── parse_docx.py         # one-time: converts .docx → books.json + extracts images
│   ├── build.py              # reads books.json → generates site/
│   ├── add_book.py           # CMS script: add a new book entry
│   └── deploy.py             # syncs site/ to S3 + CloudFront invalidation
├── site/                     # generated output (do not edit by hand)
│   ├── index.html
│   ├── style.css
│   └── covers/               # cover images copied here at build time
└── infra/
    ├── app.py
    ├── reading_stack.py
    ├── requirements.txt
    └── cdk.json
```

---

## Implementation Checklist

### Phase 1: Setup
- [x] Create Python virtual environment
- [x] Install dependencies (`python-docx`, `Pillow`, `jinja2`, `requests`, `boto3`)
- [x] Create `requirements.txt`

### Phase 2: Parse & Convert the .docx

**Script:** `src/parse_docx.py` — run once to bootstrap the project.

- [x] Walk document structure, identify all section headings (year and month/year)
- [x] Extract each book entry: title, author, review, year, month, lasting_impression flag
- [x] Extract all embedded PNG cover images to `images/covers/`
- [x] Normalize image sizes with Pillow at extraction time
- [x] Write all entries to `data/books.json`
- [x] Verify output: inspect `books.json` for correctness and completeness
- [x] Verify all cover images extracted and named consistently

#### Known missing covers (deferred)

11 books from 2022+ had their cover images land in section heading paragraphs during
the Google Docs → .docx export (a float-layout artifact). They cannot be recovered
from the .docx and will render as placeholder tiles until fixed manually.

Fix each one with:
```bash
python src/add_book.py --fix-cover --title "..." [--cover-file ~/path/to/cover.jpg]
```
Or let the script auto-fetch from Open Library/Google Books.

- [ ] Solutions and Other Problems — Allie Brosh (January 2025)
- [ ] The Talented Mrs. Mandelbaum (December 2024)
- [ ] Age of Revolutions (October 2024)
- [ ] How Adam Smith Can Change Your Life (July 2024)
- [ ] How To Know a Person (May 2024)
- [ ] Going Infinite — Michael Lewis (March 2024)
- [ ] Trust — Hernan Diaz (September 2023)
- [ ] We Don't Know Ourselves (April 2023)
- [ ] How the Other Half Eats (February 2023)
- [ ] The Profiteers (September 2022)
- [ ] Grasp (April 2022)

The per-book JSON record shape:
```json
{
  "title": "The Subtle Art of Not Giving a F*ck",
  "author": "Mark Manson",
  "review": "...",
  "year": 2019,
  "month": null,
  "cover_image": "covers/image1.png",
  "lasting_impression": false
}
```

Notes:
- 2019–2021 entries have `month: null`
- 2019–2021 entries with no cover image: `cover_image: null`

### Phase 3: Build the Static Site

**Script:** `src/build.py` — run every time `books.json` changes.

- [x] Write Jinja2 HTML template
- [x] Write CSS (card layout, typography, year nav, lasting-impression styling, responsive)
- [x] Implement build script: reads `books.json`, renders template, copies covers to `site/`
- [x] Verify local preview looks correct in browser
- [x] Iterate on design until satisfied

Design spec:
- **Card layout:** cover image left (uniform 120×180px, letterboxed), title/author/review right
- **Lasting impression:** subtle left-border accent or small badge
- **Section headers:** "March 2026" style for 2022+; plain year for 2019–2021
- **Year nav:** sticky top bar with jump links
- **Typography:** Inter (Google Fonts), ~700px reading width, centered, responsive
- **No-cover placeholder:** neutral tile with first letter of title

### Phase 4: AWS Infrastructure

**Deployed via AWS CDK (Python). All mutating actions performed by the account owner; Claude verifies with `books-ro` profile.**

#### Credentials
- [x] IAM Identity Center already configured; `books-admin` and `books-ro` CLI profiles already set up
- [ ] Verify profiles work: `aws sts get-caller-identity --profile books-ro`

#### CDK Bootstrap (one-time)
- [ ] `cdk bootstrap aws://ACCOUNT/us-east-1 --profile books-admin`

#### Stack 1: CertStack (ACM certificate)
- [x] Write `infra/cert_stack.py`
- [x] Review with account owner
- [ ] Deploy: `cdk deploy CertStack --profile books-admin`
- [ ] Add ACM validation CNAME in Route53 account (walked through step by step)
- [ ] Confirm certificate reaches `Issued` status in ACM console

#### Stack 2: ReadingStack (S3 + CloudFront)
- [x] Write `infra/reading_stack.py`: S3 bucket (account regional namespace), OAC, CloudFront distribution
- [x] Review with account owner
- [ ] Deploy: `cdk deploy ReadingStack --profile books-admin`
- [ ] Confirm stack outputs: CloudFront domain name, S3 bucket name

### Phase 5: DNS

**Action taken manually in the Route53 account (separate from content account).**

- [ ] Receive CloudFront domain name from CDK stack output
- [ ] Add CNAME record in Route53: `reading.example.com` → `<distribution>.cloudfront.net`, TTL 300
- [ ] Confirm DNS propagation (`dig reading.example.com`)
- [ ] Confirm site loads over HTTPS

### Phase 6: Deploy Script

**Script:** `src/deploy.py`

- [ ] Write deploy script: build → S3 sync (with correct Content-Type headers) → CloudFront invalidation
- [ ] Test deploy with `--dry-run` flag first
- [ ] Do first real deploy
- [ ] Verify live site matches local preview

### Phase 7: Minimal CMS — `add_book.py`

**Script:** `src/add_book.py`

- [ ] Implement CLI argument parsing (title, author, review/review-file, month, year, lasting-impression, no-cover, cover-file)
- [ ] Implement Open Library cover search
- [ ] Implement Google Books fallback
- [ ] Implement local file fallback + placeholder
- [ ] Implement books.json update (prepend new entry)
- [ ] Implement post-add rebuild + optional deploy prompt
- [ ] Test end-to-end with a real new book entry
- [ ] Verify result on live site

### Phase 8: Smoke Test
- [ ] Site loads at correct URL over HTTPS
- [ ] All cover images display
- [ ] Year navigation links work
- [ ] Lasting-impression books visually distinct
- [ ] Site is readable on mobile
- [ ] `add_book.py` round-trip works end-to-end

---

## Future Enhancements (deferred)

- Year/month filter buttons
- Full-text search (client-side, e.g. Fuse.js — no server needed)
- "Lasting impression" filter toggle
- Reading stats page (books per year, pace over time)
- RSS feed of new entries
- Open Graph tags so links preview nicely when shared

---

## Key Decisions

| Decision | Choice |
|---|---|
| Source of truth | `data/books.json` (generated once from .docx, maintained by `add_book.py` going forward) |
| Build approach | Python scripts, no framework, no Node |
| Hosting | S3 + CloudFront (new AWS account) |
| IaC | AWS CDK (Python) |
| DNS | CNAME added manually in existing Route53 account |
| Deploy credentials | IAM Identity Center SSO (short-lived tokens, no long-lived keys) |
| Cover source (new books) | Open Library → Google Books → local file fallback |
| AWS access | Account owner confirms all mutating actions; Claude walks through steps and verifies |
