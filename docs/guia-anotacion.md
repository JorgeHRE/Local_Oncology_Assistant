# Guía de anotación del ground truth

- **Estado:** v0.2, borrador (2026-11-05; v0.2 añade cómo se formula cada tipo y ejemplos). Se congela como v1.0 al terminar las 5 primeras preguntas
  (ADR-0003: con ellas se estima el tiempo total y se corrige lo que no funcione).
- **Método:** `docs/adr/0003-metodologia-de-ground-truth.md`. **Esquema y validador:**
  `src/oncology_assistant/ground_truth.py`. **Archivo:** `eval/ground_truth/ground_truth.jsonl`.
- **Validar:** `make gt-validate` (en cualquier momento) y `make gt-validate-final` (al terminar:
  exige además las cuotas exactas).

## 0. Regla de oro

**Se anota leyendo el texto original. Ningún LLM redacta, sugiere ni corrige el ground truth**, y eso
incluye a Claude Code. Tampoco se consulta el índice del RAG (`make index`, `index.py query`) mientras
se escribe una pregunta: si la pregunta se escribe mirando lo que el buscador encuentra, la evaluación
queda sesgada a favor del buscador. Los modelos solo se evalúan contra lo anotado.

Las plantillas de esta guía usan marcadores `<...>`: son estructura, no contenido.

## Antes de empezar: qué pregunta cada tipo y cómo se escribe

Esta sección es la que hay que leer primero. Las demás dan el detalle de cada campo.

### A. Sobre qué pregunta cada tipo

| Tipo | Pregunta sobre… | Se responde con… | Quién calcula la respuesta |
|---|---|---|---|
| **R** (recuperación) | Los **documentos** del corpus: fichas de ensayos y resúmenes de artículos | Un texto corto y las citas literales que lo respaldan | Tú, leyendo los documentos |
| **E** (extracción) | **Un protocolo**: convertir su sección de criterios en una lista estructurada | La lista de criterios atómicos de esa sección | Tú, leyendo el protocolo |
| **C** (cohorte) | Los **pacientes** de la base OMOP: los **1 360**, no solo la cohorte de zolbetuximab | El conjunto de pacientes que cumplen los criterios | El SQL de referencia y un recálculo con pandas, no tú (§5) |

- **R y E no tocan a los pacientes.** Son preguntas sobre textos.
- Los **218** pacientes de la cohorte de zolbetuximab son la respuesta de **una sola** pregunta C
  (la de SPOTLIGHT/GLOW). Otras C (por ejemplo, criterios de un ensayo de trastuzumab o de nivolumab)
  darán otros conjuntos de pacientes.

### B. Pregunta, respuesta y registro: qué va en lenguaje natural y qué no

Cada pregunta se guarda como **un registro JSON** en `ground_truth.jsonl`. Los bloques de código de
esta guía son la **forma de ese registro**, no la forma de la pregunta.

| Parte | Cómo se escribe | Campo |
|---|---|---|
| La pregunta | Lenguaje natural, en inglés, como la haría un investigador clínico | `question` |
| La respuesta (solo R) | Lenguaje natural, corta, con los valores literales del texto | `reference_answer` |
| Las fuentes | Citas literales copiadas del documento | `relevant` (R) o `citation` de cada criterio |
| Las condiciones (E y C) | **Estructuradas**: un objeto JSON por criterio, con `kind`, `concept`, `operator`, `value`… | `criteria` |

**Por qué en inglés:** el corpus está en inglés y el modelo de embeddings actual solo es de inglés.
Con preguntas en español se mediría a la vez la búsqueda y la traducción. Un asistente que responda
en español queda para una v2 con un modelo multilingüe.

### C. Cómo formular una pregunta R

1. **Nombra el ensayo o el contexto** cuando la respuesta dependa de él (NCT o nombre del ensayo).
   Varios ensayos copian los mismos criterios; sin el nombre, la pregunta tiene varias respuestas
   correctas.
2. **No copies la frase del documento en la pregunta.** Si la pregunta repite la cita palabra por
   palabra, se mide coincidencia de palabras, no comprensión. La cita va en `relevant`.
3. **Una pregunta, una respuesta comprobable.** Nada de "Tell me about HER2".
4. **Decide la forma** y anótala en `notes`:
   - `single`: un solo dato de un documento.
   - `multi`: varios criterios o secciones del mismo documento.
   - `compare`: dos o más documentos o fuentes.
