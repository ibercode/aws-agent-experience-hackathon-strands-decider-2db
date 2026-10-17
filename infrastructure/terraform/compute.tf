data "aws_caller_identity" "current" {
}
resource "aws_ecr_repository" "images" {
  for_each             = toset(["api", "decider"])
  name                 = "${var.project}/${each.key}"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
  encryption_configuration {
    encryption_type = "AES256"
  }
}
resource "aws_ecr_lifecycle_policy" "images" {
  for_each   = aws_ecr_repository.images
  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1, description = "Remove untagged build leftovers after one day",
      selection = {
        tagStatus = "untagged", countType = "sinceImagePushed", countUnit = "days", countNumber = 1
      },
      action = {
        type = "expire"
      }
    }]
  })
}
resource "aws_ecs_cluster" "app" {
  name = var.project
  setting {
    name  = "containerInsights"
    value = "disabled"
  }
}
resource "aws_cloudwatch_log_group" "containers" {
  for_each          = toset(["api", "decider"])
  name              = "/ecs/${var.project}/${each.key}"
  retention_in_days = 7
}
data "aws_iam_policy_document" "ecs_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:ecs:${var.region}:${data.aws_caller_identity.current.account_id}:*"]
    }
  }
}
resource "aws_iam_role" "execution" {
  name               = "${var.project}-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_trust.json
}
resource "aws_iam_role_policy" "execution" {
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17", Statement = [
      {
        Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*"
      },
      {
        Effect = "Allow", Action = ["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"], Resource = [for r in aws_ecr_repository.images : r.arn]
      },
      {
        Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = [for g in aws_cloudwatch_log_group.containers : "${g.arn}:*"]
      }
    ]
  })
}
resource "aws_iam_role" "api" {
  name               = "${var.project}-api"
  assume_role_policy = data.aws_iam_policy_document.ecs_trust.json
}
resource "aws_iam_role_policy" "api" {
  role = aws_iam_role.api.id
  policy = jsonencode({
    Version = "2012-10-17", Statement = [
      {
        Effect = "Allow", Action = ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:TransactWriteItems"], Resource = [aws_dynamodb_table.sessions.arn, "${aws_dynamodb_table.sessions.arn}/index/sessions-by-user"]
      },
      {
        Effect = "Allow", Action = ["s3:GetObject", "s3:GetObjectVersion"], Resource = "${aws_s3_bucket.storage["scenarios"].arn}/scenarios/*"
      },
      {
        Effect = "Allow", Action = ["bedrock:InvokeModel"], Resource = [
          "arn:aws:bedrock:${var.region}:${data.aws_caller_identity.current.account_id}:inference-profile/${var.bedrock_model_id}",
          "arn:aws:bedrock:eu-*::foundation-model/amazon.nova-pro-v1:0"
        ]
      }
    ]
  })
}
locals {
  containers = {
    api = {
      cpu          = 256, memory = 512, port = 8000,
      image_digest = var.api_image_digest,
      task_role    = aws_iam_role.api.arn,
      env = {
        APP_ENV                = "production", AUTH_MODE = "cognito", PROVIDER_MODE = "live", STORAGE_MODE = "dynamodb",
        AWS_REGION             = var.region, DYNAMODB_TABLE = aws_dynamodb_table.sessions.name,
        SCENARIO_BUCKET        = aws_s3_bucket.storage["scenarios"].id,
        DECIDER_URL            = "http://decider.${aws_service_discovery_private_dns_namespace.app.name}:8099",
        BEDROCK_MODEL_ID       = var.bedrock_model_id,
        COGNITO_USER_POOL_ID   = aws_cognito_user_pool.trainees.id,
        COGNITO_CLIENT_ID      = aws_cognito_user_pool_client.ui.id,
        COGNITO_DOMAIN         = "https://${aws_cognito_user_pool_domain.login.domain}.auth.${var.region}.amazoncognito.com",
        COGNITO_REQUIRED_SCOPE = "${aws_cognito_resource_server.api.identifier}/exercise",
        MAX_ACTIVE_SESSIONS    = "1", MAX_DAILY_RUNS_PER_USER = "20", MODEL_TIMEOUT_SECONDS = "180"
      }
    },
    decider = {
      cpu          = var.decider_cpu, memory = var.decider_memory, port = 8099,
      image_digest = var.decider_image_digest,
      task_role    = null,
      env = {
        DECIDER_DEVICE = "cpu", OMP_NUM_THREADS = "4", MKL_NUM_THREADS = "4", TOKENIZERS_PARALLELISM = "false"
      }
    }
  }
}
resource "aws_ecs_task_definition" "app" {
  for_each                 = local.containers
  family                   = "${var.project}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(each.value.cpu)
  memory                   = tostring(each.value.memory)
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = each.value.task_role
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }
  container_definitions = jsonencode([{
    name      = each.key,
    image     = each.value.image_digest != null ? "${aws_ecr_repository.images[each.key].repository_url}@${each.value.image_digest}" : "${aws_ecr_repository.images[each.key].repository_url}:${var.image_tag}",
    essential = true, readonlyRootFilesystem = true,
    portMappings = [{
      containerPort = each.value.port, hostPort = each.value.port, protocol = "tcp"
    }],
    environment = [for key, value in each.value.env : {
      name = key, value = value
    }],
    linuxParameters = {
      initProcessEnabled = true
      capabilities       = { add = [], drop = ["ALL"] }
    },
    mountPoints = [{
      sourceVolume = "tmp", containerPath = "/tmp", readOnly = false
    }],
    logConfiguration = {
      logDriver = "awslogs", options = {
        "awslogs-group"  = aws_cloudwatch_log_group.containers[each.key].name,
        "awslogs-region" = var.region, "awslogs-stream-prefix" = each.key
      }
    },
    healthCheck = {
      command  = ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${each.value.port}/${each.key == "api" ? "api/health" : "health"}', timeout=5)"],
      interval = 30, timeout = 10, retries = 5, startPeriod = each.key == "decider" ? 300 : 30
    },
    stopTimeout = 60
  }])
  volume {
    name = "tmp"
  }
  lifecycle {
    precondition {
      condition     = var.desired_count == 0 || (each.value.image_digest != null && timecmp(timestamp(), "${var.auto_stop_at}Z") < 0)
      error_message = "Starting services requires immutable image digests and a future automatic shutdown time."
    }
  }
}
resource "aws_ecs_service" "decider" {
  name                               = "decider"
  cluster                            = aws_ecs_cluster.app.id
  task_definition                    = aws_ecs_task_definition.app["decider"].arn
  desired_count                      = var.desired_count
  launch_type                        = "FARGATE"
  platform_version                   = "LATEST"
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.decider.id]
    assign_public_ip = true
  }
  service_registries {
    registry_arn = aws_service_discovery_service.decider.arn
  }
  enable_execute_command  = false
  propagate_tags          = "TASK_DEFINITION"
  enable_ecs_managed_tags = true
}
resource "aws_ecs_service" "api" {
  name                               = "api"
  cluster                            = aws_ecs_cluster.app.id
  task_definition                    = aws_ecs_task_definition.app["api"].arn
  desired_count                      = var.desired_count
  launch_type                        = "FARGATE"
  platform_version                   = "LATEST"
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100
  health_check_grace_period_seconds  = 60
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.backend.id]
    assign_public_ip = true
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }
  enable_execute_command  = false
  propagate_tags          = "TASK_DEFINITION"
  enable_ecs_managed_tags = true
  depends_on              = [aws_lb_listener_rule.cloudfront, aws_iam_role_policy.api]
}
