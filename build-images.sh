#!/bin/bash

# Script pentru construirea imaginilor Docker necesare pentru Docker Swarm

echo "🔨 Construire imagini Docker pentru EventFlow..."
echo ""

set -e

build_one() {
  local name="$1"
  local dir="$2"
  echo "📦 Construire ${name}..."
  docker build -t "eventflow/${name}:latest" "${dir}"
  echo "✅ ${name} construit cu succes"
  echo ""
}

build_one "user-profile-service" "./services/user-profile-service"
build_one "ticketing-service" "./services/ticketing-service"
build_one "notification-service" "./services/notification-service"
build_one "gate-service" "./services/gate-service"
build_one "payment-service" "./services/payment-service"

echo ""
echo "✅ Toate imaginile au fost construite cu succes!"
echo ""
echo "📋 Următorul pas:"
echo "   docker stack deploy -c docker-stack.yml eventflow"

