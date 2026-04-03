from aws_cdk import (
    Stack,
    CfnOutput,
    RemovalPolicy,
    Duration,
    aws_cognito as cognito,
)
from constructs import Construct


class AuthStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # Create Cognito User Pool
        self.user_pool = cognito.UserPool(
            self, "CapaUserPool",
            user_pool_name="capa-user-pool",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(
                email=True,
                username=False
            ),
            auto_verify=cognito.AutoVerifiedAttrs(
                email=True
            ),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(
                    required=True,
                    mutable=True
                ),
                fullname=cognito.StandardAttribute(
                    required=False,
                    mutable=True
                )
            ),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=False
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.DESTROY  # For dev - change to RETAIN for prod
        )

        # Create User Pool Domain for Hosted UI
        self.user_pool_domain = self.user_pool.add_domain(
            "CapaUserPoolDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix="capa-ai-auth"  # Will be: capa-ai-auth.auth.us-east-1.amazoncognito.com
            )
        )

        # Create User Pool Groups
        self.standard_group = cognito.CfnUserPoolGroup(
            self, "StandardUserGroup",
            user_pool_id=self.user_pool.user_pool_id,
            group_name="Standard",
            description="Standard users - can upload images, view reports, submit feedback",
            precedence=2
        )

        self.expert_group = cognito.CfnUserPoolGroup(
            self, "ExpertUserGroup",
            user_pool_id=self.user_pool.user_pool_id,
            group_name="Expert",
            description="Expert users - all standard permissions plus data labeling, model approval, retraining",
            precedence=1
        )

        # Create User Pool Client for Hosted UI
        self.user_pool_client = self.user_pool.add_client(
            "CapaWebClient",
            user_pool_client_name="capa-web-client",
            generate_secret=False,  # Public client for SPA
            auth_flows=cognito.AuthFlow(
                user_srp=True,
                user_password=True
            ),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(
                    authorization_code_grant=True,
                    implicit_code_grant=True  # For easier SPA integration
                ),
                scopes=[
                    cognito.OAuthScope.EMAIL,
                    cognito.OAuthScope.OPENID,
                    cognito.OAuthScope.PROFILE
                ],
                callback_urls=[
                    "http://localhost:5173/",  # Local dev
                    "http://localhost:5173/callback",
                    "https://capa-frontend-pi.vercel.app/",  # Production
                    "https://capa-frontend-pi.vercel.app/callback"
                ],
                logout_urls=[
                    "http://localhost:5173/",
                    "https://capa-frontend-pi.vercel.app/"
                ]
            ),
            supported_identity_providers=[
                cognito.UserPoolClientIdentityProvider.COGNITO
            ],
            access_token_validity=Duration.hours(1),
            id_token_validity=Duration.hours(1),
            refresh_token_validity=Duration.days(30)
        )

        # Outputs for frontend configuration
        CfnOutput(
            self, "UserPoolId",
            value=self.user_pool.user_pool_id,
            description="Cognito User Pool ID",
            export_name="CapaUserPoolId"
        )

        CfnOutput(
            self, "UserPoolClientId",
            value=self.user_pool_client.user_pool_client_id,
            description="Cognito User Pool Client ID",
            export_name="CapaUserPoolClientId"
        )

        CfnOutput(
            self, "UserPoolDomain",
            value=f"{self.user_pool_domain.domain_name}.auth.{self.region}.amazoncognito.com",
            description="Cognito Hosted UI Domain",
            export_name="CapaUserPoolDomain"
        )

        CfnOutput(
            self, "HostedUIUrl",
            value=f"https://{self.user_pool_domain.domain_name}.auth.{self.region}.amazoncognito.com/login?client_id={self.user_pool_client.user_pool_client_id}&response_type=code&scope=email+openid+profile&redirect_uri=https://capa-frontend-pi.vercel.app/callback",
            description="Hosted UI Login URL",
            export_name="CapaHostedUIUrl"
        )
