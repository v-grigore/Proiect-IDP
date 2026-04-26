#!/bin/bash

# Script de setup pentru EventFlow - Module de bază

echo "🚀 EventFlow - Setup Module de Bază"
echo "===================================="
echo ""

# Verifică Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker nu este instalat. Te rugăm să instalezi Docker."
    exit 1
fi

echo "✅ Docker găsit"

# Verifică Docker Swarm
if ! docker info | grep -q "Swarm: active"; then
    echo "📦 Inițializare Docker Swarm..."
    docker swarm init
else
    echo "✅ Docker Swarm este deja activ"
fi

# Creează rețelele
echo "Creare retele Docker..."
docker network create --driver overlay edge-network 2>/dev/null || echo "  Reteaua edge-network exista deja"
docker network create --driver overlay internal-network 2>/dev/null || echo "  Reteaua internal-network exista deja"
docker network create --driver overlay data-network 2>/dev/null || echo "  Reteaua data-network exista deja"
docker network create --driver overlay db-network 2>/dev/null || echo "  Reteaua db-network exista deja"
docker network create --driver overlay monitoring-network 2>/dev/null || echo "  Reteaua monitoring-network exista deja"

echo "Retele create"

# Verifică dacă există fișier .env
if [ ! -f .env ]; then
    echo "📝 Creare fișier .env..."
    cat > .env << EOF
# Database
POSTGRES_DB=eventflow
POSTGRES_USER=eventflow
POSTGRES_PASSWORD=eventflow

# Keycloak
KEYCLOAK_REALM=eventflow
KEYCLOAK_CLIENT_ID=eventflow-api
KEYCLOAK_CLIENT_SECRET=
KEYCLOAK_ADMIN=admin
KEYCLOAK_ADMIN_PASSWORD=admin
KEYCLOAK_HOSTNAME=localhost
KEYCLOAK_DB_PASSWORD=keycloak
EOF
    echo "✅ Fișier .env creat"
    echo "⚠️  IMPORTANT: Actualizează KEYCLOAK_CLIENT_SECRET după ce obții secret-ul din Keycloak!"
else
    echo "✅ Fișier .env există deja"
fi

echo ""
echo "📋 Pași următori:"
echo "1. Construiește imaginile: ./build-images.sh"
echo "2. Deploy stack: docker stack deploy -c docker-stack.yml eventflow"
echo "3. Așteaptă ca Keycloak să pornească (verifică: docker service logs eventflow_keycloak)"
echo "4. Accesează Keycloak Admin Console: http://localhost:8080"
echo "5. Obține client secret din Keycloak și actualizează .env"
echo "6. Restart stack: docker stack rm eventflow && docker stack deploy -c docker-stack.yml eventflow"
echo ""
echo "✅ Setup complet!"

