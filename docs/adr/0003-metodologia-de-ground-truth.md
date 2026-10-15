# ADR-0003: Metodología para construir el ground truth

- **Estado:** Propuesto. Fija el método, los tamaños y las reglas; las anotaciones se hacen cuando
  exista el corpus (paso 3 del plan).
- **Fecha:** 2026-10-14
- **Decisores:** Jorge (autor), con asistencia de Claude Code
- **Relacionado:** ADR-0002 (evaluación por capas), `docs/cohorte-zolbetuximab.md`,
  `docs/LIMITACIONES.md`, `docs/protocolo.md`

## Contexto

El profesor pidió explicar "cómo vas a construir el ground truth para comparar los modelos". El
ADR-0002 define cinco capas de evaluación; cada una necesita una referencia:

| Nivel | Referencia | Capas que la usan |
|---|---|---|
| Recuperación | Fragmentos del corpus que contienen la respuesta | 1 (retrieval) y 5 (fidelidad) |
| **a** | Criterios de inclusión/exclusión correctos por protocolo | 2 (extracción) |
| **b** | Conjunto exacto de `patient_id` que cumple esos criterios en la base OMOP | 3 (SQL) y 4 (cohorte) |

Restricciones: una sola persona anota; el corpus aún no está descargado; los datos son sintéticos y
generados por un módulo que **ya codifica** los criterios que luego se consultan (riesgo de
circularidad, ver Consecuencias).

## Opciones consideradas

### A. Tamaño y reparto

1. **40 preguntas: 12 desarrollo y 28 prueba (elegida).**
2. 30 preguntas (10 / 20), lo que dice literalmente el protocolo: los intervalos de confianza con 20
   casos de prueba son demasiado anchos para distinguir modelos.
3. 50 preguntas (15 / 35): más potencia, pero el doble de anotación manual y la calidad de un solo
   anotador baja con el cansancio.

### B. Construcción del nivel b

1. **SQL de referencia escrito a mano + recálculo independiente desde los CSV de Synthea (elegida).**
2. Solo SQL de referencia: un error de interpretación quedaría dentro del ground truth sin que nadie
   lo vea.
3. Que un LLM proponga el SQL y se revise: contamina el ground truth con un modelo de la misma
   familia que luego se evalúa.

### C. Un solo anotador

1. **Re-anotación propia a ciegas de una muestra (elegida).**
2. Re-anotación propia más revisión de una muestra por el profesor: más fuerte, pero depende de
   terceros. Queda como mejora opcional.
3. Solo declarar la limitación: deja el ground truth sin ninguna comprobación de fiabilidad.

## Decisión

### 1. Composición: 40 preguntas de tres tipos

| Tipo | Qué es | Capas | Total | Desarrollo | Prueba |
|---|---|---|---|---|---|
| R | Pregunta clínica sobre el corpus, con respuesta de referencia y fragmentos relevantes | 1, 5 | 20 | 6 | 14 |
| E | Sección de criterios de un protocolo o guía → lista de criterios estructurados | 2 | 12 | 4 | 8 |
| C | Conjunto de criterios ejecutable sobre OMOP → `patient_id` esperados | 3, 4 | 8 | 2 | 6 |

- Entre los tipo E hay **casos negativos** (~10 %): criterios que los datos no permiten evaluar
  (TNM, subestadios, histología de Lauren; ver `docs/LIMITACIONES.md`). El resultado correcto es
  declararlos "no evaluables", no inventar una consulta.
- Los tipo C salen de protocolos cuyos criterios sí se pueden expresar con el modelo de datos
  (`docs/features.md`); el resto se queda en el tipo E.
- **Partición:** para E y C, por **documento fuente** (un protocolo no aparece en desarrollo y en
  prueba a la vez, para que no se filtre información); para R, estratificada por tema. Con pocos
  protocolos, el reparto exacto se ajusta al anotar y se documenta.

### 2. Nivel a (criterios por protocolo)

- Se anota **desde el texto original**, nunca a partir de la salida de un modelo (evita el anclaje).
  **Ningún LLM redacta ni corrige el ground truth**; los modelos solo se evalúan contra él.
- Reglas en una **guía de anotación** (`docs/guia-anotacion.md`, por escribir antes de anotar):
  criterio atómico (una condición por registro), valores y umbrales literales del texto,
  inclusión/exclusión, ventana temporal y cita exacta (documento, sección, página).
