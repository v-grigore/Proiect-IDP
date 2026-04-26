import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch

fig, ax = plt.subplots(figsize=(20, 12))
ax.set_xlim(0, 20)
ax.set_ylim(0, 12)
ax.axis("off")
fig.patch.set_facecolor("#F8F9FC")

# ── helpers ───────────────────────────────────────────────────────────────
def box(ax, x, y, w, h, label, sublabel="", color="#1E3C72", text_color="white", fontsize=8):
    rect = FancyBboxPatch((x - w/2, y - h/2), w, h,
                          boxstyle="round,pad=0.05,rounding_size=0.2",
                          linewidth=1.3, edgecolor=color, facecolor=color, zorder=4)
    ax.add_patch(rect)
    if sublabel:
        ax.text(x, y + 0.14, label, ha="center", va="center",
                fontsize=fontsize, fontweight="bold", color=text_color, zorder=5)
        ax.text(x, y - 0.17, sublabel, ha="center", va="center",
                fontsize=6, color=text_color, alpha=0.88, zorder=5)
    else:
        ax.text(x, y, label, ha="center", va="center",
                fontsize=fontsize, fontweight="bold", color=text_color, zorder=5)

def light_box(ax, x, y, w, h, label, sublabel="", color="#E8EEF8", border="#1E3C72",
              text_color="#1E3C72", fontsize=8):
    rect = FancyBboxPatch((x - w/2, y - h/2), w, h,
                          boxstyle="round,pad=0.05,rounding_size=0.2",
                          linewidth=1.5, edgecolor=border, facecolor=color, zorder=4)
    ax.add_patch(rect)
    if sublabel:
        ax.text(x, y + 0.14, label, ha="center", va="center",
                fontsize=fontsize, fontweight="bold", color=text_color, zorder=5)
        ax.text(x, y - 0.17, sublabel, ha="center", va="center",
                fontsize=6, color=text_color, alpha=0.8, zorder=5)
    else:
        ax.text(x, y, label, ha="center", va="center",
                fontsize=fontsize, fontweight="bold", color=text_color, zorder=5)

def arrow(ax, x1, y1, x2, y2, color="#555", lw=1.2, label="",
          loff=(0, 0.2), cs="arc3,rad=0.0", style="->"):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=style, color=color, lw=lw,
                                connectionstyle=cs), zorder=3)
    if label:
        mx, my = (x1+x2)/2 + loff[0], (y1+y2)/2 + loff[1]
        ax.text(mx, my, label, ha="center", va="center", fontsize=5.8, color=color,
                bbox=dict(boxstyle="round,pad=0.12", fc="#F8F9FC", ec="none", alpha=0.9), zorder=6)

def darrow(ax, x1, y1, x2, y2, color="#999", lw=1.0, label="", loff=(0, 0.2)):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="->", color=color, lw=lw,
                                linestyle="dashed", connectionstyle="arc3,rad=0.0"), zorder=3)
    if label:
        mx, my = (x1+x2)/2 + loff[0], (y1+y2)/2 + loff[1]
        ax.text(mx, my, label, ha="center", va="center", fontsize=5.8, color=color,
                bbox=dict(boxstyle="round,pad=0.12", fc="#F8F9FC", ec="none", alpha=0.9), zorder=6)

def zone(ax, x, y, w, h, label, color, alpha=0.07):
    rect = FancyBboxPatch((x, y), w, h,
                          boxstyle="round,pad=0.1,rounding_size=0.35",
                          linewidth=1.2, edgecolor=color,
                          facecolor=color, alpha=alpha, zorder=1)
    ax.add_patch(rect)
    ax.text(x + 0.18, y + h - 0.18, label, fontsize=6.8, color=color,
            fontweight="bold", va="top", zorder=2)

# ── NETWORK ZONES ─────────────────────────────────────────────────────────
# edge-network: Kong + exposed services  (left strip)
zone(ax, 0.15, 3.6, 5.1, 6.0, "edge-network", "#C75B00")
# service-network: microservicii + data-service + RabbitMQ + Redis (center)
zone(ax, 5.5,  2.2, 7.2, 7.4, "service-network", "#1E3C72")
# db-network: PostgreSQL + pgAdmin (right)
zone(ax, 13.0, 4.0, 4.8, 5.2, "db-network", "#2E7D32")
# monitoring-network (bottom)
zone(ax, 0.15, 0.3, 19.7, 1.75, "monitoring-network", "#B45309")

# ── CLIENT ────────────────────────────────────────────────────────────────
light_box(ax, 1.4, 9.8, 1.7, 0.65, "CLIENT", "Browser / App",
          color="#EEF2FF", border="#4B5EAA", text_color="#1E3C72")

# ── KONG ──────────────────────────────────────────────────────────────────
box(ax, 3.5, 9.8, 1.8, 0.65, "KONG", "API Gateway :8000", color="#C75B00")
arrow(ax, 2.25, 9.8, 2.6, 9.8, color="#C75B00", lw=1.6, label="HTTPS")

