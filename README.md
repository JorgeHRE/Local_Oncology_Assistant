# Local Oncology Assistant — RAG biomédico y cohortes OMOP

Asistente **local** de tamizaje de elegibilidad clínica para **cáncer gástrico**. Responde preguntas sobre los
criterios de inclusión y exclusión de ensayos clínicos (RAG sobre 88 documentos, con **citas verificadas contra
el texto**) y cuenta cuántos pacientes **sintéticos** de una base OMOP CDM v5.4 cumplen los criterios de un
ensayo. Todo corre en tu máquina: ningún dato sale de ella para generar respuestas.

> **Prototipo de investigación, no un dispositivo médico.** No debe usarse para decisiones clínicas ni con datos
> de pacientes reales: ver [`docs/POLITICA_DE_USO.md`](docs/POLITICA_DE_USO.md) y
> [`docs/LIMITACIONES.md`](docs/LIMITACIONES.md).

## Qué hace

```text
$ make ask Q="What is the required PD-L1 CPS in trial NCT06346197?"
The required PD-L1 CPS in trial NCT06346197 is ≥ 5. ...
Sources:
  [1] ct:NCT06346197 (ok in the passage) "Patient with MSI-H/dMMR, HER2 negative ... CPS) ≥ 5."

$ make ask Q="How many patients are eligible for NCT06177041?"
Cohort of NCT06177041 in the synthetic OMOP database: 71 patients meet the criteria that the data can check.
Filters applied (attrition): ...
```

- **Preguntas sobre el texto de los ensayos** → recuperación híbrida (BM25 + vectores) con reformulación de la
  pregunta, respuesta de un LLM local y verificación de cada cita ("ok in the passage" o "NOT FOUND").
- **Preguntas por pacientes de un ensayo** ("which patients…", "how many patients…") → recuento exacto desde las
  vistas SQL de cohorte, con su tabla de atrición. El LLM no escribe SQL ni toca los números.
- Las dos rutas se eligen por palabras clave (en inglés) y el NCT de la pregunta.

### Caso de uso: repetir un estudio con otra cohorte

Los criterios de elegibilidad de cada ensayo viven en SQL versionado sobre OMOP (`sql/`), no dentro del modelo de
lenguaje. Por eso la misma definición de cohorte se puede volver a ejecutar sobre otra población OMOP y comparar los
resultados, con su tabla de atrición, que dice cuántos pacientes se pierden en cada filtro y por qué. Repetir un
estudio de viabilidad con cohortes distintas es una tarea habitual en investigación clínica.

Esto es una propiedad de diseño, **no está probada**: solo se ha ejecutado contra la población sintética de
Synthea, y los *concept sets* (por ejemplo CLDN18.2 ≈ LOINC 105011-1) pueden no coincidir con la codificación de
datos reales. Ver [`docs/LIMITACIONES.md`](docs/LIMITACIONES.md).

**Estado (2026-11-19):** corpus, índice, ground truth de 40 preguntas, 8 cohortes, asistente (CLI e interfaz
web local con Streamlit) y evaluaciones hechos. Resultados y límites en [`docs/protocolo.md`](docs/protocolo.md) §7 y en
[`eval/results/`](eval/results/). Pendiente: la re-anotación a ciegas del ground truth.

## Requisitos

- **Linux x86_64** con **Docker** (Compose v2), **make**, **Python ≥ 3.10**, `curl` y `zstd`.
  En Ubuntu/Debian: `sudo apt install make python3 python3-venv curl zstd` (sin `python3-venv`, `make venv` falla).
- **GPU NVIDIA con 12 GB de VRAM** (desarrollado en una RTX 5070). El LLM (qwen3:8b, ~5,6 GB) y el modelo
  de embeddings (bge-m3, ~1,2 GB) caben a la vez. Sin GPU (probado en un contenedor Ubuntu 24.04 solo con CPU) la ruta rápida funciona: una
  respuesta tardó ~38 s y construir el índice ~7 min, en lugar de ~30 s.
- ~35 GB libres para la base OMOP completa (base 23 GB, vocabulario 3,6 GB, datos de Synthea 3 GB, imágenes
  ~3 GB) y ~8 GB más para los modelos. La RAM solo se probó en la máquina de desarrollo (48 GB): `compose.yml`
  fija `shared_buffers=4GB` y `maintenance_work_mem=2GB`; con menos RAM habría que bajarlos.
- Una cuenta gratuita en [Athena (OHDSI)](https://athena.ohdsi.org) para el vocabulario (solo si construyes
  la base OMOP; ver abajo).

La ruta completa (Docker, ETL) y la descarga real de los modelos solo se probaron en la máquina de desarrollo. La ruta
rápida también se probó el 18 de noviembre de 2026 en un clon limpio y en un contenedor Ubuntu 24.04 sin GPU.

## Ruta rápida: solo el asistente sobre los textos (sin Docker ni base de datos)

Sirve para probar el RAG sin esperar al ETL de ~70 min. Las preguntas por pacientes necesitan la base (ruta
completa).

