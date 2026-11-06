-- Agency operations for creator pilots: deals (revenue share), launched products, sales and cost ledgers, payouts.
-- Products are sold through an EXTERNAL checkout (Stripe, Gumroad, Lemon Squeezy, Shopify…); AudienceOS records
-- and reconciles results, it does not process payments.

CREATE TABLE deals (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  creator_share_pct REAL NOT NULL DEFAULT 70 CHECK (creator_share_pct >= 0 AND creator_share_pct <= 100),
  basis TEXT NOT NULL DEFAULT 'contribution' CHECK (basis IN ('net_sales','contribution')),
  start_date TEXT,
  end_date TEXT,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('draft','active','ended')),
  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE products (
  id TEXT PRIMARY KEY,
  audience_id TEXT NOT NULL REFERENCES audiences(id) ON DELETE CASCADE,
  opportunity_id TEXT REFERENCES opportunities(id) ON DELETE SET NULL,
  experiment_id TEXT REFERENCES experiments(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  product_type TEXT,
  price REAL CHECK (price IS NULL OR price >= 0),
  price_model TEXT NOT NULL DEFAULT 'one-time',
  storefront TEXT,                 -- e.g. 'Gumroad', 'Stripe Payment Link', 'Shopify'
  checkout_url TEXT,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','launched','paused','retired')),
  approval_json TEXT NOT NULL DEFAULT '{}',   -- checklist answers + who/when approved
  approved_at TEXT,
  launched_at TEXT,
  notes TEXT,
  is_demo INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE product_sales (
  id TEXT PRIMARY KEY,
  product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  order_ref TEXT NOT NULL,
  date TEXT,
  amount REAL NOT NULL CHECK (amount >= 0),
  refunded_amount REAL NOT NULL DEFAULT 0 CHECK (refunded_amount >= 0),
  fee REAL CHECK (fee IS NULL OR fee >= 0),
  channel TEXT,                    -- attribution: where the buyer came from, if known
  origin TEXT NOT NULL DEFAULT 'csv',
  created_at TEXT NOT NULL,
  UNIQUE (product_id, order_ref)
);

CREATE TABLE product_costs (
  id TEXT PRIMARY KEY,
  product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  date TEXT,
  category TEXT NOT NULL DEFAULT 'other' CHECK (category IN ('production','ads','tools','fulfillment','contractor','other')),
  amount REAL NOT NULL CHECK (amount >= 0),
  shared INTEGER NOT NULL DEFAULT 1,  -- 1 = deducted before the revenue split (per deal basis)
  note TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE payouts (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  date TEXT NOT NULL,
  amount REAL NOT NULL CHECK (amount >= 0),
  reference TEXT,
  note TEXT,
  created_at TEXT NOT NULL
);

ALTER TABLE organizations ADD COLUMN contact_name TEXT;
ALTER TABLE organizations ADD COLUMN contact_email TEXT;
