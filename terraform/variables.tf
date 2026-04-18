variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Project name used in resource names and tags"
  type        = string
  default     = "fileproxy"
}

variable "env" {
  description = "Environment name"
  type        = string
  default     = "prod"
}

variable "github_org" {
  description = "GitHub organisation or username that owns the repo"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
  default     = "FileProxy"
}
