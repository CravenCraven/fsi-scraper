-- One row per downloadable asset found by `discover`.
-- Mirrors fsi_scraper.models.Resource field for field.
CREATE TABLE IF NOT EXISTS resource (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source         text        NOT NULL,
    provider       text        NOT NULL,
    course         text        NOT NULL,
    kind           text        NOT NULL CHECK (kind IN ('pdf', 'audio', 'zip')),
    url            text        NOT NULL UNIQUE,
    filename       text        NOT NULL,
    title          text        NOT NULL,
    section        text,
    ordinal        integer,
    part           text,
    declared_bytes bigint,
    discovered_at  timestamptz NOT NULL DEFAULT now()
);
