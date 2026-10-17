resource "aws_cognito_user_pool" "trainees" {
  name                     = "${var.project}-trainees"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  mfa_configuration        = "ON"
  software_token_mfa_configuration {
    enabled = true
  }
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }
  admin_create_user_config {
    allow_admin_create_user_only = true
  }
  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = true
    temporary_password_validity_days = 3
  }
}
resource "aws_cognito_resource_server" "api" {
  identifier   = "clearance-gap"
  name         = "Clearance Gap API"
  user_pool_id = aws_cognito_user_pool.trainees.id
  scope {
    scope_name        = "exercise"
    scope_description = "Create and inspect your own training exercises"
  }
}
resource "aws_cognito_user_pool_client" "ui" {
  name                                 = "${var.project}-browser"
  user_pool_id                         = aws_cognito_user_pool.trainees.id
  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile", "${aws_cognito_resource_server.api.identifier}/exercise"]
  supported_identity_providers         = ["COGNITO"]
  callback_urls                        = ["https://${var.app_hostname}/auth/callback"]
  logout_urls                          = ["https://${var.app_hostname}"]
  prevent_user_existence_errors        = "ENABLED"
  access_token_validity                = 15
  id_token_validity                    = 15
  refresh_token_validity               = 1
  enable_token_revocation              = true
  explicit_auth_flows                  = ["ALLOW_REFRESH_TOKEN_AUTH"]
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
}
resource "aws_cognito_user_pool_domain" "login" {
  domain       = "${var.project}-${random_id.suffix.hex}"
  user_pool_id = aws_cognito_user_pool.trainees.id
}