```bash
make venv             # .venv con las dependencias (la 1.ª vez descarga paquetes, incl. chromadb)
.venv/bin/python -m oncology_assistant.corpus fetch   # baja los 39 resúmenes de PubMed (las 49 fichas de ClinicalTrials.gov ya están en el repo)
make ollama-install   # Ollama 0.40.4 en data/raw/engines/ (SHA-256 verificado)
make llm-pull         # arranca Ollama y baja qwen3:8b (~5 GB) y bge-m3 (~1 GB)
make index-embed      # embeddings de los fragmentos con bge-m3 -> data/processed/chroma_bge-m3 (~30 s con GPU; ~7 min solo con CPU)
make ask Q="What is the HER2 requirement in trial NCT06123494?"
```

`corpus fetch` actualiza la fecha de descarga (`retrieved_at`) en `corpus/manifest.json`, así que git lo mostrará
modificado; es esperado y no cambia los hashes. Sin el paso del corpus, el índice solo tendría las 49 fichas del repositorio y las preguntas basadas en los
resúmenes de PubMed no se podrían responder. `make llm-up` / `make llm-down` arrancan y paran el servidor del
LLM (puerto 11500, en segundo plano). `make ask-text Q="…"` muestra además los fragmentos recuperados.

### Interfaz web local (opcional, Streamlit)

Para usar el asistente desde el navegador en lugar de la consola (solo en `127.0.0.1`, sin telemetría):

```bash
.venv/bin/pip install -e ".[ui]"   # instala Streamlit una sola vez (extra opcional)
make ui                             # abre http://127.0.0.1:8501
```

La interfaz consume directamente `assistant.ask()`, muestra si cada respuesta vino de una cohorte OMOP (con tabla de atrición) o del RAG (con citas verificadas y fragmentos desplegables) e incluye preguntas de demostración en inglés.

## Ruta completa: datos sintéticos, OMOP y cohortes

### Descargas manuales (una sola vez)

El vocabulario de Athena no es redistribuible, así que cada persona lo descarga con su cuenta.

1. En Athena → *Download*, pedir los vocabularios **SNOMED, LOINC, RxNorm, RxNorm Extension, CVX**
   (UCUM se añade solo). Este proyecto usa la versión "v5.0 29-AUG-26" (ver ADR-0001).
2. Poner el zip en `data/raw/vocab/` y descomprimirlo:

   ```bash
   unzip data/raw/vocab/vocabulary_download_v5_*.zip -d data/raw/vocab/extracted
   ```

El jar de Synthea sí se descarga solo (`make synthea-jar`, con verificación de SHA-256).

### Pasos

```bash
make env            # crea .env; edita POSTGRES_PASSWORD
make build          # imagen de Python para tests y herramientas
make module         # regenera el módulo gástrico y verifica sus códigos (necesita la base cargada)
make generate       # Synthea: ~1 360 registros (SYNTHEA_POP=650 vivos), unos 4 min
make db             # PostgreSQL
make etl            # CSV de Synthea + vocabulario -> OMOP, ~50–70 min; necesita base VACÍA
make post-etl       # value_as_concept_id
make cohort         # conjuntos de conceptos y las 8 cohortes (una vista SQL por ensayo)
make attrition      # tabla de atrición de la cohorte piloto de zolbetuximab
make test           # todos los tests (los de marca db necesitan la base cargada)
```

Después, la parte del asistente (ruta rápida arriba). Con la base encendida (`make db`), las preguntas por
pacientes de uno de los 8 ensayos con cohorte se responden desde OMOP.

- `make help` lista todos los comandos.
- El ETL exige una base vacía. Para empezar de cero: `make reset-db` (**borra la base**, pide confirmación).
- `make module` consulta el vocabulario, así que solo funciona con la base cargada. Sin ella,
  `make test-fast` corre lo que corre el CI.
- Los datos generados y el vocabulario quedan en `data/raw/` (ignorado por git).

## Cómo leer las respuestas

| Salida | Significa |
|---|---|
| Fuente "ok in the passage" | La cita es una copia literal del fragmento (no garantiza que respalde la afirmación) |
| Fuente "NOT FOUND" / aviso "do not trust" | La cita no es literal: no usar la respuesta |
| "The retrieved passages do not contain the answer" | No se recuperó la evidencia o el modelo se negó; no prueba que el dato no exista |
| "Cohort of NCT…: N patients" | Recuento sobre datos sintéticos con los criterios que los datos pueden comprobar: un límite superior |
| "There is no cohort defined for NCT…" | Solo hay cohorte para 8 ensayos; la lista aparece en el mensaje |

Las preguntas del ground truth están en inglés; una pregunta por pacientes **en español** no se enruta a
cohortes (ver `docs/LIMITACIONES.md`).

## Evaluación

El ground truth (40 preguntas: 20 R, 12 E, 8 C) está en `eval/ground_truth/` y lo anotó el autor sin ningún
LLM para el contenido; la metodología está en [`docs/adr/0003-metodologia-de-ground-truth.md`](docs/adr/0003-metodologia-de-ground-truth.md)
y la guía en [`docs/guia-anotacion.md`](docs/guia-anotacion.md).

