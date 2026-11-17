-- Cohort C-002: NCT06177041 (M108 + CAPOX in 1L CLDN18.2+, HER2-, PD-L1 CPS < 5 gastric/GEJ).
--
-- Index date = first stage 4 record of the person. Evaluates evaluable criteria of NCT06177041
-- on the OMOP database (needs 01_concept_sets.sql):
--   gc_nct06177041_flags       one row per person, one boolean per criterion
--   gc_nct06177041_cohort      persons meeting every criterion
--   gc_nct06177041_attrition   cumulative attrition table

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

CREATE OR REPLACE VIEW results.gc_nct06177041_flags AS
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
       -- 5. No systemic anticancer therapy in the 180 days before the index date (> 6 months from
       --    adjuvant/neoadjuvant therapy to recurrence).
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
       -- 7. CLDN18 positive (proxy for CLDN18.2).
       EXISTS (SELECT 1 FROM cdm.measurement m
               WHERE m.person_id = p.person_id
                 AND m.measurement_concept_id IN (SELECT concept_id FROM results.concept_set
                                                  WHERE concept_set_name = 'cldn18_ihc')
                 AND m.measurement_date BETWEEN i.index_date - 30 AND i.index_date + 30
                 AND m.value_as_concept_id IN (SELECT concept_id FROM results.concept_set
                                               WHERE concept_set_name = 'result_positive'))
           AS c7_cldn18_positive,
       -- 8. PD-L1 CPS < 5.
       EXISTS (SELECT 1 FROM cdm.measurement m
               WHERE m.person_id = p.person_id
                 AND m.measurement_concept_id IN (SELECT concept_id FROM results.concept_set
                                                  WHERE concept_set_name = 'pdl1_cps')
                 AND m.measurement_date BETWEEN i.index_date - 30 AND i.index_date + 30
                 AND m.value_as_number < 5)
           AS c8_pdl1_cps_lt_5,
       -- 9. Not previously treated with CLDN18.2-targeted therapy before the index date.
       i.index_date IS NOT NULL AND NOT EXISTS (
           SELECT 1 FROM cdm.drug_exposure d
           WHERE d.person_id = p.person_id
             AND d.drug_concept_id IN (SELECT concept_id FROM results.concept_set
                                       WHERE concept_set_name = 'zolbetuximab')
             AND d.drug_exposure_start_date < i.index_date)
           AS c9_no_prior_cldn18_therapy
FROM cdm.person p
LEFT JOIN results.gc_index i ON i.person_id = p.person_id;

CREATE OR REPLACE VIEW results.gc_nct06177041_cohort AS
SELECT person_id, index_date
FROM results.gc_nct06177041_flags
WHERE c1_gastric_cancer AND c2_advanced AND c3_age_18_75 AND c4_ecog_0_1
  AND c5_no_recent_systemic_therapy AND c6_her2_negative AND c7_cldn18_positive
  AND c8_pdl1_cps_lt_5 AND c9_no_prior_cldn18_therapy;

CREATE OR REPLACE VIEW results.gc_nct06177041_attrition AS
WITH cum AS (
    SELECT person_id,
           c1_gastric_cancer AS k1,
           c1_gastric_cancer AND c2_advanced AS k2,
           c1_gastric_cancer AND c2_advanced AND c3_age_18_75 AS k3,
           c1_gastric_cancer AND c2_advanced AND c3_age_18_75 AND c4_ecog_0_1 AS k4,
           c1_gastric_cancer AND c2_advanced AND c3_age_18_75 AND c4_ecog_0_1
               AND c5_no_recent_systemic_therapy AS k5,
           c1_gastric_cancer AND c2_advanced AND c3_age_18_75 AND c4_ecog_0_1
               AND c5_no_recent_systemic_therapy AND c6_her2_negative AS k6,
           c1_gastric_cancer AND c2_advanced AND c3_age_18_75 AND c4_ecog_0_1
               AND c5_no_recent_systemic_therapy AND c6_her2_negative
               AND c7_cldn18_positive AS k7,
           c1_gastric_cancer AND c2_advanced AND c3_age_18_75 AND c4_ecog_0_1
               AND c5_no_recent_systemic_therapy AND c6_her2_negative
               AND c7_cldn18_positive AND c8_pdl1_cps_lt_5 AS k8,
           c1_gastric_cancer AND c2_advanced AND c3_age_18_75 AND c4_ecog_0_1
               AND c5_no_recent_systemic_therapy AND c6_her2_negative
               AND c7_cldn18_positive AND c8_pdl1_cps_lt_5
               AND c9_no_prior_cldn18_therapy AS k9
    FROM results.gc_nct06177041_flags
),
counts (step, description, n) AS (
    SELECT 0, 'Persons in the OMOP database',                  count(*)                       FROM cum
    UNION ALL SELECT 1, 'Gastric cancer diagnosis',            count(*) FILTER (WHERE k1) FROM cum
    UNION ALL SELECT 2, 'Advanced disease (stage 4 recorded)', count(*) FILTER (WHERE k2) FROM cum
    UNION ALL SELECT 3, 'Age 18-75 at index date',             count(*) FILTER (WHERE k3) FROM cum
    UNION ALL SELECT 4, 'ECOG 0-1',                            count(*) FILTER (WHERE k4) FROM cum
    UNION ALL SELECT 5, 'No systemic therapy in prior 180 days', count(*) FILTER (WHERE k5) FROM cum
    UNION ALL SELECT 6, 'HER2 negative',                       count(*) FILTER (WHERE k6) FROM cum
    UNION ALL SELECT 7, 'CLDN18 positive',                     count(*) FILTER (WHERE k7) FROM cum
    UNION ALL SELECT 8, 'PD-L1 CPS < 5',                       count(*) FILTER (WHERE k8) FROM cum
    UNION ALL SELECT 9, 'No prior CLDN18-targeted therapy',    count(*) FILTER (WHERE k9) FROM cum
)
SELECT step,
       description,
       n AS n_remaining,
       COALESCE(lag(n) OVER (ORDER BY step) - n, 0) AS n_lost
FROM counts
ORDER BY step;
