# Declaración de uso de asistentes de IA

- **Estado:** borrador (2026-11-17), redactado con Claude Code a partir del historial del repositorio y de
  lo que el autor declaró; **el autor debe revisarlo y confirmarlo**. Las frases que dependen de su
  declaración están marcadas como *declarado por el autor*; lo que falta está en §7 (Gemini en la
  planeación y las licencias).
- **Alcance:** todo el repositorio (código, SQL, datos sintéticos, documentación y ground truth).

## 1. Resumen

El proyecto se hizo con dos asistentes de IA: **Gemini** (Google AI Studio) en la planeación, como segunda
opinión y como apoyo con el formato del ground truth, y **Claude Code** (Anthropic) en la implementación. **El autor decide, revisa y aprueba cada cambio** (cada
commit y cada PR se aprueban explícitamente, y los PR se mergean a mano). **El contenido del ground truth (preguntas, respuestas de referencia, criterios y citas), que es la
referencia con la que se evalúan los modelos, lo redactó el autor leyendo los textos** (ADR-0003). Los
asistentes intervinieron en las herramientas y, en el caso de Gemini, como **tutor del formato, visor de
los datos y segunda opinión** (§2 y §4); los límites exactos están en §4 y lo que falta por confirmar, en §7.

Los modelos de lenguaje que forman parte del sistema (§3) corren en local y no escriben ni corrigen el ground truth.

## 2. Asistentes usados en el desarrollo

| Asistente | Para qué | Evidencia |
|---|---|---|
| **Gemini** (Google AI Studio) | (a) Planeación y prototipado como copiloto de código (`CLAUDE.md` §3). (b) **Segunda opinión y lluvia de ideas** (*declarado por el autor*): se le consultó sobre el proyecto y se discutieron con él algunas recomendaciones de Claude Code, para contrastar con otro modelo. (c) **Apoyo con el formato del ground truth** (*declarado por el autor*): para no gastar la cuota de Claude Code, se le pidió que enseñara paso a paso a armar el JSON de las preguntas (qué documento mirar, que `quote` es la cita literal y que la respuesta la redacta el autor). Tuvo acceso al repositorio y **solo mostraba los datos**: pasaba a texto con formato los criterios en JSON de una sola línea para poder revisarlos. **No escribió ni propuso contenido** del ground truth: el autor lo decidió en todos los casos | No deja rastro en el repositorio |
| **Claude Code** (Anthropic; modelos Claude Opus 5.5 y Claude Sonnet 5.5) | Implementación: módulo de Synthea, ETL, corpus, chunking e indexación, validador del ground truth, cohortes SQL (ver §4), asistente RAG, evaluaciones, ADR y documentación. | 48 de los 50 commits (sin contar los merges) llevan `Co-Authored-By: Claude`: 22 con Opus 5.5 y 26 con Sonnet 5.5. Los dos sin trailer son el andamiaje inicial y el protocolo de la Sesión 10 (2026-09-17) |

Los 50 commits aparecen con la cuenta del autor porque los aprueba y los sube él; el trailer indica la
participación de la IA. **Un trailer de Claude en un commit no significa que Claude escribiera todo su
contenido**: los commits que añaden registros al ground truth (R, E y C) llevan el trailer porque Claude
Code ejecutó el `git commit` que el autor aprobó, no porque redactara las preguntas.

## 3. Modelos de IA que forman parte del sistema (no son asistentes)

Corren **en local** (Ollama 0.40.4, GPU RTX 5070); los pesos no están en el repositorio (`data/raw/` está
ignorado). Ningún dato sale de la máquina para generar respuestas.

| Modelo | Uso |
|---|---|
| qwen3:8b | LLM del asistente: respuestas con citas, reformulación de preguntas y extracción de criterios (ADR-0005, elegido por el autor) |
| gemma3:12b, medgemma:4b | Candidatos comparados en desarrollo; no se usan en el asistente |
| bge-m3 | Embeddings del retriever (ADR-0007) |
| all-MiniLM-L6-v2, qwen3-embedding:0.6b | Embeddings comparados en desarrollo |

Antes de redistribuir o ampliar el uso de cada modelo hay que **revisar su licencia** (no verificadas
aquí).

## 4. Qué hizo la IA y qué hizo el autor

| Área | IA (Claude Code) | Autor |
|---|---|---|
| Decisiones de arquitectura | Presentó opciones, mediciones y recomendaciones; redactó los ADR | Decidió (por ejemplo, **eligió qwen3:8b**, aceptó el ADR-0005 y fijó el alcance clínico con las respuestas del profesor). Contrastó algunas recomendaciones de Claude Code con Gemini (*declarado por el autor*); la decisión final fue suya |
| Datos sintéticos y ETL | Escribió el módulo de Synthea, el flujo con Docker/`make` y las pruebas | Revisó, ejecutó y aprobó; definió el alcance clínico |
| Corpus | Programó la descarga y el registro de fuentes y versiones | Revisó los términos de uso de ClinicalTrials.gov, NLM y PubMed |
| **Ground truth (40 preguntas)** | **Claude Code, solo herramientas:** el esquema y el validador, la guía de anotación (con ejemplos inventados, NCT00000000) y el recuento de errores formales. No redactó, sugirió ni corrigió preguntas, respuestas, criterios ni citas. **Gemini (*declarado por el autor*):** enseñó el formato JSON y mostraba los datos en texto legible; **no escribió ni propuso contenido** | **Anotó las 20 R, 12 E y 8 C** (*declarado por el autor*) y corrigió los flags `evaluable` (45 criterios pasaron a no evaluables) tras revisar el listado de `make review-evaluable` |
| Cohortes SQL | Escribió la base de `sql/02_cohorte.sql` (C-007, SPOTLIGHT) y su recálculo con pandas | Escribió el SQL de las otras siete cohortes (`sql/cohort_*.sql`) y sus tests, **sin ayuda de IA** salvo la orientación de Gemini ya descrita (*declarado por el autor*); **revisó manualmente** el de C-007 (*declarado por el autor*) |
| Asistente RAG y evaluaciones | Escribió el código, los tests y las evaluaciones; ejecutó las mediciones | Aprobó cada commit y PR; el **juicio de corrección** de las respuestas de los modelos es suyo |
| Documentación y protocolo | Redactó los borradores, ADR y el protocolo v2 | Revisó y aprobó |