Los comandos con `gt-validate` y `test` corren en el contenedor de Python (`make env` y `make build` antes, y
arrancan Postgres como dependencia). Los `eval-*` y `review-evaluable` corren en `.venv` (`make venv`) y los
`eval-*` necesitan Ollama (`make llm-up`).

```bash
make gt-validate-final                  # esquema, citas literales y partición; exige las cuotas exactas
make eval-retrieval                     # recall@k de las R (por defecto en desarrollo)
make eval-generation                    # compara los LLM candidatos con los mismos fragmentos
make eval-extraction                    # compara los LLM extrayendo criterios (~5 min)
make review-evaluable                   # lista criterios cuyo flag `evaluable` puede contradecir la guía
```

- Las evaluaciones con modelo usan la GPU y no corren en el CI (el CI usa modelos falsos).
- **El conjunto de prueba ya se usó una vez** (`eval/results/test_2026-11-17.md`, con la configuración fijada de
  antemano). No lo uses para iterar; cualquier cambio posterior se mide en desarrollo.
- Los archivos de revisión de las evaluaciones de desarrollo se escriben en `data/processed/` y no se versionan.

## Estructura

| Ruta | Contenido |
|---|---|
| `synthea/` | Módulo GMF de cáncer gástrico (`build_gastric_cancer.py` lo genera) y keep module |
| `etl/` | ETL-Synthea (R, en Docker), índices del CDM y pasos posteriores al ETL |
| `sql/` | Conjuntos de conceptos, cohorte piloto de zolbetuximab y una cohorte SQL por ensayo (`cohort_*.sql`) |
| `corpus/` | Selección, manifiesto (SHA-256) y las fichas recortadas de ClinicalTrials.gov |
| `src/oncology_assistant/` | Paquete: `assistant.py` (enrutado), `ui.py` (interfaz web local con Streamlit), `rag.py`, `hybrid.py`, `embedders.py`, `cohorts.py`, `chunking.py`, `index.py`, `corpus.py`, `ground_truth.py` y las evaluaciones (`eval_*.py`) |
| `tests/` | pytest; la marca `db` pide la base OMOP cargada |
| `eval/` | Ground truth, resultados versionados (`results/`) y la prueba de motores (`spike/`) |
| `docs/` | Protocolo, ADR, diccionario de datos, guía de anotación, limitaciones, política de uso y uso de IA |
| `CLAUDE.md` | Contexto y estado del proyecto |

## Documentos clave

- [`docs/protocolo.md`](docs/protocolo.md): protocolo v2 con las cuatro decisiones (LLM, motor, ground truth, evaluación).
- [`docs/adr/`](docs/adr/): decisiones de arquitectura (datos, evaluación, ground truth, motor, LLM, chunking, embeddings).
- [`docs/LIMITACIONES.md`](docs/LIMITACIONES.md) y [`docs/POLITICA_DE_USO.md`](docs/POLITICA_DE_USO.md).
- [`docs/USO_DE_IA.md`](docs/USO_DE_IA.md): qué asistentes de IA se usaron, qué hizo cada uno y las licencias de los modelos.

## Motor de inferencia

El LLM corre **nativo** con Ollama (no en Docker: el runtime de NVIDIA no está configurado en `compose.yml`),
con las versiones fijadas del [ADR-0004](docs/adr/0004-motor-de-inferencia.md). Los binarios y modelos quedan en
`data/raw/engines/` (ignorado por git). El asistente usa **qwen3:8b** ([ADR-0005](docs/adr/0005-modelo-de-lenguaje.md))
y **bge-m3** ([ADR-0007](docs/adr/0007-modelo-de-embeddings.md)); las variables `RAG_MODEL` y `RAG_EMBEDDER`
cambian el modelo. `make llm-pull MODELS="gemma3:12b medgemma:4b"` baja los candidatos comparados (licencias
propias de Google: `docs/USO_DE_IA.md` §3).

## Datos y privacidad

Solo datos sintéticos (Synthea), fichas de ClinicalTrials.gov (con atribución, `docs/corpus.md`) y resúmenes de
PubMed (no versionados). Sin credenciales en el repo: `.env` está en `.gitignore` y `.env.example` solo trae
nombres de variables. El uso de asistentes de IA (Gemini y Claude Code) está declarado en
[`docs/USO_DE_IA.md`](docs/USO_DE_IA.md).

## Flujo de trabajo

`main` está protegido: todo cambio entra por PR con el CI (ruff y pytest en Python 3.10 y 3.12) en verde. Los
tests con marca `db` necesitan el vocabulario de Athena y por eso no corren en CI.

## Licencia

El código y los documentos propios de este proyecto se publican bajo la **licencia Apache-2.0** (ver
[`LICENSE`](LICENSE) y [`NOTICE`](NOTICE)). Los textos de terceros incluidos en el corpus (fichas de
ClinicalTrials.gov y resúmenes de PubMed) **no** pasan a Apache-2.0: conservan sus propios términos, descritos en
[`docs/corpus.md`](docs/corpus.md). Las licencias de los modelos y de las herramientas que usa están en
`docs/USO_DE_IA.md` §3.
