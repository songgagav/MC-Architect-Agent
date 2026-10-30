CREATE TABLE knowledge_registry_versions (
    version INTEGER PRIMARY KEY CHECK (version > 0),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    loaded_at TEXT NOT NULL,
    snapshot_json TEXT NOT NULL
);
ALTER TABLE region_profiles ADD COLUMN registry_version INTEGER NOT NULL DEFAULT 3 CHECK (registry_version > 0);
ALTER TABLE knowledge_sources ADD COLUMN registry_version INTEGER NOT NULL DEFAULT 3 CHECK (registry_version > 0);
ALTER TABLE knowledge_rules ADD COLUMN registry_version INTEGER NOT NULL DEFAULT 3 CHECK (registry_version > 0);
CREATE INDEX idx_knowledge_sources_version ON knowledge_sources(registry_version, source_id);
CREATE INDEX idx_knowledge_rules_version_status ON knowledge_rules(registry_version, status, rule_id);
CREATE INDEX idx_region_profiles_version_status ON region_profiles(registry_version, status, region_id);
