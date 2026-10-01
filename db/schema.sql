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

-- One row per lesson in a course.
CREATE TABLE IF NOT EXISTS lesson (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    course    text    NOT NULL,
    number    integer NOT NULL,
    location  text    NOT NULL,
    title     text    NOT NULL,
    UNIQUE (course, number)
);

-- One row per line of a lesson's dialog, in order.
CREATE TABLE IF NOT EXISTS dialog_line (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lesson_id bigint  NOT NULL REFERENCES lesson(id) ON DELETE CASCADE,
    seq       integer NOT NULL,
    speaker   text,
    text      text    NOT NULL,
    page      integer NOT NULL,
    UNIQUE (lesson_id, seq)
);
