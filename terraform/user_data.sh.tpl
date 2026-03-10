#!/bin/bash
set -euo pipefail

# Skip Docker install if already present (warm pool restart fast path)
if ! command -v docker &>/dev/null; then
  dnf install -y docker aws-cli jq
  systemctl enable docker
fi
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
PRIVATE_IP=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4)
echo "DJANGO_ALLOWED_HOSTS=$ALB_DNS,$PRIVATE_IP,fileproxy.io,www.fileproxy.io" >> /etc/fileproxy.env
echo "CSRF_TRUSTED_ORIGINS=http://$ALB_DNS,https://fileproxy.io,https://www.fileproxy.io" >> /etc/fileproxy.env

# Remove previous container (idempotent across warm pool restarts)
docker stop fileproxy 2>/dev/null || true
docker rm fileproxy 2>/dev/null || true

# Pull latest image and run
docker pull ${ecr_url}:latest
docker run -d \
  --name fileproxy \
  --restart unless-stopped \
  -p 8000:8000 \
  --env-file /etc/fileproxy.env \
  ${ecr_url}:latest
