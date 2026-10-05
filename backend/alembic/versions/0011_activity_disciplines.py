"""Seed common sports and repair activity labels from linked provider payloads.

The frozen CASE mapping intentionally lives here instead of importing the
mutable connector alias tables. A repair uses only the raw row referenced by
the account-owned source link, and the user's selected main integration wins
when more than one provider is linked to an activity.
"""

from alembic import op
from sqlalchemy import text

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_DISCIPLINES = (
    ("mountain_biking", "endurance"),
    ("hiking", "endurance"),
    ("walking", "endurance"),
    ("swimming", "endurance"),
    ("rowing", "endurance"),
    ("yoga", "strength"),
    ("pilates", "strength"),
    ("gravel_cycling", "endurance"),
)

_PREFERRED_LINKED_RAW_SPORT = """
WITH linked_sports AS (
    SELECT
        a.id AS activity_id,
        a.discipline_id AS old_discipline_id,
        l.id AS link_id,
        l.source,
        r.raw_json,
        CASE WHEN i.id = u.main_integration_id THEN 0 ELSE 1 END AS main_order,
        CASE l.source
            WHEN 'garmin' THEN 0
            WHEN 'whoop' THEN 1
            WHEN 'oura' THEN 2
            WHEN 'coros' THEN 3
            WHEN 'strava' THEN 4
            ELSE 5
        END AS fallback_order
    FROM activities AS a
    JOIN users AS u ON u.id = a.user_id
    JOIN activity_source_links AS l
      ON l.activity_id = a.id AND l.user_id = a.user_id
    JOIN raw_ingest AS r
      ON r.id = l.raw_ingest_id
     AND r.user_id = a.user_id
     AND r.source = l.source
    LEFT JOIN integrations AS i
      ON i.id = u.main_integration_id
     AND i.user_id = u.id
     AND i.provider = l.source
    WHERE l.source IN ('garmin', 'strava', 'whoop')
      AND (
        (l.source = 'garmin'
          AND r.payload_type = 'activity_summary'
          AND r.raw_json->>'activityId' = l.external_id)
        OR (l.source = 'strava'
          AND r.payload_type = 'activity_summary'
          AND r.raw_json->>'id' = l.external_id)
        OR (l.source = 'whoop'
          AND r.payload_type = 'workout'
          AND r.raw_json->>'id' = l.external_id)
      )
), ranked AS (
    SELECT *, row_number() OVER (
        PARTITION BY activity_id
        ORDER BY main_order, fallback_order, link_id
    ) AS source_rank
    FROM linked_sports
), preferred AS (
    SELECT activity_id, old_discipline_id, source, raw_json
    FROM ranked WHERE source_rank = 1
), mapped AS (
    SELECT activity_id, old_discipline_id,
      CASE source
        WHEN 'garmin' THEN CASE lower(btrim(raw_json #>> '{activityType,typeKey}'))
          WHEN 'running' THEN 'running'
          WHEN 'street_running' THEN 'running'
          WHEN 'indoor_running' THEN 'running'
          WHEN 'trail_running' THEN 'running'
          WHEN 'treadmill_running' THEN 'running'
          WHEN 'track_running' THEN 'running'
          WHEN 'ultra_run' THEN 'running'
          WHEN 'virtual_run' THEN 'running'
          WHEN 'cycling' THEN 'road_cycling'
          WHEN 'road_biking' THEN 'road_cycling'
          WHEN 'road' THEN 'road_cycling'
          WHEN 'biking' THEN 'road_cycling'
          WHEN 'cyclocross' THEN 'road_cycling'
          WHEN 'track_cycling' THEN 'road_cycling'
          WHEN 'indoor_cycling' THEN 'road_cycling'
          WHEN 'virtual_ride' THEN 'road_cycling'
          WHEN 'bike_to_work' THEN 'road_cycling'
          WHEN 'mountain_biking' THEN 'mountain_biking'
          WHEN 'downhill_biking' THEN 'mountain_biking'
          WHEN 'e_mountain_biking' THEN 'mountain_biking'
          WHEN 'gravel_cycling' THEN 'gravel_cycling'
          WHEN 'strength_training' THEN 'strength'
          WHEN 'indoor_strength' THEN 'strength'
          WHEN 'gym' THEN 'gym_general'
          WHEN 'fitness_equipment' THEN 'gym_general'
          WHEN 'indoor_cardio' THEN 'gym_general'
          WHEN 'elliptical' THEN 'gym_general'
          WHEN 'stair_stepper' THEN 'gym_general'
          WHEN 'indoor_rowing' THEN 'rowing'
          WHEN 'yoga' THEN 'yoga'
          WHEN 'pilates' THEN 'pilates'
          WHEN 'walking' THEN 'walking'
          WHEN 'hiking' THEN 'hiking'
          WHEN 'swimming' THEN 'swimming'
          WHEN 'lap_swimming' THEN 'swimming'
          WHEN 'pool_swimming' THEN 'swimming'
          WHEN 'open_water_swimming' THEN 'swimming'
          WHEN 'rowing' THEN 'rowing'
          WHEN 'resort_skiing' THEN 'skiing'
          WHEN 'backcountry_skiing' THEN 'skiing'
          WHEN 'cross_country_skiing' THEN 'skiing'
          WHEN 'sailing' THEN 'sailing'
          WHEN 'kitesurf' THEN 'kitesurf'
          WHEN 'kiteboarding' THEN 'kitesurf'
          WHEN 'windsurf' THEN 'windsurf'
          WHEN 'windsurfing' THEN 'windsurf'
          WHEN 'tennis' THEN 'tennis'
          WHEN 'wakeboard' THEN 'wakeboard'
          WHEN 'wakeboarding' THEN 'wakeboard'
          WHEN 'snowboard' THEN 'snowboard'
          WHEN 'snowboarding' THEN 'snowboard'
          WHEN 'surf' THEN 'surf'
          WHEN 'surfing' THEN 'surf'
          WHEN 'stand_up_paddleboarding' THEN 'surf'
          WHEN 'sup' THEN 'surf'
          WHEN 'enduro_motorcycling' THEN 'enduro'
          ELSE NULL END
        WHEN 'strava' THEN CASE lower(btrim(coalesce(raw_json->>'sport_type', raw_json->>'type')))
          WHEN 'run' THEN 'running'
          WHEN 'trailrun' THEN 'running'
          WHEN 'virtualrun' THEN 'running'
          WHEN 'treadmill' THEN 'running'
          WHEN 'ride' THEN 'road_cycling'
          WHEN 'virtualride' THEN 'road_cycling'
          WHEN 'ridefixedgear' THEN 'road_cycling'
          WHEN 'ebikeride' THEN 'road_cycling'
          WHEN 'gravelride' THEN 'gravel_cycling'
          WHEN 'gravel_ride' THEN 'gravel_cycling'
          WHEN 'mountainbikeride' THEN 'mountain_biking'
          WHEN 'emountainbikeride' THEN 'mountain_biking'
          WHEN 'mountain_bike_ride' THEN 'mountain_biking'
          WHEN 'hike' THEN 'hiking'
          WHEN 'hiking' THEN 'hiking'
          WHEN 'walk' THEN 'walking'
          WHEN 'walking' THEN 'walking'
          WHEN 'swim' THEN 'swimming'
          WHEN 'swimming' THEN 'swimming'
          WHEN 'row' THEN 'rowing'
          WHEN 'rowing' THEN 'rowing'
          WHEN 'yoga' THEN 'yoga'
          WHEN 'pilates' THEN 'pilates'
          WHEN 'alpineski' THEN 'skiing'
          WHEN 'skitour' THEN 'skiing'
          WHEN 'nordicski' THEN 'skiing'
          WHEN 'snowboard' THEN 'snowboard'
          WHEN 'iceskate' THEN 'skiing'
          WHEN 'sail' THEN 'sailing'
          WHEN 'kitesurf' THEN 'kitesurf'
          WHEN 'kite' THEN 'kitesurf'
          WHEN 'windsurf' THEN 'windsurf'
          WHEN 'surf' THEN 'surf'
          WHEN 'surfing' THEN 'surf'
          WHEN 'tennis' THEN 'tennis'
          WHEN 'weighttraining' THEN 'strength'
          WHEN 'workout' THEN 'gym_general'
          WHEN 'crossfit' THEN 'strength'
          WHEN 'hiit' THEN 'gym_general'
          ELSE NULL END
        WHEN 'whoop' THEN CASE lower(btrim(raw_json->>'sport_name'))
          WHEN 'running' THEN 'running'
          WHEN 'running_indoor' THEN 'running'
          WHEN 'treadmill' THEN 'running'
          WHEN 'trail_running' THEN 'running'
          WHEN 'cycling' THEN 'road_cycling'
          WHEN 'cycling_indoor' THEN 'road_cycling'
          WHEN 'road_cycling' THEN 'road_cycling'
          WHEN 'mountain_biking' THEN 'mountain_biking'
          WHEN 'gravel_cycling' THEN 'gravel_cycling'
          WHEN 'hiking' THEN 'hiking'
          WHEN 'hike' THEN 'hiking'
          WHEN 'walking' THEN 'walking'
          WHEN 'walk' THEN 'walking'
          WHEN 'swimming' THEN 'swimming'
          WHEN 'swim' THEN 'swimming'
          WHEN 'rowing' THEN 'rowing'
          WHEN 'row' THEN 'rowing'
          WHEN 'yoga' THEN 'yoga'
          WHEN 'pilates' THEN 'pilates'
          WHEN 'skiing' THEN 'skiing'
          WHEN 'alpine_skiing' THEN 'skiing'
          WHEN 'cross_country_skiing' THEN 'skiing'
          WHEN 'snowboarding' THEN 'snowboard'
          WHEN 'strength_training' THEN 'strength'
          WHEN 'weight_training' THEN 'strength'
          WHEN 'gym' THEN 'gym_general'
          WHEN 'functional_fitness' THEN 'gym_general'
          WHEN 'sailing' THEN 'sailing'
          WHEN 'kitesurfing' THEN 'kitesurf'
          WHEN 'windsurfing' THEN 'windsurf'
          WHEN 'tennis' THEN 'tennis'
          WHEN 'surfing' THEN 'surf'
          WHEN 'wakeboarding' THEN 'wakeboard'
          WHEN 'motocross' THEN 'enduro'
          WHEN 'enduro' THEN 'enduro'
          ELSE NULL END
      END AS discipline_name
    FROM preferred
)
"""


