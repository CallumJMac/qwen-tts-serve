#!/usr/bin/env bash
set -euo pipefail

AWS_PROFILE="${AWS_PROFILE:-rb-voice-cloning-sandbox}"
AWS_REGION="${AWS_REGION:-us-east-1}"
export AWS_PROFILE AWS_REGION

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INFRA_DIR="$REPO_ROOT/infra"

echo "==> Getting ECR repository URL..."
cd "$INFRA_DIR"
ECR_URL=$(terraform output -raw ecr_repository_url)
echo "    ECR: $ECR_URL"

echo "==> Logging into ECR..."
aws ecr get-login-password --region "$AWS_REGION" | \
    docker login --username AWS --password-stdin "$ECR_URL"

echo "==> Building and pushing CustomVoice image..."
cd "$REPO_ROOT"
docker build \
    --platform linux/amd64 \
    --build-arg QWEN_TTS_MODEL=Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice \
    -t "$ECR_URL:custom" .
docker push "$ECR_URL:custom"

echo "==> Building and pushing Base (clone) image..."
docker build \
    --platform linux/amd64 \
    --build-arg QWEN_TTS_MODEL=Qwen/Qwen3-TTS-12Hz-0.6B-Base \
    -t "$ECR_URL:clone" .
docker push "$ECR_URL:clone"

echo "==> Running terraform apply..."
cd "$INFRA_DIR"
terraform apply -auto-approve

echo "==> Waiting for services to stabilize..."
CLUSTER=$(terraform output -raw ecs_cluster_name)
aws ecs wait services-stable \
    --cluster "$CLUSTER" \
    --services "${CLUSTER}-custom" "${CLUSTER}-clone" \
    --region "$AWS_REGION"

ALB=$(terraform output -raw alb_dns_name)
echo ""
echo "==> Deployment complete!"
echo "    CustomVoice: ws://$ALB/custom/ws/tts"
echo "    Clone:       ws://$ALB/clone/ws/tts"
echo ""
echo "    Health checks:"
echo "      curl http://$ALB/custom/health"
echo "      curl http://$ALB/clone/health"
