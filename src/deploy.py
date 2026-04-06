"""
deploy.py — build the site and publish it to S3 + CloudFront.

Reads bucket name and distribution ID from CloudFormation stack outputs so
no AWS identifiers need to be hardcoded or stored in config files.

Usage:
    python src/deploy.py [--dry-run]

Requirements:
    pip install boto3
    AWS profile 'books-admin' configured via IAM Identity Center
"""

import argparse
import mimetypes
import subprocess
import sys
from pathlib import Path

import boto3

STACK_NAME = "ReadingStack"
REGION = "us-east-1"
PROFILE = "books"
ROOT = Path(__file__).parent.parent
SITE_DIR = ROOT / "site"

# Content-Type overrides for types mimetypes may get wrong
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".ico": "image/x-icon",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
}

# Files that should never be cached by CloudFront
NO_CACHE_PATHS = {"index.html"}


def get_stack_outputs():
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    cf = session.client("cloudformation")
    response = cf.describe_stacks(StackName=STACK_NAME)
    outputs = response["Stacks"][0]["Outputs"]
    result = {}
    for o in outputs:
        result[o["OutputKey"]] = o["OutputValue"]
    return result


def build_site():
    print("Building site...")
    result = subprocess.run(
        [sys.executable, str(ROOT / "src" / "build.py")],
        check=True,
    )


def sync_to_s3(bucket_name, dry_run):
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    s3 = session.client("s3", region_name=REGION)

    local_files = {
        p.relative_to(SITE_DIR): p
        for p in SITE_DIR.rglob("*")
        if p.is_file()
    }

    print(f"\nSyncing {len(local_files)} files to s3://{bucket_name}/")

    for rel_path, abs_path in sorted(local_files.items()):
        key = rel_path.as_posix()
        suffix = abs_path.suffix.lower()
        content_type = CONTENT_TYPES.get(suffix) or mimetypes.guess_type(str(abs_path))[0] or "application/octet-stream"

        extra_args = {"ContentType": content_type}
        if rel_path.name in NO_CACHE_PATHS:
            extra_args["CacheControl"] = "no-cache, no-store, must-revalidate"
        else:
            extra_args["CacheControl"] = "public, max-age=31536000, immutable"

        if dry_run:
            print(f"  [dry-run] PUT s3://{bucket_name}/{key}  ({content_type})")
        else:
            print(f"  PUT {key}")
            s3.upload_file(str(abs_path), bucket_name, key, ExtraArgs=extra_args)

    print(f"Sync {'(dry-run) ' if dry_run else ''}complete.")


def invalidate_cloudfront(distribution_id, dry_run):
    import time
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    cf = session.client("cloudfront")

    if dry_run:
        print(f"\n[dry-run] CloudFront invalidation for distribution {distribution_id}")
        return

    print(f"\nInvalidating CloudFront distribution {distribution_id}...")
    response = cf.create_invalidation(
        DistributionId=distribution_id,
        InvalidationBatch={
            "Paths": {"Quantity": 1, "Items": ["/*"]},
            "CallerReference": str(int(time.time())),
        },
    )
    inv_id = response["Invalidation"]["Id"]
    print(f"Invalidation {inv_id} created. Propagation takes ~30–60 seconds.")


def main():
    parser = argparse.ArgumentParser(description="Build and deploy the reading site.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be uploaded without uploading")
    args = parser.parse_args()

    print("Fetching stack outputs...")
    try:
        outputs = get_stack_outputs()
    except Exception as e:
        print(f"Error fetching stack outputs: {e}")
        print("Make sure ReadingStack is deployed and 'books-admin' profile is active.")
        sys.exit(1)

    bucket_name = outputs.get("BucketName")
    distribution_id = outputs.get("DistributionId")

    if not bucket_name or not distribution_id:
        print("Missing expected stack outputs (BucketName, DistributionId).")
        print(f"Got: {outputs}")
        sys.exit(1)

    print(f"Bucket:       {bucket_name}")
    print(f"Distribution: {distribution_id}")

    build_site()
    sync_to_s3(bucket_name, args.dry_run)
    invalidate_cloudfront(distribution_id, args.dry_run)

    if not args.dry_run:
        print("\nDone. Changes will be live within ~60 seconds.")


if __name__ == "__main__":
    main()
