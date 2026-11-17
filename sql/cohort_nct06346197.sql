-- Cohort C-005: NCT06346197 (1L MSI-H/dMMR, HER2-negative, PD-L1 CPS >= 5 gastric/GEJ).
--
-- Index date = first stage 4 record of the person. Evaluates evaluable criteria of NCT06346197
-- on the OMOP database (needs 01_concept_sets.sql):
--   gc_nct06346197_flags       one row per person, one boolean per criterion
--   gc_nct06346197_cohort      persons meeting every criterion
--   gc_nct06346197_attrition   cumulative attrition table

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

CREATE OR REPLACE VIEW results.gc_nct06346197_flags AS
SELECT p.person_id,
       i.index_date,
       -- 1. Gastric / GEJ adenocarcinoma diagnosis.
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
       -- 4. ECOG 0-1.
       EXISTS (SELECT 1 FROM cdm.measurement m
               WHERE m.person_id = p.person_id
                 AND m.measurement_concept_id IN (SELECT concept_id FROM results.concept_set
                                                  WHERE concept_set_name = 'ecog')
                 AND m.measurement_date BETWEEN i.index_date - 30 AND i.index_date + 30
                 AND m.value_as_number <= 1)
           AS c4_ecog_0_1,
       -- 5. No prior systemic therapy in the 180 days before the index date (6-month washout
       --    after adjuvant/neoadjuvant chemotherapy).
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
       -- 7. PD-L1 CPS >= 5.
       EXISTS (SELECT 1 FROM cdm.measurement m
               WHERE m.person_id = p.person_id
                 AND m.measurement_concept_id IN (SELECT concept_id FROM results.concept_set
                                                  WHERE concept_set_name = 'pdl1_cps')
                 AND m.measurement_date BETWEEN i.index_date - 30 AND i.index_date + 30
                 AND m.value_as_number >= 5)
           AS c7_pdl1_cps_ge_5,
       -- 8. MSI-H / dMMR (MSI positive).
       EXISTS (SELECT 1 FROM cdm.measurement m
               WHERE m.person_id = p.person_id
                 AND m.measurement_concept_id IN (SELECT concept_id FROM results.concept_set
                                                  WHERE concept_set_name = 'msi')
                 AND m.measurement_date BETWEEN i.index_date - 30 AND i.index_date + 30
                 AND m.value_as_concept_id IN (SELECT concept_id FROM results.concept_set
                                               WHERE concept_set_name = 'result_positive'))
           AS c8_msi_high,
       -- 9. Claudin 18.2 status known and documented before inclusion.
       EXISTS (SELECT 1 FROM cdm.measurement m
               WHERE m.person_id = p.person_id
                 AND m.measurement_concept_id IN (SELECT concept_id FROM results.concept_set
                                                  WHERE concept_set_name = 'cldn18_ihc')
                 AND m.measurement_date BETWEEN i.index_date - 30 AND i.index_date + 30
                 AND m.value_as_concept_id IN (SELECT concept_id FROM results.concept_set
                                               WHERE concept_set_name IN ('result_positive', 'result_negative')))
           AS c9_cldn18_documented
FROM cdm.person p
LEFT JOIN results.gc_index i ON i.person_id = p.person_id;

CREATE OR REPLACE VIEW results.gc_nct06346197_cohort AS
SELECT person_id, index_date
FROM results.gc_nct06346197_flags
WHERE c1_gastric_cancer AND c2_advanced AND c3_adult AND c4_ecog_0_1
  AND c5_no_recent_systemic_therapy AND c6_her2_negative AND c7_pdl1_cps_ge_5
  AND c8_msi_high AND c9_cldn18_documented;

CREATE OR REPLACE VIEW results.gc_nct06346197_attrition AS
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
               AND c7_pdl1_cps_ge_5 AS k7,
           c1_gastric_cancer AND c2_advanced AND c3_adult AND c4_ecog_0_1
               AND c5_no_recent_systemic_therapy AND c6_her2_negative
               AND c7_pdl1_cps_ge_5 AND c8_msi_high AS k8,
           c1_gastric_cancer AND c2_advanced AND c3_adult AND c4_ecog_0_1
               AND c5_no_recent_systemic_therapy AND c6_her2_negative
               AND c7_pdl1_cps_ge_5 AND c8_msi_high
               AND c9_cldn18_documented AS k9
    FROM results.gc_nct06346197_flags
),
counts (step, description, n) AS (
    SELECT 0, 'Persons in the OMOP database',                  count(*)                       FROM cum
    UNION ALL SELECT 1, 'Gastric cancer diagnosis',            count(*) FILTER (WHERE k1) FROM cum
    UNION ALL SELECT 2, 'Advanced disease (stage 4 recorded)', count(*) FILTER (WHERE k2) FROM cum
    UNION ALL SELECT 3, 'Adult (>= 18) at index date',         count(*) FILTER (WHERE k3) FROM cum
    UNION ALL SELECT 4, 'ECOG 0-1',                            count(*) FILTER (WHERE k4) FROM cum
    UNION ALL SELECT 5, 'No systemic therapy in prior 180 days', count(*) FILTER (WHERE k5) FROM cum
    UNION ALL SELECT 6, 'HER2 negative',                       count(*) FILTER (WHERE k6) FROM cum
    UNION ALL SELECT 7, 'PD-L1 CPS >= 5',                      count(*) FILTER (WHERE k7) FROM cum
    UNION ALL SELECT 8, 'MSI-H / dMMR',                        count(*) FILTER (WHERE k8) FROM cum
    UNION ALL SELECT 9, 'CLDN18 status documented',            count(*) FILTER (WHERE k9) FROM cum
)
SELECT step,
       description,
       n AS n_remaining,
       COALESCE(lag(n) OVER (ORDER BY step) - n, 0) AS n_lost
FROM counts
ORDER BY step;
