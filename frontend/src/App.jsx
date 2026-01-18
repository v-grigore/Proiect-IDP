import React, { useEffect, useState } from 'react';

const API_BASE = 'http://localhost:3005'; // ticketing-service
const GATE_API_BASE = 'http://localhost:3007'; // gate-service pentru scanare
const PAYMENT_API_BASE = 'http://localhost:3008'; // payment-service pentru rezervare + plata
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
      sub: payload.sub,
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

  // Admin helpers
  const [editingEventId, setEditingEventId] = useState(null);
  const [waitlistText, setWaitlistText] = useState('');
  const [waitlistEntries, setWaitlistEntries] = useState([]);
  const [selectedWaitlistEventId, setSelectedWaitlistEventId] = useState(null);
  const [myUserNotificationsText, setMyUserNotificationsText] = useState('');
  const [paymentSession, setPaymentSession] = useState(null);
  const [paymentRemainingSec, setPaymentRemainingSec] = useState(0);

  function parseBackendIsoToMs(isoString) {
    if (!isoString) return Number.NaN;
    const s = String(isoString);
    // If backend sends naive UTC timestamps without timezone (e.g. "2026-01-18T12:34:56.123456"),
    // JS will treat them as local time; force UTC by appending "Z" when no timezone is present.
    const hasTimezone = /([zZ]|[+-]\d{2}:\d{2})$/.test(s);
    return Date.parse(hasTimezone ? s : `${s}Z`);
  }

  useEffect(() => {
    if (!paymentSession || !paymentSession.expires_at) {
      setPaymentRemainingSec(0);
      return;
    }

    const expiresAtMs = parseBackendIsoToMs(paymentSession.expires_at);
    if (Number.isNaN(expiresAtMs)) {
      setPaymentRemainingSec(0);
      return;
    }

    function tick() {
      const diffSec = Math.max(0, Math.ceil((expiresAtMs - Date.now()) / 1000));
      setPaymentRemainingSec(diffSec);
    }

    tick();
    const id = window.setInterval(() => {
      tick();
      const remaining = Math.max(0, Math.ceil((expiresAtMs - Date.now()) / 1000));
      if (remaining <= 0) window.clearInterval(id);
    }, 1000);

    return () => window.clearInterval(id);
  }, [paymentSession]);

  function formatCountdown(totalSeconds) {
    const s = Math.max(0, Number(totalSeconds) || 0);
    const m = Math.floor(s / 60);
    const r = s % 60;
    return `${m}:${String(r).padStart(2, '0')}`;
  }

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
      const isEdit = !!editingEventId;
      const url = isEdit
        ? `${API_BASE}/events/${editingEventId}`
        : `${API_BASE}/events`;
      const method = isEdit ? 'PATCH' : 'POST';

      const res = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      setCreateResult(JSON.stringify(data, null, 2));
      if (res.ok && isEdit) {
        setEditingEventId(null);
      }
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
      const res = await fetch(`${PAYMENT_API_BASE}/payments/start`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ event_id: eventId }),
      });
      const data = await res.json();
      if (!res.ok) {
        alert(`Nu am putut porni sesiunea de plată:\n${data.error || JSON.stringify(data)}`);
        return;
      }
      const session = data.session || data;
      setPaymentSession(session);
      alert(
        `Sesiune de plată creată.\nAi 2 minute să confirmi plata în secțiunea de jos (Sesiune de plată activă).\nSession ID: ${session.id}`
      );
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

  async function loadMyUserNotifications() {
    if (!token) {
      setMyUserNotificationsText('Trebuie să fii logat.');
      return;
    }
    setMyUserNotificationsText('Se încarcă notificările tale...');
    try {
      const res = await fetch('http://localhost:3006/my-notifications', {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      const data = await res.json();
      if (res.ok) {
        setMyUserNotificationsText(JSON.stringify(data, null, 2));
      } else {
        setMyUserNotificationsText(
          `Eroare la încărcarea notificărilor: ${data.error || JSON.stringify(data)}`
        );
      }
    } catch (e) {
      setMyUserNotificationsText(String(e));
    }
  }

  function isMyEvent(ev) {
    return !!(userInfo && userInfo.sub && ev.created_by === userInfo.sub);
  }

  function startEditEvent(ev) {
    setEditingEventId(ev.id);
    setEvName(ev.name || '');
    setEvLocation(ev.location || '');
    setEvStartsAt(ev.starts_at || '');
    setEvTickets(ev.total_tickets ?? 0);
    setEvDescription(ev.description || '');
    setActiveTab('admin');
  }

  async function loadWaitlistForEvent(eventId) {
    if (!token) {
      alert('Trebuie să fii logat ca ORGANIZER / ADMIN.');
      return;
    }
    setSelectedWaitlistEventId(eventId);
    setWaitlistText('Se încarcă lista de așteptare...');
    setWaitlistEntries([]);
    try {
      const res = await fetch(
        `${API_BASE}/admin/events/${eventId}/waitlist`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );
      const data = await res.json();
      if (res.ok) {
        setWaitlistEntries(Array.isArray(data) ? data : []);
        setWaitlistText(JSON.stringify(data, null, 2));
      } else {
        setWaitlistText(
          `Eroare la încărcarea listei de așteptare: ${data.error || JSON.stringify(data)}`
        );
      }
    } catch (e) {
      setWaitlistText(String(e));
    }
  }

  async function promoteFromWaitlist(eventId) {
    if (!token) {
      alert('Trebuie să fii logat ca ORGANIZER / ADMIN.');
      return;
    }
    try {
      const res = await fetch(
        `${API_BASE}/admin/events/${eventId}/waitlist/promote`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );
      const data = await res.json();
      if (res.ok) {
        alert('Am promovat următorul utilizator din waitlist în bilet real.');
        await loadEvents();
        await loadWaitlistForEvent(eventId);
      } else {
        alert(
          `Nu am putut promova utilizatorul din waitlist:\n${data.error || JSON.stringify(data)}`
        );
      }
    } catch (e) {
      alert(String(e));
    }
  }

  async function acceptWaitlistEntry(entryId, eventId) {
    if (!token) {
      alert('Trebuie să fii logat ca ORGANIZER / ADMIN.');
      return;
    }
    try {
      const res = await fetch(
        `${API_BASE}/admin/waitlist/${entryId}/promote`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );
      const data = await res.json();
      if (res.ok) {
        alert(
          'Am acceptat utilizatorul de pe lista de așteptare și i-am emis un bilet. Va primi și notificare în UI-ul de user.'
        );
        await loadEvents();
        await loadWaitlistForEvent(eventId);
      } else {
        alert(
          `Nu am putut accepta acest entry din waitlist:\n${data.error || JSON.stringify(data)}`
        );
      }
    } catch (e) {
      alert(String(e));
    }
  }

  async function joinWaitlist(eventId) {
    if (!token) {
      alert('Trebuie să fii logat în Keycloak ca să intri pe lista de așteptare.');
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/events/${eventId}/waitlist`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });
      const data = await res.json();
      if (res.ok) {
        alert(`Lista de așteptare:\n${data.message || ''}\nPozitie: ${data.entry?.position ?? 'n/a'}`);
      } else {
        alert(`Nu am putut adăuga pe lista de așteptare:\n${data.error || JSON.stringify(data)}`);
      }
    } catch (e) {
      alert(String(e));
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
        {userInfo && (
          <TabButton
            label="Notificările mele"
            active={activeTab === 'my-notifications'}
            onClick={() => {
              setActiveTab('my-notifications');
              loadMyUserNotifications();
            }}
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
            {events.map(ev => {
              const soldOut = ev.remaining_tickets <= 0;
              return (
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
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', alignItems: 'flex-end' }}>
                    <button
                      style={{
                        ...buttonStyle,
                        opacity: soldOut ? 0.5 : 1,
                        cursor: soldOut ? 'not-allowed' : 'pointer',
                      }}
                      onClick={() => !soldOut && buyTicket(ev.id)}
                      disabled={soldOut}
                    >
                      {soldOut ? 'Sold out' : 'Cumpără bilet'}
                    </button>
                    {soldOut && (
                      <button
                        style={secondaryButtonStyle}
                        onClick={() => joinWaitlist(ev.id)}
                      >
                        Intră pe lista de așteptare
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
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
            <div
              style={{
                marginTop: '0.25rem',
                fontSize: '0.8rem',
                color: t.used_at ? '#f97373' : '#4ade80',
              }}
            >
              {t.used_at
                ? `Status: FOLOSIT la ${t.used_at} de către ${t.used_by || 'gate-service'}`
                : 'Status: NEFOLOSIT (valabil)'}
            </div>
          </div>
            ))}
          </div>
          <pre style={preStyle}>{myTicketsText}</pre>
        </div>
      )}

      {activeTab === 'admin' && isOrganizerOrAdmin && (
        <div>
          <div style={cardStyle}>
            <h2>{editingEventId ? 'Editează eveniment' : 'Creează eveniment (ADMIN / ORGANIZER)'}</h2>
            <p style={{ fontSize: '0.85rem', color: '#9ca3af' }}>
              Doar utilizatorii cu rolurile ORGANIZER sau ADMIN pot crea sau modifica evenimente.
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
              {editingEventId ? 'Salvează modificările' : 'Creează eveniment'}
            </button>
            {editingEventId && (
              <button
                style={{ ...secondaryButtonStyle, marginLeft: '0.5rem' }}
                onClick={() => {
                  setEditingEventId(null);
                  setEvName('');
                  setEvLocation('');
                  setEvStartsAt('');
                  setEvTickets(100);
                  setEvDescription('');
                }}
              >
                Renunță la editare
              </button>
            )}
            <pre style={preStyle}>{createResult}</pre>
          </div>

          <div style={cardStyle}>
            <h2>Evenimentele mele</h2>
            <p style={{ fontSize: '0.85rem', color: '#9ca3af' }}>
              Evenimente create de tine (sau toate, dacă ești ADMIN). Poți să le editezi și să gestionezi lista de așteptare.
            </p>
            {events.filter(ev => isMyEvent(ev) || (userInfo && userInfo.roles.includes('ADMIN'))).length === 0 && (
              <p>Încă nu ai creat niciun eveniment.</p>
            )}
            {events
              .filter(ev => isMyEvent(ev) || (userInfo && userInfo.roles.includes('ADMIN')))
              .map(ev => (
                <div key={ev.id} style={eventStyle}>
                  <div>
                    <strong>{ev.name}</strong>
                    <div style={metaStyle}>
                      {ev.location || ''} • {ev.starts_at || ''}
                      <br />
                      Bilete: {ev.tickets_sold} / {ev.total_tickets} (rămase {ev.remaining_tickets})
                    </div>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', alignItems: 'flex-end' }}>
                    <button
                      style={secondaryButtonStyle}
                      onClick={() => startEditEvent(ev)}
                    >
                      Editează
                    </button>
                    <button
                      style={secondaryButtonStyle}
                      onClick={() => loadWaitlistForEvent(ev.id)}
                    >
                      Vezi lista de așteptare
                    </button>
                    <button
                      style={buttonStyle}
                      onClick={() => promoteFromWaitlist(ev.id)}
                    >
                      Promovează următorul din listă
                    </button>
                  </div>
                </div>
              ))}
            {selectedWaitlistEventId && (
              <div style={{ marginTop: '0.75rem' }}>
                <h3 style={{ fontSize: '0.9rem' }}>Lista de așteptare pentru eveniment ID {selectedWaitlistEventId}</h3>
                {waitlistEntries.length === 0 ? (
                  <p style={{ fontSize: '0.85rem', color: '#9ca3af' }}>Nu există intrări în lista de așteptare.</p>
                ) : (
                  <div style={{ marginBottom: '0.5rem' }}>
                    {waitlistEntries.map(entry => (
                      <div key={entry.id} style={ticketCardStyle}>
                        <div style={{ fontSize: '0.8rem', color: '#9ca3af' }}>
                          Pozitie #{entry.position} • user_sub: {entry.keycloak_sub}
                        </div>
                        <button
                          style={{ ...buttonStyle, marginTop: '0.25rem' }}
                          onClick={() => acceptWaitlistEntry(entry.id, selectedWaitlistEventId)}
                        >
                          Acceptă acest user (creează bilet și trimite notificare)
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                <pre style={preStyle}>{waitlistText}</pre>
              </div>
            )}
          </div>
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

      {activeTab === 'my-notifications' && userInfo && (
        <div style={cardStyle}>
          <h2>Notificările mele</h2>
          <p style={{ fontSize: '0.85rem', color: '#9ca3af' }}>
            Aici vezi notificări legate de biletele tale (de exemplu când un organizator te acceptă de pe lista de așteptare).
          </p>
          <button style={secondaryButtonStyle} onClick={loadMyUserNotifications}>
            Reîncarcă notificările mele
          </button>
          <pre style={preStyle}>{myUserNotificationsText}</pre>
        </div>
      )}

      {paymentSession && (
        <div style={cardStyle}>
          <h2>Sesiune de plată activă</h2>
          <p style={{ fontSize: '0.85rem', color: '#9ca3af' }}>
            Ai 2 minute să confirmi plata; după aceea sesiunea expiră și locul nu mai este rezervat.
          </p>
          <p style={{ fontSize: '0.95rem', fontWeight: 600, marginTop: '0.35rem' }}>
            Timp rămas: {formatCountdown(paymentRemainingSec)}
          </p>
          {paymentRemainingSec <= 0 && (
            <p style={{ fontSize: '0.85rem', color: '#fca5a5', marginTop: '0.35rem' }}>
              Sesiunea a expirat. Pornește o nouă sesiune de plată din lista de evenimente.
            </p>
          )}
          <p style={{ fontSize: '0.8rem', color: '#9ca3af' }}>
            Session ID: {paymentSession.id} • Event ID: {paymentSession.event_id}
            <br />
            Creată la: {paymentSession.created_at}
            <br />
            Expiră la: {paymentSession.expires_at}
          </p>
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
            <button
              disabled={paymentRemainingSec <= 0}
              style={
                paymentRemainingSec <= 0
                  ? { ...buttonStyle, opacity: 0.55, cursor: 'not-allowed' }
                  : buttonStyle
              }
              onClick={async () => {
                try {
                  const res = await fetch(
                    `${PAYMENT_API_BASE}/payments/confirm/${paymentSession.id}`,
                    {
                      method: 'POST',
                      headers: {
                        Authorization: `Bearer ${token}`,
                      },
                    }
                  );
                  const data = await res.json();
                  if (res.ok) {
                    alert(
                      `Plată confirmată și bilet emis!\nCod bilet: ${data.ticket?.code}`
                    );
                    setPaymentSession(null);
                    await loadEvents();
                    await loadMyTickets();
                  } else {
                    alert(
                      `Nu am putut confirma plata:\n${data.error || JSON.stringify(data)}`
                    );
                    if (
                      data.error &&
                      data.error.toLowerCase().includes('expired')
                    ) {
                      setPaymentSession(null);
                    }
                  }
                } catch (e) {
                  alert(String(e));
                }
              }}
            >
              Confirmă plata (emite bilet)
            </button>
            <button
              style={secondaryButtonStyle}
              onClick={async () => {
                try {
                  const res = await fetch(
                    `${PAYMENT_API_BASE}/payments/cancel/${paymentSession.id}`,
                    {
                      method: 'POST',
                      headers: {
                        Authorization: `Bearer ${token}`,
                      },
                    }
                  );
                  const data = await res.json();
                  if (res.ok) {
                    alert('Sesiunea de plată a fost anulată.');
                  } else {
                    alert(
                      `Nu am putut anula sesiunea de plată:\n${data.error || JSON.stringify(data)}`
                    );
                  }
                } catch (e) {
                  alert(String(e));
                } finally {
                  setPaymentSession(null);
                }
              }}
            >
              Anulează
            </button>
          </div>
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

