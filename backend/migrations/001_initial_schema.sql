-- ============================================================
-- Salesoorja AI Sales Intelligence - Full Database Schema
-- Migration 001: Initial Schema + Modules 8-17 additions
-- ============================================================

-- Enable pgvector extension for semantic search (Module 13)
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- CORE TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS companies (
    id                      SERIAL PRIMARY KEY,
    name                    VARCHAR(500) NOT NULL,
    city                    VARCHAR(200),
    state                   VARCHAR(200),
    country                 VARCHAR(100) DEFAULT 'India',
    industry                VARCHAR(300),
    search_keyword          VARCHAR(300),
    website                 VARCHAR(500),
    phone                   VARCHAR(100),
    email                   VARCHAR(300),

    -- Scoring
    icp_score               FLOAT DEFAULT 0.0,
    intent_velocity_score   FLOAT DEFAULT 0.0,
    calculated_tier         VARCHAR(100) DEFAULT 'Unscored',
    headcount_bracket       VARCHAR(50),

    -- NABL / Certification
    has_nabl                BOOLEAN DEFAULT FALSE,
    nabl_first_seen         TIMESTAMP,
    predicted_renewal_date  DATE,

    -- Enhanced fields (Modules 8-17)
    buying_window           TEXT DEFAULT 'unknown',
    urgency_reason          TEXT,
    competitor_pain_detected BOOLEAN DEFAULT FALSE,
    review_sentiment_score  FLOAT,
    lookalike_source_id     INT REFERENCES companies(id),
    user_rating             INT,
    negative_icp_flags      TEXT[] DEFAULT '{}',
    export_active           BOOLEAN DEFAULT FALSE,
    google_place_id         VARCHAR(300),

    -- Semantic search embedding (Module 13)
    name_embedding          vector(768),

    -- Timestamps
    created_at              TIMESTAMP DEFAULT NOW(),
    updated_at              TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_companies_name ON companies(name);
CREATE INDEX IF NOT EXISTS idx_companies_city ON companies(city);
CREATE INDEX IF NOT EXISTS idx_companies_state ON companies(state);
CREATE INDEX IF NOT EXISTS idx_companies_tier ON companies(calculated_tier);
CREATE INDEX IF NOT EXISTS idx_companies_icp_score ON companies(icp_score DESC);
CREATE INDEX IF NOT EXISTS idx_companies_buying_window ON companies(buying_window);

-- IVFFlat index for vector similarity search
-- Note: Requires at least 100 rows before creating. Run after data is populated.
-- CREATE INDEX ON companies USING ivfflat (name_embedding vector_cosine_ops) WITH (lists = 100);


CREATE TABLE IF NOT EXISTS persons (
    id                SERIAL PRIMARY KEY,
    company_id        INT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    full_name         VARCHAR(300),
    designation       VARCHAR(300),
    email             VARCHAR(300),
    phone             VARCHAR(100),
    linkedin_url      VARCHAR(500),
    seniority_level   VARCHAR(100),
    department        VARCHAR(200),
    is_decision_maker INT DEFAULT 0,

    created_at        TIMESTAMP DEFAULT NOW(),
    updated_at        TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_persons_company_id ON persons(company_id);


CREATE TABLE IF NOT EXISTS company_website_intel (
    id                        SERIAL PRIMARY KEY,
    company_id                INT NOT NULL UNIQUE REFERENCES companies(id) ON DELETE CASCADE,

    -- Instruments & Equipment
    instruments_found         TEXT[] DEFAULT '{}',
    oem_brands                TEXT[] DEFAULT '{}',

    -- Certifications
    iso_standards             TEXT[] DEFAULT '{}',
    certifications_expiry_hints TEXT,

    -- Website analysis
    expansion_signals         TEXT,
    services_offered          TEXT[] DEFAULT '{}',
    industries_served         TEXT[] DEFAULT '{}',

    -- Reviews & Competitor Intel (Module 8f)
    competitor_mentions       TEXT[] DEFAULT '{}',
    review_pain_phrases       TEXT[] DEFAULT '{}',

    -- Metadata
    last_crawled_at           TIMESTAMP,
    crawl_status              VARCHAR(50) DEFAULT 'pending',

    created_at                TIMESTAMP DEFAULT NOW(),
    updated_at                TIMESTAMP DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS company_intent_signals (
    id              SERIAL PRIMARY KEY,
    company_id      INT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    signal_type     VARCHAR(100) NOT NULL,
    weight_applied  FLOAT DEFAULT 0.0,
    source_url      TEXT,
    source_snippet  TEXT,
    urgency_reason  TEXT,
    opportunity_note TEXT,
    detected_at     TIMESTAMP DEFAULT NOW(),
    expires_at      TIMESTAMP,
    is_active       INT DEFAULT 1,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signals_company_id ON company_intent_signals(company_id);
CREATE INDEX IF NOT EXISTS idx_signals_type ON company_intent_signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_signals_active ON company_intent_signals(is_active);


CREATE TABLE IF NOT EXISTS outreach_drafts (
    id                       SERIAL PRIMARY KEY,
    company_id               INT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,

    -- Core outreach
    email_subject            TEXT,
    email_body               TEXT,
    whatsapp_message         TEXT,

    -- Enhanced (Module 10)
    email_subject_variants   TEXT[] DEFAULT '{}',
    email_ps                 TEXT,
    call_opener              TEXT,
    objection_responses      JSONB,
    free_value_offer_outline TEXT,
    linkedin_connection_note TEXT,
    followup_day3_whatsapp   TEXT,
    followup_day7_email      TEXT,
    followup_day14_breakup   TEXT,

    -- Metadata
    generated_by             VARCHAR(100) DEFAULT 'claude',
    generation_context       JSONB,

    created_at               TIMESTAMP DEFAULT NOW(),
    updated_at               TIMESTAMP DEFAULT NOW()
);


-- ============================================================
-- MODULE 11: PIPELINE CRM TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS pipeline_stages (
    id               SERIAL PRIMARY KEY,
    company_id       INT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    person_id        INT REFERENCES persons(id),

    stage            TEXT DEFAULT 'New',
    -- Stages: New → Contacted → Replied → Meeting Booked →
    --         Proposal Sent → Negotiation → Won → Lost → Nurture

    contact_channel  TEXT,
    next_action      TEXT,
    next_action_date DATE,
    deal_value_est   NUMERIC,
    loss_reason      TEXT,
    notes            TEXT,
    last_touched     TIMESTAMP DEFAULT NOW(),

    created_at       TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_company_id ON pipeline_stages(company_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_stage ON pipeline_stages(stage);
CREATE INDEX IF NOT EXISTS idx_pipeline_next_action_date ON pipeline_stages(next_action_date);


CREATE TABLE IF NOT EXISTS activities (
    id              SERIAL PRIMARY KEY,
    company_id      INT NOT NULL REFERENCES companies(id),
    person_id       INT REFERENCES persons(id),
    pipeline_id     INT REFERENCES pipeline_stages(id),

    activity_type   TEXT NOT NULL,
    -- Types: email_sent, whatsapp_sent, call_made, replied,
    --        meeting_booked, no_answer, linkedin_sent
    outcome         TEXT,
    notes           TEXT,

    occurred_at     TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_activities_company_id ON activities(company_id);
CREATE INDEX IF NOT EXISTS idx_activities_type ON activities(activity_type);


CREATE TABLE IF NOT EXISTS ab_test_results (
    id              SERIAL PRIMARY KEY,
    company_id      INT NOT NULL REFERENCES companies(id),
    subject_variant INT,
    opened          BOOLEAN DEFAULT FALSE,
    replied         BOOLEAN DEFAULT FALSE,
    sent_at         TIMESTAMP DEFAULT NOW()
);


-- ============================================================
-- MODULE 15: ICP LEARNING TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS lead_ratings (
    id            SERIAL PRIMARY KEY,
    company_id    INT NOT NULL REFERENCES companies(id),
    user_rating   INT NOT NULL CHECK (user_rating BETWEEN 1 AND 5),
    rating_reason TEXT,
    rated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lead_ratings_company ON lead_ratings(company_id);
CREATE INDEX IF NOT EXISTS idx_lead_ratings_rating ON lead_ratings(user_rating);


-- ============================================================
-- MODULE 14: LOOKALIKE TRACKING
-- ============================================================

CREATE TABLE IF NOT EXISTS won_customers (
    id              SERIAL PRIMARY KEY,
    company_id      INT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    feature_vector  JSONB,
    won_at          TIMESTAMP DEFAULT NOW()
);


-- ============================================================
-- HELPER: Update trigger for updated_at timestamps
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
   NEW.updated_at = NOW();
   RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_companies_updated_at
    BEFORE UPDATE ON companies
    FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

CREATE TRIGGER update_persons_updated_at
    BEFORE UPDATE ON persons
    FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

CREATE TRIGGER update_website_intel_updated_at
    BEFORE UPDATE ON company_website_intel
    FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

CREATE TRIGGER update_outreach_drafts_updated_at
    BEFORE UPDATE ON outreach_drafts
    FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();
