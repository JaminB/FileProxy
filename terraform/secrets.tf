# Secrets that must be set manually via aws ssm put-parameter after terraform apply.
# Terraform creates placeholder values; lifecycle ignore_changes prevents Terraform
# from overwriting values that were set manually.

resource "aws_ssm_parameter" "django_secret_key" {
  name  = "/fileproxy/prod/django_secret_key"
  type  = "SecureString"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }

  tags = { Name = "django_secret_key" }
}

resource "aws_ssm_parameter" "vault_master_key" {
  name  = "/fileproxy/prod/fileproxy_vault_master_key"
  type  = "SecureString"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }

  tags = { Name = "fileproxy_vault_master_key" }
}

resource "aws_ssm_parameter" "google_client_id" {
  name  = "/fileproxy/prod/google_client_id"
  type  = "String"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }

  tags = { Name = "google_client_id" }
}

resource "aws_ssm_parameter" "google_client_secret" {
  name  = "/fileproxy/prod/google_client_secret"
  type  = "SecureString"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }

  tags = { Name = "google_client_secret" }
}

resource "aws_ssm_parameter" "dropbox_app_key" {
  name  = "/fileproxy/prod/dropbox_app_key"
  type  = "String"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }

  tags = { Name = "dropbox_app_key" }
}

resource "aws_ssm_parameter" "dropbox_app_secret" {
  name  = "/fileproxy/prod/dropbox_app_secret"
  type  = "SecureString"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }

  tags = { Name = "dropbox_app_secret" }
}

resource "aws_ssm_parameter" "static_url" {
  name  = "/fileproxy/prod/static_url"
  type  = "String"
  value = "https://${aws_cloudfront_distribution.static.domain_name}/static/"

  tags = { Name = "static_url" }
}

# Gunicorn worker timeout in seconds.  Must be long enough to receive the full
# request body from the browser before gunicorn kills the sync worker.  For a
# 100 MB file at 3 Mbps (common residential upstream) the transfer alone takes
# ~267 s, so 300 s gives comfortable headroom for real-world upload speeds.
resource "aws_ssm_parameter" "gunicorn_timeout" {
  name  = "/fileproxy/prod/gunicorn_timeout"
  type  = "String"
  value = "300"

  tags = { Name = "gunicorn_timeout" }
}