### Regla del ground truth (ADR-0003) y excepciones

Los modelos solo se evalúan contra el ground truth. Para que no se contamine: ningún LLM redacta, sugiere
ni corrige preguntas, respuestas, criterios, citas ni el SQL de referencia, y no se consulta el índice del
RAG mientras se escribe una pregunta. Excepciones y límites **declarados**:

1. **C-007**: el SQL de referencia (`sql/02_cohorte.sql`) tiene su base escrita con Claude Code, lo que el
   ADR-0003 descarta como método. El autor lo revisó a mano. Consta en el campo `notes` del registro, en la
   guía y en el CHANGELOG. Es una limitación al informar sus resultados.
2. **Recálculo independiente con pandas**: solo existe para la cohorte de zolbetuximab y también se escribió
   con Claude Code; no está en el repositorio para las otras siete.
3. **Enrutado del asistente** (preguntas por pacientes frente a preguntas sobre textos): se ajustó viendo
   las preguntas del ground truth, incluidas las de `test`. Son palabras clave, no un modelo.
4. **Gemini y el ground truth** (*declarado por el autor*): se usó para aprender el formato y para ver los
   criterios en texto; el contenido lo decidió el autor en todos los casos. Aun así, el acceso de un LLM
   de Google al repositorio y a los datos es relevante: gemma3:12b y medgemma:4b, dos de los modelos
   comparados, son de la misma familia, y la razón del ADR-0003 era no contaminar con un modelo de la
   misma familia. Como Gemini no escribió ni propuso contenido, se considera que el efecto es mínimo; el
   lector puede valorar este límite.
5. **Herramientas que usan las preguntas ya escritas**, sin modificarlas: el validador de citas literales, el
   listado de `evaluable` (`make review-evaluable`, que solo lista) y las evaluaciones.

## 5. Cómo se verificó el trabajo de la IA

- **Revisión humana:** cada commit y cada PR requieren la aprobación del autor, y `main` está protegido
  (PR y CI obligatorios). Los PR los mergea el autor.
- **Pruebas automáticas:** pytest (con modelos falsos, sin red) y ruff en el CI, en Python 3.10 y 3.12.
- **Citas literales:** tanto el ground truth como las respuestas del asistente se validan contra el texto
  del corpus; una cita que no aparece se marca como no confiable.
- **Corrida única sobre `test`**, con la configuración fijada antes de verla (`eval/results/`).
- **Errores de la IA detectados** (ejemplos reales de esta revisión): una estimación de tiempo errónea
  por mucho; una lectura incorrecta de la columna `evaluable` de la extracción, descubierta porque la
  referencia estaba sesgada (corregida y documentada en el ADR-0005); una instrucción mía que daba por
  existente una E de SPOTLIGHT que no existía; un código que no corría en Python 3.10, detectado por el CI.

## 6. Privacidad y datos

- El repositorio **no contiene datos de pacientes reales**: solo datos sintéticos de Synthea, fichas de
  elegibilidad de ClinicalTrials.gov (con atribución) y resúmenes de PubMed (no versionados).
- Claude Code y Gemini son servicios en la nube: **procesan el contenido que se les muestra**. Eso incluye
  código, documentación, fichas de ensayos, datos sintéticos y, en el caso de Gemini, el repositorio al que
  se le dio acceso (incluido el ground truth); no incluye datos de pacientes reales.
- Los modelos del sistema (§3) se ejecutan en local; el RAG no envía datos a ninguna API externa.

## 7. Pendiente de confirmar por el autor

Confirmado por el autor (2026-11-17), ya incorporado arriba:
- Gemini solo mostró los datos del ground truth y enseñó el formato; el contenido lo decidió el autor en
  todos los registros; Gemini se usó además como segunda opinión y para lluvia de ideas.
- Los SQL de las siete cohortes (`sql/cohort_*.sql`), los cambios de `Makefile` para ejecutarlos y los tests de
  cohortes los escribió el autor sin ayuda de IA, salvo la orientación de Gemini ya descrita.
- El autor **no usó el RAG** mientras escribía el ground truth (guía §0); el asistente lo probará después.

Aún por confirmar o completar:
1. **Gemini en la planeación:** fechas y qué salida se incorporó, si se quiere detallar más.
2. Revisar las **licencias** de los modelos del §3.