5. **La respuesta solo dice lo que dicen los textos citados**, con sus valores literales. Sin
   conocimiento propio ni interpretación.

Ejemplos de forma con un ensayo **inventado** (NCT00000000 no existe):

| Forma | Mal | Bien |
|---|---|---|
| `single` | "Which trial says 'Subject has a HER2-negative tumor'?" (copia la cita) | "What HER2 status does trial NCT00000000 require?" |
| `single` | "Tell me about HER2 in gastric cancer." (sin respuesta comprobable) | "Which HER2 result excludes a patient from trial NCT00000000?" |
| `multi` | "What are the criteria?" (demasiado amplia, es una E) | "Which biomarker results must a patient have to enter trial NCT00000000?" |
| `compare` | "Are the trials similar?" (no comprobable) | "Do trials NCT00000000 and NCT00000001 accept the same ECOG range?" |

### D. Cómo formular una pregunta E

- La pregunta sigue siempre la misma plantilla:
  `"Extract the inclusion criteria of trial <NCT…>"` o
  `"Extract the exclusion criteria of trial <NCT…>"`.
- Se anotan **todos** los criterios de esa sección, evaluables o no, cada uno como un objeto.
- Cómo partir y codificar (frases inventadas):

| Texto | Cuántos criterios | Cómo |
|---|---|---|
| "HER2-negative and CLDN18.2-positive tumor" | 2 | `HER2 = negative` y `CLDN18.2 = positive` |
| "ECOG performance status 0 or 1" | 1 | `ECOG <= 1` |
| "No prior systemic therapy for advanced disease" (bajo *Inclusion*) | 1 | `kind: inclusion`, `concept: prior systemic therapy`, `operator: absent` |
| "Adequate liver function within 7 days prior to randomization" | 1 | `evaluable: false`, motivo: analítica no modelada; `time_window` literal |
| "≥ 75% of tumor cells with moderate to strong staining" | 1 | `operator: ">="`, `value: "75"`, `unit: "% of tumor cells"`; el resto de la frase queda en la cita |

### E. Cómo formular una pregunta C

- Plantilla: `"Which patients in the database meet the evaluable criteria of trial <NCT…>?"`.
- `criteria`: **solo los evaluables** de ese ensayo, con el mismo formato que en E (puedes copiarlos
  de la E del mismo ensayo).
- `reference_sql`: el archivo de `sql/` que implementa la cohorte (por ejemplo,
  `sql/02_cohorte.sql` para zolbetuximab). No escribes la lista de pacientes: la calculan el SQL y el
  recálculo con pandas, y se guardan `dataset_id` y `expected_count`.
- Las C se anotan **después** de las R y las E, cuando exista el SQL de cada una. Ver la pregunta
  abierta sobre quién escribe ese SQL.

### F. Ejemplos completos (inventados)

Los tres usan el ensayo inventado NCT00000000. **No los copies al archivo:** el validador los
rechaza porque ese documento no está en el corpus (`unknown document`).

R:

```json
{"id": "R-001", "type": "R", "split": "dev", "topic": "her2",
 "question": "What HER2 status does trial NCT00000000 require?",
 "reference_answer": "HER2-negative tumors only.",
 "relevant": [{"doc_id": "ct:NCT00000000", "quote": "Subject has a HER2-negative tumor"}],
 "annotator": "JH", "annotated_on": "2026-11-05", "notes": "single"}
```

E (tres de los criterios de la sección; en una E real van todos):

```json
{"id": "E-001", "type": "E", "split": "dev", "source": "ct:NCT00000000",
 "question": "Extract the inclusion criteria of trial NCT00000000",
 "criteria": [
   {"kind": "inclusion", "concept": "HER2", "operator": "=", "value": "negative",
    "unit": null, "time_window": null, "evaluable": true, "not_evaluable_reason": null,
    "citation": {"doc_id": "ct:NCT00000000", "quote": "Subject has a HER2-negative tumor"}},
   {"kind": "inclusion", "concept": "ECOG", "operator": "<=", "value": "1",
    "unit": null, "time_window": null, "evaluable": true, "not_evaluable_reason": null,
    "citation": {"doc_id": "ct:NCT00000000", "quote": "ECOG performance status 0 or 1"}},
   {"kind": "inclusion", "concept": "liver function", "operator": null, "value": "adequate",
    "unit": null, "time_window": "within 7 days prior to randomization", "evaluable": false,
    "not_evaluable_reason": "laboratory values are not modelled",
    "citation": {"doc_id": "ct:NCT00000000", "quote": "Adequate liver function within 7 days prior to randomization"}}
 ],
 "annotator": "JH", "annotated_on": "2026-11-05", "notes": "tiempo: 40 min"}
```

