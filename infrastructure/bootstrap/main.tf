terraform {
  required_version = ">= 1.10, < 2.0"
  required_providers {
    aws = {
      source = "hashicorp/aws", version = "~> 6.0"
    }
    random = {
      source = "hashicorp/random", version = "~> 3.0"
    }
  }
}
variable "aws_profile" {
  type    = string
  default = null
}
provider "aws" {
  region  = "eu-west-1"
  profile = var.aws_profile
  default_tags {
    tags = {
      Project = "clearance-gap", ManagedBy = "Terraform"
    }
  }
}
resource "random_id" "state" {
  byte_length = 4
}
resource "aws_s3_bucket" "state" {
  bucket = "clearance-gap-tfstate-${random_id.state.hex}"
  lifecycle {
    prevent_destroy = true
  }
}
resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = jsonencode({
    Version = "2012-10-17", Statement = [{
      Sid      = "RequireTLS", Effect = "Deny", Principal = "*", Action = "s3:*",
      Resource = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"],
      Condition = {
        Bool = {
          "aws:SecureTransport" = "false"
        }
      }
    }]
  })
}
output "state_bucket" {
  value = aws_s3_bucket.state.id
}
