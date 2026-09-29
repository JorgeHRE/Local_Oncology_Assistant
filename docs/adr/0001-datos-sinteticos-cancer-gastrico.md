# ADR-0001: Estrategia de datos sintéticos para cáncer gástrico

- **Estado:** Propuesto. La Fase 2 del spike está completa (ver abajo); pasa a *Aceptado* cuando se
  cierren las preguntas abiertas de estadio y CLDN18.2.
- **Fecha:** 2026-09-28
- **Decisores:** Jorge (autor), con asistencia de Claude Code
- **Relacionado:** `docs/protocolo.md`, hito de la Sesión 18 (cohorte + tabla de atrición)

## Contexto

La cohorte del proyecto necesita pacientes sintéticos con **adenocarcinoma gástrico avanzado**, sus
**biomarcadores** (HER2, CLDN18.2, MSI-H/dMMR, PD-L1) y **tratamientos** coherentes con ellos, cargados
en **OMOP CDM v5.4**. Sin esto, la cohorte de la Sesión 18 queda vacía y el ground truth de nivel (b)
(conjunto exacto de `person_id` elegibles) no se puede construir.

Restricciones:

- Solo datos sintéticos (sección 7 del `CLAUDE.md`).
- La ruta de datos ya elegida es Synthea → ETL-Synthea → OMOP CDM v5.4 en PostgreSQL.
- Todo debe ser reproducible: versión fija, semilla fija y fecha de referencia fija.

Hasta donde revisamos, **Synthea no incluye un módulo de cáncer gástrico** y **Eunomia (GiBleed) no
contiene** estos diagnósticos ni biomarcadores.

## Opciones consideradas

### (a) Módulo GMF propio de Synthea

Escribir un módulo en el Generic Module Framework (máquina de estados en JSON) que modele el
diagnóstico, la estadificación, los biomarcadores y el tratamiento. Se usaría como plantilla el módulo
`breast_cancer`, que ya incluye biomarcadores con tratamiento condicionado al resultado.

- ✅ Synthea genera las visitas, las fechas y los vínculos entre registros, así que la coherencia
  visita ↔ observación ↔ fármaco sale "gratis" (verificado en el spike, ver abajo).
- ✅ Los pacientes gástricos tienen además historia clínica completa (comorbilidades, otros fármacos,
  visitas no oncológicas), lo que hace realista la tabla de atrición.
- ✅ Pasa por ETL-Synthea sin código de ETL propio.
- ⚠️ Hay que aprender el GMF; esfuerzo estimado de 1 a 2 semanas.
- ⚠️ Cada código debe existir en los vocabularios OMOP y mapear a un concepto estándar.
- ⚠️ Los conteos son probabilísticos: reproducibles con semilla, pero no se fijan exactos.

### (b) Synthea estándar + inyección de pacientes con un script propio

Generar una población con Synthea estándar y agregar pacientes gástricos con un script Python de
semilla fija, escribiendo directamente en el CSV de Synthea o en las tablas OMOP.

- ✅ Control exacto de los conteos (p. ej., exactamente N pacientes HER2+).
- ❌ El script tiene que reproducir a mano la integridad referencial y temporal:
  `observation_period`, `visit_occurrence`, el orden diagnóstico → biopsia → biomarcador → fármaco,
  y los IDs sin colisiones con los del ETL. En la práctica es reimplementar parte de Synthea.
- ❌ Los errores de integridad no fallan de forma ruidosa: `drug_exposure.visit_occurrence_id`
  admite nulos, así que un vínculo roto no rompe el ETL, pero sesga la cohorte en silencio.
- ❌ Los pacientes inyectados no tienen el resto de su historia clínica, salvo que también se genere.

### (c) Solo Eunomia / datos de ejemplo existentes

- ❌ No contiene la enfermedad ni los biomarcadores. Descartada.

## Decisión (propuesta)

**Opción (a): módulo GMF propio**, construido a partir de la estructura de `breast_cancer`.

**Versión fijada: Synthea v3.3.0.** ETL-Synthea v2.1.1 (la más reciente, 2026-03-23) solo acepta las
versiones de Synthea 2.7.0 y 3.0.0–3.3.0. Synthea v4.0.0 existe, pero haría fallar el ETL.

