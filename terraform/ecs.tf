# ── Cluster ───────────────────────────────────────────────────────────────────

resource "aws_ecs_cluster" "main" {
  name = "${var.project}-${var.env}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = { Name = "${var.project}-${var.env}" }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]
}

resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/${var.project}-${var.env}"
  retention_in_days = 7

  tags = { Name = "${var.project}-${var.env}-ecs-logs" }
}

# ── Shared locals ─────────────────────────────────────────────────────────────

locals {
  ecr_image = "${aws_ecr_repository.app.repository_url}:latest"

  # Static environment variables common to all web-serving tasks.
  # DJANGO_ALLOWED_HOSTS is intentionally omitted: settings.py uses ["*"] when
  # DEBUG=False, so the env var would be silently ignored and create a false
  # sense of host restriction.  No explicit host-header conditions are applied
  # at the ALB level either; the security boundary here is HTTPS termination on
  # the ALB listener combined with the VPC security group that only allows
  # inbound 8000/tcp from the ALB security group.
  common_env = [
    { name = "CSRF_TRUSTED_ORIGINS", value = "https://fileproxy.io,https://www.fileproxy.io" },
    { name = "WRITE_CACHE_DIR",      value = "/tmp/fileproxy/write_cache" },
  ]

  # SSM parameters injected as secrets at task start.
  # ECS fetches these from SSM; values never appear in DescribeTasks output.
  common_secrets = [
    { name = "DJANGO_SECRET_KEY",          valueFrom = aws_ssm_parameter.django_secret_key.arn },
    { name = "FILEPROXY_VAULT_MASTER_KEY", valueFrom = aws_ssm_parameter.vault_master_key.arn },
    { name = "DB_HOST",                    valueFrom = aws_ssm_parameter.db_host.arn },
    { name = "DB_NAME",                    valueFrom = aws_ssm_parameter.db_name.arn },
    { name = "DB_USER",                    valueFrom = aws_ssm_parameter.db_user.arn },
    { name = "DB_PASSWORD",                valueFrom = aws_ssm_parameter.db_password.arn },
    { name = "CELERY_BROKER_URL",          valueFrom = aws_ssm_parameter.celery_broker_url.arn },
    { name = "GOOGLE_CLIENT_ID",           valueFrom = aws_ssm_parameter.google_client_id.arn },
    { name = "GOOGLE_CLIENT_SECRET",       valueFrom = aws_ssm_parameter.google_client_secret.arn },
    { name = "DROPBOX_APP_KEY",            valueFrom = aws_ssm_parameter.dropbox_app_key.arn },
    { name = "DROPBOX_APP_SECRET",         valueFrom = aws_ssm_parameter.dropbox_app_secret.arn },
    { name = "STATIC_URL",                 valueFrom = aws_ssm_parameter.static_url.arn },
  ]

  log_config = {
    logDriver = "awslogs"
    options = {
      "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
      "awslogs-region"        = var.aws_region
    }
  }

  # EFS write-cache volume and mount — used by API and worker task definitions.
  # efs_volume is consumed by dynamic "volume" blocks; efs_mount by mountPoints.
  efs_volume = {
    name            = "write-cache"
    file_system_id  = aws_efs_file_system.write_cache.id
    access_point_id = aws_efs_access_point.write_cache.id
  }
  efs_mount = {
    sourceVolume  = "write-cache"
    containerPath = "/tmp/fileproxy"
    readOnly      = false
  }

  # Per-service log configurations — merges the common log_config with the
  # awslogs-stream-prefix so each service's output lands in its own stream.
  log_config_for = { for svc in ["api", "ui", "worker", "beat"] : svc => merge(local.log_config, {
    options = merge(local.log_config.options, { "awslogs-stream-prefix" = svc })
  }) }
}

# The EFS mount point object is reused across API and worker container definitions.
# The HCL volume{} block is declared inline in each task definition that needs it.

