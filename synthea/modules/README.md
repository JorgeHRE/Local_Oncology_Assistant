# Módulos GMF propios

Aquí van los módulos de Synthea escritos para este proyecto (p. ej., `gastric_cancer.json`). Ver
ADR-0001 y `docs/alcance-clinico-modulo-gastrico.md`.

**Regla (ADR-0001):** todo código que emita un módulo debe ser un concepto estándar, o tener
"Maps to" hacia uno, en el vocabulario cargado; ETL-Synthea descarta el resto sin avisar. Los valores
codificados (`value_code`) deben estar además en el mapa de `etl/post_etl/01_value_as_concept.sql`.

Verificación antes de generar datos (necesita la base OMOP arriba):

```bash
python -m oncology_assistant.synthea_codes synthea/modules/*.json
pytest -m db tests/test_synthea_codes.py   # corre la misma regla sobre cada JSON de esta carpeta
```