## Evidencia: spike con `breast_cancer` (2026-09-28)

**Objetivo:** confirmar que Synthea vincula los biomarcadores y los fármacos a visitas reales y con
un orden temporal coherente, antes de invertir en el módulo gástrico.

**Configuración** (en Docker, `eclipse-temurin:17-jre`):

```bash
java -jar synthea-with-dependencies.jar \
  -s 42 -cs 42 -r 20260901 -p 200 -g F -a 40-85 \
  -k synthea/keep/keep_breast_cancer.json \
  --generate.thread_pool_size=1 \
  --exporter.csv.export=true --exporter.fhir.export=false \
  --exporter.years_of_history=0 \
  Massachusetts
```

- Jar de la versión v3.3.0, SHA-256 `8ba04f7d73abadd5a377e41edf24c5c83935a1cb07c6d982cd5db731ef1cf445`.
- `-k synthea/keep/keep_breast_cancer.json` es un *keep module* que conserva solo pacientes con el diagnóstico
  SNOMED 254837009.
- `--exporter.years_of_history=0` exporta el historial completo. Por defecto Synthea exporta solo
  10 años y cortaría diagnósticos antiguos.
- `--generate.thread_pool_size=1` es **obligatorio para la reproducibilidad** (ver abajo).

**Reproducibilidad: la semilla no basta.** Con la configuración por defecto (`thread_pool_size = -1`,
un hilo por núcleo), dos corridas con la misma semilla dieron resultados distintos (263 vs. 264
registros y CSV con distinto hash). La causa es que los pacientes comparten estado (proveedores,
aseguradoras), y con varios hilos el orden de acceso depende de la planificación del sistema
operativo. Con un solo hilo, dos corridas independientes produjeron los **18 CSV idénticos byte a
byte**. Costo: unos 10 min en lugar de 1 min 41 s para esta población. Los hashes de la salida de
referencia se guardan en `data/raw/synthea/output/SHA256SUMS`.

**Resultados de la Fase 1 (CSV de Synthea):**
264 registros (200 vivas, 64 fallecidas), corrida de un solo hilo.

| Verificación | Resultado |
|---|---|
| Pacientes con el diagnóstico (SNOMED 254837009) | 264 / 264 |
| Medicamentos con `ENCOUNTER` existente en `encounters.csv` | 44,718 / 44,718 |
| Trastuzumab (RxNorm 2119714) con fecha dentro de la ventana de su visita | 42 / 42 |
| Trastuzumab solo en pacientes HER2+ (LOINC 85319-2) | 42 / 42 |
| Orden diagnóstico ≤ HER2 ≤ trastuzumab | 42 / 42 |
| HER2 positivo / negativo | 53 / 211 |
| HER2+ sin trastuzumab | 11 |

**Conclusión de la Fase 1:** Synthea resuelve de forma nativa la integridad visita ↔ fármaco, que era
el riesgo principal de la opción (b).

**Patrón a replicar:** el submódulo `breast_cancer/hormone_diagnosis` hace primero el procedimiento
de prueba, luego una `Observation` con un `value_code` Positivo o Negativo, y después una transición
condicional. Los fármacos dirigidos están en `breast_cancer/hormonetherapy_breast`.

## Fase 2: ETL a OMOP (2026-09-28)

**Configuración:** `compose.yml` (PostgreSQL 16.15) + `etl/` (ETL-Synthea v2.1.1, CommonDataModel
v5.4.3, R 4.5.3), con `syntheaVersion = "3.3.0"` y `bulkLoad = TRUE`. Ver `etl/README.md`.

**Vocabularios de Athena:** descargados el 2026-09-28; versión global "v5.0 29-AUG-26". Incluyen
SNOMED (2026-02-01 Intl / 2026-03-01 US), LOINC 2.82, RxNorm 20260601, RxNorm Extension 2026-06-05,
CVX 20260409 y UCUM 1.8.2 (este último lo agrega Athena automáticamente). SHA-256 del zip:
`3526fdf41614844c6c62aaad1dbb12a65eb322337e8a0466887c074f6130ff78`.

**Tiempo:** 27.6 min en total. El vocabulario tarda 5.2 min y las tablas de eventos 21.2 min; casi
todo ese tiempo es la tabla `cost`, que el proyecto no usa.

