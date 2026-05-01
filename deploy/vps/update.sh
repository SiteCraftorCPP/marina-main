#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/projects/marina-main"
BRANCH="main"

cd "$PROJECT_DIR"

git fetch origin
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

docker compose up -d --build --remove-orphans
