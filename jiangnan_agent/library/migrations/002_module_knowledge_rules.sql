CREATE TABLE module_knowledge_rules (
    asset_id TEXT NOT NULL,
    asset_version INTEGER NOT NULL,
    rule_id TEXT NOT NULL REFERENCES knowledge_rules(rule_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    PRIMARY KEY (asset_id, asset_version, rule_id),
    FOREIGN KEY (asset_id, asset_version)
        REFERENCES module_assets(asset_id, version) ON UPDATE CASCADE ON DELETE CASCADE
);
CREATE INDEX idx_module_knowledge_rules_rule ON module_knowledge_rules(rule_id, asset_id, asset_version);