def upgrade() -> None:
    for name, category in _DISCIPLINES:
        op.execute(
            "INSERT INTO disciplines (name, category) VALUES "
            f"('{name}', '{category}') ON CONFLICT (name) DO NOTHING"
        )

    op.execute("""
        CREATE TABLE activity_discipline_changes_0011 (
            activity_id BIGINT PRIMARY KEY REFERENCES activities(id) ON DELETE CASCADE,
            old_discipline_id BIGINT NULL REFERENCES disciplines(id),
            new_discipline_id BIGINT NULL REFERENCES disciplines(id)
        )
    """)
    op.execute(text(_PREFERRED_LINKED_RAW_SPORT + """
        INSERT INTO activity_discipline_changes_0011
            (activity_id, old_discipline_id, new_discipline_id)
        SELECT m.activity_id, m.old_discipline_id, target.id
        FROM mapped AS m
        LEFT JOIN disciplines AS target ON target.name = m.discipline_name
        LEFT JOIN disciplines AS current ON current.id = m.old_discipline_id
        WHERE (m.old_discipline_id IS NULL OR current.name IN ('gym_general', 'enduro'))
          AND m.old_discipline_id IS DISTINCT FROM target.id
    """))
    op.execute("""
        UPDATE activities AS a
        SET discipline_id = changes.new_discipline_id
        FROM activity_discipline_changes_0011 AS changes
        WHERE a.id = changes.activity_id
    """)


