-- Blogger Analytics SaaS - PostgreSQL Schema

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'user',
    plan VARCHAR(50) DEFAULT 'free',
    created_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- User limits by plan
CREATE TABLE IF NOT EXISTS user_limits (
    id SERIAL PRIMARY KEY,
    plan VARCHAR(50) UNIQUE NOT NULL,
    max_bloggers INTEGER DEFAULT 5,
    max_videos_per_day INTEGER DEFAULT 100,
    trend_watch_enabled BOOLEAN DEFAULT FALSE,
    api_rate_limit INTEGER DEFAULT 100
);

INSERT INTO user_limits (plan, max_bloggers, max_videos_per_day, trend_watch_enabled, api_rate_limit) VALUES
('free', 5, 100, FALSE, 100),
('pro', 50, 1000, TRUE, 1000),
('enterprise', -1, -1, TRUE, -1)
ON CONFLICT (plan) DO NOTHING;

-- Bloggers table (multi-tenant)
CREATE TABLE IF NOT EXISTS bloggers (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    youtube_url VARCHAR(500),
    tiktok_url VARCHAR(500),
    instagram_url VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_bloggers_user ON bloggers(user_id);

-- Video history
CREATE TABLE IF NOT EXISTS video_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    blogger_id INTEGER REFERENCES bloggers(id) ON DELETE CASCADE,
    video_url VARCHAR(500) NOT NULL,
    platform VARCHAR(50),
    title TEXT,
    uploader VARCHAR(255),
    upload_date DATE,
    views BIGINT DEFAULT 0,
    likes BIGINT DEFAULT 0,
    comments BIGINT DEFAULT 0,
    shares BIGINT DEFAULT 0,
    engagement_rate REAL DEFAULT 0,
    viral_score REAL DEFAULT 0,
    velocity REAL DEFAULT 0,
    recorded_at TIMESTAMP DEFAULT NOW(),
    hashtags JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_video_user ON video_history(user_id);
CREATE INDEX IF NOT EXISTS idx_video_blogger ON video_history(blogger_id);
CREATE INDEX IF NOT EXISTS idx_video_recorded ON video_history(recorded_at);
CREATE INDEX IF NOT EXISTS idx_video_url ON video_history(video_url);

-- Trend Watch: Videos being monitored
CREATE TABLE IF NOT EXISTS trend_videos (
    id SERIAL PRIMARY KEY,
    video_url VARCHAR(500) UNIQUE NOT NULL,
    platform VARCHAR(50),
    title TEXT,
    uploader VARCHAR(255),
    first_seen TIMESTAMP DEFAULT NOW(),
    last_checked TIMESTAMP,
    initial_views BIGINT DEFAULT 0,
    current_views BIGINT DEFAULT 0,
    velocity REAL DEFAULT 0,
    acceleration REAL DEFAULT 0,
    status VARCHAR(50) DEFAULT 'monitoring',
    hashtags JSONB DEFAULT '[]',
    topics JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_trend_status ON trend_videos(status);
CREATE INDEX IF NOT EXISTS idx_trend_velocity ON trend_videos(velocity DESC);

-- Trend snapshots (hourly metrics)
CREATE TABLE IF NOT EXISTS trend_snapshots (
    id SERIAL PRIMARY KEY,
    video_id INTEGER REFERENCES trend_videos(id) ON DELETE CASCADE,
    views BIGINT DEFAULT 0,
    likes BIGINT DEFAULT 0,
    comments BIGINT DEFAULT 0,
    recorded_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_snapshot_video ON trend_snapshots(video_id);
CREATE INDEX IF NOT EXISTS idx_snapshot_time ON trend_snapshots(recorded_at);

-- Detected trends
CREATE TABLE IF NOT EXISTS detected_trends (
    id SERIAL PRIMARY KEY,
    trend_type VARCHAR(50),
    trend_key VARCHAR(255),
    video_count INTEGER DEFAULT 0,
    avg_velocity REAL DEFAULT 0,
    score REAL DEFAULT 0,
    video_urls JSONB DEFAULT '[]',
    detected_at TIMESTAMP DEFAULT NOW(),
    status VARCHAR(50) DEFAULT 'active'
);

CREATE INDEX IF NOT EXISTS idx_trend_score ON detected_trends(score DESC);
CREATE INDEX IF NOT EXISTS idx_trend_detected ON detected_trends(detected_at);

-- Sessions for auth
CREATE TABLE IF NOT EXISTS sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    token VARCHAR(500) UNIQUE NOT NULL,
    refresh_token VARCHAR(500) UNIQUE,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_session_token ON sessions(token);
CREATE INDEX IF NOT EXISTS idx_session_user ON sessions(user_id);

-- Activity logs (for admin)
CREATE TABLE IF NOT EXISTS activity_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    details JSONB DEFAULT '{}',
    ip_address VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_logs_user ON activity_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_logs_time ON activity_logs(created_at);

-- Create admin user (password: admin123 - CHANGE IN PRODUCTION!)
INSERT INTO users (email, password_hash, name, role, plan) VALUES
('admin@example.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewKyNiAYMyzJ/Iwe', 'Admin', 'admin', 'enterprise')
ON CONFLICT (email) DO NOTHING;

-- Functions

-- Update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for bloggers
DROP TRIGGER IF EXISTS bloggers_updated_at ON bloggers;
CREATE TRIGGER bloggers_updated_at
    BEFORE UPDATE ON bloggers
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();
