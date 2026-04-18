# EC2 launch template, ASG, and gunicorn_timeout SSM parameter have been
# migrated to ECS Fargate.  See ecs.tf for the replacement resources.
#
# The gunicorn_timeout SSM parameter (/fileproxy/prod/gunicorn_timeout) is no
# longer needed — timeouts are set per-service in the ECS task definitions.
# Run `terraform state rm aws_ssm_parameter.gunicorn_timeout` before applying
# if the old parameter still exists in Terraform state.
