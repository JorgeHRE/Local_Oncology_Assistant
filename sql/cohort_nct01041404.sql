-- Cohort C-003: NCT01041404 (ToGA: 1L trastuzumab + chemotherapy in HER2-positive gastric/GEJ).
--
-- Index date = first stage 4 record of the person. Evaluates evaluable criteria of NCT01041404
-- on the OMOP database (needs 01_concept_sets.sql):
--   gc_nct01041404_flags       one row per person, one boolean per criterion
--   gc_nct01041404_cohort      persons meeting every criterion
--   gc_nct01041404_attrition   cumulative attrition table

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

CREATE OR REPLACE VIEW results.gc_nct01041404_flags AS
SELECT p.person_id,
       i.index_date,
       -- 1. Gastric cancer / GEJ adenocarcinoma diagnosis.
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
       -- 3. Adult (>= 18) at the index date.
       COALESCE(date_part('year', age(i.index_date, p.birth_datetime::date)) >= 18, false)
           AS c3_adult,
       -- 4. No previous chemotherapy for advanced/metastatic disease (180-day washout before index).
       i.index_date IS NOT NULL AND NOT EXISTS (
           SELECT 1 FROM cdm.drug_exposure d
           WHERE d.person_id = p.person_id
             AND d.drug_concept_id IN (SELECT concept_id FROM results.concept_set
                                       WHERE concept_set_name = 'systemic_antineoplastic')
             AND d.drug_exposure_start_date >= i.index_date - 180
             AND d.drug_exposure_start_date <  i.index_date)
           AS c4_no_recent_systemic_therapy,
       -- 5. HER2-positive tumor.
       EXISTS (SELECT 1 FROM cdm.measurement m
               WHERE m.person_id = p.person_id
                 AND m.measurement_concept_id IN (SELECT concept_id FROM results.concept_set
                                                  WHERE concept_set_name = 'her2_ihc')
                 AND m.measurement_date BETWEEN i.index_date - 30 AND i.index_date + 30
                 AND m.value_as_concept_id IN (SELECT concept_id FROM results.concept_set
                                               WHERE concept_set_name = 'result_positive'))
           AS c5_her2_positive
FROM cdm.person p
LEFT JOIN results.gc_index i ON i.person_id = p.person_id;

CREATE OR REPLACE VIEW results.gc_nct01041404_cohort AS
SELECT person_id, index_date
FROM results.gc_nct01041404_flags
WHERE c1_gastric_cancer AND c2_advanced AND c3_adult
  AND c4_no_recent_systemic_therapy AND c5_her2_positive;

CREATE OR REPLACE VIEW results.gc_nct01041404_attrition AS
WITH cum AS (
    SELECT person_id,
           c1_gastric_cancer AS k1,
           c1_gastric_cancer AND c2_advanced AS k2,
           c1_gastric_cancer AND c2_advanced AND c3_adult AS k3,
           c1_gastric_cancer AND c2_advanced AND c3_adult
               AND c4_no_recent_systemic_therapy AS k4,
           c1_gastric_cancer AND c2_advanced AND c3_adult
               AND c4_no_recent_systemic_therapy AND c5_her2_positive AS k5
    FROM results.gc_nct01041404_flags
),
counts (step, description, n) AS (
    SELECT 0, 'Persons in the OMOP database',                  count(*)                       FROM cum
    UNION ALL SELECT 1, 'Gastric cancer diagnosis',            count(*) FILTER (WHERE k1) FROM cum
    UNION ALL SELECT 2, 'Advanced disease (stage 4 recorded)', count(*) FILTER (WHERE k2) FROM cum
    UNION ALL SELECT 3, 'Adult (>= 18) at index date',         count(*) FILTER (WHERE k3) FROM cum
    UNION ALL SELECT 4, 'No systemic therapy in prior 180 days', count(*) FILTER (WHERE k4) FROM cum
    UNION ALL SELECT 5, 'HER2 positive',                       count(*) FILTER (WHERE k5) FROM cum
)
SELECT step,
       description,
       n AS n_remaining,
       COALESCE(lag(n) OVER (ORDER BY step) - n, 0) AS n_lost
FROM counts
ORDER BY step;
