#!/bin/bash
set -euo pipefail

# Install Docker
yum update -y
yum install -y docker aws-cli jq
systemctl enable docker
systemctl start docker

# ECR login
aws ecr get-login-password --region ${aws_region} \
  | docker login --username AWS --password-stdin ${ecr_url}

# Fetch all SSM parameters under /fileproxy/prod/ and write to /etc/fileproxy.env
mkdir -p /etc
aws ssm get-parameters-by-path \
  --path "/fileproxy/prod/" \
  --with-decryption \
  --region ${aws_region} \
  --query "Parameters[*].[Name,Value]" \
  --output json \
  | jq -r '.[] | (.[0] | split("/") | last | ascii_upcase) + "=" + .[1]' \
  > /etc/fileproxy.env

# Append runtime values
ALB_DNS="${alb_dns}"
echo "DJANGO_ALLOWED_HOSTS=$ALB_DNS" >> /etc/fileproxy.env
echo "CSRF_TRUSTED_ORIGINS=http://$ALB_DNS" >> /etc/fileproxy.env

# Pull and run the container
docker pull ${ecr_url}:latest
docker run -d \
  --name fileproxy \
  --restart unless-stopped \
  -p 8000:8000 \
  --env-file /etc/fileproxy.env \
  ${ecr_url}:latest
