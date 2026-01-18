## EventFlow — Proiect Sisteme Concurente și Distribuite (2025–2026)

Platformă web pentru organizarea de evenimente, construită ca **arhitectură distribuită** (microservicii) și livrată “out-of-the-box” ca **Docker Swarm stack**.

Scopul README-ului este să explice proiectul **conform baremului/cerințelor** din enunț (SSO, roluri, DB+ORM, minim 5 componente, Swarm, DNS între servicii, rețele, replicare + funcție avansată + unit tests).

---

## 1) Cerința proiectului (pe scurt)

Se cere o platformă web cu arhitectură concurentă/distribuită, care include obligatoriu:
- autentificare/autorizație prin SSO (ex. Keycloak);
- management roluri + profil utilizator;
- bază de date + ORM;
- livrare ca Docker Swarm stack;
- minim 5 componente (minim 2 dezvoltate de student);
- comunicare între servicii prin DNS (nu hardcodare IP-uri) + configurare prin variabile de mediu;
- rețele cu izolare;
- cel puțin un serviciu care suportă **replicare** și demonstrează o funcționalitate avansată, validată prin **unit tests**.

---

## 2) Context și motivație

EventFlow e o platformă tipică pentru sisteme distribuite: multe servicii specializate (autentificare, ticketing, plată, scanare, notificări) care colaborează prin API-uri și un broker de mesaje. Arhitectura permite scalare/replicare, izolare pe rețele și integrare prin protocoale standard (HTTP + OIDC/JWT + AMQP).

---

## 3) Arhitectură (componente + comunicare)

### Componente (minim 5, cu echilibru OSS / proprii)

**Open-source:**
- **Keycloak** (SSO OIDC/OAuth2) — `docker-stack.yml`
- **PostgreSQL** (DB) — `docker-stack.yml` + `database/schema.sql`
- **RabbitMQ** (message broker) — `docker-stack.yml`
- **Redis** (storage partajat pentru rate limiting distribuit) — `docker-stack.yml`

**Dezvoltate în proiect (microservicii Python/Flask):**
- `services/user-profile-service` — profil + roluri (CRUD) + sincronizare cu Keycloak
- `services/ticketing-service` — evenimente + bilete + waitlist + banlist + rate limiting
- `services/payment-service` — sesiune de plată (rezervare 2 minute) + confirm/cancel
- `services/gate-service` — scan/validare bilet la intrare
- `services/notification-service` — consumă mesaje din RabbitMQ și expune notificări prin REST

### Comunicare între servicii (DNS, nu IP hardcodat)

În Swarm, serviciile comunică folosind numele de serviciu (DNS Docker), de exemplu:
- DB: `postgres`
- SSO: `keycloak`
- broker: `rabbitmq`
- redis: `redis`

Configurația este expusă prin variabile de mediu în `docker-stack.yml` (ex. `DATABASE_URL`, `KEYCLOAK_URL`, `RABBITMQ_URL`, `REDIS_URL`).

### Rețele și securitate (izolare)

În `docker-stack.yml` există 2 rețele overlay:
- `data-network` — pentru DB-uri
- `internal-network` — pentru comunicația internă a microserviciilor

Serviciile sunt conectate doar la rețelele necesare.

---

## 4) Implementarea interfeței (REST API) — conform baremului

Serviciile expun endpoint-uri HTTP cu:
- resurse (`/events`, `/profile/...`, `/my-tickets`, `/notifications`) și metode HTTP corespunzătoare (GET/POST/PATCH);
- coduri de răspuns (200/201/400/401/403/404/429/503);
- autentificare stateless (Bearer JWT).



---

## 5) Module și funcționalități (bază + avansate)

### 5.1 Module de bază (obligatorii)

#### Modul de autentificare (SSO)
- Keycloak (OIDC/OAuth2), JWT tokens, RBAC prin roluri: `ADMIN`, `ORGANIZER`, `ATTENDEE`, `STAFF`
- Config: `keycloak-config/eventflow-realm.json`

#### Modul profil utilizator (management roluri)
- `user-profile-service`:
  - `GET /profile/<sub>`
  - `PUT /profile/<sub>`
  - `GET /profile/<sub>/roles`
  - `POST /profile/<sub>/roles` (ADMIN)
  - `DELETE /profile/<sub>/roles/<role>` (ADMIN)

#### Baza de date + ORM
- PostgreSQL + SQLAlchemy în fiecare microserviciu
- schema inițială: `database/schema.sql`

