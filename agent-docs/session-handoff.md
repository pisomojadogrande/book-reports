# Session Handoff — Reading Site Project

## Where we are

Phases 1–3 are complete and committed. We are mid-way through **Phase 4 (AWS Infrastructure)** — the CDK stack has NOT been written yet. We were in the planning/Q&A stage when the session ended.

## What is done

- `src/parse_docx.py` — one-time parser, already run, output is in `data/books.json` + `images/covers/`
- `src/build.py` + `src/templates/` — static site generator, already run, output is in `site/`
- `src/fix_covers.py`, `src/fetch_covers.py` — cover image tooling, already used
- `requirements.txt` — all Python deps installed in `.venv/`
- `agent-docs/plan.md` — full project plan with checklists (Phases 1–3 checked off)

## What is NOT done yet

- Phase 4: CDK stack (`infra/`) — not written
- Phase 5: DNS CNAME in Route53 account
- Phase 6: `src/deploy.py`
- Phase 7: `src/add_book.py`
- Phase 8: Smoke test

## AWS context (NEVER commit these values to git)

- **New AWS account** (S3 + CloudFront): account ID is in gitignored `infra/.env` (not yet created)
- **Site domain**: books.example.com
- **Route53 account**: SEPARATE account from the deployment account — only needs a manual CNAME record added, no CDK involvement
- **CDK version**: 2.1109.0
- **Region**: us-east-1
- **AWS CLI profiles**:
  - `books-ro` — read-only, for Claude to use for verification/troubleshooting
  - `books-admin` — admin, for the user to run deployments (Claude never uses this)
- **CDK bootstrap status**: probably NOT done yet — needs to be done before first `cdk deploy`
- **IAM Identity Center**: already set up in the deployment account; no CDK work needed for it

## CDK stack design (agreed, not yet written)

**Identifier handling** — nothing account-specific committed to git:
- Account ID, domain, any ARNs → gitignored `infra/.env`, read via `os.environ` in `app.py`
- CloudFront distribution ID, bucket name → stack outputs only

**Resources in the stack:**
1. **S3 bucket** — using account regional namespaces (`bucket_namespace="account-regional"`, `bucket_name_prefix="books"`). Uses CDK L1 `CfnBucket`. Bucket name will resolve to `books-{accountId}-us-east-1-an` at deploy time.
2. **CloudFront OAC** — `CfnOriginAccessControl` for S3
3. **CloudFront Distribution** — origin is S3 via OAC, default root `index.html`, 404→`/index.html`, alternate domain `books.example.com`, SSL via ACM cert
4. **ACM Certificate** — DNS validation (manual), us-east-1. Deploy will pause waiting for validation — user adds CNAME in Route53 account, then deploy continues.

**NOT in the stack:** IAM permission sets (already handled by existing `books-admin` profile)

**infra/ layout:**
```
infra/
├── app.py
├── reading_stack.py
├── requirements.txt
├── cdk.json
└── .env          ← gitignored, contains CDK_ACCOUNT and DOMAIN
```

## What to do in the new session

1. The new session should have the `awslabs.aws-documentation-mcp-server` MCP enabled (the fix was: copy `~/.claude/.claude.json` to `~/.claude.json` and restart)
2. Use the AWS docs MCP to verify exact CDK L1 `CfnBucket` properties for regional namespaces and confirm CloudFront OAC + regional namespace bucket URL format
3. Write the CDK stack
4. Walk user through: CDK bootstrap → `cdk deploy` → ACM validation → verify stack outputs
5. Then proceed to Phase 5 (DNS), Phase 6 (deploy.py), Phase 7 (add_book.py)

## Key project constraints (important for any agent)

- **Never commit to git**: AWS account IDs, CloudFront distribution IDs, S3 bucket names, domain names, any AWS identifiers
- Claude uses `books-ro` profile only — never `books-admin`
- All mutating AWS actions are done by the user after Claude walks through the steps
- Check off plan.md checklist items as work is completed
- Ask for visual verification before marking UI/output steps complete
- The `data/`, `images/`, and `site/` directories are gitignored (contain personal content)
