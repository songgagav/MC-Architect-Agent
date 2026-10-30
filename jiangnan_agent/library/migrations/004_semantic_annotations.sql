CREATE TABLE semantic_annotation_revisions (
    annotation_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    asset_id TEXT NOT NULL,
    asset_version INTEGER NOT NULL CHECK (asset_version > 0),
    region_name TEXT NOT NULL,
    component_type TEXT NOT NULL CHECK (component_type IN (
        'roof_surface', 'roof_ridge', 'eaves', 'column', 'beam', 'wall', 'door',
        'window', 'floor', 'foundation', 'railing', 'decoration', 'unknown'
    )),
    geometry_type TEXT NOT NULL CHECK (geometry_type IN ('region', 'box', 'block_set')),
    geometry_json TEXT NOT NULL,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('manual', 'rule')),
    rule_id TEXT,
    confidence REAL CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)),
    status TEXT NOT NULL CHECK (status IN ('candidate', 'verified', 'rejected')),
    reviewer TEXT,
    reviewed_at TEXT,
    review_note TEXT,
    created_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (annotation_id, revision),
    FOREIGN KEY (asset_id, asset_version)
        REFERENCES reference_assets(asset_id, version) ON UPDATE CASCADE ON DELETE RESTRICT,
    CHECK ((status = 'verified' AND reviewer IS NOT NULL AND reviewed_at IS NOT NULL) OR status != 'verified')
);
CREATE INDEX idx_semantic_annotations_asset_status
    ON semantic_annotation_revisions(asset_id, asset_version, status, component_type, annotation_id, revision);

CREATE TABLE reference_components (
    component_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    source_asset_id TEXT NOT NULL,
    source_asset_version INTEGER NOT NULL CHECK (source_asset_version > 0),
    annotation_id TEXT NOT NULL,
    annotation_revision INTEGER NOT NULL CHECK (annotation_revision > 0),
    name TEXT NOT NULL,
    component_type TEXT NOT NULL CHECK (component_type IN (
        'roof_surface', 'roof_ridge', 'eaves', 'column', 'beam', 'wall', 'door',
        'window', 'floor', 'foundation', 'railing', 'decoration', 'unknown'
    )),
    region_name TEXT NOT NULL,
    origin_json TEXT NOT NULL,
    dimensions_json TEXT NOT NULL,
    bounding_box_json TEXT NOT NULL,
    block_count INTEGER NOT NULL CHECK (block_count > 0),
    block_states_json TEXT NOT NULL,
    materials_json TEXT NOT NULL,
    layer_materials_json TEXT NOT NULL,
    coordinate_runs_json TEXT NOT NULL,
    style_tags_json TEXT NOT NULL,
    component_status TEXT NOT NULL CHECK (component_status = 'static_reference'),
    parameterization_status TEXT NOT NULL CHECK (parameterization_status IN ('not_parameterized', 'planned')),
    created_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (component_id, version),
    UNIQUE (annotation_id, annotation_revision),
    FOREIGN KEY (source_asset_id, source_asset_version)
        REFERENCES reference_assets(asset_id, version) ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (annotation_id, annotation_revision)
        REFERENCES semantic_annotation_revisions(annotation_id, revision) ON UPDATE CASCADE ON DELETE RESTRICT
);
CREATE INDEX idx_reference_components_source
    ON reference_components(source_asset_id, source_asset_version, component_type, component_id, version);

CREATE TABLE style_analysis_revisions (
    analysis_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    profile_id TEXT NOT NULL,
    profile_version INTEGER NOT NULL CHECK (profile_version > 0),
    status TEXT NOT NULL CHECK (status IN ('candidate', 'verified', 'rejected')),
    analysis_json TEXT NOT NULL,
    reviewer TEXT,
    reviewed_at TEXT,
    review_note TEXT,
    created_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (analysis_id, revision),
    FOREIGN KEY (profile_id, profile_version)
        REFERENCES style_profiles(profile_id, version) ON UPDATE CASCADE ON DELETE RESTRICT,
    CHECK ((status = 'verified' AND reviewer IS NOT NULL AND reviewed_at IS NOT NULL) OR status != 'verified')
);
CREATE INDEX idx_style_analysis_profile_status
    ON style_analysis_revisions(profile_id, profile_version, status, analysis_id, revision);

CREATE TABLE style_analysis_sources (
    analysis_id TEXT NOT NULL,
    analysis_revision INTEGER NOT NULL CHECK (analysis_revision > 0),
    asset_id TEXT NOT NULL,
    asset_version INTEGER NOT NULL CHECK (asset_version > 0),
    source_role TEXT NOT NULL,
    PRIMARY KEY (analysis_id, analysis_revision, asset_id, asset_version),
    FOREIGN KEY (analysis_id, analysis_revision)
        REFERENCES style_analysis_revisions(analysis_id, revision) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (asset_id, asset_version)
        REFERENCES reference_assets(asset_id, version) ON UPDATE CASCADE ON DELETE RESTRICT
);