**Resultados:**

| Verificación | Resultado |
|---|---|
| `person` | 264 ✅ |
| Diagnóstico → concepto estándar 4112853 (*Malignant neoplasm of breast*) | 264 personas ✅ |
| Trastuzumab en `drug_exposure` (concepto 1366764) | 42 personas, 42 filas ✅ |
| … con `visit_occurrence_id` no nulo y fecha dentro de la visita | 42 / 42 ✅ |
| **HER2 (LOINC 85319-2) en `measurement` u `observation`** | **0 ❌** |
| **Estadio clínico (LOINC 21908-9)** | **0 ❌** (515 registros de origen) |
| `death` | 62 de 64 ⚠️ |

**Hallazgo crítico: ETL-Synthea descarta en silencio los códigos sin mapeo estándar.** Las
consultas de inserción (p. ej., `insert_measurement.sql`) hacen un `JOIN` interno contra
`source_to_standard_vocab_map` con `target_standard_concept = 'S'`. Un código de origen que no es
estándar y no tiene relación "Maps to" **no produce error ni fila con `concept_id = 0`: desaparece.**
El chequeo "0 filas con `concept_id = 0`" da una falsa sensación de completitud.

- LOINC 85319-2 (HER2 en espécimen de mama) y los *stage group* 21908-9, 21902-2 y 21914-7 existen
  en el vocabulario, pero no son estándar y no tienen "Maps to". Las 264 filas de HER2 (53+ / 211−)
  están en `native.observations` y no llegaron al CDM.
- Pérdida total en esta corrida: 1,147 condiciones (181 códigos), 52,163 observaciones (23 códigos;
  casi todas son QALY/DALY/QOLS, pseudo-códigos de Synthea) y 15,257 procedimientos (312 códigos;
  sobre todo dentales CDT, vocabulario no descargado). Ningún medicamento se perdió.
- Los valores Positivo/Negativo (SNOMED 10828004 / 260385009) sí mapean como *Meas Value*
  (9191 / 9189).
- Las 2 defunciones faltantes corresponden a pacientes con visitas registradas después de la fecha
  de muerte (incoherencia de Synthea); el ETL no les crea fila en `death`. Impacto menor, pero se
  documenta.
- 6,335 filas de `drug_exposure` no tienen visita. Son fármacos crónicos (insulina, lisinopril) y
  vacunas; ninguna es de trastuzumab.

**Qué implica para la decisión:** no invalida la opción (a). La integridad visita ↔ fármaco se
confirma en OMOP. Pero agrega una **regla obligatoria para el módulo gástrico**: *todo código que
emita el módulo debe ser un concepto estándar, o tener "Maps to" hacia uno, en la versión de
vocabulario cargada.* Se verificará con un test automático que lea el JSON del módulo y consulte el
vocabulario, antes de generar datos.

Conceptos estándar encontrados para reemplazar a los que se pierden:

- **HER2:** LOINC 18474-7 (*HER2 Ag [Presence] in Tissue by Immune stain*, concepto 3019066) o
  48676-1 (*HER2 Ag [Interpretation] in Tissue*, 3048223). Ninguno es específico de mama, así que
  sirven para tejido gástrico. Para FISH: 31150-6 (*ERBB2 gene duplication [Presence] in Tissue*).
- **Estadio:** LOINC 42100-8 (*Derived AJCC stage group*, 3031548) es estándar. La alternativa
  alineada con OMOP Oncology sería el vocabulario **Cancer Modifier**, que no está en la descarga
  actual (ver preguntas abiertas).

### Fase 2b: códigos estándar (2026-09-28)

**Prueba:** `synthea/spike/patch_breast_cancer_codes.py` crea una copia del jar en la que el módulo
`breast_cancer` usa 42100-8 en lugar de 21908-9 (estadio) y 18474-7 en lugar de 85319-2 (HER2). El
cambio se aplica a todo el JSON: son 18 referencias, porque las condiciones y guardas del módulo
también consultan esos códigos. Si solo se cambiaran las observaciones, la lógica clínica se
alteraría sin ningún error visible. Después se regeneró con la misma semilla y se corrió el ETL
completo.

**Resultados:**