def downgrade() -> None:
    # Restore only rows still holding the value this migration wrote, so a
    # subsequent owner edit is never overwritten. Activities are never deleted.
    bind = op.get_bind()
    if bind.scalar(text("SELECT to_regclass('public.activity_discipline_changes_0011')")):
        changes_table = "activity_discipline_changes_0011"
    elif bind.scalar(text("SELECT to_regclass('public._0011_activity_discipline_changes')")):
        # Compatibility with disposable databases created while this migration
        # used its original private table name.
        changes_table = "_0011_activity_discipline_changes"
    else:
        changes_table = None

    if changes_table is not None:
        op.execute(f"""
        UPDATE activities AS a
        SET discipline_id = changes.old_discipline_id
        FROM {changes_table} AS changes
        WHERE a.id = changes.activity_id
          AND a.discipline_id IS NOT DISTINCT FROM changes.new_discipline_id
        """)
        op.execute(f'DROP TABLE "{changes_table}"')

    # Remove only seed rows that no table references. Dynamic FK discovery
    # keeps this safe if another feature starts referencing disciplines.
    op.execute("""
        DO $$
        DECLARE fk RECORD;
        DECLARE guards TEXT := '';
        BEGIN
          FOR fk IN
            SELECT c.conrelid::regclass AS table_name, a.attname AS column_name
            FROM pg_constraint AS c
            JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS source_col(attnum, ord) ON true
            JOIN LATERAL unnest(c.confkey) WITH ORDINALITY AS target_col(attnum, ord)
              ON target_col.ord = source_col.ord
            JOIN pg_attribute AS a
              ON a.attrelid = c.conrelid AND a.attnum = source_col.attnum
            WHERE c.contype = 'f' AND c.confrelid = 'disciplines'::regclass
          LOOP
            guards := guards || format(
              ' AND NOT EXISTS (SELECT 1 FROM %s AS ref WHERE ref.%I = d.id)',
              fk.table_name, fk.column_name
            );
          END LOOP;
          EXECUTE 'DELETE FROM disciplines AS d WHERE d.name IN '
            || '(''mountain_biking'',''hiking'',''walking'',''swimming'',''rowing'',''yoga'',''pilates'',''gravel_cycling'')'
            || guards;
        END $$;
    """)
