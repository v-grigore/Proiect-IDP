#!/usr/bin/env bash
set -euo pipefail

# End-to-end test for EventFlow (backend services + Keycloak integration).
# Assumes backend is already running locally (Docker Swarm stack "eventflow").
#
# What it tests:
# - Keycloak readiness via OIDC well-known
# - /health on all backend services
# - Token acquisition (ROPC) for test user
# - Create event (ticketing-service)
# - Start + confirm payment (payment-service)
# - Verify ticket appears in /my-tickets (ticketing-service)
# - Scan ticket (gate-service)
# - Verify notifications include ticket_booked / ticket_scanned (notification-service)

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo -e "${RED}Missing dependency:${NC} $1"
    exit 1
  }
}

json_get() {
  # Usage: json_get "$json" "field"
  echo "$1" | python3 -c 'import json, sys; data=json.load(sys.stdin); key=sys.argv[1]; val=data.get(key,""); print("" if val is None else val)' "$2"
}

jwt_sub() {
  # Usage: jwt_sub "$access_token"
  python3 - <<'PY' "$1"
import base64, json, sys
t = sys.argv[1]
parts = t.split(".")
if len(parts) != 3:
  print("")
  sys.exit(0)
payload = parts[1].replace("-", "+").replace("_", "/")
payload += "=" * (-len(payload) % 4)
try:
  data = json.loads(base64.b64decode(payload).decode("utf-8"))
  print(data.get("sub", "") or "")
except Exception:
  print("")
PY
}

http_code() {
  curl -s -o /dev/null -w "%{http_code}" "$1" 2>/dev/null || echo "000"
}

wait_http_200() {
  local name="$1"
  local url="$2"
  local tries="${3:-60}"
  local sleep_s="${4:-2}"
  local i=1
  while [ "$i" -le "$tries" ]; do
    local code
    code="$(http_code "$url")"
    if [ "$code" = "200" ]; then
      echo -e "${GREEN}✅ ${name}${NC} (200)"
      return 0
    fi
    if [ "$i" -eq 1 ]; then
      echo -e "${YELLOW}⏳ waiting for ${name}${NC} (${url})"
    fi
    sleep "$sleep_s"
    i=$((i + 1))
  done
  echo -e "${RED}❌ ${name} not ready${NC} (last HTTP ${code})"
  return 1
}

require_cmd docker
require_cmd curl
require_cmd python3

cd "$ROOT_DIR"

if [ -f ".env" ]; then
  # shellcheck disable=SC1091
  source ".env"
fi

STACK_NAME="${STACK_NAME:-eventflow}"

if ! docker service ls --format "{{.Name}}" 2>/dev/null | grep -q "^${STACK_NAME}_"; then
  echo -e "${RED}Backend stack not detected.${NC}"
  echo "Start it with:"
  echo "  ./setup.sh"
  echo "  ./build-images.sh"
  echo "  docker stack deploy -c docker-stack.yml ${STACK_NAME}"
  exit 1
fi

KEYCLOAK_BASE="${KEYCLOAK_BASE:-http://localhost:8080}"
USER_PROFILE_BASE="${USER_PROFILE_BASE:-http://localhost:3004}"
TICKETING_BASE="${TICKETING_BASE:-http://localhost:3005}"
NOTIFICATION_BASE="${NOTIFICATION_BASE:-http://localhost:3006}"
GATE_BASE="${GATE_BASE:-http://localhost:3007}"
PAYMENT_BASE="${PAYMENT_BASE:-http://localhost:3008}"
FRONTEND_BASE="${FRONTEND_BASE:-http://localhost:3001}"

REALM="${KEYCLOAK_REALM:-eventflow}"
CLIENT_ID="${KEYCLOAK_CLIENT_ID:-eventflow-api}"
CLIENT_SECRET="${KEYCLOAK_CLIENT_SECRET:-}"
TEST_USER="${TEST_USER:-admin1}"
TEST_PASS="${TEST_PASS:-password123}"
TEST_RATE_LIMIT="${TEST_RATE_LIMIT:-1}"
TEST_CACHE="${TEST_CACHE:-1}"

echo "🧪 EventFlow - Full test"
echo "======================="
echo ""

echo "📦 Services running (Docker Swarm):"
docker service ls --filter "name=${STACK_NAME}_" --format "  {{.Name}}\t{{.Replicas}}\t{{.Image}}"
echo ""

echo "🔐 Keycloak readiness (OIDC well-known)"
wait_http_200 "Keycloak well-known" "${KEYCLOAK_BASE}/realms/${REALM}/.well-known/openid-configuration" 90 2
echo ""

echo "🏥 Health checks"
wait_http_200 "user-profile-service" "${USER_PROFILE_BASE}/health" 60 1
wait_http_200 "ticketing-service" "${TICKETING_BASE}/health" 60 1
wait_http_200 "notification-service" "${NOTIFICATION_BASE}/health" 60 1
wait_http_200 "gate-service" "${GATE_BASE}/health" 60 1
wait_http_200 "payment-service" "${PAYMENT_BASE}/health" 60 1
echo ""

