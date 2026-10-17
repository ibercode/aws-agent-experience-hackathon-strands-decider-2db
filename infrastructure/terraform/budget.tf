resource "aws_budgets_budget" "demo" {
  name         = "${var.project}-100-usd"
  budget_type  = "COST"
  limit_amount = tostring(var.budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
  # Account-wide: includes Bedrock usage and resources before cost-allocation tags activate.
  dynamic "notification" {
    for_each = var.budget_email == null ? [] : [50, 80, 100]
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = [var.budget_email]
    }
  }
}
resource "aws_iam_role" "shutdown" {
  name = "${var.project}-shutdown"
  assume_role_policy = jsonencode({
    Version = "2012-10-17", Statement = [{
      Effect = "Allow", Action = "sts:AssumeRole", Principal = {
        Service = "scheduler.amazonaws.com"
      },
      Condition = {
        StringEquals = {
          "aws:SourceAccount" = data.aws_caller_identity.current.account_id
        }
      }
    }]
  })
}
resource "aws_iam_role_policy" "shutdown" {
  role = aws_iam_role.shutdown.id
  policy = jsonencode({
    Version = "2012-10-17", Statement = [{
      Effect = "Allow", Action = ["ecs:UpdateService"], Resource = [aws_ecs_service.api.id, aws_ecs_service.decider.id],
      Condition = {
        ArnEquals = {
          "ecs:cluster" = aws_ecs_cluster.app.arn
        }
      }
    }]
  })
}
resource "aws_scheduler_schedule" "shutdown" {
  for_each = {
    api = aws_ecs_service.api.name, decider = aws_ecs_service.decider.name
  }
  name                         = "${var.project}-stop-${each.key}"
  schedule_expression          = "at(${var.auto_stop_at})"
  schedule_expression_timezone = "UTC"
  action_after_completion      = "DELETE"
  flexible_time_window {
    mode = "OFF"
  }
  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ecs:updateService"
    role_arn = aws_iam_role.shutdown.arn
    input = jsonencode({
      Cluster = aws_ecs_cluster.app.name, Service = each.value, DesiredCount = 0
    })
    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 3
    }
  }
  depends_on = [aws_iam_role_policy.shutdown]
}
