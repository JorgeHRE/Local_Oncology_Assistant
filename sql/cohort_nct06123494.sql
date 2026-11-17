-- Cohort C-001: NCT06123494 (SHR-A1811 in 2L HER2-positive gastric/GEJ cancer after anti-HER2).
--
-- Index date = first stage 4 record of the person. Evaluates evaluable criteria of NCT06123494
-- on the OMOP database (needs 01_concept_sets.sql):
--   gc_nct06123494_flags       one row per person, one boolean per criterion
--   gc_nct06123494_cohort      persons meeting every criterion
--   gc_nct06123494_attrition   cumulative attrition table

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

CREATE OR REPLACE VIEW results.gc_nct06123494_flags AS
SELECT p.person_id,
       i.index_date,
       -- 1. Gastric cancer diagnosis.
       EXISTS (SELECT 1 FROM cdm.condition_occurrence c
               WHERE c.person_id = p.person_id
                 AND c.condition_concept_id IN (SELECT concept_id FROM results.concept_set
                                                WHERE concept_set_name = 'gastric_cancer'))
           AS c1_gastric_cancer,
       -- 2. Advanced disease (stage 4 recorded on or after gastric cancer diagnosis).
       EXISTS (SELECT 1 FROM cdm.condition_occurrence c
               WHERE c.person_id = p.person_id
                 AND c.condition_start_date <= i.index_date
                 AND c.condition_concept_id IN (SELECT concept_id FROM results.concept_set
                                                WHERE concept_set_name = 'gastric_cancer'))
           AS c2_advanced,
       -- 3. Age 18-75 years at the index date.
       COALESCE(date_part('year', age(i.index_date, p.birth_datetime::date)) BETWEEN 18 AND 75, false)
           AS c3_age_18_75,
       -- 4. ECOG 0-1.
       EXISTS (SELECT 1 FROM cdm.measurement m
               WHERE m.person_id = p.person_id
                 AND m.measurement_concept_id IN (SELECT concept_id FROM results.concept_set
                                                  WHERE concept_set_name = 'ecog')
                 AND m.measurement_date BETWEEN i.index_date - 30 AND i.index_date + 30
                 AND m.value_as_number <= 1)
           AS c4_ecog_0_1,
       -- 5. HER2 positive.
       EXISTS (SELECT 1 FROM cdm.measurement m
               WHERE m.person_id = p.person_id
                 AND m.measurement_concept_id IN (SELECT concept_id FROM results.concept_set
                                                  WHERE concept_set_name = 'her2_ihc')
                 AND m.measurement_date BETWEEN i.index_date - 30 AND i.index_date + 30
                 AND m.value_as_concept_id IN (SELECT concept_id FROM results.concept_set
                                               WHERE concept_set_name = 'result_positive'))
           AS c5_her2_positive,
       -- 6. Prior anti-HER2-containing first-line therapy (trastuzumab on or after index_date).
       i.index_date IS NOT NULL AND EXISTS (
           SELECT 1 FROM cdm.drug_exposure d
           WHERE d.person_id = p.person_id
             AND d.drug_concept_id IN (SELECT concept_id FROM results.concept_set
                                       WHERE concept_set_name = 'trastuzumab')
             AND d.drug_exposure_start_date >= i.index_date)
           AS c6_prior_anti_her2
FROM cdm.person p
LEFT JOIN results.gc_index i ON i.person_id = p.person_id;

CREATE OR REPLACE VIEW results.gc_nct06123494_cohort AS
SELECT person_id, index_date
FROM results.gc_nct06123494_flags
WHERE c1_gastric_cancer AND c2_advanced AND c3_age_18_75 AND c4_ecog_0_1
  AND c5_her2_positive AND c6_prior_anti_her2;

CREATE OR REPLACE VIEW results.gc_nct06123494_attrition AS
WITH cum AS (
    SELECT person_id,
           c1_gastric_cancer AS k1,
           c1_gastric_cancer AND c2_advanced AS k2,
           c1_gastric_cancer AND c2_advanced AND c3_age_18_75 AS k3,
           c1_gastric_cancer AND c2_advanced AND c3_age_18_75 AND c4_ecog_0_1 AS k4,
           c1_gastric_cancer AND c2_advanced AND c3_age_18_75 AND c4_ecog_0_1
               AND c5_her2_positive AS k5,
           c1_gastric_cancer AND c2_advanced AND c3_age_18_75 AND c4_ecog_0_1
               AND c5_her2_positive AND c6_prior_anti_her2 AS k6
    FROM results.gc_nct06123494_flags
),
counts (step, description, n) AS (
    SELECT 0, 'Persons in the OMOP database',                  count(*)                       FROM cum
    UNION ALL SELECT 1, 'Gastric cancer diagnosis',            count(*) FILTER (WHERE k1) FROM cum
    UNION ALL SELECT 2, 'Advanced disease (stage 4 recorded)', count(*) FILTER (WHERE k2) FROM cum
    UNION ALL SELECT 3, 'Age 18-75 at index date',             count(*) FILTER (WHERE k3) FROM cum
    UNION ALL SELECT 4, 'ECOG 0-1',                            count(*) FILTER (WHERE k4) FROM cum
    UNION ALL SELECT 5, 'HER2 positive',                       count(*) FILTER (WHERE k5) FROM cum
    UNION ALL SELECT 6, 'Prior anti-HER2 therapy (trastuzumab)', count(*) FILTER (WHERE k6) FROM cum
)
SELECT step,
       description,
       n AS n_remaining,
       COALESCE(lag(n) OVER (ORDER BY step) - n, 0) AS n_lost
FROM counts
ORDER BY step;
