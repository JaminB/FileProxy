# Secrets that must be set manually via aws ssm put-parameter after terraform apply.
# Terraform creates placeholder values; lifecycle ignore_changes prevents Terraform
# from overwriting values that were set manually.

resource "aws_ssm_parameter" "django_secret_key" {
  name  = "/fileproxy/${var.env}/django_secret_key"
  type  = "SecureString"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }

  tags = { Name = "django_secret_key" }
}

resource "aws_ssm_parameter" "vault_master_key" {
  name  = "/fileproxy/${var.env}/fileproxy_vault_master_key"
  type  = "SecureString"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }

  tags = { Name = "fileproxy_vault_master_key" }
}

resource "aws_ssm_parameter" "google_client_id" {
  name  = "/fileproxy/${var.env}/google_client_id"
  type  = "String"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }

  tags = { Name = "google_client_id" }
}

resource "aws_ssm_parameter" "google_client_secret" {
  name  = "/fileproxy/${var.env}/google_client_secret"
  type  = "SecureString"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }

  tags = { Name = "google_client_secret" }
}

resource "aws_ssm_parameter" "dropbox_app_key" {
  name  = "/fileproxy/${var.env}/dropbox_app_key"
  type  = "String"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }

  tags = { Name = "dropbox_app_key" }
}

resource "aws_ssm_parameter" "dropbox_app_secret" {
  name  = "/fileproxy/${var.env}/dropbox_app_secret"
  type  = "SecureString"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }

  tags = { Name = "dropbox_app_secret" }
}

resource "aws_ssm_parameter" "static_url" {
  name  = "/fileproxy/${var.env}/static_url"
  type  = "String"
  value = "https://${aws_cloudfront_distribution.static.domain_name}/static/"

  tags = { Name = "static_url" }
}
