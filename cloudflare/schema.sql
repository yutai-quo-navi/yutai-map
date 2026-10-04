CREATE TABLE IF NOT EXISTS stores (
  issuer_id TEXT NOT NULL,
  store_id TEXT NOT NULL,
  name TEXT NOT NULL,
  address TEXT NOT NULL DEFAULT '',
  phone TEXT NOT NULL DEFAULT '',
  brand_name TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT 'restaurant',
  lat REAL NOT NULL,
  lng REAL NOT NULL,
  official_url TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL,
  PRIMARY KEY (issuer_id, store_id)
);
CREATE INDEX IF NOT EXISTS idx_stores_geo ON stores(lat, lng);
CREATE INDEX IF NOT EXISTS idx_stores_issuer_geo ON stores(issuer_id, lat, lng);

CREATE TABLE IF NOT EXISTS reference_stores (
  issuer_id TEXT NOT NULL,
  store_id TEXT NOT NULL,
  name TEXT NOT NULL,
  address TEXT NOT NULL DEFAULT '',
  phone TEXT NOT NULL DEFAULT '',
  name_norm TEXT NOT NULL DEFAULT '',
  address_norm TEXT NOT NULL DEFAULT '',
  phone_norm TEXT NOT NULL DEFAULT '',
  brand_name TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT 'restaurant',
  official_url TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL,
  PRIMARY KEY (issuer_id, store_id)
);
CREATE INDEX IF NOT EXISTS idx_reference_stores_issuer ON reference_stores(issuer_id);
CREATE INDEX IF NOT EXISTS idx_reference_stores_phone ON reference_stores(issuer_id, phone_norm);

CREATE TABLE IF NOT EXISTS issuer_search_config (
  issuer_id TEXT PRIMARY KEY,
  aliases_json TEXT NOT NULL DEFAULT '[]',
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS store_raw (
  issuer_id TEXT NOT NULL,
  store_id TEXT NOT NULL,
  raw_json TEXT NOT NULL,
  PRIMARY KEY (issuer_id, store_id)
);

CREATE TABLE IF NOT EXISTS issuer_state (
  issuer_id TEXT PRIMARY KEY,
  current_meta_json TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL
);
