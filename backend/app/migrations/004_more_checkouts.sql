-- requires: foreign_keys_off
-- Allow Shopify and Lemon Squeezy as checkout-sync providers. SQLite can't change a CHECK constraint in place,
-- so the products table is rebuilt (same columns, same data); product_sales/product_costs keep their rows.
CREATE TABLE products_new (
  id TEXT PRIMARY KEY,
  audience_id TEXT NOT NULL REFERENCES audiences(id) ON DELETE CASCADE,
  opportunity_id TEXT REFERENCES opportunities(id) ON DELETE SET NULL,
  experiment_id TEXT REFERENCES experiments(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  product_type TEXT,
  price REAL CHECK (price IS NULL OR price >= 0),
  price_model TEXT NOT NULL DEFAULT 'one-time',
  storefront TEXT,
  checkout_url TEXT,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','launched','paused','retired')),
  approval_json TEXT NOT NULL DEFAULT '{}',
  approved_at TEXT,
  launched_at TEXT,
  notes TEXT,
  is_demo INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  sync_provider TEXT CHECK (sync_provider IS NULL OR sync_provider IN ('stripe','gumroad','shopify','lemonsqueezy')),
  sync_ref TEXT,
  last_synced_at TEXT,
  last_sync_json TEXT
);
INSERT INTO products_new (id, audience_id, opportunity_id, experiment_id, name, product_type, price, price_model, storefront,
  checkout_url, status, approval_json, approved_at, launched_at, notes, is_demo, created_at, updated_at, sync_provider,
  sync_ref, last_synced_at, last_sync_json)
SELECT id, audience_id, opportunity_id, experiment_id, name, product_type, price, price_model, storefront,
  checkout_url, status, approval_json, approved_at, launched_at, notes, is_demo, created_at, updated_at, sync_provider,
  sync_ref, last_synced_at, last_sync_json FROM products;
DROP TABLE products;
ALTER TABLE products_new RENAME TO products;
