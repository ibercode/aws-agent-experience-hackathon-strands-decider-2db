variable "region" {
  type    = string
  default = "eu-west-1"
}
variable "aws_profile" {
  type        = string
  default     = null
  description = "Local CLI profile, supplied privately. Leave null for a deployment role."
}
variable "project" {
  type    = string
  default = "clearance-gap"
}
variable "domain_name" {
  type        = string
  description = "Existing public Route 53 hosted zone. Keep personal deployment values in ignored tfvars."
}
variable "app_hostname" {
  type        = string
  description = "Application hostname under the existing zone."
}
variable "image_tag" {
  type    = string
  default = "v0.1.0"
}
variable "desired_count" {
  type        = number
  default     = 0
  description = "Bootstrap with zero tasks. Set to 1 after both images are pushed and live model sizing is verified."
  validation {
    condition     = contains([0, 1], var.desired_count)
    error_message = "The MVP supports one authoritative backend coordinator. Choose 0 or 1."
  }
}
variable "bedrock_model_id" {
  type    = string
  default = "eu.amazon.nova-pro-v1:0"
}
variable "decider_cpu" {
  type    = number
  default = 4096
}
variable "decider_memory" {
  type        = number
  default     = 16384
  description = "CPU inference uses FP32 weights; allow startup and inference headroom above the FP32 model."
}
variable "budget_usd" {
  type    = number
  default = 100
}
variable "budget_email" {
  type        = string
  default     = null
  sensitive   = true
  description = "Optional alert recipient, supplied only via ignored configuration. Alerts are not spending caps."
}
variable "auto_stop_at" {
  type        = string
  description = "UTC shutdown time, YYYY-MM-DDTHH:MM:SS. Set explicitly for the authorized demo window."
  validation {
    condition     = can(formatdate("YYYY", "${var.auto_stop_at}Z"))
    error_message = "Use a UTC date/time without the trailing Z."
  }
}
variable "api_image_digest" {
  type        = string
  default     = null
  description = "Immutable ECR image digest, required when starting tasks."
}
variable "decider_image_digest" {
  type        = string
  default     = null
  description = "Immutable ECR image digest, required when starting tasks."
}
