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
- [ ] Create Python virtual environment
- [ ] Install dependencies (`python-docx`, `Pillow`, `jinja2`, `requests`, `boto3`)
- [ ] Create `requirements.txt`

### Phase 2: Parse & Convert the .docx

**Script:** `src/parse_docx.py` — run once to bootstrap the project.

- [ ] Walk document structure, identify all section headings (year and month/year)
- [ ] Extract each book entry: title, author, review, year, month, lasting_impression flag
- [ ] Extract all embedded PNG cover images to `images/covers/`
- [ ] Normalize image sizes with Pillow at extraction time
- [ ] Write all entries to `data/books.json`
- [ ] Verify output: inspect `books.json` for correctness and completeness
- [ ] Verify all cover images extracted and named consistently

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

- [ ] Write Jinja2 HTML template
- [ ] Write CSS (card layout, typography, year nav, lasting-impression styling, responsive)
- [ ] Implement build script: reads `books.json`, renders template, copies covers to `site/`
- [ ] Verify local preview looks correct in browser
- [ ] Iterate on design until satisfied

Design spec:
- **Card layout:** cover image left (uniform 120×180px, letterboxed), title/author/review right
- **Lasting impression:** subtle left-border accent or small badge
- **Section headers:** "March 2026" style for 2022+; plain year for 2019–2021
- **Year nav:** sticky top bar with jump links
- **Typography:** Inter (Google Fonts), ~700px reading width, centered, responsive
- **No-cover placeholder:** neutral tile with first letter of title

### Phase 4: AWS Infrastructure

**Deployed via AWS CDK (Python). All mutating actions confirmed by the account owner before execution.**

#### Credentials (IAM Identity Center, not IAM Users)
- [ ] Discuss and confirm IAM Identity Center setup with account owner
- [ ] Enable IAM Identity Center in new AWS account
- [ ] Create permission set with inline policy: `s3:PutObject`, `s3:DeleteObject`, `s3:ListBucket` + `cloudfront:CreateInvalidation`
- [ ] Assign permission set to account owner's user
- [ ] Configure local AWS CLI profile (`aws configure sso --profile reading`)
- [ ] Verify: `aws sts get-caller-identity --profile reading`

#### CDK Stack
- [ ] Write CDK stack (`infra/reading_stack.py`): S3 bucket, OAC, CloudFront distribution, ACM cert
- [ ] Review CDK stack with account owner before deploying
- [ ] Bootstrap CDK in account: `cdk bootstrap --profile reading`
- [ ] Deploy stack: `cdk deploy --profile reading`
- [ ] Note the CloudFront distribution domain name from stack outputs

#### ACM Certificate DNS Validation
- [ ] Add validation CNAME record in Route53 account (walked through step by step)
- [ ] Confirm certificate reaches `Issued` status in ACM console

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
