data "aws_availability_zones" "available" {
  state = "available"
}
resource "aws_vpc" "app" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
}
resource "aws_internet_gateway" "app" {
  vpc_id = aws_vpc.app.id
}
resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.app.id
  cidr_block              = cidrsubnet(aws_vpc.app.cidr_block, 8, count.index)
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true
}
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.app.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.app.id
  }
}
resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}
data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}
resource "aws_security_group" "alb" {
  name_prefix = "${var.project}-alb-"
  vpc_id      = aws_vpc.app.id
}
resource "aws_security_group" "backend" {
  name_prefix = "${var.project}-backend-"
  vpc_id      = aws_vpc.app.id
}
resource "aws_security_group" "decider" {
  name_prefix = "${var.project}-decider-"
  vpc_id      = aws_vpc.app.id
}
resource "aws_vpc_security_group_ingress_rule" "cloudfront_https" {
  security_group_id = aws_security_group.alb.id
  prefix_list_id    = data.aws_ec2_managed_prefix_list.cloudfront.id
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}
resource "aws_vpc_security_group_egress_rule" "alb_api" {
  security_group_id            = aws_security_group.alb.id
  referenced_security_group_id = aws_security_group.backend.id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}
resource "aws_vpc_security_group_ingress_rule" "api_alb" {
  security_group_id            = aws_security_group.backend.id
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}
resource "aws_vpc_security_group_egress_rule" "api_decider" {
  security_group_id            = aws_security_group.backend.id
  referenced_security_group_id = aws_security_group.decider.id
  ip_protocol                  = "tcp"
  from_port                    = 8099
  to_port                      = 8099
}
resource "aws_vpc_security_group_ingress_rule" "decider_api" {
  security_group_id            = aws_security_group.decider.id
  referenced_security_group_id = aws_security_group.backend.id
  ip_protocol                  = "tcp"
  from_port                    = 8099
  to_port                      = 8099
}
resource "aws_vpc_security_group_egress_rule" "task_https" {
  for_each = {
    api = aws_security_group.backend.id, decider = aws_security_group.decider.id
  }
  security_group_id = each.value
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}
resource "aws_service_discovery_private_dns_namespace" "app" {
  name = "${var.project}.internal"
  vpc  = aws_vpc.app.id
}
resource "aws_service_discovery_service" "decider" {
  name = "decider"
  dns_config {
    namespace_id   = aws_service_discovery_private_dns_namespace.app.id
    routing_policy = "MULTIVALUE"
    dns_records {
      ttl  = 10
      type = "A"
    }
  }
}
