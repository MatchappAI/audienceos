-- Post-pilot money features: deal options, direct checkout sync.

-- Loss carry-forward: when on, losses on one product (or an earlier period) offset later profits before the
-- creator's share is computed (deal-wide, cumulative). When off (default) each product's split base is floored at 0.
ALTER TABLE deals ADD COLUMN loss_carry_forward INTEGER NOT NULL DEFAULT 0;
-- Minimum guarantee: a recoupable monthly minimum paid to the creator from the deal start date
-- (entitlement to date = max(earned share, monthly minimum × months elapsed, capped at guarantee_months)).
ALTER TABLE deals ADD COLUMN min_guarantee_monthly REAL CHECK (min_guarantee_monthly IS NULL OR min_guarantee_monthly >= 0);
ALTER TABLE deals ADD COLUMN guarantee_months INTEGER CHECK (guarantee_months IS NULL OR guarantee_months > 0);

-- Direct checkout sync (read-only): which provider and which product/payment-link ID to pull orders for.
ALTER TABLE products ADD COLUMN sync_provider TEXT CHECK (sync_provider IS NULL OR sync_provider IN ('stripe','gumroad'));
ALTER TABLE products ADD COLUMN sync_ref TEXT;
ALTER TABLE products ADD COLUMN last_synced_at TEXT;
ALTER TABLE products ADD COLUMN last_sync_json TEXT;