C:

```json
{"id": "C-001", "type": "C", "split": "dev", "source": "ct:NCT00000000",
 "question": "Which patients in the database meet the evaluable criteria of trial NCT00000000?",
 "criteria": [<los criterios evaluables, como en la E>],
 "reference_sql": "sql/<archivo>.sql", "dataset_id": null, "expected_count": null,
 "annotator": "JH", "annotated_on": "2026-11-05"}
```

### G. Paso a paso para cada registro

1. Elige el documento (para la tanda piloto, uno de `dev` en §6).
2. Léelo en la fuente original (§1), **sin** el RAG ni un LLM.
3. Escribe el registro con formato, como en los ejemplos, en un borrador fuera del repo (por
   ejemplo `~/borrador.json`).
4. Añádelo al archivo en una sola línea:
   `jq -c . ~/borrador.json >> eval/ground_truth/ground_truth.jsonl`
5. Valida: `make gt-validate`. Si una cita no aparece literal en el documento, te lo dice con el id
   del registro.
6. Apunta el tiempo que tardaste en `notes` (con las 5 primeras se estima el total).
7. Anota el cambio en `eval/ground_truth/CHANGELOG.md`.

## 1. Dónde leer

| Fuente | Texto original | Qué se puede citar |
|---|---|---|
| ClinicalTrials.gov | `https://clinicaltrials.gov/study/<NCT>` (pestaña *Eligibility*) o `corpus/clinicaltrials/<NCT>.json` | Solo los criterios de elegibilidad (las fichas versionadas están recortadas a eso) |
| PubMed | `https://pubmed.ncbi.nlm.nih.gov/<PMID>/` o `data/raw/corpus/pubmed/<PMID>.json` | Título y resumen |

La versión que cuenta es la del corpus (congelada en `corpus/manifest.json`). Si la web y el archivo
difieren, manda el archivo, y se anota la diferencia en `notes`.

## 2. Formato

Un registro JSON por línea en `ground_truth.jsonl`. Campos comunes a los tres tipos:

| Campo | Valor |
|---|---|
| `id` | `R-001`, `E-001`, `C-001`… (el prefijo es el tipo; números sin huecos) |
| `type` | `R`, `E` o `C` |
| `split` | `dev` o `test` (ver §6) |
| `question` | La pregunta, en inglés (el corpus está en inglés) |
| `annotator` | Tu nombre o iniciales |
| `annotated_on` | Fecha `AAAA-MM-DD` |
| `notes` | Opcional: dudas, decisiones, diferencias con la web |

## 3. Citas literales

Toda referencia a un documento es una **cita literal**: `{"doc_id": "<ct:NCT…|pm:…>", "quote": "<texto>"}`.

- Copia el texto **tal cual**. Los espacios, saltos de línea, viñetas (`*`, `1.`) y escapes de
  Markdown (`1\.`, `18\~75`) no importan: el validador los normaliza. **Las mayúsculas, los números y
  los símbolos sí** ("≥ 75%" no es "> 75%").
- **Mínima suficiente:** la frase que contiene la información, no el párrafo entero. Al menos 10
  caracteres.
- **Dentro de un criterio o de una sección** del resumen. Una cita que cruza dos viñetas no la
  contiene ningún chunk de la estrategia B y siempre contaría como fallo.
- Si la información está en dos sitios, son dos citas.

Por qué así: con citas literales, un chunk de **cualquier** estrategia de chunking cuenta como acierto
si contiene la cita (ADR-0006). El ground truth no menciona ids de chunk y no favorece a ninguna.

## 4. Criterios (tipos E y C)

Un registro por condición **atómica**:

```json
{"kind": "<inclusion|exclusion>", "concept": "<HER2|ECOG|…>", "operator": "<=|!=|>|>=|<|<=|in|present|absent>",
 "value": "<literal>", "unit": "<literal o null>", "time_window": "<literal o null>",
 "evaluable": <true|false>, "not_evaluable_reason": "<motivo o null>",
 "citation": {"doc_id": "<ct:NCT…>", "quote": "<texto>"}}
```

