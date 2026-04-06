#!/usr/bin/env python3
"""
CDK app for the reading site.

Configuration is read from infra/.env (gitignored). Create it by copying
infra/.env.example and filling in the values.
"""
import os
from pathlib import Path

import aws_cdk as cdk
from dotenv import load_dotenv

from cert_stack import CertStack
from reading_stack import ReadingStack

# Load gitignored config
load_dotenv(Path(__file__).parent / ".env")

account = os.environ["CDK_ACCOUNT"]
domain = os.environ["DOMAIN"]
region = "us-east-1"  # Must be us-east-1: ACM certs for CloudFront + S3 regional naming

env = cdk.Environment(account=account, region=region)

app = cdk.App()

# Stack 1: ACM certificate only.
# Deploy this first, validate DNS, wait for cert to reach Issued,
# then deploy ReadingStack.
cert_stack = CertStack(app, "CertStack", domain=domain, env=env)

# Stack 2: S3 bucket + CloudFront distribution.
# Reads the cert ARN from CertStack via CloudFormation cross-stack export.
ReadingStack(
    app,
    "ReadingStack",
    domain=domain,
    cert_arn=cert_stack.cert.certificate_arn,
    env=env,
)

app.synth()
