output "application_url" {
  value = "https://${var.app_hostname}"
}
output "ui_bucket" {
  value = aws_s3_bucket.storage["ui"].id
}
output "distribution_id" {
  value = aws_cloudfront_distribution.app.id
}
output "ecr_repositories" {
  value = {
    for k, v in aws_ecr_repository.images : k => v.repository_url
  }
}
output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.trainees.id
}
output "cognito_client_id" {
  value = aws_cognito_user_pool_client.ui.id
}
output "cognito_domain" {
  value = "https://${aws_cognito_user_pool_domain.login.domain}.auth.${var.region}.amazoncognito.com"
}
output "cluster_name" {
  value = aws_ecs_cluster.app.name
}
output "shutdown_at_utc" {
  value = "${var.auto_stop_at}Z"
}
output "load_balancer_arn" {
  value = aws_lb.api.arn
}
