data "aws_route53_zone" "public" {
  name         = var.domain_name
  private_zone = false
}
locals {
  origin_hostname = "origin-${var.app_hostname}"
}

resource "aws_acm_certificate" "edge" {
  provider          = aws.edge
  domain_name       = var.app_hostname
  validation_method = "DNS"
  lifecycle {
    create_before_destroy = true
  }
}
resource "aws_acm_certificate" "origin" {
  domain_name       = local.origin_hostname
  validation_method = "DNS"
  lifecycle {
    create_before_destroy = true
  }
}
resource "aws_route53_record" "edge_validation" {
  for_each = {
    for d in aws_acm_certificate.edge.domain_validation_options : d.domain_name => d
  }
  zone_id = data.aws_route53_zone.public.zone_id
  name    = each.value.resource_record_name
  type    = each.value.resource_record_type
  records = [each.value.resource_record_value]
  ttl     = 60
}
resource "aws_route53_record" "origin_validation" {
  for_each = {
    for d in aws_acm_certificate.origin.domain_validation_options : d.domain_name => d
  }
  zone_id = data.aws_route53_zone.public.zone_id
  name    = each.value.resource_record_name
  type    = each.value.resource_record_type
  records = [each.value.resource_record_value]
  ttl     = 60
}
resource "aws_acm_certificate_validation" "edge" {
  provider                = aws.edge
  certificate_arn         = aws_acm_certificate.edge.arn
  validation_record_fqdns = [for r in aws_route53_record.edge_validation : r.fqdn]
}
resource "aws_acm_certificate_validation" "origin" {
  certificate_arn         = aws_acm_certificate.origin.arn
  validation_record_fqdns = [for r in aws_route53_record.origin_validation : r.fqdn]
}
resource "random_password" "origin_header" {
  length  = 48
  special = false
}
resource "aws_lb" "api" {
  name                       = "${var.project}-api"
  internal                   = false
  load_balancer_type         = "application"
  security_groups            = [aws_security_group.alb.id]
  subnets                    = aws_subnet.public[*].id
  drop_invalid_header_fields = true
  idle_timeout               = 120
  desync_mitigation_mode     = "strictest"
}
resource "aws_lb_target_group" "api" {
  name                 = "${var.project}-api"
  port                 = 8000
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = aws_vpc.app.id
  deregistration_delay = 30
  health_check {
    path                = "/api/health"
    matcher             = "200"
    interval            = 30
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.api.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.origin.certificate_arn
  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      message_body = "Forbidden"
      status_code  = "403"
    }
  }
}
resource "aws_lb_listener_rule" "cloudfront" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 10
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
  condition {
    http_header {
      http_header_name = "X-Clearance-Origin"
      values           = [random_password.origin_header.result]
    }
  }
  condition {
    path_pattern {
      values = ["/api/*"]
    }
  }
}
resource "aws_route53_record" "origin" {
  zone_id = data.aws_route53_zone.public.zone_id
  name    = local.origin_hostname
  type    = "A"
  alias {
    name                   = aws_lb.api.dns_name
    zone_id                = aws_lb.api.zone_id
    evaluate_target_health = true
  }
}
resource "aws_cloudfront_origin_access_control" "ui" {
  name                              = "${var.project}-ui"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}
resource "aws_cloudfront_function" "spa" {
  name    = "${var.project}-spa"
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = <<-JS
    function handler(event) {
      var request = event.request;
      if (!request.uri.split('/').pop().includes('.')) request.uri = '/index.html';
      return request;
    }
  JS
}
resource "aws_cloudfront_response_headers_policy" "security" {
  name = "${var.project}-security"
  security_headers_config {
    content_type_options {
      override = true
    }
    frame_options {
      frame_option = "DENY"
      override     = true
    }
    referrer_policy {
      referrer_policy = "no-referrer"
      override        = true
    }
    strict_transport_security {
      access_control_max_age_sec = 31536000
      include_subdomains         = false
      preload                    = false
      override                   = true
    }
    content_security_policy {
      content_security_policy = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' https://${aws_cognito_user_pool_domain.login.domain}.auth.${var.region}.amazoncognito.com https://cognito-idp.${var.region}.amazonaws.com; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self' https://${aws_cognito_user_pool_domain.login.domain}.auth.${var.region}.amazoncognito.com"
      override                = true
    }
  }
}
data "aws_cloudfront_cache_policy" "disabled" {
  name = "Managed-CachingDisabled"
}
data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}
data "aws_cloudfront_origin_request_policy" "api" {
  name = "Managed-AllViewerExceptHostHeader"
}
resource "aws_cloudfront_distribution" "app" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  aliases             = [var.app_hostname]
  price_class         = "PriceClass_100"
  http_version        = "http2and3"
  origin {
    domain_name              = aws_s3_bucket.storage["ui"].bucket_regional_domain_name
    origin_id                = "ui"
    origin_access_control_id = aws_cloudfront_origin_access_control.ui.id
  }
  origin {
    domain_name = aws_route53_record.origin.fqdn
    origin_id   = "api"
    custom_header {
      name  = "X-Clearance-Origin"
      value = random_password.origin_header.result
    }
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
      origin_read_timeout    = 60
    }
  }
  default_cache_behavior {
    target_origin_id           = "ui"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD", "OPTIONS"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.disabled.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.security.id
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa.arn
    }
  }
  ordered_cache_behavior {
    path_pattern               = "/api/*"
    target_origin_id           = "api"
    viewer_protocol_policy     = "https-only"
    allowed_methods            = ["GET", "HEAD", "OPTIONS", "PUT", "PATCH", "POST", "DELETE"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.disabled.id
    origin_request_policy_id   = data.aws_cloudfront_origin_request_policy.api.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.security.id
  }
  ordered_cache_behavior {
    path_pattern               = "/assets/*"
    target_origin_id           = "ui"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD", "OPTIONS"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.optimized.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.security.id
  }
  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }
  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.edge.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}
resource "aws_route53_record" "app" {
  for_each = toset(["A", "AAAA"])
  zone_id  = data.aws_route53_zone.public.zone_id
  name     = var.app_hostname
  type     = each.value
  alias {
    name                   = aws_cloudfront_distribution.app.domain_name
    zone_id                = aws_cloudfront_distribution.app.hosted_zone_id
    evaluate_target_health = false
  }
}
resource "aws_s3_bucket_policy" "storage" {
  for_each = aws_s3_bucket.storage
  bucket   = each.value.id
  policy = jsonencode({
    Version = "2012-10-17", Statement = concat([{
      Sid      = "RequireTLS", Effect = "Deny", Principal = "*", Action = "s3:*",
      Resource = [each.value.arn, "${each.value.arn}/*"],
      Condition = {
        Bool = {
          "aws:SecureTransport" = "false"
        }
      }
      }], each.key == "ui" ? [{
      Sid = "CloudFrontRead", Effect = "Allow", Principal = {
        Service = "cloudfront.amazonaws.com"
      },
      Action = "s3:GetObject", Resource = "${each.value.arn}/*",
      Condition = {
        StringEquals = {
          "AWS:SourceArn" = aws_cloudfront_distribution.app.arn
        }
      }
    }] : [])
  })
}
