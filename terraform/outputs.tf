output "alb_dns_name" {
  description = "Public DNS name of the Application Load Balancer"
  value       = aws_lb.main.dns_name
}

output "ecr_repository_url" {
  description = "ECR repository URL for Docker images"
  value       = aws_ecr_repository.app.repository_url
}

output "s3_static_bucket" {
  description = "S3 bucket name for static files"
  value       = aws_s3_bucket.static.id
}

output "cloudfront_domain" {
  description = "CloudFront distribution domain for static files"
  value       = aws_cloudfront_distribution.static.domain_name
}

output "github_actions_role_arn" {
  description = "IAM role ARN for GitHub Actions to assume"
  value       = aws_iam_role.github_actions.arn
}
