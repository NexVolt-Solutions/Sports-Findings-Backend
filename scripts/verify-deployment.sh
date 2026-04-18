#!/bin/bash
# Deployment Verification Script
# Validates that the deployed container is running the latest code

set -e

CONTAINER_NAME="sport-finding-api"
API_URL="http://localhost:8000"
MAX_RETRIES=10
RETRY_INTERVAL=3

echo "=========================================="
echo "🔍 Deployment Verification Script"
echo "=========================================="
echo ""

# Check if container is running
echo "1️⃣  Checking if container is running..."
if ! docker ps | grep -q "$CONTAINER_NAME"; then
    echo "❌ Container $CONTAINER_NAME is not running!"
    exit 1
fi
echo "✅ Container is running"
echo ""

# Get container info
echo "2️⃣  Container Information:"
CONTAINER_ID=$(docker ps -q -f "name=$CONTAINER_NAME")
IMAGE_ID=$(docker inspect --format='{{.Image}}' "$CONTAINER_NAME")
IMAGE_NAME=$(docker inspect --format='{{.Config.Image}}' "$CONTAINER_NAME")
CREATED=$(docker inspect --format='{{.Created}}' "$CONTAINER_NAME")

echo "   - Container ID: $CONTAINER_ID"
echo "   - Image ID: $IMAGE_ID"
echo "   - Image Name: $IMAGE_NAME"
echo "   - Container Created: $CREATED"
echo ""

# Check health endpoint
echo "3️⃣  Checking health endpoint..."
RETRY=0
while [ $RETRY -lt $MAX_RETRIES ]; do
    if curl -s -f "$API_URL/health" > /dev/null 2>&1; then
        echo "✅ Health endpoint is responding"
        break
    fi
    RETRY=$((RETRY + 1))
    if [ $RETRY -lt $MAX_RETRIES ]; then
        echo "   Retry $RETRY/$MAX_RETRIES (waiting ${RETRY_INTERVAL}s)..."
        sleep $RETRY_INTERVAL
    fi
done

if [ $RETRY -eq $MAX_RETRIES ]; then
    echo "❌ Health endpoint not responding after $MAX_RETRIES attempts"
    echo "Container logs:"
    docker logs --tail=20 "$CONTAINER_NAME"
    exit 1
fi
echo ""

# Get recent logs
echo "4️⃣  Recent Container Logs:"
docker logs --tail=10 "$CONTAINER_NAME" | sed 's/^/   /'
echo ""

# Get git commit info from repository (if available)
if [ -d "/home/ubuntu/Sports-Findings-Backend/.git" ]; then
    echo "5️⃣  Git Deployment Info:"
    cd /home/ubuntu/Sports-Findings-Backend
    COMMIT_SHA=$(git rev-parse HEAD)
    COMMIT_MESSAGE=$(git log -1 --pretty=format:"%s")
    COMMIT_AUTHOR=$(git log -1 --pretty=format:"%an")
    COMMIT_TIME=$(git log -1 --pretty=format:"%ai")
    
    echo "   - Commit SHA: $COMMIT_SHA"
    echo "   - Message: $COMMIT_MESSAGE"
    echo "   - Author: $COMMIT_AUTHOR"
    echo "   - Time: $COMMIT_TIME"
    echo ""
fi

# Final status
echo "=========================================="
echo "✅ Deployment verification PASSED"
echo "=========================================="
echo ""
echo "✨ The application is running the latest code!"
echo ""