# ── MICROSERVICES (center column) ─────────────────────────────────────────
# auth-service is on edge-network + service-network
box(ax, 4.6, 8.0, 2.3, 0.62, "auth-service", ":3003  |  2 replici", color="#5C3D99")
# other services in service-network
svcs = [
    (7.5, 9.2,  "user-profile-service", ":3004  |  2 replici", "#1E3C72"),
    (7.5, 7.95, "ticketing-service",    ":3005  |  2 replici", "#1E3C72"),
    (7.5, 6.7,  "payment-service",      ":3008  |  2 replici", "#1E3C72"),
    (7.5, 5.45, "gate-service",         ":3007  |  2 replici", "#1E3C72"),
    (7.5, 4.2,  "notification-service", ":3006  |  2 replici", "#1E3C72"),
]
for (sx, sy, sl, sp, sc) in svcs:
    box(ax, sx, sy, 2.7, 0.62, sl, sp, color=sc)

# ── KONG -> services ──────────────────────────────────────────────────────
# Kong -> auth-service
arrow(ax, 4.4, 9.47, 4.55, 8.31, color="#C75B00", lw=1.1, cs="arc3,rad=0.1")
# Kong -> other services
for (sx, sy, sl, sp, sc) in svcs:
    arrow(ax, 4.4, 9.47, 6.15, sy, color="#C75B00", lw=0.9, cs="arc3,rad=0.0")

# ── KEYCLOAK (edge-network, beside auth) ──────────────────────────────────
box(ax, 4.2, 6.3, 2.2, 0.65, "KEYCLOAK", "OIDC/OAuth2 :8080", color="#6D1FCC")
# auth-service <-> Keycloak (double arrow)
arrow(ax, 4.5, 7.69, 4.3, 6.63, color="#6D1FCC", lw=1.3, label="OIDC flow", loff=(-0.7, 0))

# ── data-service (central DB gateway) ─────────────────────────────────────
box(ax, 10.2, 6.8, 2.5, 0.68, "data-service", ":3002  |  2 replici  |  unic acces DB", color="#0D7377", fontsize=7.5)

# all services -> data-service
for (sx, sy, sl, sp, sc) in svcs:
    arrow(ax, 8.85, sy, 8.95, 6.8, color="#0D7377", lw=1.0,
          cs=f"arc3,rad={0.0 if sy == 6.7 else 0.1 if sy > 6.7 else -0.1}")

# ── RABBITMQ ──────────────────────────────────────────────────────────────
box(ax, 10.2, 8.6, 2.3, 0.65, "RABBITMQ", "broker :5672", color="#E05D00")

# ticketing -> RabbitMQ
arrow(ax, 8.85, 7.95, 9.05, 8.45, color="#E05D00", lw=1.0,
      label="publish ticket_booked", loff=(0.0, 0.25), cs="arc3,rad=0.15")
# payment -> RabbitMQ
arrow(ax, 8.85, 6.7, 9.05, 8.3, color="#E05D00", lw=1.0, cs="arc3,rad=0.2")
# gate -> RabbitMQ
arrow(ax, 8.85, 5.45, 9.05, 8.28, color="#E05D00", lw=1.0,
      label="publish ticket_scanned", loff=(-1.1, 0.0), cs="arc3,rad=0.25")
# RabbitMQ -> notification
arrow(ax, 9.05, 8.28, 8.85, 4.2, color="#E05D00", lw=1.1,
      label="consume ticket_booked", loff=(-1.0, 0.0), cs="arc3,rad=-0.25")

# ── REDIS ─────────────────────────────────────────────────────────────────
box(ax, 10.2, 5.1, 2.3, 0.65, "REDIS", "cache / rate-limit :6379", color="#C62828")
# ticketing + payment -> Redis
arrow(ax, 8.85, 7.95, 9.05, 5.25, color="#C62828", lw=1.0,
      label="rate limit + cache", loff=(0.6, 0.1), cs="arc3,rad=-0.2")
arrow(ax, 8.85, 6.7,  9.05, 5.1,  color="#C62828", lw=1.0, cs="arc3,rad=-0.1")

# ── POSTGRESQL ────────────────────────────────────────────────────────────
box(ax, 15.4, 8.1, 2.3, 0.65, "POSTGRESQL", "eventflow DB :5432", color="#2E7D32")
box(ax, 15.4, 6.7, 2.3, 0.65, "POSTGRESQL", "keycloak DB :5432",  color="#558B2F")

# data-service -> postgres (only connection)
arrow(ax, 11.45, 6.95, 14.25, 8.1, color="#2E7D32", lw=1.5,
      label="unic acces DB", loff=(0.0, 0.28))
# Keycloak -> keycloak DB
darrow(ax, 5.3, 6.3, 14.25, 6.7, color="#558B2F", label="Keycloak DB", loff=(0.0, 0.22))

