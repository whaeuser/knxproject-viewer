#!/bin/bash
set -e

echo "==> git pull"
git pull

echo "==> docker compose down"
docker compose down

echo "==> docker compose up --build"
docker compose up -d --build

echo "==> Fertig. Status:"
docker compose ps