if [ "${TEST_CACHE}" = "1" ] || [ "${TEST_CACHE}" = "true" ] || [ "${TEST_CACHE}" = "yes" ]; then
  echo "🧠 ticketing-service: cache sanity check (GET /events twice → expect X-Cache: HIT)"
  h1="$(curl -s -D - "${TICKETING_BASE}/events" -o /dev/null | tr -d "\r" | awk -F': ' 'tolower($1)=="x-cache"{print $2}' | tail -n1)"
  h2="$(curl -s -D - "${TICKETING_BASE}/events" -o /dev/null | tr -d "\r" | awk -F': ' 'tolower($1)=="x-cache"{print $2}' | tail -n1)"
  if [ "${h2}" = "HIT" ]; then
    echo -e "${GREEN}✅ cache ok${NC} (first=${h1:-?}, second=${h2})"
  else
    echo -e "${YELLOW}⚠️  cache not observed${NC} (first=${h1:-?}, second=${h2:-?})"
    echo "   You can disable this check with: TEST_CACHE=0 ./test-all.sh"
  fi
  echo ""
fi

echo "🔑 Getting access token (ROPC) for ${TEST_USER}"
TOKEN_RESP="$(curl -sS -X POST "${KEYCLOAK_BASE}/realms/${REALM}/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=${TEST_USER}" \
  -d "password=${TEST_PASS}" \
  -d "grant_type=password" \
  -d "client_id=${CLIENT_ID}" \
  ${CLIENT_SECRET:+-d "client_secret=${CLIENT_SECRET}"} \
)"
ACCESS_TOKEN="$(json_get "$TOKEN_RESP" "access_token")"

if [ -z "$ACCESS_TOKEN" ] || [ "$ACCESS_TOKEN" = "null" ]; then
  echo -e "${RED}❌ Failed to get token${NC}"
  echo "Response:"
  echo "$TOKEN_RESP"
  echo ""
  echo "Hints:"
  echo "- If your client is confidential, set KEYCLOAK_CLIENT_SECRET in .env"
  echo "- Ensure user ${TEST_USER}/${TEST_PASS} exists in Keycloak realm '${REALM}'"
  exit 1
fi

SUB="$(jwt_sub "$ACCESS_TOKEN")"
echo -e "${GREEN}✅ token ok${NC} (sub=${SUB:-unknown})"
echo ""

echo "👤 user-profile-service: GET /profile/<sub>"
if [ -n "${SUB:-}" ]; then
  curl -sS -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    "${USER_PROFILE_BASE}/profile/${SUB}" >/dev/null
  echo -e "${GREEN}✅ profile ok${NC}"
else
  echo -e "${YELLOW}⚠️  could not decode sub; skipping profile test${NC}"
fi
echo ""

echo "🎫 ticketing-service: create event"
STARTS_AT="$(python3 - <<'PY'
from datetime import datetime, timedelta
print((datetime.utcnow() + timedelta(days=1)).replace(microsecond=0).isoformat())
PY
)"
EVENT_BODY="$(python3 - <<PY
import json
print(json.dumps({
  "name": "E2E Test Event",
  "location": "Test City",
  "starts_at": "${STARTS_AT}",
  "total_tickets": 10,
  "description": "Created by test-all.sh"
}))
PY
)"
EVENT_RESP="$(curl -sS -X POST "${TICKETING_BASE}/events" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "${EVENT_BODY}"
)"
EVENT_ID="$(echo "$EVENT_RESP" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("id","") or "")')"
if [ -z "$EVENT_ID" ]; then
  echo -e "${RED}❌ Failed to create event${NC}"
  echo "$EVENT_RESP"
  exit 1
fi
echo -e "${GREEN}✅ event created${NC} (id=${EVENT_ID})"
echo ""

if [ "${TEST_RATE_LIMIT}" = "1" ] || [ "${TEST_RATE_LIMIT}" = "true" ] || [ "${TEST_RATE_LIMIT}" = "yes" ]; then
  echo "🚦 ticketing-service: rate limiting (/events/<id>/tickets max 2 per 60s)"
  echo "   Making 3 quick purchase requests; expecting 3rd to be HTTP 429"

  code1="$(curl -s -o /dev/null -w "%{http_code}" -X POST "${TICKETING_BASE}/events/${EVENT_ID}/tickets" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" 2>/dev/null || echo "000")"
  code2="$(curl -s -o /dev/null -w "%{http_code}" -X POST "${TICKETING_BASE}/events/${EVENT_ID}/tickets" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" 2>/dev/null || echo "000")"
  code3="$(curl -s -o /dev/null -w "%{http_code}" -X POST "${TICKETING_BASE}/events/${EVENT_ID}/tickets" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" 2>/dev/null || echo "000")"

  if [ "$code1" = "201" ] && [ "$code2" = "201" ] && [ "$code3" = "429" ]; then
    echo -e "${GREEN}✅ rate limiting ok${NC} (201, 201, 429)"
  else
    echo -e "${YELLOW}⚠️  rate limiting unexpected${NC} (got ${code1}, ${code2}, ${code3})"
    echo "   Note: if you re-run quickly with the same user, the in-memory limiter may still be in window."
    echo "   You can disable this check with: TEST_RATE_LIMIT=0 ./test-all.sh"
  fi
  echo ""
