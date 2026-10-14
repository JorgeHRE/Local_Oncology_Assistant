# Local Oncology Assistant — RAG biomédico y cohorte OMOP

Asistente local de tamizaje de elegibilidad clínica para **cáncer gástrico**. Toma criterios de
inclusión/exclusión de protocolos y guías (RAG sobre texto no estructurado) y los traduce a consultas
SQL sobre una base de pacientes **sintéticos** en OMOP CDM v5.4. Todo corre en local: ningún dato sale
de la máquina.

> **Estado:** en desarrollo. Hecho: generación de pacientes sintéticos (módulo de Synthea propio),
> base OMOP en Docker, verificación de códigos y CI. Pendiente: corpus RAG, NL2SQL, cohorte con tabla
> de atrición y evaluación. Detalle en `CLAUDE.md` §11.

## Requisitos

- Linux o macOS con **Docker** (con Compose v2) y **make**. No hace falta instalar Python, R ni Java.
- ~35 GB libres en disco (medido: base OMOP 23 GB, vocabulario 3,6 GB, datos de Synthea 3 GB,
  imágenes ~3 GB). La RAM no está probada fuera de la máquina de desarrollo (48 GB): `compose.yml` fija
  `shared_buffers=4GB` y `maintenance_work_mem=2GB` para la carga; con menos RAM habría que bajarlos.
- Una cuenta gratuita en [Athena (OHDSI)](https://athena.ohdsi.org) para el vocabulario (ver abajo).

## Descargas manuales (una sola vez)

El vocabulario de Athena no es redistribuible, así que cada persona lo descarga con su cuenta.

1. En Athena → *Download*, pedir los vocabularios **SNOMED, LOINC, RxNorm, RxNorm Extension, CVX**
   (UCUM se añade solo). Este proyecto usa la versión "v5.0 29-AUG-26" (ver ADR-0001).
2. Poner el zip en `data/raw/vocab/` y descomprimirlo:

   ```bash
   unzip data/raw/vocab/vocabulary_download_v5_*.zip -d data/raw/vocab/extracted
   ```

El jar de Synthea sí se descarga solo (`make synthea-jar`, con verificación de SHA-256).

## Reproducir el trabajo

```bash
make env            # crea .env; edita POSTGRES_PASSWORD
make build          # imagen de Python para tests y herramientas
make module         # regenera el módulo gástrico y verifica sus códigos (necesita la base cargada)
make generate       # Synthea: ~1 300 registros (SYNTHEA_POP=650 vivos), unos 10–20 min
make db             # PostgreSQL
make etl            # CSV de Synthea + vocabulario -> OMOP, ~50 min; necesita base VACÍA
make post-etl       # value_as_concept_id
make test           # todos los tests
```

- `make help` lista todos los comandos.
- El ETL exige una base vacía. Para empezar de cero: `make reset-db` (**borra la base**, pide
  confirmación).
- `make module` consulta el vocabulario, así que solo funciona con la base cargada. Sin ella,
  `make test-fast` corre lo que corre el CI.
- Los datos generados y el vocabulario quedan en `data/raw/` (ignorado por git).

## Estructura

| Ruta | Contenido |
|---|---|
| `synthea/` | Módulo GMF de cáncer gástrico (`build_gastric_cancer.py` lo genera) y keep module |
| `etl/` | ETL-Synthea (R, en Docker), índices del CDM y pasos posteriores al ETL |
| `src/oncology_assistant/` | Paquete Python (conexión a la base, verificador de códigos de módulos) |
| `tests/` | pytest; la marca `db` pide la base OMOP cargada |
| `docs/` | Alcance clínico, ADRs, diccionario de datos (`features.md`), limitaciones |
| `CLAUDE.md` | Contexto y estado del proyecto |

## Datos y privacidad

Solo datos sintéticos (Synthea). Sin credenciales en el repo: `.env` está en `.gitignore` y
`.env.example` solo trae nombres de variables. El uso de asistentes de IA se declarará en
`docs/USO_DE_IA.md` (pendiente).

## Flujo de trabajo

`main` está protegido: todo cambio entra por PR con el CI (ruff y pytest en Python 3.10 y 3.12) en
verde. Los tests con marca `db` necesitan el vocabulario de Athena y por eso no corren en CI.

## Limitaciones

Ver `docs/LIMITACIONES.md` (por ejemplo, CLDN18.2 se aproxima con el código LOINC de Claudina 18).
