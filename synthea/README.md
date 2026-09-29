# Configuración de Synthea

Archivos de configuración versionados para generar la población sintética (ver ADR-0001).
Aquí solo va configuración; los datos generados van en `data/raw/synthea/`, que git ignora.

| Ruta | Contenido |
|---|---|
| `keep/` | *Keep modules*: filtros que conservan solo a los pacientes que cumplen una condición |
| `modules/` | (pendiente) módulo GMF propio de cáncer gástrico |

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
