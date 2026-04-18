output "ecr_repository_url" {
  description = "ECR repository URL for docker push"
  value       = aws_ecr_repository.this.repository_url
}

output "alb_dns_name" {
  description = "ALB DNS name — connect WebSocket to ws://<this>/ws/tts"
  value       = aws_lb.this.dns_name
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.this.name
}
