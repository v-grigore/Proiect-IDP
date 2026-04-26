from fpdf import FPDF
from fpdf.enums import XPos, YPos

LM = 15
RM = 15
PW = 210
UW = PW - LM - RM  # 180


class PDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_fill_color(30, 60, 114)
        self.set_text_color(255, 255, 255)
        self.rect(0, 0, 210, 14, "F")
        self.set_y(3)
        self.cell(0, 8, "EventFlow - Documentatie Tehnica Etapa 1", align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)
        self.ln(10)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"Pagina {self.page_no()}", align="C")

    def chapter_title(self, num, title):
        self.set_font("Helvetica", "B", 13)
        self.set_fill_color(30, 60, 114)
        self.set_text_color(255, 255, 255)
        self.cell(0, 9, f"{num}. {title}", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)
        self.ln(3)

    def section_title(self, title):
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(30, 60, 114)
        self.cell(0, 7, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)
        self.set_draw_color(30, 60, 114)
        self.set_line_width(0.3)
        y = self.get_y()
        self.line(LM, y, LM + UW, y)
        self.ln(3)

    def body_text(self, text):
        self.set_font("Helvetica", "", 10)
        self.multi_cell(UW, 6, text)
        self.ln(1)

    def bullet(self, text, indent=8):
        self.set_font("Helvetica", "", 10)
        self.set_x(LM + indent)
        self.cell(5, 6, chr(149), new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.multi_cell(UW - indent - 5, 6, text)

    def kv(self, key, value):
        kw = 50
        self.set_font("Helvetica", "B", 10)
        self.set_x(LM)
        self.cell(kw, 6, key + ":", new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_font("Helvetica", "", 10)
        self.multi_cell(UW - kw, 6, value)

    def table_header(self, cols, widths):
        self.set_font("Helvetica", "B", 9)
        self.set_fill_color(30, 60, 114)
        self.set_text_color(255, 255, 255)
        for col, w in zip(cols, widths):
            self.cell(w, 7, col, border=1, fill=True, new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.ln()
        self.set_text_color(0, 0, 0)

    def table_row(self, cells, widths, fill=False):
        self.set_font("Helvetica", "", 9)
        self.set_fill_color(235, 240, 250 if fill else 255)
        for cell, w in zip(cells, widths):
            self.cell(w, 6, cell, border=1, fill=fill, new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.ln()

    def service_entry(self, name, port, replicas, desc):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(30, 60, 114)
        self.cell(0, 7, f"  {name}  (port {port}, {replicas} replici)",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)
        self.set_font("Helvetica", "B", 9.5)
        self.set_x(LM + 8)
        self.multi_cell(UW - 8, 5.5, desc)
        self.ln(1)


pdf = PDF()
pdf.set_margins(LM, 20, RM)
pdf.set_auto_page_break(auto=True, margin=18)
pdf.add_page()

# ─────────────────────────────────────────────────────────────────────────
# COVER
# ─────────────────────────────────────────────────────────────────────────
pdf.ln(8)
pdf.set_font("Helvetica", "B", 26)
pdf.set_text_color(30, 60, 114)
pdf.cell(0, 14, "EventFlow", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
pdf.set_font("Helvetica", "", 13)
pdf.set_text_color(60, 60, 60)
pdf.cell(0, 8, "Platforma distribuita de rezervare bilete la evenimente",
         align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
pdf.ln(4)
pdf.set_draw_color(30, 60, 114)
pdf.set_line_width(0.8)
pdf.line(30, pdf.get_y(), 180, pdf.get_y())
pdf.ln(6)
pdf.set_font("Helvetica", "", 10)
pdf.set_text_color(0, 0, 0)
for line in ["Asistent laborator: Alexandru Tudor",
             "Etapa 1 - Arhitectura proiectului",
             "Deadline: 29 martie 2026"]:
    pdf.cell(0, 6, line, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
pdf.ln(10)

# ─────────────────────────────────────────────────────────────────────────
# 1. INFORMATII GENERALE
# ─────────────────────────────────────────────────────────────────────────
pdf.chapter_title("1", "Informatii generale")
pdf.kv("Nume proiect", "EventFlow")
pdf.kv("Tema", "Platforma cloud-native pentru management evenimente, rezervari, plati si validare bilete")
pdf.ln(2)

# ─────────────────────────────────────────────────────────────────────────
# 2. ECHIPA
# ─────────────────────────────────────────────────────────────────────────
pdf.chapter_title("2", "Formarea echipei si alegerea temei")
pdf.section_title("Echipa de proiect")
pdf.kv("Membru 1", "Robert Barbu 343C1")
pdf.kv("Membru 2", "Vlad Grigore 343C1")
pdf.ln(4)

pdf.section_title("Tema aleasa")
pdf.body_text("Tema proiectului este dezvoltarea unei aplicatii de tip microservicii pentru:")
for item in [
    "autentificare si autorizare utilizatori cu Keycloak (OIDC/OAuth2, RBAC)",
    "administrare si listare evenimente (creare, actualizare, disponibilitate)",
    "rezervare bilete, flux de plata cu sesiune temporara si lista de asteptare",
    "validare bilete la intrarea la eveniment (gate scanning)",
    "notificari asincrone dupa confirmarea platii",
]:
    pdf.bullet(item)
pdf.ln(3)

pdf.section_title("Descriere generala")
pdf.body_text(
    "EventFlow este o platforma distribuita pentru rezervarea biletelor la evenimente. "
    "Utilizatorul se autentifica prin auth-service, care integreaza Keycloak, navigheaza "
    "lista de evenimente disponibile, selecteaza un eveniment si cumpara un bilet printr-un "
    "flux de plata cu rezervare temporara de 2 minute. Dupa confirmarea platii, biletul devine "
    "activ si poate fi scanat la intrare de catre personalul evenimentului. Sistemul include "
    "lista de asteptare pentru evenimentele epuizate, rate limiting distribuit pentru protectia "
    "API-ului si caching Redis pentru performanta ridicata."
)
pdf.ln(2)

# ─────────────────────────────────────────────────────────────────────────
# 3. ARHITECTURA
# ─────────────────────────────────────────────────────────────────────────
pdf.chapter_title("3", "Arhitectura tehnica")

pdf.section_title("3.1 Retele Docker Swarm (Overlay Networks)")
pdf.body_text("Stack-ul foloseste patru retele overlay izolate:")
for net, desc in [
    ("edge-network",       "Trafic dintre Kong API Gateway si microserviciile expuse public."),
    ("service-network",    "Trafic intern intre microservicii, data-service, RabbitMQ si Redis."),
    ("db-network",         "Acces la PostgreSQL permis exclusiv pentru data-service si pgAdmin."),
    ("monitoring-network", "Trafic intre Prometheus, Grafana si serviciile monitorizate."),
]:
    pdf.bullet(f"{net}: {desc}")
pdf.ln(3)

pdf.body_text("Clusterul Docker Swarm este format din 3 noduri:")
for item in [
    "1 manager node responsabil pentru orchestrare si managementul clusterului",
    "2 worker nodes pe care ruleaza microserviciile aplicatiei",
]:
    pdf.bullet(item)
pdf.ln(2)

pdf.body_text("Placement constraints:")
for item in [
    "Serviciile aplicatiei (auth-service, data-service, user-profile-service, ticketing-service, "
    "payment-service, gate-service, notification-service) ruleaza pe worker nodes",
    "Componentele de infrastructura (PostgreSQL, pgAdmin, Portainer) ruleaza pe manager node",
]:
    pdf.bullet(item)
pdf.ln(1)
pdf.body_text("Replicile serviciilor sunt distribuite intre worker nodes pentru toleranta la defecte.")
pdf.ln(2)

pdf.section_title("3.2 Microservicii proprii (Python / Flask)")
svcs = [
    ("auth-service", "3003", "2",
     "Autentificare utilizatori prin Keycloak (OIDC). Gestionare login/register, callback, "
     "sesiuni si token-uri JWT."),
    ("data-service", "3002", "2",
     "Serviciu dedicat accesului la date. Expune API CRUD pentru utilizatori, evenimente, "
     "bilete, plati si notificari. Singurul serviciu care comunica direct cu PostgreSQL."),
    ("user-profile-service", "3004", "2",
     "Profil utilizator si gestionare roluri (ADMIN/ORGANIZER/ATTENDEE/STAFF). "
     "Sincronizare automata cu Keycloak la primul acces. CRUD profil, adaugare/stergere roluri."),
    ("ticketing-service", "3005", "2",
     "API business pentru evenimente si bilete: creare/listare evenimente, cumparare bilet, "
     "lista de asteptare (waitlist), scanare, ban utilizatori. "
     "Rate limiting distribuit Redis (Lua scripting) + caching JSON cu TTL 5s."),
    ("payment-service", "3008", "2",
     "Initiere sesiune de plata cu rezervare temporara 2 minute, confirmare/anulare plata, "
     "creare bilet dupa confirmare. Rate limiting Redis. Publica ticket_booked in RabbitMQ."),
    ("gate-service", "3007", "2",
     "Validare bilete la intrarea la eveniment prin cod unic. Previne dubla scanare. "
     "Publica eveniment ticket_scanned in RabbitMQ."),
    ("notification-service", "3006", "2",
     "Consumer RabbitMQ (coada ticket_booked) rulat pe thread background. "
     "Persista notificari prin data-service si le expune prin API REST filtrat dupa rol."),
]
for name, port, rep, desc in svcs:
    pdf.service_entry(name, port, rep, desc)

pdf.ln(2)
pdf.section_title("3.3 Componente suport - infrastructura de date si mesagerie")
for comp, desc in [
    ("Keycloak 25.0",
     "Identity Provider OIDC/OAuth2 cu RBAC, JWT, realm pre-configurat cu roluri si utilizatori de test."),
    ("PostgreSQL 15",
     "Persistenta relationala - baza de date aplicatie (eventflow) + baza de date dedicata Keycloak."),
    ("RabbitMQ 3.13",
     "Broker mesaje asincrone: cozi ticket_booked si ticket_scanned."),
    ("Redis 7",
     "Rate limiting distribuit (ZSET + Lua scripting) si caching JSON (TTL 5s) pentru GET /events."),
]:
    pdf.bullet(f"{comp}: {desc}")
pdf.ln(3)

pdf.section_title("3.4 Componente cloud-native obligatorii")
pdf.body_text("Conform cerintelor proiectului, stack-ul integreaza urmatoarele componente cloud-native:")
cloud = [
    ("Kong API Gateway",
     "Expunere publica controlata a tuturor microserviciilor. Kong ruleaza in fata intregului "
     "cluster si aplica rutare unificata (rute declarate per serviciu), rate limiting la nivel "
     "de gateway, autentificare JWT plugin si logging centralizat. Toate requesturile externe "
     "trec exclusiv prin Kong."),
    ("Portainer",
     "Gestiune vizuala a cluster-ului Docker Swarm: vizualizare servicii, stacks, containere, "
     "volume, retele si logs din browser. Accesat pe portul 9000 (UI) si 9443 (HTTPS)."),
    ("pgAdmin 4",
     "Administrare vizuala a bazelor de date PostgreSQL in mediu de dezvoltare si test. "
     "Permite inspectarea schemei, rularea query-urilor si exportul datelor."),
    ("Prometheus + Grafana",
     "Sistem de monitorizare si observabilitate: Prometheus scrapeaza metricile expuse de "
     "microservicii (endpoint /metrics) la intervale de 15 secunde; Grafana ofera dashboards "
     "vizuale si alerte configurabile pe baza metricilor colectate."),
    ("GitHub Actions CI/CD",
     "Pipeline automat declansat la fiecare push pe branch-ul main: build imagini Docker, "
     "rulare teste pytest, push imagini pe Docker Hub (idp/*), deploy automat in cluster "
     "prin docker stack deploy."),
]
for comp, desc in cloud:
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(30, 60, 114)
    pdf.set_x(LM + 8)
    pdf.cell(5, 6, chr(149), new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.multi_cell(UW - 13, 6, comp)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_x(LM + 18)
    pdf.multi_cell(UW - 18, 5.5, desc)
    pdf.ln(1)
pdf.ln(2)

pdf.section_title("3.5 Flux de comunicare")
pdf.body_text("Serviciile comunica prin DNS intern Docker Swarm (rezolutie prin numele serviciului):")
for f in [
    "Client extern -> Kong:8000 (singurul punct de intrare public, rutare catre microservicii)",
    "Kong -> auth-service (autentificare utilizatori)",
    "auth-service -> Keycloak:8080 (flux OIDC)",
    "user-profile-service -> data-service:3002",
    "ticketing-service -> data-service:3002",
    "payment-service -> data-service:3002",
    "gate-service -> data-service:3002",
    "notification-service -> data-service:3002",
    "data-service -> PostgreSQL:5432 (persistenta date)",
    "ticketing-service / payment-service -> Redis:6379",
    "ticketing-service / payment-service -> RabbitMQ:5672",
    "gate-service -> RabbitMQ:5672",
    "notification-service -> RabbitMQ:5672",
    "Prometheus -> toate microserviciile :*/metrics",
    "Grafana -> Prometheus:9090",
]:
    pdf.bullet(f)
pdf.ln(3)

pdf.section_title("3.6 Flux de plata (Payment Session - 2 minute)")
for i, s in enumerate([
    "POST /payments/start -> creeaza sesiune de plata cu expirare in 2 minute",
    "Frontend afiseaza timer countdown de 2 minute",
    "POST /payments/{id}/confirm -> confirma plata si creeaza biletul daca sesiunea e activa",
    "POST /payments/{id}/cancel -> anuleaza sesiunea explicit",
    "Dupa confirmare -> se publica eveniment ticket_booked in RabbitMQ",
    "notification-service consuma evenimentul si persista notificarea prin data-service",
], 1):
    pdf.set_font("Helvetica", "", 10)
    pdf.set_x(LM + 8)
    pdf.cell(8, 6, f"{i}.", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.multi_cell(UW - 16, 6, s)
pdf.ln(3)

# ─────────────────────────────────────────────────────────────────────────
# DIAGRAMA (pagina separata)
# ─────────────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.set_font("Helvetica", "B", 13)
pdf.set_fill_color(30, 60, 114)
pdf.set_text_color(255, 255, 255)
pdf.cell(0, 9, "Diagrama arhitectura - comunicare inter-servicii", fill=True,
         new_x=XPos.LMARGIN, new_y=YPos.NEXT)
pdf.set_text_color(0, 0, 0)
pdf.ln(3)
DIAG = "/Users/robert/Facultate/SCD/PROIECTV2/Proiect-SCD-V2/architecture_diagram.png"
pdf.set_auto_page_break(False)
pdf.image(DIAG, x=LM, y=pdf.get_y(), w=UW)
pdf.set_auto_page_break(True, margin=18)

# ─────────────────────────────────────────────────────────────────────────
# 4. SCHEMA BD
# ─────────────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.chapter_title("4", "Schema baza de date (PostgreSQL)")
tables = [
    ("users",            "Profiluri utilizatori (keycloak_sub, email, name, timestamps)"),
    ("user_roles",       "Roluri per utilizator (ADMIN, ORGANIZER, ATTENDEE, STAFF)"),
    ("events",           "Evenimente (name, location, starts_at, total_tickets, tickets_sold, created_by)"),
    ("tickets",          "Bilete cumparate (event_id, keycloak_sub, cod unic 32 char, used_at, used_by)"),
    ("banned_users",     "Utilizatori blocati (keycloak_sub, reason)"),
    ("waitlist_entries", "Lista de asteptare (event_id, keycloak_sub, status, pozitie, promoted_ticket_id)"),
    ("payment_sessions", "Sesiuni plata (event_id, keycloak_sub, status, expires_at, ticket_id)"),
    ("notifications",    "Notificari ticket_booked (event_id, organizer_sub, buyer_sub, cod, timestamp)"),
]
pdf.table_header(["Tabel", "Descriere"], [55, 125])
for i, (t, d) in enumerate(tables):
    pdf.table_row([t, d], [55, 125], fill=(i % 2 == 0))
pdf.ln(4)

# ─────────────────────────────────────────────────────────────────────────
# 5. LIMBAJE SI FRAMEWORK-URI
# ─────────────────────────────────────────────────────────────────────────
pdf.chapter_title("5", "Limbaje si framework-uri pe servicii")
headers = ["Serviciu", "Limbaj", "Framework / Biblioteci principale"]
widths = [48, 22, 110]
rows = [
    ("auth-service",         "Python 3.11", "Flask, requests, PyJWT"),
    ("data-service",         "Python 3.11", "Flask, Flask-SQLAlchemy, psycopg2"),
    ("user-profile-service", "Python 3.11", "Flask, Flask-CORS, PyJWT, requests"),
    ("ticketing-service",    "Python 3.11", "Flask, pika, redis, PyJWT, pytest, fakeredis, requests"),
    ("payment-service",      "Python 3.11", "Flask, pika, redis, PyJWT, pytest, fakeredis, requests"),
    ("gate-service",         "Python 3.11", "Flask, pika, PyJWT, requests"),
    ("notification-service", "Python 3.11", "Flask, pika, PyJWT, requests"),
]
pdf.table_header(headers, widths)
for i, row in enumerate(rows):
    pdf.table_row(list(row), widths, fill=(i % 2 == 0))
pdf.ln(4)

pdf.body_text("Tehnologii concrete folosite in platforma:")
for t in [
    "Backend microservicii: Python 3.11 + Flask 3.0",
    "Persistenta relationala: PostgreSQL 15 (Alpine)",
    "Cache + Rate Limiting: Redis 7 (ZSET cu Lua scripting atomic)",
    "Mesagerie asincrona: RabbitMQ 3.13 (cozi durable, consumer pe thread background)",
    "Autentificare/Autorizare: Keycloak 25 (OIDC/OAuth2, JWT, RBAC, 4 roluri)",
    "API Gateway: Kong 3.7 (rutare, rate limiting, JWT plugin, logging)",
    "Gestiune cluster: Portainer CE (UI Docker Swarm)",
    "Administrare DB: pgAdmin 4",
    "Monitorizare: Prometheus + Grafana (scraping metrici, dashboards, alerte)",
    "CI/CD: GitHub Actions (build, test, push Docker Hub, deploy Swarm)",
    "Orchestrare containere: Docker + Docker Swarm (overlay networks, 2 replici per serviciu)",
    "Frontend: Vite + React (SPA)",
    "Testare: pytest + fakeredis (unit tests rate limiter si cache)",
]:
    pdf.bullet(t)
pdf.ln(3)

# ─────────────────────────────────────────────────────────────────────────
# 6. ROLURI
# ─────────────────────────────────────────────────────────────────────────
pdf.chapter_title("6", "Roluri si permisiuni (RBAC Keycloak)")
pdf.table_header(["Rol", "Permisiuni principale"], [35, 145])
for i, (r, p) in enumerate([
    ("ADMIN",     "Acces complet: gestionare utilizatori/roluri, bannare, toate notificarile/biletele"),
    ("ORGANIZER", "Creare/editare evenimente, gestionare waitlist, vizualizare notificari proprii"),
    ("ATTENDEE",  "Cumparare bilete, vizualizare bilete proprii, intrare in lista de asteptare"),
    ("STAFF",     "Scanare si validare bilete la intrarea la eveniment"),
]):
    pdf.table_row([r, p], [35, 145], fill=(i % 2 == 0))
pdf.ln(4)

pdf.section_title("Utilizatori de test pre-configurati in Keycloak")
pdf.table_header(["Username", "Parola", "Rol"], [50, 50, 80])
for i, (u, pw, r) in enumerate([
    ("admin1",     "password123", "ADMIN"),
    ("organizer1", "password123", "ORGANIZER"),
    ("attendee1",  "password123", "ATTENDEE"),
    ("staff1",     "password123", "STAFF"),
]):
    pdf.table_row([u, pw, r], [50, 50, 80], fill=(i % 2 == 0))
pdf.ln(4)

# ─────────────────────────────────────────────────────────────────────────
# 7. TASK-URI
# ─────────────────────────────────────────────────────────────────────────
pdf.chapter_title("7", "Impartirea task-urilor in echipa")

pdf.section_title("Robert Barbu")
for t in [
    "Arhitectura infrastructura Docker Swarm (docker-stack.yml, retele overlay, volume, deploy policies)",
    "Configurare Keycloak: realm, clienti OIDC, roluri, utilizatori de test, import automat la start",
    "Implementare user-profile-service (profil utilizator, roluri, sincronizare Keycloak)",
    "Implementare ticketing-service (evenimente, bilete, waitlist, ban, rate limiting Redis, caching)",
    "Implementare payment-service (sesiuni plata 2 min, confirmare, anulare, rate limiting Redis)",
    "Implementare gate-service (scanare bilete, validare cod unic, publicare RabbitMQ)",
    "Implementare notification-service (consumer RabbitMQ background, API notificari filtrat RBAC)",
    "Implementare rate_limiter.py si cache.py (Redis Lua scripting, unit tests pytest + fakeredis)",
    "Scrierea schemei SQL si a scripturilor de setup/build/test (setup.sh, build-images.sh, test-all.sh)",
]:
    pdf.bullet(t)
pdf.ln(3)

pdf.section_title("Vlad Grigore")
for t in [
    "Configurare Kong API Gateway: rute, plugins JWT, rate limiting si logging la nivel de gateway",
    "Configurare Portainer pentru gestiunea vizuala a cluster-ului Docker Swarm",
    "Configurare pgAdmin 4 si conectare la bazele de date PostgreSQL din cluster",
    "Configurare Prometheus: scraping configuratie, targets pentru fiecare microserviciu",
    "Configurare Grafana: dashboards pentru latenta, throughput si starea serviciilor",
    "Implementare pipeline GitHub Actions CI/CD: build, test, push imagini Docker Hub (idp/*)",
    "Documentatie tehnica a proiectului si diagrama de arhitectura",
    "Testare integrare end-to-end a fluxului complet (autentificare, rezervare, plata, scanare)",
]:
    pdf.bullet(t)
pdf.ln(4)

# ─────────────────────────────────────────────────────────────────────────
# 8. DOCKERHUB + GITHUB
# ─────────────────────────────────────────────────────────────────────────
pdf.chapter_title("8", "DockerHub + GitHub - cont si repository-uri")

pdf.body_text("Implementarea componentelor aplicatiei va fi realizata in repository-ul GitHub:")
pdf.set_font("Helvetica", "", 10)
pdf.set_text_color(30, 60, 200)
pdf.cell(0, 6, "https://github.com/v-grigore/Proiect-IDP",
         new_x=XPos.LMARGIN, new_y=YPos.NEXT)
pdf.set_text_color(0, 0, 0)
pdf.ln(2)
pdf.body_text("Pentru etapa de containerizare si deployment, imaginile Docker aferente "
              "microserviciilor vor fi publicate in contul Docker Hub al echipei:")
pdf.set_text_color(30, 60, 200)
pdf.cell(0, 6, "https://hub.docker.com/u/vladgrigore",
         new_x=XPos.LMARGIN, new_y=YPos.NEXT)
pdf.set_text_color(0, 0, 0)
pdf.ln(3)

pdf.section_title("Repository-uri imagini aplicative (custom)")
headers = ["Serviciu", "Repository Docker Hub", "Port"]
widths = [45, 115, 20]
images = [
    ("auth-service",         "https://hub.docker.com/r/vladgrigore/auth-service",         "3003"),
    ("data-service",         "https://hub.docker.com/r/vladgrigore/data-service",         "3002"),
    ("user-profile-service", "https://hub.docker.com/r/vladgrigore/user-profile-service", "3004"),
    ("ticketing-service",    "https://hub.docker.com/r/vladgrigore/ticketing-service",    "3005"),
    ("notification-service", "https://hub.docker.com/r/vladgrigore/notification-service", "3006"),
    ("gate-service",         "https://hub.docker.com/r/vladgrigore/gate-service",         "3007"),
    ("payment-service",      "https://hub.docker.com/r/vladgrigore/payment-service",      "3008"),
]
pdf.table_header(headers, widths)
for i, row in enumerate(images):
    pdf.table_row(list(row), widths, fill=(i % 2 == 0))
pdf.ln(4)

pdf.section_title("Componente suport (imagini publice Docker Hub / Quay.io)")
pub = [
    ("postgres:15-alpine",                 "Baza de date relationala"),
    ("quay.io/keycloak/keycloak:25.0.0",   "Identity Provider OIDC/OAuth2"),
    ("rabbitmq:3.13-management",           "Message broker"),
    ("redis:7-alpine",                     "Cache si rate limiting"),
    ("kong:3.7",                           "API Gateway"),
    ("portainer/portainer-ce:latest",      "Gestiune cluster Docker Swarm"),
    ("dpage/pgadmin4:latest",              "Administrare PostgreSQL"),
    ("prom/prometheus:latest",             "Colectare metrici"),
    ("grafana/grafana:latest",             "Vizualizare metrici si dashboards"),
]
pdf.table_header(["Imagine", "Rol"], [100, 80])
for i, row in enumerate(pub):
    pdf.table_row(list(row), [100, 80], fill=(i % 2 == 0))
pdf.ln(4)

# ─────────────────────────────────────────────────────────────────────────
# 9. CONCLUZIE
# ─────────────────────────────────────────────────────────────────────────
pdf.chapter_title("9", "Concluzie")
pdf.body_text(
    "EventFlow este o platforma distribuita pentru rezervarea biletelor la evenimente, "
    "construita pe 7 microservicii Python/Flask care separa clar autentificarea, "
    "gestionarea evenimentelor, platile, validarea biletelor si notificarile. "
    "Autentificarea este gestionata printr-un serviciu dedicat (auth-service) care integreaza "
    "Keycloak, iar accesul la baza de date este centralizat prin data-service. "
    "Arhitectura respecta integral cerintele proiectului: microservicii autonome orchestrate "
    "cu Docker Swarm, expunere publica prin Kong API Gateway, gestiune vizuala prin Portainer, "
    "administrare DB prin pgAdmin, monitorizare prin Prometheus+Grafana si pipeline CI/CD "
    "automat prin GitHub Actions. "
    "RabbitMQ asigura comunicarea asincrona, Redis ofera rate limiting distribuit si caching, "
    "iar Keycloak gestioneaza OIDC/RBAC cu 4 roluri distincte. "
    "Fiecare serviciu custom ruleaza cu 2 replici, demonstrand scalabilitatea orizontala "
    "si rezilienta in caz de esec al unui container."
)

OUT = "/Users/robert/Facultate/SCD/PROIECTV2/Proiect-SCD-V2/EventFlow_Etapa1.pdf"
pdf.output(OUT)
print(f"PDF generat: {OUT}")
