resource "random_id" "suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "storage" {
  for_each = toset(["ui", "scenarios", "session-files"])
  bucket   = "${var.project}-${each.key}-${random_id.suffix.hex}"
}
resource "aws_s3_bucket_public_access_block" "storage" {
  for_each                = aws_s3_bucket.storage
  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_versioning" "storage" {
  for_each = aws_s3_bucket.storage
  bucket   = each.value.id
  versioning_configuration {
    status = "Enabled"
  }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "storage" {
  for_each = aws_s3_bucket.storage
  bucket   = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
resource "aws_s3_object" "scenarios" {
  for_each     = toset(["incorrect-readback", "words-versus-actions", "missing-evidence"])
  bucket       = aws_s3_bucket.storage["scenarios"].id
  key          = "scenarios/${each.key}/v1/scenario.json"
  source       = "${path.module}/../../scenarios/${each.key}/v1/scenario.json"
  etag         = filemd5("${path.module}/../../scenarios/${each.key}/v1/scenario.json")
  content_type = "application/json"
  depends_on   = [aws_s3_bucket_versioning.storage]
}

# Keep existing objects and their Terraform addresses for historical sessions.
resource "aws_s3_object" "scenarios_v2" {
  for_each     = toset(["incorrect-readback", "words-versus-actions", "missing-evidence"])
  bucket       = aws_s3_bucket.storage["scenarios"].id
  key          = "scenarios/${each.key}/v2/scenario.json"
  source       = "${path.module}/../../scenarios/${each.key}/v2/scenario.json"
  etag         = filemd5("${path.module}/../../scenarios/${each.key}/v2/scenario.json")
  content_type = "application/json"
  depends_on   = [aws_s3_bucket_versioning.storage]
}
# Version 3 uses runway 36/18; retain earlier assets for saved-session replay.
resource "aws_s3_object" "scenarios_v3" {
  for_each     = toset(["incorrect-readback", "words-versus-actions", "missing-evidence"])
  bucket       = aws_s3_bucket.storage["scenarios"].id
  key          = "scenarios/${each.key}/v3/scenario.json"
  source       = "${path.module}/../../scenarios/${each.key}/v3/scenario.json"
  etag         = filemd5("${path.module}/../../scenarios/${each.key}/v3/scenario.json")
  content_type = "application/json"
  depends_on   = [aws_s3_bucket_versioning.storage]
}
resource "aws_dynamodb_table" "sessions" {
  name         = "${var.project}-sessions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"
  attribute {
    name = "PK"
    type = "S"
  }
  attribute {
    name = "SK"
    type = "S"
  }
  attribute {
    name = "GSI1PK"
    type = "S"
  }
  attribute {
    name = "GSI1SK"
    type = "S"
  }
  global_secondary_index {
    name            = "sessions-by-user"
    hash_key        = "GSI1PK"
    range_key       = "GSI1SK"
    projection_type = "ALL"
  }
  point_in_time_recovery {
    enabled = true
  }
  server_side_encryption {
    enabled = true
  }
}
