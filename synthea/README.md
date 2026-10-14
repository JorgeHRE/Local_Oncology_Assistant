# Configuración de Synthea

Archivos de configuración versionados para generar la población sintética (ver ADR-0001).
Aquí solo va configuración; los datos generados van en `data/raw/synthea/`, que git ignora.

| Ruta | Contenido |
|---|---|
| `keep/` | *Keep modules*: filtros que conservan solo a los pacientes que cumplen una condición |
| `build_gastric_cancer.py` | Genera `modules/gastric_cancer.json` (las probabilidades están en `PARAMS`) |
| `modules/` | Módulo GMF propio de cáncer gástrico (generado; no editar a mano) |

## Versión fijada

- **Synthea v3.3.0**, la más alta que acepta ETL-Synthea v2.1.1.
- Jar: `synthea-with-dependencies.jar` del release v3.3.0,
  SHA-256 `8ba04f7d73abadd5a377e41edf24c5c83935a1cb07c6d982cd5db731ef1cf445`.

## Spike `breast_cancer` (2026-09-28)

Se corre desde la raíz del repo. Supone que el jar está en `data/raw/synthea/`.

```bash
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/work -w /work eclipse-temurin:17-jre \
  java -jar data/raw/synthea/synthea-with-dependencies-v3.3.0.jar \
  -s 42 -cs 42 -r 20260901 -p 200 -g F -a 40-85 \
  -k synthea/keep/keep_breast_cancer.json \
  --generate.thread_pool_size=1 \
  --exporter.baseDirectory=./data/raw/synthea/output \
  --exporter.csv.export=true --exporter.fhir.export=false \
  --exporter.years_of_history=0 \
  Massachusetts
```

Resultado esperado: 264 registros (200 vivas, 64 fallecidas), con los CSV idénticos a
`data/raw/synthea/output/SHA256SUMS`. Tarda unos 10 min.

**No quites `--generate.thread_pool_size=1`.** Con varios hilos, la misma semilla produce una
población distinta en cada corrida (ver ADR-0001). Para verificar una regeneración:

```bash
cd data/raw/synthea/output && sha256sum -c SHA256SUMS
```

## Módulo `gastric_cancer`

Regenerar el módulo tras cambiar `PARAMS` (un test comprueba que el JSON versionado coincide):

```bash
python synthea/build_gastric_cancer.py
python -m oncology_assistant.synthea_codes synthea/modules/gastric_cancer.json
```

Generar la población (objetivo: 1 000–1 500 pacientes con cáncer gástrico). `-p` cuenta solo a los
**vivos**: los fallecidos se suman (≈ 1:1), así que `-p 650` da ≈ 1 300 registros.

```bash
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/work -w /work eclipse-temurin:17-jre \
  java -jar data/raw/synthea/synthea-with-dependencies-v3.3.0.jar \
  -s 42 -cs 42 -r 20260901 -p 650 -a 36-85 \
  -d synthea/modules -k synthea/keep/keep_gastric_cancer.json \
  --generate.thread_pool_size=1 \
  --exporter.baseDirectory=./data/raw/synthea/output_gastric \
  --exporter.csv.export=true --exporter.fhir.export=false \
  --exporter.years_of_history=0 \
  Massachusetts
```

- `-d synthea/modules` carga el módulo propio; `-k` conserva solo a quienes tienen el diagnóstico.
- **`-a 36-85`, no `30-85`:** el módulo dispara entre 2021 y 2023 y la edad al diagnóstico es 2,7–5,7
  años menor que la de generación. Con un mínimo bajo, Synthea reintenta 1 000 veces la misma
  demografía y aborta.
- Edad y sexo no se pueden reponderar desde el módulo (ver `docs/alcance-clinico-modulo-gastrico.md` §8).
- Pruebas hechas el 2026-10-14: 60 pacientes vivos en ≈ 46 s (≈ 120 registros, 69 % avanzados).