- **`kind`:** la sección en la que aparece en el texto, aunque la frase sea negativa ("No prior
  chemotherapy" bajo *Inclusion* es `inclusion` con `operator: "absent"`).
- **Atómico:** "HER2-negative **and** CLDN18.2-positive" son dos criterios. Las alternativas del mismo
  concepto ("ECOG 0 or 1") son uno (`operator: "<="`, `value: "1"`, o `in` con `value: "0; 1"`). Las
  alternativas entre conceptos distintos ("not of child-bearing potential **or** uses
  contraception") son uno, con el concepto que las agrupa y la explicación en `notes`.
- **Valores, unidades y ventanas literales:** "≥ 75% of tumor cells" → `operator: ">="`,
  `value: "75"`, `unit: "% of tumor cells"`. "within 28 days prior to randomization" va entero en
  `time_window`. No se convierte nada (ni semanas a días).
- **`evaluable`:** ¿se puede comprobar con los datos OMOP de este proyecto? Sí, para lo que emite el
  módulo (`docs/features.md`):

  | Evaluable | No evaluable (motivo típico) |
  |---|---|
  | Diagnóstico gástrico o del cardias; estadio agrupado 1–4 o enfermedad avanzada | TNM, subestadios, enfermedad medible (RECIST), sitio de metástasis |
  | HER2, CLDN18 (con la aproximación de `docs/LIMITACIONES.md`), PD-L1 CPS, MSI, ECOG | Histología de Lauren, EBV, FGFR2b, otros biomarcadores |
  | Edad, sexo, fallecimiento | Embarazo, lactancia, anticoncepción, consentimiento |
  | Fármacos y fechas: tratamiento previo, lavado, ingredientes | Analítica (función de órganos), comorbilidades no modeladas, metástasis cerebrales, radioterapia, cirugía |

  Si no es evaluable, `not_evaluable_reason` dice por qué en una línea. Estos son los **casos
  negativos** del ADR: el resultado correcto para un modelo es declararlos no evaluables.

## 5. Los tres tipos

### R: recuperación (20 preguntas)

```json
{"id": "R-<nnn>", "type": "R", "split": "<dev|test>", "topic": "<her2|cldn18|pdl1_immunotherapy|msi|other>",
 "question": "<…>", "reference_answer": "<…>", "relevant": [<citas>], "annotator": "<…>", "annotated_on": "<…>"}
```

- `topic`: el biomarcador o la diana. `other` agrupa FGFR2b, perioperatorio, estadificación, Lauren y
  líneas posteriores.
- **Mezcla de formas** (para no sesgar a favor de los chunks pequeños): preguntas sobre un solo dato
  ("¿qué umbral de CLDN18.2…?"), preguntas que necesitan **varios criterios** del mismo ensayo y
  preguntas que **comparan** ensayos o fuentes. Anota en `notes` cuál es (`single`, `multi`,
  `compare`): la evaluación se reporta por forma, no solo en promedio.
- `relevant`: **todas** las citas necesarias para responder, de cualquier documento. Si un distractor
  también contiene la respuesta (pasa con criterios copiados entre ensayos), no se incluye: la
  pregunta debe nombrar el ensayo o el contexto que lo desambigua.
- `reference_answer`: corta, con los valores literales.

### E: extracción (12 preguntas)

```json
{"id": "E-<nnn>", "type": "E", "split": "<dev|test>", "source": "<ct:NCT…>",
 "question": "<Extract the <inclusion|exclusion> criteria of <trial>>", "criteria": [<criterios>], …}
```

- Una E cubre **una sección completa** (inclusión **o** exclusión) de un documento: todos sus
  criterios, evaluables o no. Una sección incompleta impide medir la precisión de la extracción.
- Todas las citas son del documento `source` (el validador lo exige).

### C: cohorte (8 preguntas)

```json
{"id": "C-<nnn>", "type": "C", "split": "<dev|test>", "source": "<ct:NCT…>", "question": "<…>",
 "criteria": [<solo criterios evaluables>], "reference_sql": "sql/<archivo>.sql", …}
```

- Solo criterios evaluables (el validador lo exige).
- Los pacientes esperados **no se escriben a mano**: salen del SQL de referencia y de un recálculo
  independiente con pandas, que tienen que coincidir (ADR-0003 §3). Se guardan con `dataset_id`
  (`make gt-dataset-id`) y `expected_count`; si se regenera la población, se recalculan.

## 6. Partición

- E y C se parten **por documento**: un documento (o grupo, abajo) no puede tener preguntas en `dev` y
  en `test` a la vez.
- **Grupos de documentos casi idénticos** (`eval/ground_truth/split_groups.json`): GLOW comparte 30
  de sus 35 criterios con SPOTLIGHT (> 90 % de similitud, medido el 2026-11-05). Si uno estuviera en
  desarrollo y el otro en prueba, el conjunto de prueba se filtraría. El grupo de zolbetuximab de
  Astellas va entero en la misma partición.
- R se estratifica por `topic`: unas 30 % de cada tema en `dev`.
- Cuotas (ADR-0003): R 6/14, E 4/8, C 2/6 (`dev`/`test`).

**Propuesta de documentos para E y C** (2026-11-05, a confirmar al anotar). Son los 4 pivotales más
los 8 candidatos que mencionan más criterios evaluables (HER2, CLDN18, CPS, MSI, ECOG, estadio,
tratamiento previo):

| Partición | Documento | Por qué |
|---|---|---|
| test | SPOTLIGHT (NCT03504397), GLOW (NCT03653507), NCT06901531, NCT07673887 | Grupo de zolbetuximab; base de la cohorte piloto |
| test | ToGA (NCT01041404), CheckMate 649 (NCT02872116) | Pivotales. Sus fichas tienen poco texto (539 y 1 101 caracteres): secciones cortas |
| test | NCT07385703 (CLDN18.2 + PD-L1), NCT05427383 (HER2+) | Diversidad de biomarcadores |
| dev | NCT06504732 (HER2+), NCT06346197 (MSI-H, CPS ≥ 5), NCT06177041 (CLDN18.2, CPS < 5), NCT03675737 (KEYNOTE-859, HER2−) | Un ejemplo de cada biomarcador para iterar prompts sin tocar prueba |

Las C saldrían de los mismos documentos (2 de `dev`, 6 de `test`).

## 7. Re-anotación a ciegas

- Una muestra del 25 % (10 preguntas, estratificada por tipo y partición) se vuelve a anotar **al
  menos una semana después**, sin ver la primera anotación, en `eval/ground_truth/reannotation.jsonl`
  (mismo formato y mismos `id`).
- Se mide el acuerdo (κ de Cohen para las decisiones categóricas, coincidencia exacta para valores,
  Jaccard para las citas). Si κ < 0,6, se revisa esta guía y se re-anota el tipo afectado.

## 8. Versiones y cambios

- Cada cambio al archivo va en `eval/ground_truth/CHANGELOG.md` (qué, por qué, fecha).
- Al terminar, el conjunto de prueba se congela con su hash (v1.0). Se evalúa una vez por candidato;
  no se usa para iterar. Un cambio posterior crea una versión nueva.

## 9. Lista de comprobación por registro

1. ¿La pregunta se escribió leyendo el documento, sin consultar el RAG ni un LLM?
   ¿Nombra el ensayo cuando hace falta y no copia la cita?
2. ¿Cada cita es literal, mínima y está dentro de un criterio o sección?
3. ¿Cada criterio es atómico, con valores y ventanas literales?
4. ¿`evaluable` está decidido con la tabla del §4, y con motivo si es `false`?
5. ¿La partición respeta el documento y su grupo?
6. ¿`make gt-validate` pasa?

## Preguntas abiertas

- **Quién escribe el SQL de referencia de las C.** El ADR-0003 descarta que un LLM proponga el SQL
  del ground truth (contaminaría la evaluación con un modelo de la misma familia). Pero
  `sql/02_cohorte.sql` (zolbetuximab) y su recálculo con pandas se escribieron con Claude Code.
  Opciones: revisarlo tú línea por línea contra la E correspondiente y declararlo, o reescribir tú
  el recálculo independiente. Se decide antes de anotar las C.

- ¿Una E por sección (inclusión o exclusión) es una carga razonable? SPOTLIGHT tiene 14 viñetas de
  inclusión y 20 de exclusión (chunks de la estrategia B; los criterios atómicos pueden ser más). Se decide con las 5 primeras preguntas.
