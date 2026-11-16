-- requires: foreign_keys_off
-- Re-processing a source replaces its comments and content items. Evidence used to cascade-delete with them,
-- which silently stripped every quote (and the signals and opportunity links built on it) from finished
-- analyses. Evidence keeps its verbatim quote, so it now survives: the pointer is cleared, then re-linked
-- to the re-imported row by the ingest job when the same text is still there.
CREATE TABLE evidence_new (
  id TEXT PRIMARY KEY,
  audience_id TEXT NOT NULL REFERENCES audiences(id) ON DELETE CASCADE,
  source_id TEXT REFERENCES sources(id) ON DELETE CASCADE,
  content_item_id TEXT REFERENCES content_items(id) ON DELETE SET NULL,
  comment_id TEXT REFERENCES comments(id) ON DELETE SET NULL,
  quote TEXT NOT NULL,
  locator TEXT,
  verified INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
INSERT INTO evidence_new (id, audience_id, source_id, content_item_id, comment_id, quote, locator, verified, created_at)
  SELECT id, audience_id, source_id, content_item_id, comment_id, quote, locator, verified, created_at FROM evidence;
DROP TABLE evidence;
ALTER TABLE evidence_new RENAME TO evidence;
CREATE INDEX ix_evidence_audience ON evidence(audience_id);
