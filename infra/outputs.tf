output "ecr_repository_url" {
  description = "ECR repository URL for docker push"
  value       = aws_ecr_repository.this.repository_url
}

output "alb_dns_name" {
  description = "ALB DNS name"
  value       = aws_lb.this.dns_name
}

output "custom_endpoint" {
  description = "CustomVoice WebSocket endpoint"
  value       = "ws://${aws_lb.this.dns_name}/custom/ws/tts"
}

output "clone_endpoint" {
  description = "Base (clone) WebSocket endpoint"
  value       = "ws://${aws_lb.this.dns_name}/clone/ws/tts"
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.this.name
}
