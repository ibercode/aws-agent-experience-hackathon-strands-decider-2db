terraform {
  backend "s3" {
  }
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

provider "aws" {
  region  = var.region
  profile = var.aws_profile
  default_tags {
    tags = {
      Project = var.project, ManagedBy = "Terraform"
    }
  }
}
provider "aws" {
  alias   = "edge"
  region  = "us-east-1"
  profile = var.aws_profile
  default_tags {
    tags = {
      Project = var.project, ManagedBy = "Terraform"
    }
  }
}