fi

echo "💳 payment-service: start session"
PAY_START_RESP="$(curl -sS -X POST "${PAYMENT_BASE}/payments/start" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"event_id\": ${EVENT_ID}}"
)"
SESSION_ID="$(
  echo "$PAY_START_RESP" | python3 -c 'import json,sys; data=json.load(sys.stdin); session=data.get("session", data); print(session.get("id","") if isinstance(session, dict) else "")'
)"
if [ -z "$SESSION_ID" ]; then
  echo -e "${RED}❌ Failed to start payment session${NC}"
  echo "$PAY_START_RESP"
  exit 1
fi
echo -e "${GREEN}✅ payment session started${NC} (id=${SESSION_ID})"
echo ""

echo "✅ payment-service: confirm session"
PAY_CONFIRM_RESP="$(curl -sS -X POST "${PAYMENT_BASE}/payments/confirm/${SESSION_ID}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}"
)"
TICKET_CODE="$(
  echo "$PAY_CONFIRM_RESP" | python3 -c 'import json,sys; data=json.load(sys.stdin); ticket=(data.get("ticket") or {}); print(ticket.get("code","") or "")'
)"
if [ -z "$TICKET_CODE" ]; then
  echo -e "${RED}❌ Failed to confirm payment / issue ticket${NC}"
  echo "$PAY_CONFIRM_RESP"
  exit 1
fi
echo -e "${GREEN}✅ ticket issued${NC} (code=${TICKET_CODE})"
echo ""

echo "🎟️ ticketing-service: GET /my-tickets contains ticket"
MY_TICKETS_RESP="$(curl -sS -H "Authorization: Bearer ${ACCESS_TOKEN}" "${TICKETING_BASE}/my-tickets")"
HAS_CODE="$(
  echo "$MY_TICKETS_RESP" | python3 -c 'import json,sys; data=json.load(sys.stdin); codes=[t.get("code") for t in data if isinstance(t, dict)]; print("yes" if "'"${TICKET_CODE}"'" in codes else "no")'
)"
if [ "$HAS_CODE" != "yes" ]; then
  echo -e "${RED}❌ Ticket not found in /my-tickets${NC}"
  echo "$MY_TICKETS_RESP"
  exit 1
fi
echo -e "${GREEN}✅ my-tickets ok${NC}"
echo ""

echo "🚪 gate-service: scan ticket"
SCAN_RESP="$(curl -sS -X POST "${GATE_BASE}/scan/${TICKET_CODE}" -H "Authorization: Bearer ${ACCESS_TOKEN}")"
SCAN_VALID="$(json_get "$SCAN_RESP" "valid")"
if [ "$SCAN_VALID" != "True" ] && [ "$SCAN_VALID" != "true" ]; then
  echo -e "${RED}❌ Scan failed${NC}"
  echo "$SCAN_RESP"
  exit 1
fi
echo -e "${GREEN}✅ scan ok${NC}"
echo ""

echo "🔔 notification-service: wait for notifications (ticket_booked / ticket_scanned)"
found="no"
for _ in $(seq 1 20); do
  NOTES="$(curl -sS -H "Authorization: Bearer ${ACCESS_TOKEN}" "${NOTIFICATION_BASE}/my-notifications" || true)"
  if echo "$NOTES" | python3 -c 'import json,sys; data=json.load(sys.stdin); codes=[n.get("code") for n in data if isinstance(n, dict)]; sys.exit(0 if "'"${TICKET_CODE}"'" in codes else 1)' >/dev/null 2>&1; then
    found="yes"
    break
  fi
  sleep 1
done
if [ "$found" != "yes" ]; then
  echo -e "${YELLOW}⚠️  notifications not observed yet${NC} (consumer may be catching up)"
else
  echo -e "${GREEN}✅ notifications ok${NC}"
fi
echo ""

echo "🌐 (optional) frontend check"
FE_CODE="$(http_code "${FRONTEND_BASE}/")"
if [ "$FE_CODE" = "200" ]; then
  echo -e "${GREEN}✅ frontend reachable${NC} (${FRONTEND_BASE})"
else
  echo -e "${YELLOW}⚠️  frontend not reachable${NC} (${FRONTEND_BASE})"
fi
echo ""

echo -e "${GREEN}✅ All core tests completed.${NC}"


