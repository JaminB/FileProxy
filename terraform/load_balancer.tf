resource "aws_lb" "main" {
  name               = "${var.project}-${var.env}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  # Must exceed the API gunicorn --timeout (300 s) so the ALB does not drop the
  # backend connection before a long-running file transfer completes.
  idle_timeout = 305

  tags = { Name = "${var.project}-${var.env}-alb" }
}

# ── Target groups ─────────────────────────────────────────────────────────────

# API service: long deregistration drain (active file transfers may take up to 300 s)
resource "aws_lb_target_group" "api" {
  name                 = "${var.project}-${var.env}-api-tg"
  port                 = 8000
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = aws_vpc.main.id
  deregistration_delay = 300

  health_check {
    path                = "/health/"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 15
    timeout             = 5
    matcher             = "200"
  }

  tags = { Name = "${var.project}-${var.env}-api-tg" }
}

# UI service: short drain — HTML page requests complete quickly
resource "aws_lb_target_group" "ui" {
  name                 = "${var.project}-${var.env}-ui-tg"
  port                 = 8000
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = aws_vpc.main.id
  deregistration_delay = 60

  health_check {
    path                = "/health/"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 15
    timeout             = 5
    matcher             = "200"
  }

  tags = { Name = "${var.project}-${var.env}-ui-tg" }
}

# ── Listeners ─────────────────────────────────────────────────────────────────

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.main.certificate_arn

  # Default: all non-API traffic goes to the UI service
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.ui.arn
  }

  depends_on = [aws_acm_certificate_validation.main]
}

# ── Listener rules — route /api/* to the API service ─────────────────────────
# Priority 10: REST API endpoints
resource "aws_lb_listener_rule" "api" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    path_pattern {
      values = ["/api/*"]
    }
  }
}

# Priority 20: OpenAPI schema + Swagger UI (used by Windows Explorer client)
resource "aws_lb_listener_rule" "api_schema" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 20

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    path_pattern {
      values = ["/api/schema*", "/api/docs*"]
    }
  }
}
