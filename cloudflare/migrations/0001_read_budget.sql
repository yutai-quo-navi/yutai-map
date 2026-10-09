CREATE TABLE issuer_stats (
  issuer_id TEXT PRIMARY KEY,
  geo_count INTEGER NOT NULL DEFAULT 0 CHECK(geo_count >= 0),
  reference_count INTEGER NOT NULL DEFAULT 0 CHECK(reference_count >= 0),
  raw_count INTEGER NOT NULL DEFAULT 0 CHECK(raw_count >= 0),
  catalog_revision INTEGER NOT NULL DEFAULT 0,
  reference_revision INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE brand_catalog (
  issuer_id TEXT NOT NULL,
  brand_name TEXT NOT NULL,
  store_count INTEGER NOT NULL CHECK(store_count >= 0),
  PRIMARY KEY(issuer_id, brand_name)
);
INSERT INTO issuer_stats(issuer_id,geo_count,reference_count,raw_count)
SELECT issuer_id,SUM(geo_count),SUM(reference_count),SUM(raw_count) FROM (
  SELECT issuer_id,COUNT(*) AS geo_count,0 AS reference_count,0 AS raw_count FROM stores GROUP BY issuer_id
  UNION ALL SELECT issuer_id,0,COUNT(*),0 FROM reference_stores GROUP BY issuer_id
  UNION ALL SELECT issuer_id,0,0,COUNT(*) FROM store_raw GROUP BY issuer_id
) GROUP BY issuer_id;
INSERT INTO brand_catalog(issuer_id,brand_name,store_count)
SELECT issuer_id,brand_name,COUNT(*) FROM (
  SELECT issuer_id,brand_name FROM stores UNION ALL SELECT issuer_id,brand_name FROM reference_stores
) WHERE brand_name != '' GROUP BY issuer_id,brand_name;
CREATE INDEX idx_stores_issuer_brand_geo ON stores(issuer_id,brand_name,lat,lng);
CREATE INDEX idx_reference_stores_issuer_brand ON reference_stores(issuer_id,brand_name);

CREATE TRIGGER stats_stores_insert AFTER INSERT ON stores BEGIN
INSERT INTO issuer_stats(issuer_id,geo_count,catalog_revision) VALUES(NEW.issuer_id,1,1) ON CONFLICT(issuer_id) DO UPDATE SET geo_count=geo_count+1,catalog_revision=catalog_revision+1;
INSERT INTO brand_catalog(issuer_id,brand_name,store_count) SELECT NEW.issuer_id,NEW.brand_name,1 WHERE NEW.brand_name != '' ON CONFLICT(issuer_id,brand_name) DO UPDATE SET store_count=store_count+1;
END;
CREATE TRIGGER stats_stores_delete AFTER DELETE ON stores BEGIN
UPDATE issuer_stats SET geo_count=geo_count-1,catalog_revision=catalog_revision+1 WHERE issuer_id=OLD.issuer_id;
UPDATE brand_catalog SET store_count=store_count-1 WHERE issuer_id=OLD.issuer_id AND brand_name=OLD.brand_name AND OLD.brand_name != '';
END;
CREATE TRIGGER stats_stores_move AFTER UPDATE OF issuer_id ON stores WHEN OLD.issuer_id != NEW.issuer_id BEGIN
UPDATE issuer_stats SET geo_count=geo_count-1,catalog_revision=catalog_revision+1 WHERE issuer_id=OLD.issuer_id;
INSERT INTO issuer_stats(issuer_id,geo_count,catalog_revision) VALUES(NEW.issuer_id,1,1) ON CONFLICT(issuer_id) DO UPDATE SET geo_count=geo_count+1,catalog_revision=catalog_revision+1;
UPDATE brand_catalog SET store_count=store_count-1 WHERE issuer_id=OLD.issuer_id AND brand_name=OLD.brand_name AND OLD.brand_name != '';
INSERT INTO brand_catalog(issuer_id,brand_name,store_count) SELECT NEW.issuer_id,NEW.brand_name,1 WHERE NEW.brand_name != '' ON CONFLICT(issuer_id,brand_name) DO UPDATE SET store_count=store_count+1;
END;
CREATE TRIGGER catalog_stores_brand AFTER UPDATE OF brand_name ON stores
WHEN OLD.issuer_id = NEW.issuer_id AND OLD.brand_name != NEW.brand_name BEGIN
UPDATE brand_catalog SET store_count=store_count-1 WHERE issuer_id=OLD.issuer_id AND brand_name=OLD.brand_name AND OLD.brand_name != '';
INSERT INTO brand_catalog(issuer_id,brand_name,store_count) SELECT NEW.issuer_id,NEW.brand_name,1 WHERE NEW.brand_name != '' ON CONFLICT(issuer_id,brand_name) DO UPDATE SET store_count=store_count+1;
UPDATE issuer_stats SET catalog_revision=catalog_revision+1 WHERE issuer_id=NEW.issuer_id;
END;
CREATE TRIGGER stats_reference_stores_insert AFTER INSERT ON reference_stores BEGIN
INSERT INTO issuer_stats(issuer_id,reference_count,catalog_revision,reference_revision) VALUES(NEW.issuer_id,1,1,1) ON CONFLICT(issuer_id) DO UPDATE SET reference_count=reference_count+1,catalog_revision=catalog_revision+1,reference_revision=reference_revision+1;
INSERT INTO brand_catalog(issuer_id,brand_name,store_count) SELECT NEW.issuer_id,NEW.brand_name,1 WHERE NEW.brand_name != '' ON CONFLICT(issuer_id,brand_name) DO UPDATE SET store_count=store_count+1;
END;
CREATE TRIGGER stats_reference_stores_delete AFTER DELETE ON reference_stores BEGIN
UPDATE issuer_stats SET reference_count=reference_count-1,catalog_revision=catalog_revision+1,reference_revision=reference_revision+1 WHERE issuer_id=OLD.issuer_id;
UPDATE brand_catalog SET store_count=store_count-1 WHERE issuer_id=OLD.issuer_id AND brand_name=OLD.brand_name AND OLD.brand_name != '';
END;
CREATE TRIGGER stats_reference_stores_move AFTER UPDATE OF issuer_id ON reference_stores WHEN OLD.issuer_id != NEW.issuer_id BEGIN
UPDATE issuer_stats SET reference_count=reference_count-1,catalog_revision=catalog_revision+1,reference_revision=reference_revision+1 WHERE issuer_id=OLD.issuer_id;
INSERT INTO issuer_stats(issuer_id,reference_count,catalog_revision,reference_revision) VALUES(NEW.issuer_id,1,1,1) ON CONFLICT(issuer_id) DO UPDATE SET reference_count=reference_count+1,catalog_revision=catalog_revision+1,reference_revision=reference_revision+1;
UPDATE brand_catalog SET store_count=store_count-1 WHERE issuer_id=OLD.issuer_id AND brand_name=OLD.brand_name AND OLD.brand_name != '';
INSERT INTO brand_catalog(issuer_id,brand_name,store_count) SELECT NEW.issuer_id,NEW.brand_name,1 WHERE NEW.brand_name != '' ON CONFLICT(issuer_id,brand_name) DO UPDATE SET store_count=store_count+1;
END;
CREATE TRIGGER catalog_reference_stores_brand AFTER UPDATE OF brand_name ON reference_stores
WHEN OLD.issuer_id = NEW.issuer_id AND OLD.brand_name != NEW.brand_name BEGIN
UPDATE brand_catalog SET store_count=store_count-1 WHERE issuer_id=OLD.issuer_id AND brand_name=OLD.brand_name AND OLD.brand_name != '';
INSERT INTO brand_catalog(issuer_id,brand_name,store_count) SELECT NEW.issuer_id,NEW.brand_name,1 WHERE NEW.brand_name != '' ON CONFLICT(issuer_id,brand_name) DO UPDATE SET store_count=store_count+1;
UPDATE issuer_stats SET catalog_revision=catalog_revision+1 WHERE issuer_id=NEW.issuer_id;
END;
CREATE TRIGGER stats_reference_stores_update AFTER UPDATE ON reference_stores
WHEN OLD.issuer_id = NEW.issuer_id BEGIN
UPDATE issuer_stats SET reference_revision=reference_revision+1 WHERE issuer_id=NEW.issuer_id;
END;
CREATE TRIGGER stats_store_raw_insert AFTER INSERT ON store_raw BEGIN
INSERT INTO issuer_stats(issuer_id,raw_count) VALUES(NEW.issuer_id,1) ON CONFLICT(issuer_id) DO UPDATE SET raw_count=raw_count+1;

END;
CREATE TRIGGER stats_store_raw_delete AFTER DELETE ON store_raw BEGIN
UPDATE issuer_stats SET raw_count=raw_count-1 WHERE issuer_id=OLD.issuer_id;

END;
CREATE TRIGGER stats_store_raw_move AFTER UPDATE OF issuer_id ON store_raw WHEN OLD.issuer_id != NEW.issuer_id BEGIN
UPDATE issuer_stats SET raw_count=raw_count-1 WHERE issuer_id=OLD.issuer_id;
INSERT INTO issuer_stats(issuer_id,raw_count) VALUES(NEW.issuer_id,1) ON CONFLICT(issuer_id) DO UPDATE SET raw_count=raw_count+1;


END;