### 5.2 Module suplimentare (aplicația finală)
- `ticketing-service`: evenimente, bilete, waitlist, ban list, scan (în ticketing există și scan, iar `gate-service` este poarta de acces)
- `payment-service`: rezervare 2 minute + confirm/cancel (cu countdown în frontend)
- `notification-service`: notificări asincrone (consumer RabbitMQ) + endpoint-uri REST
- `gate-service`: scan/validare bilet (marcare ca folosit)

### 5.3 Funcționalități avansate (2+ module avansate)

#### (A) Sistem asincron de notificări (RabbitMQ)
- Evenimente publicate de servicii (ex. ticket booked / ticket scanned)
- Consumate de `notification-service` (thread consumer) și persistate în DB
- Vizualizare prin:
  - `GET /notifications` (ADMIN/ORGANIZER)
  - `GET /my-notifications` (user curent)

#### (B) Rate limiting distribuit + replicare (cerința 10)

**Replicare:**
- `ticketing-service` rulează cu **2 replici** în `docker-stack.yml`.

**Rate limiting distribuit (funcționalitate avansată):**
- endpoint limitat: `POST /events/<id>/tickets`
- implementare sliding window în **Redis** (atomic, funcționează pe mai multe replici)
- configurație:
  - `RATE_LIMIT_BACKEND=redis`
  - `REDIS_URL=redis://redis:6379/0`
- cod: `services/ticketing-service/rate_limiter.py`

**Unit tests (obligatoriu pentru funcția avansată):**
- `services/ticketing-service/tests/test_rate_limiter.py` (pytest + fakeredis)

#### (C) Caching distribuit (Redis) pentru citiri publice (GET)

Pentru a reduce încărcarea pe DB și a demonstra o funcționalitate avansată tip “caching”, `ticketing-service` cache-uiește răspunsuri pentru:
- `GET /events`
- `GET /events/<id>`

Caracteristici:
- cache în **Redis** (shared între replici) cu TTL scurt (implicit 5s) → consistență “eventuală” acceptabilă pentru demo
- header `X-Cache: HIT/MISS` pentru demonstrație
- configurare prin env:
  - `CACHE_ENABLED=1`
  - `CACHE_TTL_SECONDS=5`
- cod: `services/ticketing-service/cache.py`
- unit tests: `services/ticketing-service/tests/test_cache.py`

---

## 6) Livrare și rulare “out-of-the-box” (Docker Swarm)

### Prerechizite
- Docker Desktop / Docker Engine cu suport Swarm
- Node.js (doar pentru frontend, dacă îl rulezi local)

### Pornire backend (Swarm stack)

Din root:

```bash
./setup.sh
./build-images.sh
docker stack deploy -c docker-stack.yml eventflow
```

Verificare:

```bash
docker service ls --filter "name=eventflow"
```

Ar trebui să vezi:
- `eventflow_ticketing-service` **2/2**
- `eventflow_redis` **1/1**

### URL-uri utile (local)
- Keycloak: `http://localhost:8080`
- user-profile-service: `http://localhost:3004/health`
- ticketing-service: `http://localhost:3005/health`
- notification-service: `http://localhost:3006/health`
- gate-service: `http://localhost:3007/health`
- payment-service: `http://localhost:3008/health`

---

## 7) Frontend (Vite)

```bash
cd frontend
npm install
npm run dev
```

Frontend: `http://localhost:3001`

Notă: pentru demo local, frontend-ul folosește `localhost` pentru API-uri. Backend-ul, în schimb, folosește DNS între servicii în Swarm (conform cerinței).

---

## 8) Testare (script automat + unit tests)

### 8.1 Test end-to-end (recomandat pentru prezentare)

Rulează după ce backend-ul e pornit:

```bash
./test-all.sh
```

Ce testează:
- Keycloak readiness (OIDC well-known)
- `/health` pentru toate microserviciile
- obținere token (ROPC) pentru user de test
- creare eveniment → start/confirm payment → ticket → scan ticket → notificări
- rate limiting (3 request-uri rapide → al 3-lea = 429)

Dezactivare rate limit check (opțional):

```bash
TEST_RATE_LIMIT=0 ./test-all.sh
```

### 8.2 Unit tests (cerința 10 — rate limiting)

```bash
cd services/ticketing-service
python3 -m pytest -q
```

---

## 9) Securitate și control acces (RBAC)

Majoritatea endpoint-urilor sensibile cer:
- `Authorization: Bearer <JWT>`
- roluri (ex. `ADMIN`, `ORGANIZER`, `STAFF`) în decoratorii din servicii

---

