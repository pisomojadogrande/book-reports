import aws_cdk as cdk
from aws_cdk import (
    aws_certificatemanager as acm,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_s3 as s3,
)
from constructs import Construct


class ReadingStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        domain: str,
        cert_arn: str,
        **kwargs,
    ):
        super().__init__(scope, construct_id, **kwargs)

        # ------------------------------------------------------------------
        # S3 bucket — account regional namespace
        #
        # Bucket name resolves to: books-{accountId}-us-east-1-an
        # Fn.sub uses CloudFormation pseudo-parameters so no account ID
        # appears in source code.
        # ------------------------------------------------------------------
        bucket = s3.Bucket(
            self,
            "ContentBucket",
            bucket_name=cdk.Fn.sub(
                "books-${AWS::AccountId}-${AWS::Region}-an"
            ),
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=cdk.RemovalPolicy.RETAIN,
            enforce_ssl=True,
        )

        # Escape hatch: add BucketNamespace (not yet in CDK L2).
        # Must use add_override to patch the raw CloudFormation JSON —
        # direct attribute assignment is silently ignored for unknown properties.
        cfn_bucket = bucket.node.default_child
        cfn_bucket.add_override("Properties.BucketNamespace", "account-regional")

        # ------------------------------------------------------------------
        # CloudFront Origin Access Control + distribution
        #
        # S3BucketOrigin.with_origin_access_control() automatically:
        #   - Creates the OAC resource
        #   - Adds a bucket policy allowing cloudfront.amazonaws.com
        #     as service principal, scoped to this distribution's ARN
        # ------------------------------------------------------------------
        cert = acm.Certificate.from_certificate_arn(
            self, "SiteCert", cert_arn
        )

        distribution = cloudfront.Distribution(
            self,
            "Distribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                compress=True,
            ),
            domain_names=[domain],
            certificate=cert,
            default_root_object="index.html",
            error_responses=[
                # Return index.html on 403/404 so the site handles missing
                # paths gracefully (e.g. /covers/ paths that don't exist)
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
            ],
            minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
            http_version=cloudfront.HttpVersion.HTTP2_AND_3,
        )

        # ------------------------------------------------------------------
        # Outputs
        # ------------------------------------------------------------------
        cdk.CfnOutput(
            self,
            "DistributionDomain",
            value=distribution.distribution_domain_name,
            description="Add a CNAME in Route53: your-domain → this value",
        )

        cdk.CfnOutput(
            self,
            "BucketName",
            value=bucket.bucket_name,
            description="S3 bucket name — needed for deploy.py config",
        )

        cdk.CfnOutput(
            self,
            "DistributionId",
            value=distribution.distribution_id,
            description="CloudFront distribution ID — needed for deploy.py config",
        )
