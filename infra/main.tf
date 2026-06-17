terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# --- ECR ---

resource "aws_ecr_repository" "this" {
  name                 = var.project_name
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

# --- IAM (ECS task execution) ---

resource "aws_iam_role" "ecs_execution" {
  name = "${var.project_name}-ecs-execution"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "ecs_task" {
  name = "${var.project_name}-ecs-task"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

# --- IAM (EC2 instances in the cluster) ---

resource "aws_iam_role" "ecs_ec2" {
  name = "${var.project_name}-ecs-ec2"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_ec2" {
  role       = aws_iam_role.ecs_ec2.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
}

resource "aws_iam_role_policy_attachment" "ecs_ec2_ssm" {
  role       = aws_iam_role.ecs_ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "ecs_ec2_ecr_push" {
  name = "${var.project_name}-ecr-push"
  role = aws_iam_role.ecs_ec2.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ecr:PutImage", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:BatchCheckLayerAvailability"]
      Resource = aws_ecr_repository.this.arn
    }]
  })
}

resource "aws_iam_instance_profile" "ecs_ec2" {
  name = "${var.project_name}-ecs-ec2"
  role = aws_iam_role.ecs_ec2.name
}

# --- CloudWatch ---

resource "aws_cloudwatch_log_group" "this" {
  name              = "/ecs/${var.project_name}"
  retention_in_days = 14
}

# --- Security Groups ---

resource "aws_security_group" "alb" {
  name_prefix = "${var.project_name}-alb-"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "ecs" {
  name_prefix = "${var.project_name}-ecs-"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port       = 0
    to_port         = 65535
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# --- ALB ---

resource "aws_lb" "this" {
  name               = var.project_name
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = data.aws_subnets.default.ids
  idle_timeout       = 300
}

resource "aws_lb_target_group" "custom" {
  name        = "${var.project_name}-custom"
  port        = var.container_port
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.default.id
  target_type = "instance"

  health_check {
    path                = "/custom/health"
    interval            = 30
    timeout             = 10
    healthy_threshold   = 2
    unhealthy_threshold = 5
  }

  stickiness {
    type    = "lb_cookie"
    enabled = true
  }
}

resource "aws_lb_target_group" "clone" {
  name        = "${var.project_name}-clone"
  port        = var.container_port
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.default.id
  target_type = "instance"

  health_check {
    path                = "/clone/health"
    interval            = 30
    timeout             = 10
    healthy_threshold   = 2
    unhealthy_threshold = 5
  }

  stickiness {
    type    = "lb_cookie"
    enabled = true
  }
}

resource "aws_lb_listener" "this" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.clone.arn
  }
}

resource "aws_lb_listener_rule" "custom" {
  listener_arn = aws_lb_listener.this.arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.custom.arn
  }

  condition {
    path_pattern {
      values = ["/custom/*"]
    }
  }
}

resource "aws_lb_listener_rule" "clone" {
  listener_arn = aws_lb_listener.this.arn
  priority     = 20

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.clone.arn
  }

  condition {
    path_pattern {
      values = ["/clone/*"]
    }
  }
}

# --- EC2 Auto Scaling Group (backs the ECS cluster) ---

data "aws_ssm_parameter" "ecs_gpu_ami" {
  name = "/aws/service/ecs/optimized-ami/amazon-linux-2/gpu/recommended/image_id"
}

resource "aws_launch_template" "ecs" {
  name_prefix   = "${var.project_name}-"
  image_id      = data.aws_ssm_parameter.ecs_gpu_ami.value
  instance_type = var.instance_type

  iam_instance_profile {
    arn = aws_iam_instance_profile.ecs_ec2.arn
  }

  network_interfaces {
    associate_public_ip_address = true
    security_groups             = [aws_security_group.ecs.id]
  }

  user_data = base64encode(<<-EOF
    #!/bin/bash
    echo ECS_CLUSTER=${var.project_name} >> /etc/ecs/ecs.config
  EOF
  )

  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size = 100
      volume_type = "gp3"
    }
  }

  tag_specifications {
    resource_type = "instance"
    tags          = { Name = var.project_name }
  }
}

