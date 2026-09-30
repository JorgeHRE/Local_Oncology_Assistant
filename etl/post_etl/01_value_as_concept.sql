-- Post-ETL step: fill cdm.measurement.value_as_concept_id.
--
-- ETL-Synthea v2.1.1 never fills value_as_concept_id: Synthea exports the display text of coded
-- values (e.g. "Positive (qualifier value)"), not their SNOMED code, and the ETL filters on
-- 'Meas value' while the vocabulary uses 'Meas Value'. See ADR-0001, phase 2b.
--
-- The map below stores the SNOMED *source* code for each text; the standard concept is resolved
-- through "Maps to", so the script does not hard-code vocabulary-version-specific concept_ids.
-- Only values needed by the oncology cohort are mapped. Sub-stages (1A, 2B, ...) and TNM categories
-- have no standard SNOMED concept and stay at 0 (pending the Cancer Modifier decision).
--
-- Idempotent: only rows still at 0/NULL are updated. Aborts without changes if any code does not
-- resolve to exactly one standard 'Meas Value' concept.
--
-- Run: docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' \
--        < etl/post_etl/01_value_as_concept.sql

BEGIN;

CREATE TEMP TABLE value_concept_map (
    value_source_value text PRIMARY KEY,
    snomed_code        text NOT NULL
) ON COMMIT DROP;

INSERT INTO value_concept_map (value_source_value, snomed_code) VALUES
    ('Positive (qualifier value)',     '10828004'),
    ('Negative (qualifier value)',     '260385009'),
    ('Detected (qualifier value)',     '260373001'),
    ('Not detected (qualifier value)', '260415000'),
    ('Stage 1 (qualifier value)',      '258215001'),
    ('Stage 2 (qualifier value)',      '258219007'),
    ('Stage 3 (qualifier value)',      '258224005'),
    ('Stage 4 (qualifier value)',      '258228008');

CREATE TEMP TABLE value_concept_resolved ON COMMIT DROP AS
SELECT m.value_source_value,
       m.snomed_code,
       std.concept_id
FROM value_concept_map m
LEFT JOIN cdm.concept src
       ON src.vocabulary_id = 'SNOMED'
      AND src.concept_code = m.snomed_code
LEFT JOIN cdm.concept_relationship r
       ON r.concept_id_1 = src.concept_id
      AND r.relationship_id = 'Maps to'
      AND r.invalid_reason IS NULL
LEFT JOIN cdm.concept std
       ON std.concept_id = r.concept_id_2
      AND std.standard_concept = 'S'
      AND std.domain_id = 'Meas Value'
      AND std.invalid_reason IS NULL;

DO $$
DECLARE
    bad text;
BEGIN
    SELECT string_agg(format('%s (SNOMED %s): %s standard concepts', value_source_value, snomed_code, n), '; ')
      INTO bad
      FROM (SELECT value_source_value, snomed_code, count(concept_id) AS n
              FROM value_concept_resolved
             GROUP BY value_source_value, snomed_code) t
     WHERE n <> 1;
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'value_concept_map does not resolve to exactly one standard Meas Value concept: %', bad;
    END IF;
END
$$;

UPDATE cdm.measurement AS m
   SET value_as_concept_id = r.concept_id
  FROM value_concept_resolved r
 WHERE m.value_source_value = r.value_source_value
   AND COALESCE(m.value_as_concept_id, 0) = 0
   AND r.concept_id IS NOT NULL;

COMMIT;