# ── Task definitions ──────────────────────────────────────────────────────────

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.project}-${var.env}-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024"
  memory                   = "2048"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  dynamic "volume" {
    for_each = [local.efs_volume]
    content {
      name = volume.value.name
      efs_volume_configuration {
        file_system_id     = volume.value.file_system_id
        transit_encryption = "ENABLED"
        authorization_config {
          access_point_id = volume.value.access_point_id
          iam             = "ENABLED"
        }
      }
    }
  }

  container_definitions = jsonencode([{
    name      = "app"
    image     = local.ecr_image
    essential = true

    portMappings = [{ containerPort = 8000, protocol = "tcp" }]

    environment = concat(local.common_env, [
      { name = "DJANGO_MODE",      value = "api" },
      { name = "GUNICORN_WORKERS", value = "4" },
      { name = "GUNICORN_TIMEOUT", value = tostring(local.api_timeout_s) },
    ])

    secrets = local.common_secrets

    mountPoints = [local.efs_mount]

    logConfiguration = local.log_config_for["api"]
  }])

  tags = { Name = "${var.project}-${var.env}-api" }
}

resource "aws_ecs_task_definition" "ui" {
  family                   = "${var.project}-${var.env}-ui"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "app"
    image     = local.ecr_image
    essential = true

    portMappings = [{ containerPort = 8000, protocol = "tcp" }]

    environment = concat(local.common_env, [
      { name = "DJANGO_MODE",      value = "ui" },
      { name = "GUNICORN_WORKERS", value = "2" },
      { name = "GUNICORN_TIMEOUT", value = "60" },
    ])

    secrets = local.common_secrets

    logConfiguration = local.log_config_for["ui"]
  }])

  tags = { Name = "${var.project}-${var.env}-ui" }
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.project}-${var.env}-worker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024"
  memory                   = "2048"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  dynamic "volume" {
    for_each = [local.efs_volume]
    content {
      name = volume.value.name
      efs_volume_configuration {
        file_system_id     = volume.value.file_system_id
        transit_encryption = "ENABLED"
        authorization_config {
          access_point_id = volume.value.access_point_id
          iam             = "ENABLED"
        }
      }
    }
  }

  container_definitions = jsonencode([{
    name      = "worker"
    image     = local.ecr_image
    essential = true

    environment = concat(local.common_env, [
      { name = "DJANGO_MODE",    value = "worker" },
      { name = "CELERY_WORKERS", value = "4" },
    ])

    secrets = local.common_secrets

    mountPoints = [local.efs_mount]

    logConfiguration = local.log_config_for["worker"]
  }])

  tags = { Name = "${var.project}-${var.env}-worker" }
}

resource "aws_ecs_task_definition" "beat" {
  family                   = "${var.project}-${var.env}-beat"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "beat"
    image     = local.ecr_image
    essential = true

    environment = concat(local.common_env, [
      { name = "DJANGO_MODE", value = "beat" },
    ])

    secrets = local.common_secrets

    logConfiguration = local.log_config_for["beat"]
  }])

  tags = { Name = "${var.project}-${var.env}-beat" }
}

# ── ECS services ──────────────────────────────────────────────────────────────
# All services run in public subnets with assign_public_ip = ENABLED so Fargate
# tasks can reach ECR, CloudWatch, and SSM without a NAT gateway.

resource "aws_ecs_service" "api" {
  name                               = "${var.project}-${var.env}-api"
  cluster                            = aws_ecs_cluster.main.id
  task_definition                    = aws_ecs_task_definition.api.arn
  desired_count                      = 1
  launch_type                        = "FARGATE"
  health_check_grace_period_seconds  = 120

  network_configuration {
    # Pinned to azs[0] — One Zone EFS only has a mount target in that AZ;
    # tasks in azs[1] fail DNS resolution for the EFS endpoint.
    subnets          = [aws_subnet.public[0].id]
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "app"
    container_port   = 8000
  }

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  depends_on = [aws_lb_listener.https]

  lifecycle {
    # Ignore desired_count so auto-scaling can adjust it without Terraform reverting
    ignore_changes = [desired_count]
  }

  tags = { Name = "${var.project}-${var.env}-api" }
}

