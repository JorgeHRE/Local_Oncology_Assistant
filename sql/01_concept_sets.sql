-- Concept sets for the gastric cancer cohort (OMOP CDM v5.4, Athena v5.0 29-AUG-26).
--
-- results.concept_set(concept_set_name, concept_id): one row per concept, with descendants
-- expanded through concept_ancestor, so the cohort query never hard-codes concept ids.
-- Codes and their meaning: docs/features.md.
--
-- Idempotent: rebuilds results.concept_set. Aborts if a set comes out empty.
--
-- Run: make cohort

CREATE SCHEMA IF NOT EXISTS results;

CREATE TABLE IF NOT EXISTS results.concept_set (
    concept_set_name text    NOT NULL,
    concept_id       integer NOT NULL,
    PRIMARY KEY (concept_set_name, concept_id)
);
-- TRUNCATE, not DROP: the cohort views in 02_cohorte.sql depend on this table.
TRUNCATE results.concept_set;

-- Conditions and drugs: the listed concepts plus all their descendants (DISTINCT: two listed
-- concepts can share descendants).
INSERT INTO results.concept_set (concept_set_name, concept_id)
SELECT DISTINCT s.concept_set_name, a.descendant_concept_id
FROM (VALUES
    -- 4248802 Adenocarcinoma of stomach, 4094856 Malignant neoplasm of cardia of stomach
    ('gastric_cancer',        4248802),
    ('gastric_cancer',        4094856),
    -- Ingredients of the systemic anticancer drugs in the module: oxaliplatin, capecitabine,
    -- fluorouracil, leucovorin, docetaxel, trastuzumab, zolbetuximab, nivolumab.
    ('systemic_antineoplastic', 1318011),
    ('systemic_antineoplastic', 1337620),
    ('systemic_antineoplastic', 955632),
    ('systemic_antineoplastic', 1388796),
    ('systemic_antineoplastic', 1315942),
    ('systemic_antineoplastic', 1387104),
    ('systemic_antineoplastic', 1735539),
    ('systemic_antineoplastic', 45892628),
    ('zolbetuximab',          1735539)
) AS s(concept_set_name, concept_id)
JOIN cdm.concept_ancestor a ON a.ancestor_concept_id = s.concept_id;

-- Measurements and coded values: used as they are (no hierarchy).
INSERT INTO results.concept_set (concept_set_name, concept_id) VALUES
    ('stage_group',       3031548),   -- LOINC 42100-8 Derived AJCC stage group
    ('stage_4',           4123017),   -- Stage 4
    ('her2_ihc',          3019066),   -- LOINC 18474-7
    ('cldn18_ihc',        1091409),   -- LOINC 105011-1 (Claudin 18, proxy for CLDN18.2; see LIMITACIONES)
    ('ecog',              36305384),  -- LOINC 89247-1, numeric 0-4
    ('result_positive',   9191),
    ('result_negative',   9189);

DO $$
DECLARE
    missing text;
BEGIN
    SELECT string_agg(expected, ', ') INTO missing
    FROM unnest(ARRAY['gastric_cancer', 'systemic_antineoplastic', 'zolbetuximab', 'stage_group',
                      'stage_4', 'her2_ihc', 'cldn18_ihc', 'ecog', 'result_positive',
                      'result_negative']) AS expected
    WHERE NOT EXISTS (SELECT 1 FROM results.concept_set cs WHERE cs.concept_set_name = expected);
    IF missing IS NOT NULL THEN
        RAISE EXCEPTION 'empty concept sets (vocabulary not loaded?): %', missing;
    END IF;
END
$$;
