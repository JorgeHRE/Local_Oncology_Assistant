# ETL Synthea → OMOP CDM v5.4

Construye la base OMOP en PostgreSQL a partir de los CSV de Synthea y los vocabularios de Athena,
con el paquete oficial **ETL-Synthea** de OHDSI. Ver ADR-0001.

## Versiones fijadas

| Componente | Versión |
|---|---|
| PostgreSQL | `postgres:16.15` |
| R | `rocker/r-ver:4.5.3` (CRAN fijado a una fecha por rocker) |
| ETL-Synthea (`ETLSyntheaBuilder`) | tag `v2.1.1` |
| CommonDataModel | tag `v5.4.3` |
| Synthea (datos de entrada) | v3.3.0 (ver `synthea/README.md`) |
| Vocabularios | Athena, versión "v5.0 29-AUG-26" (ver ADR-0001) |

## Requisitos previos

1. `cp .env.example .env` y poner una contraseña real. `.env` está en `.gitignore`.
2. CSV de Synthea en `data/raw/synthea/output/csv/` (ver `synthea/README.md`).
3. Vocabularios de Athena descomprimidos en `data/raw/vocab/extracted/`:

   ```bash
   unzip data/raw/vocab/vocabulary_download_v5_*.zip -d data/raw/vocab/extracted
   ```

## Ejecución

```bash
docker compose up -d db                        # PostgreSQL; crea los esquemas cdm y native
docker compose --profile etl build etl         # solo la primera vez
docker compose --profile etl run --rm etl      # corre etl/run_etl_synthea.R
```

Esquemas resultantes: `cdm` (tablas OMOP y vocabulario) y `native` (CSV de Synthea en crudo,
usados como tablas intermedias).

Para empezar de cero, se borra el volumen: `docker compose down -v`. **Esto destruye la base.**

## Pasos después del ETL

ETL-Synthea v2.1.1 no llena `measurement.value_as_concept_id` (ver ADR-0001, Fase 2b). Después de
cada corrida del ETL:

```bash
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' \
  < etl/post_etl/01_value_as_concept.sql
```

El script mapea el texto del valor (p. ej., "Positive (qualifier value)") a su código SNOMED y de
ahí, vía "Maps to", al concepto estándar de dominio `Meas Value`. Es idempotente y aborta sin cambios
si algún código no llega a exactamente un concepto estándar. Los subestadios (1A, 2B…) y las
categorías TNM quedan en 0 porque no tienen concepto estándar en SNOMED.

Test (necesita la base arriba; se salta si no hay conexión):

```bash
pip install -e ".[db]"
pytest -m db
```
