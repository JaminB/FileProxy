resource "aws_db_subnet_group" "main" {
  name       = "${var.project}-${var.env}-db-subnet"
  subnet_ids = aws_subnet.private[*].id

  tags = { Name = "${var.project}-${var.env}-db-subnet" }
}

resource "random_password" "db" {
  length  = 32
  special = false
}

resource "aws_rds_cluster" "main" {
  cluster_identifier        = "${var.project}-${var.env}"
  engine                    = "aurora-postgresql"
  engine_mode               = "provisioned"
  engine_version            = "16.6"
  database_name             = "fileproxy"
  master_username           = "fileproxy"
  master_password           = random_password.db.result
  db_subnet_group_name      = aws_db_subnet_group.main.name
  vpc_security_group_ids    = [aws_security_group.rds.id]
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.project}-${var.env}-final"
  storage_encrypted         = true

  serverlessv2_scaling_configuration {
    min_capacity = 0.5
    max_capacity = 16
  }

  tags = { Name = "${var.project}-${var.env}-aurora" }
}

resource "aws_rds_cluster_instance" "main" {
  cluster_identifier = aws_rds_cluster.main.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.main.engine
  engine_version     = aws_rds_cluster.main.engine_version

  tags = { Name = "${var.project}-${var.env}-aurora-instance" }
}

# Store DB connection info in SSM for user-data to pick up
resource "aws_ssm_parameter" "db_host" {
  name  = "/fileproxy/prod/db_host"
  type  = "String"
  value = aws_rds_cluster.main.endpoint

  tags = { Name = "db_host" }
}

resource "aws_ssm_parameter" "db_name" {
  name  = "/fileproxy/prod/db_name"
  type  = "String"
  value = aws_rds_cluster.main.database_name

  tags = { Name = "db_name" }
}

resource "aws_ssm_parameter" "db_user" {
  name  = "/fileproxy/prod/db_user"
  type  = "String"
  value = aws_rds_cluster.main.master_username

  tags = { Name = "db_user" }
}

resource "aws_ssm_parameter" "db_password" {
  name  = "/fileproxy/prod/db_password"
  type  = "SecureString"
  value = random_password.db.result

  tags = { Name = "db_password" }
}