# ── pgAdmin ───────────────────────────────────────────────────────────────
light_box(ax, 15.4, 5.15, 2.3, 0.62, "pgAdmin 4", "admin DB :5050",
          color="#E8F5E9", border="#2E7D32", text_color="#2E7D32")
darrow(ax, 15.4, 5.46, 15.4, 6.37, color="#2E7D32")
darrow(ax, 15.4, 5.46, 15.4, 7.77, color="#2E7D32")

# ── PORTAINER ─────────────────────────────────────────────────────────────
light_box(ax, 18.2, 9.8, 2.1, 0.65, "PORTAINER", "cluster UI :9000",
          color="#E8EEF8", border="#1E3C72", text_color="#1E3C72")
ax.annotate("", xy=(18.5, 8.0), xytext=(18.2, 9.47),
            arrowprops=dict(arrowstyle="->", color="#1E3C72", lw=0.9, linestyle="dashed"), zorder=3)
ax.text(18.85, 8.75, "manages\nSwarm", fontsize=5.8, color="#1E3C72", ha="center")

# ── PLACEMENT CONSTRAINTS label ───────────────────────────────────────────
ax.text(9.1, 3.45, "worker nodes", fontsize=6, color="#1E3C72",
        ha="center", style="italic",
        bbox=dict(boxstyle="round,pad=0.2", fc="#E8EEF8", ec="#1E3C72", lw=0.8))
ax.text(15.4, 3.7, "manager node", fontsize=6, color="#2E7D32",
        ha="center", style="italic",
        bbox=dict(boxstyle="round,pad=0.2", fc="#E8F5E9", ec="#2E7D32", lw=0.8))

# ── MONITORING (bottom zone) ───────────────────────────────────────────────
box(ax, 4.5,  1.1, 2.0, 0.65, "PROMETHEUS", ":9090", color="#B45309")
box(ax, 7.3,  1.1, 2.0, 0.65, "GRAFANA",    "dashboards :3000", color="#B45309")
arrow(ax, 5.5, 1.1, 6.3, 1.1, color="#B45309", lw=1.2, label="metrici", loff=(0, 0.22))

# scraping arrows from all microservices
for (sx, sy, sl, sp, sc) in svcs:
    darrow(ax, sx, sy - 0.31, sx - 0.5, 1.43, color="#B45309")
darrow(ax, 4.6, 7.69, 4.5, 1.43, color="#B45309")  # auth-service

ax.text(6.2, 2.35, "scraping /metrics (15s)", fontsize=6.2, color="#B45309", ha="center",
        bbox=dict(boxstyle="round,pad=0.2", fc="#FFF8EC", ec="#B45309", lw=0.8))

# CI/CD
light_box(ax, 13.5, 1.1, 2.7, 0.65, "GitHub Actions CI/CD",
          "build > test > push > deploy", color="#F0FFF4", border="#2E7D32", text_color="#1a5c1a")
ax.text(13.5, 2.1, "push to main", fontsize=6, color="#2E7D32", ha="center",
        bbox=dict(boxstyle="round,pad=0.2", fc="#F0FFF4", ec="#2E7D32", lw=0.8))
ax.annotate("", xy=(13.5, 1.43), xytext=(13.5, 1.95),
            arrowprops=dict(arrowstyle="->", color="#2E7D32", lw=1.0), zorder=3)

# ── TITLE ─────────────────────────────────────────────────────────────────
ax.text(10.0, 11.65, "EventFlow - Diagrama Arhitectura",
        ha="center", va="center", fontsize=15, fontweight="bold", color="#1E3C72")
ax.text(10.0, 11.2, "Comunicare inter-servicii, retele si componente cloud-native",
        ha="center", va="center", fontsize=9.5, color="#555")

# ── LEGEND ────────────────────────────────────────────────────────────────
items = [
    ("#C75B00", "Trafic HTTP extern (Kong)"),
    ("#E05D00", "Mesaje asincrone (RabbitMQ)"),
    ("#C62828", "Cache / Rate Limiting (Redis)"),
    ("#6D1FCC", "Flux OIDC (Keycloak)  [---]"),
    ("#2E7D32", "Persistenta (PostgreSQL)"),
    ("#0D7377", "Acces date (data-service)"),
    ("#B45309", "Monitorizare (Prometheus)  [---]"),
]
lx, ly = 0.3, 11.55
ax.text(lx, ly, "Legenda:", fontsize=7.5, fontweight="bold", color="#333")
for i, (c, lbl) in enumerate(items):
    col = i % 4
    row = i // 4
    xi = lx + col * 4.8
    yi = ly - 0.45 - row * 0.4
    ax.plot([xi, xi + 0.45], [yi, yi], color=c, lw=2.2)
    ax.text(xi + 0.6, yi, lbl, fontsize=6.5, color="#333", va="center")

plt.tight_layout(pad=0.2)
plt.savefig("/Users/robert/Facultate/SCD/PROIECTV2/Proiect-SCD-V2/architecture_diagram.png",
            dpi=180, bbox_inches="tight", facecolor="#F8F9FC")
print("Diagrama salvata.")
