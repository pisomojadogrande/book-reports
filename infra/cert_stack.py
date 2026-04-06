import aws_cdk as cdk
from aws_cdk import aws_certificatemanager as acm
from constructs import Construct


class CertStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, domain: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # ACM certificate for the site domain.
        # Validation is DNS-based. Since the Route53 hosted zone is in a
        # separate account, CDK cannot auto-validate — it will output the
        # required CNAME record. Add that record in the Route53 account,
        # then wait for the certificate to reach Issued status before
        # deploying ReadingStack.
        self.cert = acm.Certificate(
            self,
            "SiteCert",
            domain_name=domain,
            validation=acm.CertificateValidation.from_dns(),
        )

        # Export the cert ARN so ReadingStack can reference it
        self.cert_arn_output = cdk.CfnOutput(
            self,
            "CertArn",
            value=self.cert.certificate_arn,
            description="ACM certificate ARN — pass to ReadingStack",
            export_name="ReadingSiteCertArn",
        )
