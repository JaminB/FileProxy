resource "aws_security_group" "efs" {
  name        = "${var.project}-${var.env}-efs-sg"
  description = "Allow NFS from EC2"
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

resource "aws_efs_file_system" "write_cache" {
  encrypted = true

  tags = { Name = "${var.project}-${var.env}-write-cache" }
}

# One mount target per private subnet so EC2 instances in either AZ can
# reach EFS via the VPC-local route (same pattern used for RDS).
resource "aws_efs_mount_target" "write_cache" {
  count           = length(aws_subnet.private)
  file_system_id  = aws_efs_file_system.write_cache.id
  subnet_id       = aws_subnet.private[count.index].id
  security_groups = [aws_security_group.efs.id]
}

