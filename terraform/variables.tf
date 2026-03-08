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

variable "asg_min_size" {
  description = "ASG minimum instance count"
  type        = number
  default     = 1
}

variable "asg_max_size" {
  description = "ASG maximum instance count"
  type        = number
  default     = 4
}

variable "asg_desired_capacity" {
  description = "ASG desired instance count"
  type        = number
  default     = 1
}

variable "on_demand_base_capacity" {
  description = "Number of on-demand instances to maintain as a base"
  type        = number
  default     = 1
}

variable "instance_types" {
  description = "Ordered list of instance types for the mixed policy"
  type        = list(string)
  default     = ["t3.small", "t3.medium"]
}