resource "aws_ecs_service" "ui" {
  name                               = "${var.project}-${var.env}-ui"
  cluster                            = aws_ecs_cluster.main.id
  task_definition                    = aws_ecs_task_definition.ui.arn
  desired_count                      = 1
  health_check_grace_period_seconds  = 90

  # Prefer SPOT; fall back to on-demand. The ALB drains connections before the
  # task stops, so a SPOT interruption causes a replacement start (~30s) rather
  # than a hard error for active users.
  capacity_provider_strategy {
    capacity_provider = "FARGATE_SPOT"
    weight            = 4
  }
  capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.ui.arn
    container_name   = "app"
    container_port   = 8000
  }

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  depends_on = [aws_lb_listener.https]

  lifecycle {
    ignore_changes = [desired_count]
  }

  tags = { Name = "${var.project}-${var.env}-ui" }
}

resource "aws_ecs_service" "worker" {
  name            = "${var.project}-${var.env}-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = 1

  # Prefer SPOT (~70% cheaper); fall back to on-demand if no SPOT capacity.
  # recover_pending_uploads runs at startup to handle any interrupted uploads.
  capacity_provider_strategy {
    capacity_provider = "FARGATE_SPOT"
    weight            = 4
  }
  capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }

  network_configuration {
    # Pinned to azs[0] — One Zone EFS only has a mount target in that AZ.
    subnets          = [aws_subnet.public[0].id]
    # Use the egress-only worker SG — worker tasks have no HTTP listener and
    # must not inherit the ALB 8000/tcp ingress rule from ecs-sg.
    security_groups  = [aws_security_group.ecs_worker.id]
    assign_public_ip = true
  }

  # Keep at least one worker running during deployments so in-flight async
  # uploads are not interrupted mid-transfer.
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  lifecycle {
    ignore_changes = [desired_count]
  }

  tags = { Name = "${var.project}-${var.env}-worker" }
}

resource "aws_ecs_service" "beat" {
  name            = "${var.project}-${var.env}-beat"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.beat.arn
  desired_count   = 1

  # Prefer SPOT for cost savings; fall back to on-demand if no SPOT capacity
  # is available so scheduled jobs still run.
  capacity_provider_strategy {
    capacity_provider = "FARGATE_SPOT"
    weight            = 4
  }
  capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }

  network_configuration {
    subnets          = aws_subnet.public[*].id
    # Beat has no HTTP listener — use the egress-only worker SG.
    security_groups  = [aws_security_group.ecs_worker.id]
    assign_public_ip = true
  }

  # Beat must run as a singleton — two concurrent instances would schedule every
  # job twice. deployment_maximum_percent = 100 prevents ECS from ever starting a
  # second task, and deployment_minimum_healthy_percent = 0 allows stop-then-start
  # rollouts (the brief scheduling gap during deploys is acceptable).
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  tags = { Name = "${var.project}-${var.env}-beat" }
}

# ── Application Auto Scaling ──────────────────────────────────────────────────

locals {
  autoscaling = {
    api    = { service = aws_ecs_service.api.name,    max = 10, min = 1, target_cpu = 60.0, scale_in = 120 }
    ui     = { service = aws_ecs_service.ui.name,     max = 3,  min = 1, target_cpu = 70.0, scale_in = 180 }
    worker = { service = aws_ecs_service.worker.name, max = 5,  min = 1, target_cpu = 60.0, scale_in = 120 }
  }
}

resource "aws_appautoscaling_target" "svc" {
  for_each           = local.autoscaling
  max_capacity       = each.value.max
  min_capacity       = each.value.min
  resource_id        = "service/${aws_ecs_cluster.main.name}/${each.value.service}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "svc_cpu" {
  for_each           = local.autoscaling
  name               = "${var.project}-${var.env}-${each.key}-cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.svc[each.key].resource_id
  scalable_dimension = aws_appautoscaling_target.svc[each.key].scalable_dimension
  service_namespace  = aws_appautoscaling_target.svc[each.key].service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = each.value.target_cpu
    scale_in_cooldown  = each.value.scale_in
    scale_out_cooldown = 60
  }
}