resource "aws_autoscaling_group" "ecs" {
  name                = var.project_name
  desired_capacity    = var.desired_count * 2
  min_size            = 0
  max_size            = var.desired_count * 2
  vpc_zone_identifier = data.aws_subnets.default.ids

  launch_template {
    id      = aws_launch_template.ecs.id
    version = "$Latest"
  }

  tag {
    key                 = "AmazonECSManaged"
    value               = true
    propagate_at_launch = true
  }
}

resource "aws_ecs_capacity_provider" "this" {
  name = var.project_name

  auto_scaling_group_provider {
    auto_scaling_group_arn = aws_autoscaling_group.ecs.arn
  }
}

# --- ECS ---

resource "aws_ecs_cluster" "this" {
  name = var.project_name
}

resource "aws_ecs_cluster_capacity_providers" "this" {
  cluster_name       = aws_ecs_cluster.this.name
  capacity_providers = [aws_ecs_capacity_provider.this.name]

  default_capacity_provider_strategy {
    capacity_provider = aws_ecs_capacity_provider.this.name
    weight            = 1
  }
}

resource "aws_ecs_task_definition" "custom" {
  family                   = "${var.project_name}-custom"
  network_mode             = "bridge"
  requires_compatibilities = ["EC2"]
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn
  cpu                      = "4096"
  memory                   = "14336"

  container_definitions = jsonencode([{
    name      = "${var.project_name}-custom"
    image     = "${aws_ecr_repository.this.repository_url}:custom"
    essential = true

    portMappings = [{
      containerPort = var.container_port
      hostPort      = 0
      protocol      = "tcp"
    }]

    environment = [
      { name = "QWEN_TTS_ENGINE", value = "faster" },
      { name = "QWEN_TTS_MODEL", value = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice" },
      { name = "URL_PREFIX", value = "/custom" },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.this.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "custom"
      }
    }

    resourceRequirements = [{
      type  = "GPU"
      value = "1"
    }]
  }])
}

resource "aws_ecs_task_definition" "clone" {
  family                   = "${var.project_name}-clone"
  network_mode             = "bridge"
  requires_compatibilities = ["EC2"]
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn
  cpu                      = "4096"
  memory                   = "14336"

  container_definitions = jsonencode([{
    name      = "${var.project_name}-clone"
    image     = "${aws_ecr_repository.this.repository_url}:clone"
    essential = true

    portMappings = [{
      containerPort = var.container_port
      hostPort      = 0
      protocol      = "tcp"
    }]

    environment = [
      { name = "QWEN_TTS_ENGINE", value = "faster" },
      { name = "QWEN_TTS_MODEL", value = "Qwen/Qwen3-TTS-12Hz-0.6B-Base" },
      { name = "URL_PREFIX", value = "/clone" },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.this.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "clone"
      }
    }

    resourceRequirements = [{
      type  = "GPU"
      value = "1"
    }]
  }])
}

resource "aws_ecs_service" "custom" {
  name            = "${var.project_name}-custom"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.custom.arn
  desired_count   = var.desired_count

  capacity_provider_strategy {
    capacity_provider = aws_ecs_capacity_provider.this.name
    weight            = 1
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.custom.arn
    container_name   = "${var.project_name}-custom"
    container_port   = var.container_port
  }

  depends_on = [aws_lb_listener.this, aws_ecs_cluster_capacity_providers.this]
}

resource "aws_ecs_service" "clone" {
  name            = "${var.project_name}-clone"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.clone.arn
  desired_count   = var.desired_count

  capacity_provider_strategy {
    capacity_provider = aws_ecs_capacity_provider.this.name
    weight            = 1
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.clone.arn
    container_name   = "${var.project_name}-clone"
    container_port   = var.container_port
  }

  depends_on = [aws_lb_listener.this, aws_ecs_cluster_capacity_providers.this]
}
