-- Supplemental locations never overwrite official store records. Exact identity
-- joins automatically stop using a pin after a store moves or changes identity.
CREATE TABLE IF NOT EXISTS coordinate_resolutions (
  issuer_id TEXT NOT NULL,
  store_id TEXT NOT NULL,
  name TEXT NOT NULL,
  address TEXT NOT NULL,
  phone TEXT NOT NULL DEFAULT '',
  lat REAL,
  lng REAL,
  status TEXT NOT NULL CHECK(status IN ('verified','unresolved','ambiguous','source_unavailable')),
  method TEXT NOT NULL,
  evidence_url TEXT NOT NULL DEFAULT '',
  evidence_json TEXT NOT NULL DEFAULT '[]',
  checked_at TEXT NOT NULL,
  PRIMARY KEY (issuer_id,store_id),
  CHECK(status <> 'verified' OR (lat IS NOT NULL AND lng IS NOT NULL AND lat BETWEEN 20 AND 46 AND lng BETWEEN 122 AND 154))
);
CREATE INDEX IF NOT EXISTS coordinate_resolution_position ON coordinate_resolutions(issuer_id,status,lat,lng);
CREATE TABLE IF NOT EXISTS issuer_catalog_audit (
  issuer_id TEXT PRIMARY KEY,
  catalog_revision INTEGER NOT NULL,
  reference_revision INTEGER NOT NULL,
  official_count INTEGER,
  missing_count INTEGER,
  extra_count INTEGER,
  identity_mismatch_count INTEGER,
  status TEXT NOT NULL CHECK(status IN ('verified','unverified','mismatch','source_unavailable')),
  source_url TEXT NOT NULL DEFAULT '',
  evidence_sha256 TEXT NOT NULL DEFAULT '',
  checked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS location_revision (
  id INTEGER PRIMARY KEY CHECK(id=1),
  revision INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO location_revision(id,revision) VALUES(1,0);
CREATE TRIGGER IF NOT EXISTS locations_insert AFTER INSERT ON coordinate_resolutions BEGIN
 UPDATE location_revision SET revision=revision+1 WHERE id=1;
END;
CREATE TRIGGER IF NOT EXISTS locations_update AFTER UPDATE ON coordinate_resolutions BEGIN
 UPDATE location_revision SET revision=revision+1 WHERE id=1;
END;
CREATE TRIGGER IF NOT EXISTS locations_delete AFTER DELETE ON coordinate_resolutions BEGIN
 UPDATE location_revision SET revision=revision+1 WHERE id=1;
END;
CREATE VIEW IF NOT EXISTS searchable_stores AS
 SELECT issuer_id,store_id,name,address,phone,brand_name,category,lat,lng,official_url,updated_at FROM stores
 UNION ALL
 SELECT r.issuer_id,r.store_id,r.name,r.address,r.phone,r.brand_name,r.category,c.lat,c.lng,r.official_url,r.updated_at
 FROM reference_stores r JOIN coordinate_resolutions c
 ON c.issuer_id=r.issuer_id AND c.store_id=r.store_id
 AND c.name=r.name AND c.address=r.address AND c.phone=r.phone
 WHERE c.status='verified'
 AND NOT EXISTS (SELECT 1 FROM stores s WHERE s.issuer_id=r.issuer_id AND s.store_id=r.store_id);
