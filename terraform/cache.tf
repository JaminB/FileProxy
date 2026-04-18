resource "aws_security_group" "redis" {
  name        = "${var.project}-${var.env}-redis-sg"
  description = "Allow Redis from ECS tasks"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Redis from web ECS tasks"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  ingress {
    description     = "Redis from worker/beat ECS tasks"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_worker.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-${var.env}-redis-sg" }
}

resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.project}-${var.env}-redis-subnet-group"
  subnet_ids = aws_subnet.private[*].id

  tags = { Name = "${var.project}-${var.env}-redis-subnet-group" }
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id       = "${var.project}-${var.env}-redis"
  description                = "Write-cache Celery broker"
  engine                     = "redis"
  engine_version             = "7.1"
  node_type                  = "cache.t4g.micro"
  num_cache_clusters         = 1
  parameter_group_name       = "default.redis7"
  port                       = 6379
  subnet_group_name          = aws_elasticache_subnet_group.main.name
  security_group_ids         = [aws_security_group.redis.id]
  transit_encryption_enabled = true

  tags = { Name = "${var.project}-${var.env}-redis" }
}

# Terraform-managed: value is derived from the ElastiCache endpoint above.
# Do NOT set this manually — it will be overwritten on next apply.
resource "aws_ssm_parameter" "celery_broker_url" {
  name  = "/fileproxy/prod/celery_broker_url"
  type  = "SecureString"
  value = "rediss://${aws_elasticache_replication_group.main.primary_endpoint_address}:6379/0"

  tags = { Name = "celery_broker_url" }
}
