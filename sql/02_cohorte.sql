-- Pilot cohort: first-line zolbetuximab candidates (SPOTLIGHT / GLOW criteria).
--
-- Index date = first stage 4 record of the person (at diagnosis, or at recurrence for those who
-- started in stage I-III). Every criterion is evaluated at the index date; vital status today is
-- NOT used (half of the synthetic patients have died since). Biomarkers and ECOG are taken from
-- a +-30 day window around the index date.
--
-- Creates views in the `results` schema (idempotent; needs 01_concept_sets.sql):
--   gc_index                    person_id, index_date
--   gc_zolbetuximab_flags       one row per person, one boolean per criterion (not cumulative)
--   gc_zolbetuximab_cohort      persons meeting every criterion
--   gc_zolbetuximab_attrition   cumulative attrition table, in the order of the criteria
--
-- Run: make cohort

CREATE SCHEMA IF NOT EXISTS results;

CREATE OR REPLACE VIEW results.gc_index AS
SELECT m.person_id,
       min(m.measurement_date) AS index_date
FROM cdm.measurement m
WHERE m.measurement_concept_id IN (SELECT concept_id FROM results.concept_set
                                   WHERE concept_set_name = 'stage_group')
  AND m.value_as_concept_id IN (SELECT concept_id FROM results.concept_set
                                WHERE concept_set_name = 'stage_4')
GROUP BY m.person_id;

CREATE OR REPLACE VIEW results.gc_zolbetuximab_flags AS
SELECT p.person_id,
       i.index_date,
       -- 1. Gastric cancer diagnosis.
       EXISTS (SELECT 1 FROM cdm.condition_occurrence c
               WHERE c.person_id = p.person_id
                 AND c.condition_concept_id IN (SELECT concept_id FROM results.concept_set
                                                WHERE concept_set_name = 'gastric_cancer'))
           AS c1_gastric_cancer,
       -- 2. Advanced disease: has a stage 4 record, which defines the index date, and the
       --    gastric cancer diagnosis is on or before it.
       EXISTS (SELECT 1 FROM cdm.condition_occurrence c
               WHERE c.person_id = p.person_id
                 AND c.condition_start_date <= i.index_date
                 AND c.condition_concept_id IN (SELECT concept_id FROM results.concept_set
                                                WHERE concept_set_name = 'gastric_cancer'))
           AS c2_advanced,
       -- 3. Adult at the index date.
       COALESCE(date_part('year', age(i.index_date, p.birth_datetime::date)) >= 18, false)
           AS c3_adult,
       -- 4. ECOG 0-1.
       EXISTS (SELECT 1 FROM cdm.measurement m
               WHERE m.person_id = p.person_id
                 AND m.measurement_concept_id IN (SELECT concept_id FROM results.concept_set
                                                  WHERE concept_set_name = 'ecog')
                 AND m.measurement_date BETWEEN i.index_date - 30 AND i.index_date + 30
                 AND m.value_as_number <= 1)
           AS c4_ecog_0_1,
       -- 5. No systemic anticancer therapy in the 180 days before the index date (washout after
       --    any perioperative FLOT / adjuvant platinum). Exposures ON the index date are the
       --    first line itself and do not count.
       i.index_date IS NOT NULL AND NOT EXISTS (
           SELECT 1 FROM cdm.drug_exposure d
           WHERE d.person_id = p.person_id
             AND d.drug_concept_id IN (SELECT concept_id FROM results.concept_set
                                       WHERE concept_set_name = 'systemic_antineoplastic')
             AND d.drug_exposure_start_date >= i.index_date - 180
             AND d.drug_exposure_start_date <  i.index_date)
           AS c5_no_recent_systemic_therapy,
       -- 6. HER2 negative.
       EXISTS (SELECT 1 FROM cdm.measurement m
               WHERE m.person_id = p.person_id
                 AND m.measurement_concept_id IN (SELECT concept_id FROM results.concept_set
                                                  WHERE concept_set_name = 'her2_ihc')
                 AND m.measurement_date BETWEEN i.index_date - 30 AND i.index_date + 30
                 AND m.value_as_concept_id IN (SELECT concept_id FROM results.concept_set
                                               WHERE concept_set_name = 'result_negative'))
           AS c6_her2_negative,
       -- 7. CLDN18 positive (proxy for CLDN18.2; see docs/LIMITACIONES.md).
       EXISTS (SELECT 1 FROM cdm.measurement m
               WHERE m.person_id = p.person_id
                 AND m.measurement_concept_id IN (SELECT concept_id FROM results.concept_set
                                                  WHERE concept_set_name = 'cldn18_ihc')
                 AND m.measurement_date BETWEEN i.index_date - 30 AND i.index_date + 30
                 AND m.value_as_concept_id IN (SELECT concept_id FROM results.concept_set
                                               WHERE concept_set_name = 'result_positive'))
           AS c7_cldn18_positive
FROM cdm.person p
LEFT JOIN results.gc_index i ON i.person_id = p.person_id;

CREATE OR REPLACE VIEW results.gc_zolbetuximab_cohort AS
SELECT person_id, index_date
FROM results.gc_zolbetuximab_flags
WHERE c1_gastric_cancer AND c2_advanced AND c3_adult AND c4_ecog_0_1
  AND c5_no_recent_systemic_therapy AND c6_her2_negative AND c7_cldn18_positive;

CREATE OR REPLACE VIEW results.gc_zolbetuximab_attrition AS
WITH cum AS (
    SELECT person_id,
           c1_gastric_cancer AS k1,
           c1_gastric_cancer AND c2_advanced AS k2,
           c1_gastric_cancer AND c2_advanced AND c3_adult AS k3,
           c1_gastric_cancer AND c2_advanced AND c3_adult AND c4_ecog_0_1 AS k4,
           c1_gastric_cancer AND c2_advanced AND c3_adult AND c4_ecog_0_1
               AND c5_no_recent_systemic_therapy AS k5,
           c1_gastric_cancer AND c2_advanced AND c3_adult AND c4_ecog_0_1
               AND c5_no_recent_systemic_therapy AND c6_her2_negative AS k6,
           c1_gastric_cancer AND c2_advanced AND c3_adult AND c4_ecog_0_1
               AND c5_no_recent_systemic_therapy AND c6_her2_negative
               AND c7_cldn18_positive AS k7
    FROM results.gc_zolbetuximab_flags
),
counts (step, description, n) AS (
    SELECT 0, 'Persons in the OMOP database',                  count(*)                       FROM cum
    UNION ALL SELECT 1, 'Gastric cancer diagnosis',            count(*) FILTER (WHERE k1) FROM cum
    UNION ALL SELECT 2, 'Advanced disease (stage 4 recorded)', count(*) FILTER (WHERE k2) FROM cum
    UNION ALL SELECT 3, 'Adult (>= 18) at index date',         count(*) FILTER (WHERE k3) FROM cum
    UNION ALL SELECT 4, 'ECOG 0-1',                            count(*) FILTER (WHERE k4) FROM cum
    UNION ALL SELECT 5, 'No systemic therapy in prior 180 days', count(*) FILTER (WHERE k5) FROM cum
    UNION ALL SELECT 6, 'HER2 negative',                       count(*) FILTER (WHERE k6) FROM cum
    UNION ALL SELECT 7, 'CLDN18 positive',                     count(*) FILTER (WHERE k7) FROM cum
)
SELECT step,
       description,
       n AS n_remaining,
       COALESCE(lag(n) OVER (ORDER BY step) - n, 0) AS n_lost
FROM counts
ORDER BY step;
