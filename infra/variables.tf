variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "qwen-tts-serve"
}

variable "instance_type" {
  description = "EC2 instance type for ECS (must have GPU)"
  type        = string
  default     = "g5.xlarge"
}

variable "container_port" {
  description = "Port the container listens on"
  type        = number
  default     = 8000
}

variable "desired_count" {
  description = "Number of instances per service"
  type        = number
  default     = 1
}
