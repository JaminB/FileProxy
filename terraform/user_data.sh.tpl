#!/bin/bash
set -euo pipefail

# Install Docker if not present (runs once on first boot)
if ! command -v docker &>/dev/null; then
  dnf install -y docker
  systemctl enable docker
fi

# Install jq and amazon-efs-utils independently — these are needed on every boot
# (warm pool restarts skip the Docker block above but still need mount.efs and jq)
if ! command -v jq &>/dev/null; then
  dnf install -y jq
fi
if ! command -v mount.efs &>/dev/null; then
  dnf install -y amazon-efs-utils
fi

# Write the application startup script (always overwritten so deploys update it)
cat > /usr/local/bin/fileproxy-start.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail

ECR_URL="${ecr_url}"
AWS_REGION="${aws_region}"
ALB_DNS="${alb_dns}"
EFS_DNS="${efs_dns}"

# ECR login
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ECR_URL"

# Fetch all SSM parameters and write env file
mkdir -p /etc
aws ssm get-parameters-by-path \
  --path "/fileproxy/prod/" \
  --with-decryption \
  --region "$AWS_REGION" \
  --query "Parameters[*].[Name,Value]" \
  --output json \
  | jq -r '.[] | (.[0] | split("/") | last | ascii_upcase) + "=" + .[1]' \
  > /etc/fileproxy.env

# Append runtime values
PRIVATE_IP=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4)
echo "DJANGO_ALLOWED_HOSTS=$ALB_DNS,$PRIVATE_IP,fileproxy.io,www.fileproxy.io" >> /etc/fileproxy.env
echo "CSRF_TRUSTED_ORIGINS=http://$ALB_DNS,https://fileproxy.io,https://www.fileproxy.io" >> /etc/fileproxy.env

# Mount shared EFS write-cache volume (idempotent across warm pool restarts).
mkdir -p /mnt/fileproxy
if ! mountpoint -q /mnt/fileproxy; then
  mount -t efs -o tls "$EFS_DNS":/ /mnt/fileproxy
fi
# Persist across reboots (grep prevents duplicate fstab entries).
if ! grep -q "$EFS_DNS" /etc/fstab; then
  echo "$EFS_DNS:/ /mnt/fileproxy efs _netdev,tls 0 0" >> /etc/fstab
fi

# Stop and remove previous containers
docker stop fileproxy-worker fileproxy 2>/dev/null || true
docker rm   fileproxy-worker fileproxy 2>/dev/null || true

# Pull latest app image (only changed layers downloaded on warm pool restarts)
docker pull "$ECR_URL:latest"

# App container: mount shared EFS write-cache dir.
docker run -d \
  --name fileproxy \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /mnt/fileproxy:/tmp/fileproxy \
  --env-file /etc/fileproxy.env \
  "$ECR_URL:latest"

# Celery worker: same image, same shared volume.
# CELERY_BROKER_URL (fetched from SSM) points to ElastiCache — not localhost.
# --entrypoint overrides the image's gunicorn ENTRYPOINT so Celery actually runs.
docker run -d \
  --name fileproxy-worker \
  --restart unless-stopped \
  -v /mnt/fileproxy:/tmp/fileproxy \
  --env-file /etc/fileproxy.env \
  --entrypoint celery \
  "$ECR_URL:latest" \
  -A config worker -l info

# Wait until the app is serving before declaring success.
# This gates systemd (Type=oneshot) so the ASG only counts the instance
# ready once /health/ actually returns 200 — eliminating 502s during deploys.
echo "Waiting for fileproxy to become ready..."
READY=0
for i in $(seq 1 36); do
  if curl -sf http://localhost:8000/health/ > /dev/null 2>&1; then
    echo "fileproxy is ready after $((i * 5))s"
    READY=1
    break
  fi
  sleep 5
done

if [ "$READY" -eq 0 ]; then
  echo "ERROR: fileproxy did not become ready within 180s" >&2
  docker logs fileproxy >&2
  exit 1
fi
SCRIPT

chmod +x /usr/local/bin/fileproxy-start.sh

# Install systemd service so it runs on every boot (including warm pool restarts)
cat > /etc/systemd/system/fileproxy.service << 'SERVICE'
[Unit]
Description=FileProxy Application
After=docker.service network-online.target
Wants=network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/fileproxy-start.sh
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable fileproxy.service
systemctl start docker
systemctl start fileproxy.service
