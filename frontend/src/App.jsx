import React, { useEffect, useState } from 'react';

const API_BASE = 'http://localhost:3005'; // ticketing-service
const GATE_API_BASE = 'http://localhost:3007'; // gate-service pentru scanare
const KEYCLOAK_BASE = 'http://localhost:8080/realms/eventflow/protocol/openid-connect';
const FRONTEND_CLIENT_ID = 'eventflow-frontend';

function getStoredToken() {
  return window.localStorage.getItem('eventflow_token') || '';
}

function setStoredToken(token) {
  window.localStorage.setItem('eventflow_token', token || '');
}

function decodeToken(t) {
  try {
    if (!t) return null;
    const parts = t.split('.');
    if (parts.length !== 3) return null;
    const payload = JSON.parse(
      atob(parts[1].replace(/-/g, '+').replace(/_/g, '/'))
    );
    const roles =
      payload.realm_access && Array.isArray(payload.realm_access.roles)
        ? payload.realm_access.roles
        : [];
    return {
      username: payload.preferred_username || payload.email || payload.sub,
      roles,
    };
  } catch {
    return null;
  }
}

export default function App() {
  const [token, setToken] = useState(getStoredToken());
  const [userInfo, setUserInfo] = useState(decodeToken(getStoredToken()));
  const [tokenStatus, setTokenStatus] = useState(
    userInfo
      ? `logat ca ${userInfo.username} [${userInfo.roles.join(', ')}]`
      : 'no token'
  );

  const [events, setEvents] = useState([]);
  const [loadingEvents, setLoadingEvents] = useState(false);
  const [createResult, setCreateResult] = useState('');
  const [myTicketsText, setMyTicketsText] = useState('');
  const [myTicketsList, setMyTicketsList] = useState([]);

  const [evName, setEvName] = useState('');
  const [evLocation, setEvLocation] = useState('');
  const [evStartsAt, setEvStartsAt] = useState('');
  const [evTickets, setEvTickets] = useState(100);
  const [evDescription, setEvDescription] = useState('');

  const [scanCode, setScanCode] = useState('');
  const [scanResult, setScanResult] = useState('');
  const [notifications, setNotifications] = useState('');

  // UI / "pagini"
  const [activeTab, setActiveTab] = useState('events'); // events | my-tickets | admin | scan | notifications | debug

  useEffect(() => {
    // dacă venim din redirect Keycloak, token-ul este în hash (#access_token=...)
    const hash = window.location.hash;
    if (hash && hash.includes('access_token=')) {
      const params = new URLSearchParams(hash.substring(1));
      const t = params.get('access_token');
      if (t) {
        setToken(t);
        setStoredToken(t);
        const info = decodeToken(t);
        setUserInfo(info);
        if (info) {
          setTokenStatus(`logat ca ${info.username} [${info.roles.join(', ')}]`);
        } else {
          setTokenStatus('token invalid / no token');
        }
        // curăță hash-ul din adresă
        window.history.replaceState(
          null,
          '',
          window.location.pathname + window.location.search
        );
      }
    } else {
      const existing = getStoredToken();
      if (existing) {
        const info = decodeToken(existing);
        setToken(existing);
        setUserInfo(info);
        if (info) {
          setTokenStatus(
            `logat ca ${info.username} [${info.roles.join(', ')}]`
          );
        }
      }
    }
    loadEvents();
  }, []);

  function hasRole(role) {
    return !!(
      userInfo &&
      Array.isArray(userInfo.roles) &&
      userInfo.roles.includes(role)
    );
  }

  const isOrganizerOrAdmin = hasRole('ORGANIZER') || hasRole('ADMIN');
  const isStaffOrOrganizerOrAdmin = hasRole('STAFF') || isOrganizerOrAdmin;

  function handleSaveToken() {
    setStoredToken(token);
    const info = decodeToken(token);
    setUserInfo(info);
    if (info) {
      setTokenStatus(`logat ca ${info.username} [${info.roles.join(', ')}]`);
    } else {
      setTokenStatus('token invalid / no token');
    }
  }

  async function loadEvents() {
    setLoadingEvents(true);
    try {
      const res = await fetch(`${API_BASE}/events`);
      const data = await res.json();
      if (Array.isArray(data)) {
        setEvents(data);
      } else {
        setEvents([]);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingEvents(false);
    }
  }

  async function createEvent() {
    setCreateResult('Sending...');
    if (!token) {
      setCreateResult('Trebuie să fii logat ca ADMIN / ORGANIZER în Keycloak.');
      return;
    }
    const body = {
      name: evName,
      location: evLocation,
      starts_at: evStartsAt,
      total_tickets: Number(evTickets || 0),
      description: evDescription,
    };
    try {
      const res = await fetch(`${API_BASE}/events`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      setCreateResult(JSON.stringify(data, null, 2));
      await loadEvents();
    } catch (e) {
      setCreateResult(String(e));
    }
  }

  async function buyTicket(eventId) {
    if (!token) {
      alert('Trebuie să fii logat în Keycloak ca să cumperi bilet.');
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/events/${eventId}/tickets`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      const data = await res.json();
      if (data && data.code) {
        alert(`Ticket cumpărat!\nCod bilet: ${data.code}`);
      } else {
        alert(`Ticket response:\n${JSON.stringify(data, null, 2)}`);
      }
      await loadEvents();
    } catch (e) {
      alert(`Error: ${e}`);
    }
  }

  async function loadMyTickets() {
    if (!token) {
      setMyTicketsText('Trebuie să fii logat în Keycloak.');
      setMyTicketsList([]);
      return;
    }
    setMyTicketsText('Loading...');
    setMyTicketsList([]);
    try {
      const res = await fetch(`${API_BASE}/my-tickets`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      const data = await res.json();
      setMyTicketsText(JSON.stringify(data, null, 2));
      if (Array.isArray(data)) {
        setMyTicketsList(data);
      } else {
        setMyTicketsList([]);
      }
    } catch (e) {
      setMyTicketsText(String(e));
      setMyTicketsList([]);
    }
  }

  function openKeycloak() {
    const params = new URLSearchParams({
      client_id: FRONTEND_CLIENT_ID,
      redirect_uri: window.location.origin + '/',
      response_type: 'token',
      scope: 'openid profile email',
    });
    window.location.href = `${KEYCLOAK_BASE}/auth?${params.toString()}`;
  }

  function logout() {
    setToken('');
    setStoredToken('');
    setUserInfo(null);
    setTokenStatus('no token');
    // logout și din Keycloak (șterge sesiunea de SSO)
    const redirect = window.location.origin + '/';
    const url =
      `${KEYCLOAK_BASE}/logout` +
      `?client_id=${encodeURIComponent(FRONTEND_CLIENT_ID)}` +
      `&post_logout_redirect_uri=${encodeURIComponent(redirect)}`;
    window.location.href = url;
  }

  async function scanTicket() {
    if (!token) {
      setScanResult('Trebuie să fii logat (STAFF / ORGANIZER / ADMIN).');
      return;
    }
    if (!scanCode.trim()) {
      setScanResult('Introdu un cod de bilet.');
      return;
    }
    setScanResult('Se verifică biletul...');
    try {
      const res = await fetch(
        `${GATE_API_BASE}/scan/${encodeURIComponent(scanCode.trim())}`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );
      const data = await res.json();
      if (res.ok && data.valid) {
        setScanResult(
          `VALID ticket for event "${data.ticket.event?.name || data.ticket.event_id}" (code ${data.ticket.code}).`
        );
      } else {
        setScanResult(`INVALID: ${data.error || 'unknown error'}`);
      }
    } catch (e) {
      setScanResult(String(e));
    }
  }

  async function loadNotifications() {
    if (!token) {
      setNotifications('Trebuie să fii logat ca ORGANIZER / ADMIN.');
      return;
    }
    setNotifications('Se încarcă notificările...');
    try {
      const res = await fetch('http://localhost:3006/notifications', {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      const data = await res.json();
      setNotifications(JSON.stringify(data, null, 2));
    } catch (e) {
      setNotifications(String(e));
    }
  }

  return (
    <div
      style={{
        fontFamily: 'system-ui, sans-serif',
        background: '#0f172a',
        minHeight: '100vh',
        color: '#e5e7eb',
        padding: '2rem',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '1.5rem',
        }}
      >
        <div>
          <h1 style={{ color: '#f9fafb', marginBottom: '0.25rem' }}>
            EventFlow – Ticketing
          </h1>
          <div style={{ fontSize: '0.9rem', color: '#9ca3af' }}>
            Platformă demo cu Keycloak SSO, bilete și roluri (ATTENDEE / ORGANIZER / ADMIN).
          </div>
        </div>
        <div>
          <button style={buttonStyle} onClick={openKeycloak}>
            Login / Register cu Keycloak
          </button>
          {userInfo && (
            <button
              style={{ ...secondaryButtonStyle, marginLeft: '0.5rem' }}
              onClick={logout}
            >
              Logout
            </button>
          )}
        </div>
      </div>

      {/* bară de navigare pe "pagini" */}
      <div
        style={{
          display: 'flex',
          gap: '0.5rem',
          marginBottom: '1rem',
          flexWrap: 'wrap',
        }}
      >
        <TabButton
          label="Evenimente"
          active={activeTab === 'events'}
          onClick={() => setActiveTab('events')}
        />
        {userInfo && (
          <TabButton
            label="Biletele mele"
            active={activeTab === 'my-tickets'}
            onClick={() => setActiveTab('my-tickets')}
          />
        )}
        {isOrganizerOrAdmin && (
          <TabButton
            label="Admin / Organizer"
            active={activeTab === 'admin'}
            onClick={() => setActiveTab('admin')}
          />
        )}
        {isStaffOrOrganizerOrAdmin && (
          <TabButton
            label="Scanare bilete"
            active={activeTab === 'scan'}
            onClick={() => setActiveTab('scan')}
          />
        )}
        {isOrganizerOrAdmin && (
          <TabButton
            label="Notificări"
            active={activeTab === 'notifications'}
            onClick={() => {
              setActiveTab('notifications');
              loadNotifications();
            }}
          />
        )}
      </div>

      {/* conținutul paginilor */}
      {activeTab === 'events' && (
        <div style={cardStyle}>
          <h2>Evenimente disponibile</h2>
          <p
            style={{
              fontSize: '0.85rem',
              color: '#9ca3af',
              marginBottom: '0.5rem',
            }}
          >
            Orice utilizator (chiar și neautentificat) poate vedea lista de
            evenimente. Pentru a cumpăra bilete trebuie să fii logat ca ATTENDEE
            / ORGANIZER / ADMIN.
          </p>
          <button
            style={secondaryButtonStyle}
            onClick={loadEvents}
            disabled={loadingEvents}
          >
            {loadingEvents ? 'Se încarcă...' : 'Reîncarcă evenimentele'}
          </button>
          <div style={{ marginTop: '0.75rem' }}>
            {events.length === 0 && !loadingEvents && (
              <p>Nu există evenimente încă.</p>
            )}
            {events.map(ev => (
              <div key={ev.id} style={eventStyle}>
                <div>
                  <strong>{ev.name}</strong>
                  <div style={metaStyle}>
                    {ev.location || ''} • {ev.starts_at || ''}
                    <br />
                    Bilete: {ev.tickets_sold} / {ev.total_tickets} (rămase{' '}
                    {ev.remaining_tickets})
                  </div>
                </div>
                <button style={buttonStyle} onClick={() => buyTicket(ev.id)}>
                  Cumpără bilet
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {activeTab === 'my-tickets' && (
        <div style={cardStyle}>
          <h2>Biletele mele</h2>
          <p style={{ fontSize: '0.85rem', color: '#9ca3af' }}>
            Vezi toate biletele cumpărate cu contul tău Keycloak (ATTENDEE /
            ORGANIZER / ADMIN).
          </p>
          <button style={secondaryButtonStyle} onClick={loadMyTickets}>
            Încarcă biletele mele
          </button>
          <div style={{ marginTop: '0.75rem' }}>
            {myTicketsList.map(t => (
              <div key={t.id} style={ticketCardStyle}>
                <div style={{ fontSize: '0.8rem', color: '#9ca3af' }}>
                  Event: {t.event?.name || t.event_id} •{' '}
                  {t.event?.starts_at || t.purchased_at}
                </div>
                <div
                  style={{
                    fontSize: '1.1rem',
                    fontWeight: 600,
                    letterSpacing: '0.1em',
                  }}
                >
                  {t.code}
                </div>
              </div>
            ))}
          </div>
          <pre style={preStyle}>{myTicketsText}</pre>
        </div>
      )}

      {activeTab === 'admin' && isOrganizerOrAdmin && (
        <div style={cardStyle}>
          <h2>Creează eveniment (ADMIN / ORGANIZER)</h2>
          <p style={{ fontSize: '0.85rem', color: '#9ca3af' }}>
            Doar utilizatorii cu rolurile ORGANIZER sau ADMIN pot crea
            evenimente noi.
          </p>
          <label style={labelStyle}>Nume eveniment</label>
          <input
            style={inputStyle}
            value={evName}
            onChange={e => setEvName(e.target.value)}
          />

          <label style={labelStyle}>Locație</label>
          <input
            style={inputStyle}
            value={evLocation}
            onChange={e => setEvLocation(e.target.value)}
          />

          <label style={labelStyle}>Începe la (ISO 8601)</label>
          <input
            style={inputStyle}
            value={evStartsAt}
            onChange={e => setEvStartsAt(e.target.value)}
            placeholder="2025-12-31T20:00:00"
          />

          <label style={labelStyle}>Număr total de bilete</label>
          <input
            style={inputStyle}
            type="number"
            min={1}
            value={evTickets}
            onChange={e => setEvTickets(e.target.value)}
          />

          <label style={labelStyle}>Descriere</label>
          <textarea
            style={textareaStyle}
            rows={2}
            value={evDescription}
            onChange={e => setEvDescription(e.target.value)}
          />

          <button style={buttonStyle} onClick={createEvent}>
            Creează eveniment
          </button>
          <pre style={preStyle}>{createResult}</pre>
        </div>
      )}

      {activeTab === 'scan' && isStaffOrOrganizerOrAdmin && (
        <div style={cardStyle}>
          <h2>Scanare / validare bilete</h2>
          <p style={{ fontSize: '0.85rem', color: '#9ca3af' }}>
            Pentru rolurile STAFF / ORGANIZER / ADMIN. Introdu codul biletului
            primit de participant și validează-l împotriva serviciului de
            ticketing.
          </p>
          <label style={labelStyle}>Cod bilet</label>
          <input
            style={inputStyle}
            value={scanCode}
            onChange={e => setScanCode(e.target.value)}
            placeholder="ex: TCK-ABC123"
          />
          <button style={buttonStyle} onClick={scanTicket}>
            Validează bilet
          </button>
          <pre style={preStyle}>{scanResult}</pre>
        </div>
      )}

      {activeTab === 'notifications' && isOrganizerOrAdmin && (
        <div style={cardStyle}>
          <h2>Notificări (RabbitMQ)</h2>
          <p style={{ fontSize: '0.85rem', color: '#9ca3af' }}>
            Organizatorii și adminii pot vedea notificări generate de
            cumpărarea biletelor (mesaje consumate din RabbitMQ de
            notification-service).
          </p>
          <button style={secondaryButtonStyle} onClick={loadNotifications}>
            Reîncarcă notificările
          </button>
          <pre style={preStyle}>{notifications}</pre>
        </div>
      )}

      {/* nu mai avem pagină de debug cu lipit token; login doar prin Keycloak */}
    </div>
  );
}

function TabButton({ label, active, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        borderRadius: '999px',
        border: active ? '1px solid #3b82f6' : '1px solid #1f2937',
        background: active ? 'rgba(59,130,246,0.15)' : 'transparent',
        color: '#e5e7eb',
        padding: '0.35rem 0.9rem',
        fontSize: '0.8rem',
        cursor: 'pointer',
      }}
    >
      {label}
    </button>
  );
}

const cardStyle = {
  background: '#020617',
  borderRadius: '0.75rem',
  padding: '1.25rem 1.5rem',
  marginBottom: '1rem',
  border: '1px solid #1f2937',
  boxShadow: '0 10px 25px rgba(15,23,42,0.8)',
};

const labelStyle = {
  fontSize: '0.875rem',
  color: '#9ca3af',
  display: 'block',
  marginBottom: '0.25rem',
};

const inputStyle = {
  width: '100%',
  padding: '0.5rem 0.75rem',
  borderRadius: '0.5rem',
  border: '1px solid #374151',
  background: '#020617',
  color: '#e5e7eb',
  fontSize: '0.875rem',
  marginBottom: '0.75rem',
};

const textareaStyle = {
  ...inputStyle,
  minHeight: '3rem',
};

const buttonStyle = {
  border: 'none',
  borderRadius: '999px',
  padding: '0.45rem 0.9rem',
  fontSize: '0.85rem',
  cursor: 'pointer',
  background: '#3b82f6',
  color: 'white',
};

const secondaryButtonStyle = {
  ...buttonStyle,
  background: '#111827',
  color: '#e5e7eb',
  border: '1px solid #374151',
};

const badgeStyle = {
  fontSize: '0.7rem',
  padding: '0.1rem 0.45rem',
  borderRadius: '999px',
  border: '1px solid #4b5563',
  color: '#9ca3af',
  marginLeft: '0.5rem',
};

const eventStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: '0.75rem',
  marginBottom: '0.5rem',
};

const metaStyle = {
  fontSize: '0.8rem',
  color: '#9ca3af',
};

const preStyle = {
  fontSize: '0.8rem',
  background: '#020617',
  padding: '0.75rem',
  borderRadius: '0.5rem',
  overflowX: 'auto',
  border: '1px solid #1f2937',
  marginTop: '0.75rem',
};

const ticketCardStyle = {
  borderRadius: '0.5rem',
  border: '1px dashed #4b5563',
  padding: '0.5rem 0.75rem',
  marginBottom: '0.5rem',
  background: '#020617',
};

