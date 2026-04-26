-- EventFlow Database Schema - complet

-- Users table (synced with Keycloak)
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    keycloak_sub VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) NOT NULL,
    name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User roles (mapped from Keycloak)
CREATE TABLE IF NOT EXISTS user_roles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, role)
);

-- Events
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    location VARCHAR(255),
    starts_at TIMESTAMP NOT NULL,
    total_tickets INTEGER NOT NULL,
    tickets_sold INTEGER NOT NULL DEFAULT 0,
    created_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tickets
CREATE TABLE IF NOT EXISTS tickets (
    id SERIAL PRIMARY KEY,
    event_id INTEGER REFERENCES events(id) ON DELETE CASCADE NOT NULL,
    keycloak_sub VARCHAR(255) NOT NULL,
    code VARCHAR(32) NOT NULL,
    purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    used_at TIMESTAMP,
    used_by VARCHAR(255)
);

-- Waitlist entries
CREATE TABLE IF NOT EXISTS waitlist_entries (
    id SERIAL PRIMARY KEY,
    event_id INTEGER REFERENCES events(id) ON DELETE CASCADE NOT NULL,
    keycloak_sub VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    position INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    promoted_ticket_id INTEGER
);

-- Banned users
CREATE TABLE IF NOT EXISTS banned_users (
    id SERIAL PRIMARY KEY,
    keycloak_sub VARCHAR(255) UNIQUE NOT NULL,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Payment sessions
CREATE TABLE IF NOT EXISTS payment_sessions (
    id SERIAL PRIMARY KEY,
    event_id INTEGER REFERENCES events(id) ON DELETE CASCADE NOT NULL,
    keycloak_sub VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    ticket_id INTEGER
);

-- Notifications (consumate din RabbitMQ de notification-service)
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    event_id INTEGER NOT NULL,
    organizer_sub VARCHAR(255),
    buyer_sub VARCHAR(255) NOT NULL,
    code VARCHAR(32) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_users_keycloak_sub ON users(keycloak_sub);
CREATE INDEX IF NOT EXISTS idx_user_roles_user_id ON user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_roles(role);
CREATE INDEX IF NOT EXISTS idx_events_starts_at ON events(starts_at);
CREATE INDEX IF NOT EXISTS idx_tickets_event_id ON tickets(event_id);
CREATE INDEX IF NOT EXISTS idx_tickets_keycloak_sub ON tickets(keycloak_sub);
CREATE INDEX IF NOT EXISTS idx_tickets_code ON tickets(code);
CREATE INDEX IF NOT EXISTS idx_waitlist_event_id ON waitlist_entries(event_id);
CREATE INDEX IF NOT EXISTS idx_payment_sessions_event_id ON payment_sessions(event_id);
CREATE INDEX IF NOT EXISTS idx_notifications_organizer_sub ON notifications(organizer_sub);
CREATE INDEX IF NOT EXISTS idx_notifications_buyer_sub ON notifications(buyer_sub);
