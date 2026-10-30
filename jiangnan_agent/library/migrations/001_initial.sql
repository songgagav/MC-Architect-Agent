CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY CHECK (version > 0),
    applied_at TEXT NOT NULL
);

CREATE TABLE library_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE region_profiles (
    region_id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'catalog_only')),
    scope TEXT NOT NULL,
    notes TEXT NOT NULL,
    record_json TEXT NOT NULL
);

CREATE TABLE knowledge_sources (
    source_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    title TEXT NOT NULL,
    publisher_or_author TEXT NOT NULL,
    publication_date TEXT,
    date_note TEXT NOT NULL,
    url TEXT,
    doi TEXT,
    isbn TEXT,
    section_or_page TEXT NOT NULL,
    verification_level TEXT NOT NULL,
    accessed_date TEXT NOT NULL,
    record_json TEXT NOT NULL
);

CREATE TABLE knowledge_rules (
    rule_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES knowledge_sources(source_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    evidence_kind TEXT NOT NULL,
    confidence TEXT NOT NULL,
    basis TEXT NOT NULL,
    scope TEXT NOT NULL,
    statement TEXT NOT NULL,
    verification_level TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'pending_verification')),
    building_types_json TEXT NOT NULL,
    record_json TEXT NOT NULL
);

CREATE TABLE knowledge_rule_regions (
    rule_id TEXT NOT NULL REFERENCES knowledge_rules(rule_id) ON UPDATE CASCADE ON DELETE CASCADE,
    region_id TEXT NOT NULL REFERENCES region_profiles(region_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    PRIMARY KEY (rule_id, region_id)
);
CREATE INDEX idx_knowledge_rules_status_kind ON knowledge_rules(status, evidence_kind);
CREATE INDEX idx_knowledge_rule_regions_region ON knowledge_rule_regions(region_id, rule_id);

CREATE TABLE parameter_schemas (
    schema_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    asset_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    definition_path TEXT NOT NULL,
    schema_json TEXT NOT NULL,
    PRIMARY KEY (schema_id, version)
);

CREATE TABLE module_assets (
    asset_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    kind TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('implemented', 'planned')),
    generator_source_id TEXT,
    parameter_schema_id TEXT,
    parameter_schema_version INTEGER,
    definition_path TEXT NOT NULL,
    region_association_kind TEXT NOT NULL,
    anchor_interfaces_json TEXT NOT NULL,
    dependencies_json TEXT NOT NULL,
    preview_files_json TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (asset_id, version),
    FOREIGN KEY (parameter_schema_id, parameter_schema_version)
        REFERENCES parameter_schemas(schema_id, version) ON UPDATE CASCADE ON DELETE RESTRICT,
    CHECK ((parameter_schema_id IS NULL) = (parameter_schema_version IS NULL))
);
CREATE INDEX idx_module_assets_kind_status ON module_assets(kind, status);

CREATE TABLE module_asset_regions (
    asset_id TEXT NOT NULL,
    asset_version INTEGER NOT NULL,
    region_id TEXT NOT NULL REFERENCES region_profiles(region_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    PRIMARY KEY (asset_id, asset_version, region_id),
    FOREIGN KEY (asset_id, asset_version)
        REFERENCES module_assets(asset_id, version) ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE TABLE module_dependencies (
    asset_id TEXT NOT NULL,
    asset_version INTEGER NOT NULL,
    dependency_asset_id TEXT NOT NULL,
    dependency_version INTEGER NOT NULL,
    PRIMARY KEY (asset_id, asset_version, dependency_asset_id, dependency_version),
    FOREIGN KEY (asset_id, asset_version)
        REFERENCES module_assets(asset_id, version) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (dependency_asset_id, dependency_version)
        REFERENCES module_assets(asset_id, version) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE style_profiles (
    profile_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    label TEXT NOT NULL,
    region_profile_id TEXT REFERENCES region_profiles(region_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    status TEXT NOT NULL CHECK (status IN ('draft', 'ready', 'planned')),
    definition_path TEXT NOT NULL,
    profile_json TEXT NOT NULL,
    PRIMARY KEY (profile_id, version)
);

CREATE TABLE reference_files (
    file_id INTEGER PRIMARY KEY,
    sha256 TEXT NOT NULL UNIQUE CHECK (length(sha256) = 64),
    file_format TEXT NOT NULL CHECK (file_format = 'litematic'),
    byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
    minecraft_data_version INTEGER NOT NULL CHECK (minecraft_data_version > 0),
    parser_version TEXT NOT NULL
);

CREATE TABLE reference_assets (
    asset_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    file_id INTEGER NOT NULL REFERENCES reference_files(file_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    name TEXT NOT NULL,
    source_file TEXT NOT NULL,
    region_profile_id TEXT REFERENCES region_profiles(region_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    region_assignment_status TEXT NOT NULL CHECK (
        region_assignment_status IN ('unverified', 'user_assigned', 'source_verified')
    ),
    building_type TEXT NOT NULL,
    dimensions_json TEXT NOT NULL,
    block_count INTEGER NOT NULL CHECK (block_count >= 0),
    block_palette_json TEXT NOT NULL,
    bounding_box_json TEXT NOT NULL,
    style_tags_json TEXT NOT NULL,
    preview_files_json TEXT NOT NULL,
    import_status TEXT NOT NULL CHECK (import_status IN ('imported', 'pending')),
    validation_status TEXT NOT NULL,
    author TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    usage_rights_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    PRIMARY KEY (asset_id, version),
    UNIQUE (asset_id, file_id),
    CHECK ((region_profile_id IS NULL) = (region_assignment_status = 'unverified'))
);
CREATE INDEX idx_reference_assets_type ON reference_assets(building_type, import_status);
CREATE INDEX idx_reference_assets_region ON reference_assets(region_profile_id, region_assignment_status);
CREATE INDEX idx_reference_assets_file ON reference_assets(file_id, asset_id, version);

CREATE TABLE reference_material_counts (
    file_id INTEGER NOT NULL REFERENCES reference_files(file_id) ON UPDATE CASCADE ON DELETE CASCADE,
    block_state TEXT NOT NULL,
    block_count INTEGER NOT NULL CHECK (block_count > 0),
    PRIMARY KEY (file_id, block_state)
);

CREATE TABLE reference_layer_counts (
    file_id INTEGER NOT NULL REFERENCES reference_files(file_id) ON UPDATE CASCADE ON DELETE CASCADE,
    y INTEGER NOT NULL,
    block_state TEXT NOT NULL,
    block_count INTEGER NOT NULL CHECK (block_count > 0),
    PRIMARY KEY (file_id, y, block_state)
);
CREATE INDEX idx_reference_layer_counts_y ON reference_layer_counts(file_id, y);

CREATE TABLE style_reference_assets (
    profile_id TEXT NOT NULL,
    profile_version INTEGER NOT NULL,
    asset_id TEXT NOT NULL,
    asset_version INTEGER NOT NULL,
    reference_role TEXT NOT NULL,
    PRIMARY KEY (profile_id, profile_version, asset_id, asset_version),
    FOREIGN KEY (profile_id, profile_version)
        REFERENCES style_profiles(profile_id, version) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (asset_id, asset_version)
        REFERENCES reference_assets(asset_id, version) ON UPDATE CASCADE ON DELETE RESTRICT
);