- Cada registro lleva un campo `evaluable` (sí / no con motivo) para los casos negativos.

### 3. Nivel b (cohorte esperada)

Para cada pregunta tipo C hay **dos implementaciones independientes** que deben coincidir:

1. Un **SQL de referencia** en `sql/` (como `02_cohorte.sql`), con su vista de atrición.
2. Un **recálculo con pandas** sobre los CSV de Synthea, sin SQL ni `concept_id`, como en
   `tests/test_cohort_zolbetuximab.py`.

Si difieren, el desacuerdo se investiga antes de aceptar el ground truth (en la cohorte de
zolbetuximab así apareció un paciente con quimioterapia previa de otro módulo).

El ground truth b depende de los **datos exactos**: se guarda junto con un identificador del
conjunto de datos (hash de `data/raw/synthea/output_gastric/SHA256SUMS`). Si se regenera la
población, hay que recalcularlo y subir la versión.

### 4. Formato, versionado y congelación

- Archivos JSONL en `eval/ground_truth/` (un registro por pregunta), con esquema validado por
  pydantic: identificador, partición, tipo, pregunta, referencias y metadatos de anotación.
  El esquema exacto se fija al implementarlo.
- Versión semántica del ground truth (`v1.0`), con registro de cambios.
- El conjunto de **prueba se congela** con su hash en el repo. Se evalúa una vez por candidato para
  la decisión final; no se usa para iterar prompts ni chunking (eso es el conjunto de desarrollo).
  Cualquier cambio posterior crea una versión nueva y se anota por qué.

### 5. Un solo anotador

- **Re-anotación a ciegas** de una muestra del 25 % (10 preguntas, estratificadas por tipo y
  partición), con **al menos una semana** de distancia y sin ver la primera anotación.
- Acuerdo consigo mismo: **κ de Cohen** para decisiones categóricas (incluye/excluye, evaluable,
  tipo de criterio); coincidencia exacta para valores y umbrales; **Jaccard** para los conjuntos de
  fragmentos relevantes.
- Si κ < 0,6 (por debajo de acuerdo sustancial, convención de Landis y Koch), se revisa la guía de
  anotación y se re-anota el tipo afectado. Los desacuerdos se resuelven caso por caso y cada
  cambio queda en el registro.
- Se declara que **no hay acuerdo entre anotadores**: la fiabilidad medida es la propia.
  Revisión por el profesor de una muestra: opcional, no se cuenta con ella.

> 💡 **Por qué esto importa en la industria:** en entornos regulados al ground truth se le llama
> *reference standard*; se espera que esté documentado, versionado, con su protocolo de anotación y
> una medida de fiabilidad. Que una sola persona anote es habitual en proyectos pequeños, pero sin
> declararlo ni medir la consistencia, el estándar no es auditable.

## Consecuencias

- **Buenas:** el nivel b es objetivo y verificado por dos vías; el conjunto de prueba está protegido
  contra el sobreajuste; la fiabilidad del anotador se mide, no se supone.
- **Costos:** escribir la guía de anotación; anotar 40 preguntas con cita exacta, que es trabajo
  manual lento (la estimación de horas se hace con las primeras 5); un segundo pase del 25 %; esperar
  al corpus para empezar.
- **Riesgos y límites:**
  - **Circularidad en el nivel b:** los datos los generó un módulo que usa los mismos criterios que se
    consultan. Medir que un modelo reproduce la cohorte de referencia no equivale a validar la
    elegibilidad en pacientes reales.
  - **Umbrales del módulo de memoria:** hasta contrastarlos con el corpus, el nivel b refleja el
    proyecto, no la literatura. Conviene fijar el nivel a antes de dar por bueno el b.
  - **n pequeño:** 28 casos de prueba dan intervalos anchos; se reportan con su intervalo y no se
    declaran diferencias menores.
  - **Pocos protocolos:** la partición por documento deja pocos grupos; una pregunta mal anotada
    puede pesar mucho.
  - Un solo anotador: sesgos de lectura sin detectar.

## Preguntas abiertas

- ¿Qué protocolos y guías entran al corpus? (Paso 3.) Determina el reparto final de E y C.
- ¿Qué tema define la estratificación de los tipo R?
- ¿Se pide al profesor una revisión de muestra? (Opcional.)
