-- AudienceOS initial schema. Original evidence (sources, content_items, transcripts, comments)
-- is stored separately from AI interpretations (ai_runs, signals, clusters, opportunities).

CREATE TABLE workspaces (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE organizations (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'creator' CHECK (kind IN ('creator','business','publisher','community','other')),
  description TEXT,
  is_demo INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE audiences (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  niche TEXT,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
  is_demo INTEGER NOT NULL DEFAULT 0,
  last_analyzed_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- A channel = one platform presence (e.g. the creator's YouTube channel). Several per audience.
CREATE TABLE channels (
  id TEXT PRIMARY KEY,
  audience_id TEXT NOT NULL REFERENCES audiences(id) ON DELETE CASCADE,
  platform TEXT NOT NULL,
  handle TEXT,
  url TEXT,
  follower_count INTEGER CHECK (follower_count IS NULL OR follower_count >= 0),
  follower_count_source TEXT,            -- e.g. 'entered by user', 'YouTube Data API'
  created_at TEXT NOT NULL
);

-- A source = one thing that was imported (URL, file, pasted text, feed).
CREATE TABLE sources (
  id TEXT PRIMARY KEY,
  audience_id TEXT NOT NULL REFERENCES audiences(id) ON DELETE CASCADE,
  channel_id TEXT REFERENCES channels(id) ON DELETE SET NULL,
  kind TEXT NOT NULL CHECK (kind IN ('url','file','text','feed')),
  platform TEXT NOT NULL DEFAULT 'other',
  voice TEXT NOT NULL DEFAULT 'creator' CHECK (voice IN ('creator','audience')),  -- whose words these are
  title TEXT,
  original_url TEXT,
  filename TEXT,
  stored_path TEXT,
  mime TEXT,
  size_bytes INTEGER,
  sha256 TEXT,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','ready','partial','failed','unsupported')),
  status_detail TEXT,
  retrieval_method TEXT,
  retrieved_at TEXT,
  obtained_json TEXT NOT NULL DEFAULT '[]',   -- what was actually retrieved
  missing_json TEXT NOT NULL DEFAULT '[]',    -- what could not be retrieved, and why
  alternatives_json TEXT NOT NULL DEFAULT '[]',
  is_demo INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX ux_sources_hash ON sources(audience_id, sha256) WHERE sha256 IS NOT NULL;
CREATE INDEX ix_sources_audience ON sources(audience_id);

CREATE TABLE content_items (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  audience_id TEXT NOT NULL REFERENCES audiences(id) ON DELETE CASCADE,
  platform TEXT NOT NULL DEFAULT 'other',
  kind TEXT NOT NULL DEFAULT 'document',
  title TEXT,
  url TEXT,
  author TEXT,
  published_at TEXT,
  text TEXT NOT NULL DEFAULT '',
  word_count INTEGER NOT NULL DEFAULT 0,
  content_hash TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE INDEX ix_items_audience ON content_items(audience_id);
CREATE UNIQUE INDEX ux_items_hash ON content_items(audience_id, content_hash) WHERE content_hash IS NOT NULL;

CREATE TABLE transcripts (
  id TEXT PRIMARY KEY,
  content_item_id TEXT NOT NULL REFERENCES content_items(id) ON DELETE CASCADE,
  engine TEXT NOT NULL,
  language TEXT,
  text TEXT NOT NULL,
  segments_json TEXT NOT NULL DEFAULT '[]',   -- [{start,end,text}] seconds
  created_at TEXT NOT NULL
);

CREATE TABLE media_frames (
  id TEXT PRIMARY KEY,
  content_item_id TEXT NOT NULL REFERENCES content_items(id) ON DELETE CASCADE,
  timestamp_s REAL NOT NULL,
  path TEXT NOT NULL,
  description TEXT,
  described_by TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE comments (
  id TEXT PRIMARY KEY,
  audience_id TEXT NOT NULL REFERENCES audiences(id) ON DELETE CASCADE,
  source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  content_item_id TEXT REFERENCES content_items(id) ON DELETE SET NULL,
  parent_ref TEXT,
  platform TEXT NOT NULL DEFAULT 'other',
  author_ref TEXT,          -- hashed identifier only; raw handles are not stored
  text TEXT NOT NULL,
  norm_hash TEXT NOT NULL,
  published_at TEXT,
  likes INTEGER CHECK (likes IS NULL OR likes >= 0),
  replies INTEGER CHECK (replies IS NULL OR replies >= 0),
  is_duplicate INTEGER NOT NULL DEFAULT 0,
  duplicate_of TEXT,
  is_spam INTEGER NOT NULL DEFAULT 0,
  spam_reason TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX ix_comments_audience ON comments(audience_id);
CREATE INDEX ix_comments_hash ON comments(audience_id, norm_hash);

CREATE TABLE engagement_metrics (
  id TEXT PRIMARY KEY,
  content_item_id TEXT NOT NULL REFERENCES content_items(id) ON DELETE CASCADE,
  metric TEXT NOT NULL,
  value REAL NOT NULL,
  measured_at TEXT,
  source_note TEXT NOT NULL,
  created_at TEXT NOT NULL
);

-- Verbatim excerpts from original material. AI outputs point here; they never live here.
CREATE TABLE evidence (
  id TEXT PRIMARY KEY,
  audience_id TEXT NOT NULL REFERENCES audiences(id) ON DELETE CASCADE,
  source_id TEXT REFERENCES sources(id) ON DELETE CASCADE,
  content_item_id TEXT REFERENCES content_items(id) ON DELETE CASCADE,
  comment_id TEXT REFERENCES comments(id) ON DELETE CASCADE,
  quote TEXT NOT NULL,
  locator TEXT,             -- e.g. '01:23' timestamp or 'chars 120-260'
  verified INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE INDEX ix_evidence_audience ON evidence(audience_id);

CREATE TABLE ai_runs (
  id TEXT PRIMARY KEY,
  audience_id TEXT REFERENCES audiences(id) ON DELETE CASCADE,
  analysis_id TEXT,
  stage TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT,
  external INTEGER NOT NULL DEFAULT 0,
  input_chars INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','done','failed')),
  error TEXT,
  notes TEXT,
  output_json TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT
);
CREATE INDEX ix_runs_audience ON ai_runs(audience_id);

CREATE TABLE analyses (
  id TEXT PRIMARY KEY,
  audience_id TEXT NOT NULL REFERENCES audiences(id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  model TEXT,
  external INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'running',
  profile_json TEXT,
  stats_json TEXT NOT NULL DEFAULT '{}',
  unknowns_json TEXT NOT NULL DEFAULT '[]',
  started_at TEXT NOT NULL,
  finished_at TEXT
);

CREATE TABLE clusters (
  id TEXT PRIMARY KEY,
  audience_id TEXT NOT NULL REFERENCES audiences(id) ON DELETE CASCADE,
  analysis_id TEXT NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
  label TEXT NOT NULL,
  description TEXT,
  signal_count INTEGER NOT NULL DEFAULT 0,
  unique_authors INTEGER NOT NULL DEFAULT 0,
  source_count INTEGER NOT NULL DEFAULT 0,
  platform_count INTEGER NOT NULL DEFAULT 0,
  median_age_days REAL,
  intent_score REAL NOT NULL DEFAULT 0,
  evidence_quality TEXT,
  intent_breakdown_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE TABLE signals (
  id TEXT PRIMARY KEY,
  audience_id TEXT NOT NULL REFERENCES audiences(id) ON DELETE CASCADE,
  analysis_id TEXT NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
  ai_run_id TEXT REFERENCES ai_runs(id) ON DELETE SET NULL,
  evidence_id TEXT REFERENCES evidence(id) ON DELETE CASCADE,
  cluster_id TEXT REFERENCES clusters(id) ON DELETE SET NULL,
  signal_type TEXT NOT NULL CHECK (signal_type IN ('question','frustration','unmet_need','resource_request','dislikes_existing_solution','repetitive_task','desired_outcome')),
  intent_level TEXT NOT NULL CHECK (intent_level IN ('engagement','curiosity','free_info_request','existing_spending','buying_question','paid_solution_request','verified_purchase')),
  summary TEXT NOT NULL,
  author_ref TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX ix_signals_analysis ON signals(analysis_id);

CREATE TABLE competitors (
  id TEXT PRIMARY KEY,
  audience_id TEXT NOT NULL REFERENCES audiences(id) ON DELETE CASCADE,
  opportunity_id TEXT REFERENCES opportunities(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  url TEXT,
  price_text TEXT,
  prices_found_json TEXT NOT NULL DEFAULT '[]',
  description TEXT,
  provenance TEXT NOT NULL CHECK (provenance IN ('retrieved','entered','ai_suggestion')),
  retrieved_at TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE opportunities (
  id TEXT PRIMARY KEY,
  audience_id TEXT NOT NULL REFERENCES audiences(id) ON DELETE CASCADE,
  analysis_id TEXT REFERENCES analyses(id) ON DELETE SET NULL,
  ai_run_id TEXT REFERENCES ai_runs(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  buyer TEXT,
  problem TEXT,
  product_type TEXT,
  format_rationale TEXT,
  price REAL CHECK (price IS NULL OR price >= 0),
  price_model TEXT DEFAULT 'one-time',
  price_rationale TEXT,
  production TEXT,
  production_cost REAL,
  fulfillment_cost_per_unit REAL,
  delivery_difficulty TEXT,
  recurring TEXT,
  distribution TEXT,
  validation_plan TEXT,
  competition_notes TEXT,
  risks_json TEXT NOT NULL DEFAULT '[]',
  confidence_json TEXT NOT NULL DEFAULT '{}',
  missing_evidence_json TEXT NOT NULL DEFAULT '[]',
  scores_json TEXT NOT NULL DEFAULT '{}',
  total_score REAL,
  cluster_ids_json TEXT NOT NULL DEFAULT '[]',
  scenario_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','approved','testing','validated','rejected')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE opportunity_evidence (
  opportunity_id TEXT NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
  evidence_id TEXT NOT NULL REFERENCES evidence(id) ON DELETE CASCADE,
  PRIMARY KEY (opportunity_id, evidence_id)
);

CREATE TABLE experiments (
  id TEXT PRIMARY KEY,
  audience_id TEXT NOT NULL REFERENCES audiences(id) ON DELETE CASCADE,
  opportunity_id TEXT REFERENCES opportunities(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  hypothesis TEXT,
  target_audience TEXT,
  offer TEXT,
  price REAL CHECK (price IS NULL OR price >= 0),
  channel TEXT,
  target_exposure INTEGER,
  criteria_json TEXT NOT NULL DEFAULT '[]',   -- [{metric, op, value}]
  start_date TEXT,
  end_date TEXT,
  payment_fee_pct REAL NOT NULL DEFAULT 0,
  payment_fee_fixed REAL NOT NULL DEFAULT 0,
  checkout_url TEXT,
  attribution_notes TEXT,
  findings TEXT,
  next_action TEXT,
  decision TEXT CHECK (decision IS NULL OR decision IN ('go','revise','stop')),
  decision_note TEXT,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','running','completed')),
  is_demo INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE experiment_events (
  id TEXT PRIMARY KEY,
  experiment_id TEXT NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
  date TEXT,
  impressions INTEGER CHECK (impressions IS NULL OR impressions >= 0),
  clicks INTEGER CHECK (clicks IS NULL OR clicks >= 0),
  landing_visits INTEGER CHECK (landing_visits IS NULL OR landing_visits >= 0),
  checkout_visits INTEGER CHECK (checkout_visits IS NULL OR checkout_visits >= 0),
  purchases INTEGER CHECK (purchases IS NULL OR purchases >= 0),
  gross_revenue REAL CHECK (gross_revenue IS NULL OR gross_revenue >= 0),
  refunds INTEGER CHECK (refunds IS NULL OR refunds >= 0),
  refund_amount REAL CHECK (refund_amount IS NULL OR refund_amount >= 0),
  payment_fees REAL CHECK (payment_fees IS NULL OR payment_fees >= 0),
  other_costs REAL CHECK (other_costs IS NULL OR other_costs >= 0),
  note TEXT,
  origin TEXT NOT NULL DEFAULT 'manual',
  import_key TEXT,
  created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX ux_events_import ON experiment_events(experiment_id, import_key) WHERE import_key IS NOT NULL;

CREATE TABLE orders (
  id TEXT PRIMARY KEY,
  experiment_id TEXT NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
  order_ref TEXT NOT NULL,
  date TEXT,
  amount REAL NOT NULL CHECK (amount >= 0),
  refunded_amount REAL NOT NULL DEFAULT 0 CHECK (refunded_amount >= 0),
  fee REAL,
  origin TEXT NOT NULL DEFAULT 'csv',
  created_at TEXT NOT NULL,
  UNIQUE (experiment_id, order_ref)
);

CREATE TABLE assets (
  id TEXT PRIMARY KEY,
  audience_id TEXT NOT NULL REFERENCES audiences(id) ON DELETE CASCADE,
  opportunity_id TEXT REFERENCES opportunities(id) ON DELETE CASCADE,
  experiment_id TEXT REFERENCES experiments(id) ON DELETE SET NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  data_json TEXT NOT NULL DEFAULT '{}',
  review_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved')),
  approved_at TEXT,
  ai_run_id TEXT REFERENCES ai_runs(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE reports (
  id TEXT PRIMARY KEY,
  audience_id TEXT NOT NULL REFERENCES audiences(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  files_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE TABLE jobs (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  audience_id TEXT REFERENCES audiences(id) ON DELETE CASCADE,
  ref_id TEXT,
  payload_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','done','failed','cancelled')),
  progress REAL NOT NULL DEFAULT 0,
  message TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 2,
  error TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT
);
CREATE INDEX ix_jobs_status ON jobs(status);

CREATE TABLE activity (
  id TEXT PRIMARY KEY,
  audience_id TEXT REFERENCES audiences(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  message TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE settings (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL
);
