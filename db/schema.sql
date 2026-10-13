-- ShadeWalk pilot schema. Applied by `python -m shadewalk.store.seed`, idempotent.
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS dataset (
    key   text PRIMARY KEY,
    value jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS nodes (
    id   integer PRIMARY KEY,
    geom geometry(Point, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS segments (
    id       integer PRIMARY KEY,
    u        integer NOT NULL REFERENCES nodes (id),
    v        integer NOT NULL REFERENCES nodes (id),
    length_m double precision NOT NULL,
    kind     text NOT NULL,
    name     text,
    street   text,
    covered  boolean NOT NULL DEFAULT false,
    geom     geometry(LineString, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS segments_geog_idx ON segments USING gist ((geom::geography));

-- Shade fraction * 250, one row per segment, month (1-12) and local clock hour (0-23).
CREATE TABLE IF NOT EXISTS shade (
    month           smallint NOT NULL,
    hour            smallint NOT NULL,
    segment_id      integer  NOT NULL REFERENCES segments (id),
    shade_all       smallint NOT NULL,
    shade_buildings smallint NOT NULL,
    PRIMARY KEY (month, hour, segment_id)
);

CREATE TABLE IF NOT EXISTS pois (
    id   integer PRIMARY KEY,
    kind text NOT NULL,
    name text,
    osm  text NOT NULL,
    geom geometry(Point, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS pois_geog_idx ON pois USING gist ((geom::geography));

CREATE TABLE IF NOT EXISTS poi_shade (
    month           smallint NOT NULL,
    hour            smallint NOT NULL,
    poi_id          integer  NOT NULL REFERENCES pois (id),
    shade_all       smallint NOT NULL,
    shade_buildings smallint NOT NULL,
    PRIMARY KEY (month, hour, poi_id)
);

CREATE TABLE IF NOT EXISTS sun (
    month     smallint NOT NULL,
    slot      smallint NOT NULL,
    azimuth   real NOT NULL,
    elevation real NOT NULL,
    PRIMARY KEY (month, slot)
);

CREATE TABLE IF NOT EXISTS buildings (
    id            integer PRIMARY KEY,
    height_m      real NOT NULL,
    height_source text NOT NULL,
    name          text,
    osm           text NOT NULL,
    part          boolean NOT NULL,
    in_pilot      boolean NOT NULL,
    geom          geometry(Polygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS buildings_geom_idx ON buildings USING gist (geom);

CREATE TABLE IF NOT EXISTS canopy (
    id       integer PRIMARY KEY,
    height_m real NOT NULL,
    area_m2  real NOT NULL,
    geom     geometry(Polygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS canopy_geom_idx ON canopy USING gist (geom);