- 262 de 264 pacientes son idénticas byte a byte a las de la corrida original. 2 plazas generaron
  otra paciente (misma fecha de nacimiento, otro ID); la causa probable son los reintentos del
  *keep module*, no está confirmada. **Consecuencia: cualquier cambio en el módulo puede mover
  pacientes, así que el ground truth debe recalcularse desde los datos en cada regeneración.**
- ✅ HER2 (18474-7 → concepto 3019066): 264 filas en `measurement`, todas con visita.
- ✅ Estadio (42100-8 → concepto 3031548): 515 filas en `measurement`, todas con visita.
- ❌ **`value_as_concept_id = 0` en todas las filas**, no solo en estas: 0 de 599,763 mediciones
  tienen un valor codificado. El valor sobrevive solo como texto en `value_source_value`
  (p. ej., "Positive (qualifier value)", "Stage 4 (qualifier value)").

**Causa (dos defectos que se suman en ETL-Synthea v2.1.1, `insert_measurement.sql`):**

1. El CSV de Synthea trae en `VALUE` el *display* del valor codificado, no el código SNOMED; el ETL
   lo cruza contra `source_code`.
2. El filtro usa `target_domain_id = 'Meas value'`, pero el vocabulario usa `'Meas Value'`, y en
   PostgreSQL la comparación distingue mayúsculas.

**Valores de estadio:** Stage 1, 2, 3 y 4 son conceptos estándar (Stage 4 → 4123017). Los
subestadios (1A, 2B, 3C…) no lo son y no tienen "Maps to".

## Consecuencias

**Positivas**

- El ground truth de nivel (b) sale de una fuente con integridad garantizada por el generador.
- La tabla de atrición refleja pérdidas "naturales", como pacientes HER2+ sin terapia anti-HER2.

**Negativas / riesgos**

- **Dependencia de versión:** quedamos atados a Synthea ≤ 3.3.0 hasta que ETL-Synthea acepte una
  versión posterior.
- **Circularidad:** el mismo equipo diseña el módulo (prevalencias, reglas de tratamiento) y define
  el ground truth. Hay que declararlo en `docs/LIMITACIONES.md`: el sistema se evalúa contra datos
  cuya lógica clínica escribimos nosotros.
- **Prevalencia:** con incidencia realista habría que generar poblaciones enormes. Se usarán una
  probabilidad de inicio elevada y el *keep module*, y se documentará que la prevalencia no es
  epidemiológicamente realista.

## Preguntas abiertas (a resolver antes o durante la construcción del módulo)

- [ ] **CLDN18.2:** ¿existe un concepto estándar? Ojo: la opción de un "código local con
      `concept_id = 0`" **no sirve**, porque ETL-Synthea descarta los códigos sin mapeo (ver Fase 2).
      Si no existe un concepto estándar, habrá que insertar un concepto propio (`concept_id` >
      2,000,000,000, la convención de OHDSI) más su mapeo, o hacer un paso posterior al ETL.
- [x] **HER2 gástrico:** usar LOINC 18474-7 o 48676-1 (estándar, tejido genérico). Ver Fase 2.
- [ ] **Estadio:** LOINC 42100-8 (ya disponible) vs. descargar el vocabulario Cancer Modifier
      (convención de OMOP Oncology; otra descarga lenta de Athena).
- [ ] **Zolbetuximab y nivolumab:** confirmar que existen en la versión descargada de RxNorm / RxNorm
      Extension.
- [ ] **Diagnóstico:** elegir el código SNOMED de adenocarcinoma gástrico y confirmar que es concepto
      estándar en OMOP.
- [ ] **Alcance clínico del módulo:** estados y líneas de tratamiento mínimos para cubrir los criterios
      del protocolo (p. ej., FLOT perioperatorio; primera línea con quimioterapia más trastuzumab,
      nivolumab o zolbetuximab según el biomarcador; progresión y muerte). Definirlo a partir de los
      criterios de inclusión/exclusión que el RAG debe extraer.
- [ ] **Tamaño de la población** final y semilla(s) a publicar en el README.

> 💡 En un entorno regulado, este ADR junto con la configuración fijada (versión, semilla, fecha de
> referencia, hash del jar) es lo que permite a un auditor regenerar exactamente la misma base.