## 10) Structura proiectului (navigare rapidă)

```
Proiect-SCD-V2/
├── database/
│   └── schema.sql
├── keycloak-config/
│   └── eventflow-realm.json
├── services/
│   ├── user-profile-service/
│   ├── ticketing-service/
│   │   ├── app.py
│   │   ├── rate_limiter.py
│   │   └── tests/
│   ├── payment-service/
│   ├── gate-service/
│   └── notification-service/
├── docker-stack.yml
├── build-images.sh
├── setup.sh
├── test-all.sh
└── frontend/
```

---

## 11) Note pentru evaluare / prezentare

- Proiectul include **SSO + roluri + DB+ORM + Swarm stack + 5+ componente**.
- Există **replicare** (ticketing-service 2 replici).
- Funcționalitatea avansată “rate limiting” este **distribuită** (Redis) și are **unit tests**.
- Există un modul avansat asincron (RabbitMQ notifications) care demonstrează integrare distribuită.

### Testare Locală (Docker Compose)

```bash
# Pornire Keycloak
docker-compose -f docker-compose.keycloak.yml up -d

# Pornire User Profile Service (în alt terminal)
cd services/user-profile-service
docker build -t user-profile-service .
docker run -p 3004:3004 \
  -e DATABASE_URL=postgresql://eventflow:eventflow@localhost:5432/eventflow \
  -e KEYCLOAK_URL=http://localhost:8080 \
  user-profile-service
```

## Configurare

### Variabile de Mediu

Creează un fișier `.env` sau setează variabilele:

```env
# Database
POSTGRES_DB=eventflow
POSTGRES_USER=eventflow
POSTGRES_PASSWORD=eventflow

# Keycloak
KEYCLOAK_REALM=eventflow
KEYCLOAK_CLIENT_ID=eventflow-api
KEYCLOAK_CLIENT_SECRET=<obține din Keycloak Admin Console>
KEYCLOAK_ADMIN=admin
KEYCLOAK_ADMIN_PASSWORD=admin
KEYCLOAK_HOSTNAME=localhost
```

### Obținere Client Secret

1. Accesează Keycloak Admin Console: http://localhost:8080
2. Login: `admin` / `admin`
3. Selectează realm `eventflow`
4. Mergi la **Clients** → **eventflow-api** → **Credentials**
5. Copiază **Secret** și setează în `KEYCLOAK_CLIENT_SECRET`

## API Endpoints

### User Profile Service

- `GET /health` - Health check
- `GET /profile/<keycloak_sub>` - Obține profil utilizator (necesită JWT)
- `PUT /profile/<keycloak_sub>` - Actualizează profil (necesită JWT)
- `GET /profile/<keycloak_sub>/roles` - Obține rolurile (necesită JWT)
- `POST /profile/<keycloak_sub>/roles` - Adaugă rol (necesită ADMIN)
- `DELETE /profile/<keycloak_sub>/roles/<role>` - Șterge rol (necesită ADMIN)

### Autentificare

Obține token de la Keycloak:

```bash
curl -X POST http://localhost:8080/realms/eventflow/protocol/openid-connect/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin1" \
  -d "password=password123" \
  -d "grant_type=password" \
  -d "client_id=eventflow-api" \
  -d "client_secret=<YOUR_SECRET>"
```

## Utilizatori de Test

| Username | Password | Role |
|----------|----------|------|
| admin1 | password123 | ADMIN |
| organizer1 | password123 | ORGANIZER |
| attendee1 | password123 | ATTENDEE |
| staff1 | password123 | STAFF |

## Verificare Funcționalitate

```bash
# 1. Verifică serviciile
docker service ls

# 2. Verifică logs
docker service logs -f eventflow_user-profile-service

# 3. Testează health check
curl http://localhost:3004/health

# 4. Obține token și testează API
TOKEN=$(curl -s -X POST http://localhost:8080/realms/eventflow/protocol/openid-connect/token \
  -d "username=admin1&password=password123&grant_type=password&client_id=eventflow-api&client_secret=<SECRET>" \
  | jq -r '.access_token')

curl -H "Authorization: Bearer $TOKEN" http://localhost:3004/profile/<keycloak_sub>
```

## Componente

- **Open Source**: Keycloak, PostgreSQL
- **Proprii**: User Profile Service (Python/Flask)

## Note

- Toate serviciile comunică prin nume DNS (ex: `postgres`, `keycloak`)
- Variabilele de mediu sunt folosite pentru configurare (nu hardcoded)
- Stack-ul este gata pentru producție (cu ajustări de securitate)

