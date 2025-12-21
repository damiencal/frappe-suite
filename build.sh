#!/bin/bash
# Build and push Frappe Press with Shared Bench support
# Usage: ./build.sh [push]

set -e

IMAGE_NAME="ghcr.io/damiencal/frappe-press"
TAG="v15-shared"
FRAPPE_VERSION="v15"

echo "Building ${IMAGE_NAME}:${TAG}..."

docker build \
    --build-arg FRAPPE_VERSION=${FRAPPE_VERSION} \
    -t ${IMAGE_NAME}:${TAG} \
    -f Containerfile \
    .

if [ "$1" == "push" ]; then
    echo "Pushing ${IMAGE_NAME}:${TAG}..."
    docker push ${IMAGE_NAME}:${TAG}
    
    # Also tag as latest-shared
    docker tag ${IMAGE_NAME}:${TAG} ${IMAGE_NAME}:latest-shared
    docker push ${IMAGE_NAME}:latest-shared
fi

echo "Done!"
echo ""
echo "To push:"
echo "  docker login ghcr.io"
echo "  ./build.sh push"
