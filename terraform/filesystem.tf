# Write-cache EFS: One Zone (cheapest — ephemeral temp files need no redundancy),
# Elastic Throughput (no burst-credit starvation on a near-empty filesystem).
# One Zone keeps all data in a single AZ; EC2 instances in the second AZ pay a
# small cross-AZ data transfer fee (~$0.01/GB) but avoid EFS Standard's 2× storage cost.

resource "aws_efs_file_system" "write_cache" {
  availability_zone_name = local.azs[0]
  throughput_mode        = "elastic"
  encrypted              = true

  tags = { Name = "${var.project}-${var.env}-write-cache" }
}

# Temp files are ephemeral — disable automatic backups to avoid AWS Backup costs.
resource "aws_efs_backup_policy" "write_cache" {
  file_system_id = aws_efs_file_system.write_cache.id

  backup_policy {
    status = "DISABLED"
  }
}

resource "aws_security_group" "efs" {
  name        = "${var.project}-${var.env}-efs-sg"
  description = "NFS inbound from EC2 instances"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "NFS from EC2"
    from_port       = 2049
    to_port         = 2049
    protocol        = "tcp"
    security_groups = [aws_security_group.ec2.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-${var.env}-efs-sg" }
}

# Single mount target in the same AZ as the EFS file system.
# Instances in azs[1] can still mount via NFS; they just cross AZs for the data path.
resource "aws_efs_mount_target" "write_cache" {
  file_system_id  = aws_efs_file_system.write_cache.id
  subnet_id       = aws_subnet.public[0].id
  security_groups = [aws_security_group.efs.id]
}
