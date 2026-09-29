-- Runs once, on first start of an empty data volume.
-- cdm:     OMOP CDM v5.4 tables + vocabulary
-- native:  raw Synthea CSVs as loaded by ETL-Synthea (staging)
CREATE SCHEMA IF NOT EXISTS cdm;
CREATE SCHEMA IF NOT EXISTS native;
