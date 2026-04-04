-- Sarkari Naukri Alert Bot - Database Schema
-- Run this in Supabase SQL Editor

-- ============================================
-- ENUM TYPES
-- ============================================

CREATE TYPE qualification_level AS ENUM (
    '8th', '10th', '12th', 'ITI', 'Diploma', 'Graduate', 'Postgraduate'
);

CREATE TYPE category_type AS ENUM (
    'General', 'OBC', 'SC', 'ST', 'EWS'
);

CREATE TYPE gender_type AS ENUM (
    'Male', 'Female', 'Other'
);

CREATE TYPE exam_category AS ENUM (
    'Railway', 'SSC', 'Banking', 'Defence', 'Teaching', 'State_PSC', 'UPSC', 'Police'
);

CREATE TYPE language_pref AS ENUM (
    'Hindi', 'English', 'Both'
);

CREATE TYPE subscription_tier AS ENUM (
    'free_trial', 'basic', 'pro', 'premium'
);

CREATE TYPE onboarding_step AS ENUM (
    'started', 'name', 'dob', 'qualification', 'stream', 'state',
    'category', 'gender', 'pwd', 'ex_serviceman', 'exam_prefs', 'language', 'completed'
);

CREATE TYPE alert_status AS ENUM (
    'pending', 'sent', 'failed', 'skipped'
);

CREATE TYPE notification_type AS ENUM (
    'new_recruitment', 'admit_card', 'result', 'exam_date_change',
    'deadline_reminder', 'answer_key', 'document_verification'
);

-- ============================================
-- TABLES
-- ============================================

-- User profiles collected during WhatsApp onboarding
CREATE TABLE user_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone VARCHAR(15) UNIQUE NOT NULL,
    name VARCHAR(100),
    date_of_birth DATE,
    age_years INTEGER,
    qualification qualification_level,
    qualification_stream VARCHAR(50),  -- Arts/Commerce/Science/Engineering/Medical/Law
    state_domicile VARCHAR(50),
    category category_type,
    gender gender_type,
    pwd_status BOOLEAN DEFAULT FALSE,
    ex_serviceman BOOLEAN DEFAULT FALSE,
    exam_preferences exam_category[] DEFAULT '{}',
    state_psc_states VARCHAR(50)[] DEFAULT '{}',  -- specific states for State PSC
    language_preference language_pref DEFAULT 'Hindi',
    subscription_tier subscription_tier DEFAULT 'free_trial',
    subscription_expires_at TIMESTAMPTZ,
    onboarding_step onboarding_step DEFAULT 'started',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Government job notifications scraped from official sources
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Identity & dedup
    source_url VARCHAR(500),
    pdf_url VARCHAR(500),
    dedup_hash VARCHAR(64) UNIQUE NOT NULL,  -- hash of recruiting_body + post_name + source_url

    -- Core info
    recruiting_body VARCHAR(100) NOT NULL,   -- SSC, UPSC, IBPS, RRB, NTA, etc.
    post_name VARCHAR(300) NOT NULL,
    exam_category exam_category NOT NULL,
    notification_type notification_type DEFAULT 'new_recruitment',

    -- Eligibility criteria (extracted by LLM)
    min_qualification qualification_level,
    qualification_stream VARCHAR(50),
    min_age INTEGER,
    max_age INTEGER,
    obc_relaxation INTEGER DEFAULT 3,
    sc_st_relaxation INTEGER DEFAULT 5,
    ews_relaxation INTEGER DEFAULT 0,
    pwd_relaxation INTEGER DEFAULT 10,
    ex_serviceman_relaxation INTEGER DEFAULT 5,
    gender_restriction gender_type[],       -- NULL means all genders
    state_restriction VARCHAR(50),          -- NULL means all-India

    -- Important dates
    notification_date DATE,
    application_start_date DATE,
    application_end_date DATE,
    exam_date DATE,
    admit_card_date DATE,

    -- Details
    total_vacancies INTEGER,
    vacancy_breakdown JSONB,  -- {"General": 100, "OBC": 50, "SC": 30, ...}
    application_fee JSONB,    -- {"General": 100, "OBC": 50, "SC_ST": 0}
    official_website VARCHAR(200),
    summary_hindi TEXT,
    summary_english TEXT,
    documents_needed TEXT[],

    -- Metadata
    is_verified BOOLEAN DEFAULT FALSE,
    scraped_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Alert queue: matched notifications to send to users
CREATE TABLE alert_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profiles(id) ON DELETE CASCADE,
    notification_id UUID REFERENCES notifications(id) ON DELETE CASCADE,
    alert_type VARCHAR(30) DEFAULT 'new_alert',  -- new_alert, reminder_7d, reminder_3d, reminder_1d
    status alert_status DEFAULT 'pending',
    scheduled_for TIMESTAMPTZ DEFAULT NOW(),
    sent_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, notification_id, alert_type)
);

-- Scraper run logs for monitoring
CREATE TABLE scraper_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scraper_name VARCHAR(50) NOT NULL,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'running',  -- running, success, failed
    notifications_found INTEGER DEFAULT 0,
    new_notifications INTEGER DEFAULT 0,
    error_message TEXT
);

-- ============================================
-- INDEXES
-- ============================================

CREATE INDEX idx_users_phone ON user_profiles(phone);
CREATE INDEX idx_users_active ON user_profiles(is_active) WHERE is_active = TRUE;
CREATE INDEX idx_users_onboarding ON user_profiles(onboarding_step);
CREATE INDEX idx_notifications_dedup ON notifications(dedup_hash);
CREATE INDEX idx_notifications_category ON notifications(exam_category);
CREATE INDEX idx_notifications_dates ON notifications(application_end_date);
CREATE INDEX idx_notifications_body ON notifications(recruiting_body);
CREATE INDEX idx_alert_queue_pending ON alert_queue(status, scheduled_for) WHERE status = 'pending';
CREATE INDEX idx_alert_queue_user ON alert_queue(user_id);

-- ============================================
-- FUNCTIONS
-- ============================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER users_updated_at BEFORE UPDATE ON user_profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER notifications_updated_at BEFORE UPDATE ON notifications
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Auto-calculate age from DOB
CREATE OR REPLACE FUNCTION calculate_age()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.date_of_birth IS NOT NULL THEN
        NEW.age_years = EXTRACT(YEAR FROM age(NEW.date_of_birth));
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER users_calc_age BEFORE INSERT OR UPDATE OF date_of_birth ON user_profiles
    FOR EACH ROW EXECUTE FUNCTION calculate_age();
