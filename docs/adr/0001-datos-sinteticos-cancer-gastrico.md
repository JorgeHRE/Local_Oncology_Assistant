# ADR-0001: Estrategia de datos sintéticos para cáncer gástrico

- **Estado:** Propuesto (borrador). Pasa a *Aceptado* cuando se complete la Fase 2 del spike (ver "Validación").
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
  -k keep_breast_cancer.json \
  --exporter.csv.export=true --exporter.fhir.export=false \
  --exporter.years_of_history=0 \
  Massachusetts
```

- Jar de la versión v3.3.0, SHA-256 `8ba04f7d73abadd5a377e41edf24c5c83935a1cb07c6d982cd5db731ef1cf445`.
- `-k keep_breast_cancer.json` es un *keep module* que conserva solo pacientes con el diagnóstico
  SNOMED 254837009.
- `--exporter.years_of_history=0` exporta el historial completo. Por defecto Synthea exporta solo
  10 años y cortaría diagnósticos antiguos.

**Resultados de la Fase 1 (CSV de Synthea):**
263 registros (200 vivas, 63 fallecidas), generados en 1 min 41 s.

| Verificación | Resultado |
|---|---|
| Pacientes con el diagnóstico (SNOMED 254837009) | 263 / 263 |
| Medicamentos con `ENCOUNTER` existente en `encounters.csv` | 45,465 / 45,465 |
| Trastuzumab (RxNorm 2119714) con fecha dentro de la ventana de su visita | 42 / 42 |
| Trastuzumab solo en pacientes HER2+ (LOINC 85319-2) | 42 / 42 |
| Orden diagnóstico ≤ HER2 ≤ trastuzumab | 42 / 42 |
| HER2 positivo / negativo | 53 / 210 |
| HER2+ sin trastuzumab | 11 |

**Conclusión de la Fase 1:** Synthea resuelve de forma nativa la integridad visita ↔ fármaco, que era
el riesgo principal de la opción (b).

**Patrón a replicar:** el submódulo `breast_cancer/hormone_diagnosis` hace primero el procedimiento
de prueba, luego una `Observation` con un `value_code` Positivo o Negativo, y después una transición
condicional. Los fármacos dirigidos están en `breast_cancer/hormonetherapy_breast`.

## Validación pendiente para aceptar este ADR (Fase 2)

1. Cargar los vocabularios de Athena (SNOMED, LOINC, RxNorm, RxNorm Extension, CVX; verificar si UCUM
   viene incluido) en PostgreSQL y registrar la versión y la fecha de descarga.
2. Correr ETL-Synthea v2.1.1 con `syntheaVersion = "3.3.0"` sobre los CSV del spike.
3. Confirmar en OMOP que:
   - HER2 (LOINC 85319-2) queda en `measurement` u `observation`, con su `value_as_concept_id`;
   - el trastuzumab queda en `drug_exposure` con un `visit_occurrence_id` no nulo;
   - los conteos coinciden con la tabla de la Fase 1.

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

- [ ] **CLDN18.2:** ¿existe un código LOINC específico? Si no, decidir la alternativa (código local
      con `concept_id = 0` más `source_value`, o un concepto de OMOP Oncology/Genomic) y cómo lo
      consulta el SQL.
- [ ] **HER2 gástrico:** el LOINC 85319-2 es específico de espécimen de mama. Buscar un código de
      HER2 que no sea específico de mama o que aplique a tejido gástrico.
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
