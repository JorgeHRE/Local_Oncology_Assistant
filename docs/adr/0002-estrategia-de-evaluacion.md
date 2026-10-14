# ADR-0002: Estrategia de evaluación por capas

- **Estado:** Propuesto. Pasa a *Aceptado* cuando el profesor lo revise y se cierre ADR-0003 (ground truth).
- **Fecha:** 2026-10-14
- **Decisores:** Jorge (autor), con asistencia de Claude Code
- **Relacionado:** `docs/protocolo.md` (feedback del profesor, `CLAUDE.md` §13), ADR-0003 (ground
  truth), ADR-0004 (motor de inferencia), ADR-0005 (LLM), `docs/cohorte-zolbetuximab.md`

## Contexto

El profesor preguntó "qué estrategia vas a utilizar para evaluar a los modelos y cómo la vas a
implementar". Hay que decidirlo **antes** de elegir motor y LLM: son las métricas las que permiten
comparar modelos con evidencia y no por reputación.

El sistema tiene cuatro etapas encadenadas: recuperar texto del corpus (RAG), extraer criterios de
inclusión/exclusión, traducirlos a SQL y ejecutarlos sobre OMOP. Un error en una etapa contamina las
siguientes, así que una sola métrica final ("¿salió la cohorte correcta?") no dice dónde falló.

Restricciones:

- **Local:** el LLM corre en una RTX 5070 de **12 GB de VRAM**. No caben a la vez el modelo evaluado
  y un juez de tamaño comparable.
- **CI:** los runners de GitHub no tienen GPU ni el vocabulario de Athena (no redistribuible), así
  que hoy solo corren los tests sin base de datos.
- **Muestra pequeña:** el protocolo habla de 30–50 preguntas. Con tan pocos casos, una diferencia
  de uno o dos puntos entre modelos es ruido.

## Opciones consideradas

### A. Qué corre en CI

1. **Capas deterministas en CI; capas con LLM solo en local (elegida).**
2. Todo local; CI solo lint y tests unitarios.
3. Todo en CI con un LLM diminuto.

La opción 3 se descarta porque un modelo de juguete en CPU es lento y sus resultados no
representan al modelo real. La opción 2 deja la evaluación fuera de la puerta de calidad de cada PR.

### B. Cómo medir la fidelidad del RAG

1. **Juez LLM local, distinto del modelo evaluado (elegida).**
2. El mismo modelo como juez.
3. Sin juez: solo métricas con respuesta de referencia.

La opción 2 introduce sesgo de autoevaluación (un modelo tiende a favorecer su propio estilo). La
opción 3 no mide si la respuesta se apoya en el contexto recuperado, que el protocolo pide.

### C. Herramienta

1. **Ragas para las métricas del RAG; pytest y SQL propios para lo determinista (elegida).**
2. DeepEval para todo.
3. Todo propio.

Ragas ya aparece en el protocolo. Las capas deterministas no necesitan framework: son
comparaciones de conjuntos.

## Decisión

### 1. Cinco capas, cada una con su ground truth y su lugar de ejecución

| # | Capa | Qué mide | Métrica | Ground truth | Depende de LLM | Dónde corre |
|---|---|---|---|---|---|---|
| 1 | Retrieval | ¿Se recuperan los fragmentos que contienen el criterio? | recall@k, MRR | Fragmentos relevantes por pregunta (ADR-0003) | No (solo embeddings) | Local |
| 2 | Extracción | ¿Los criterios extraídos son correctos? | Precisión/recall/F1 por criterio (concepto, operador, valor, ventana temporal) y **validez del esquema** (pydantic) | Criterios correctos por protocolo (nivel *a*) | Sí | Local; la validación de esquema también en CI sobre salidas guardadas |
| 3 | SQL | ¿La consulta ejecuta y es segura? | Tasa de ejecución sin error; solo `SELECT` | Ninguno | Sí | Local; en CI con el SQL de referencia |
| 4 | Cohorte | ¿Devuelve a los pacientes correctos? | Precisión, recall y Jaccard de `person_id` | Conjunto exacto de `person_id` (nivel *b*) | Sí | Local; en CI con el SQL de referencia |
| 5 | Fidelidad RAG | ¿La respuesta se apoya en el contexto? | `faithfulness`, `context_precision` (Ragas) | Juez LLM | Sí (dos modelos) | Local |

La capa 4 es **determinista**: se compara un conjunto de enteros, sin juez. Es la única métrica
final sin ambigüedad y por eso es la principal.

### 2. Qué entra en CI y qué no

- **CI (en cada PR):** pruebas del *arnés* de evaluación, sin GPU y sin Athena: el cálculo de
  métricas sobre casos de ejemplo, la validación de esquema de salidas guardadas y el formato del
  ground truth. El test de la cohorte contra los CSV (`tests/test_cohort_zolbetuximab.py`) sigue
  siendo local por necesitar la base.
- **Local (con GPU):** las corridas con LLM. Cada corrida escribe un archivo de resultados
  versionado en `eval/results/` con: modelo y cuantización, versión del motor, hash del prompt,
  semilla, temperatura 0, hash del corpus, commit del repo y métricas **por pregunta** (no solo el
  promedio).

> 💡 **Por qué esto importa en la industria:** lo que se audita no es "el modelo anda bien" sino
> "con esta versión, estos datos y este prompt, se obtuvo este resultado". Versionar datos, prompt y
> modelo junto al código es lo que permite reproducir una validación meses después.

### 3. Juez de la capa 5

Un LLM abierto local, **distinto del evaluado**. Como en 12 GB no caben los dos, la evaluación va en
**dos pasadas** (diseño en la sección siguiente): primero se generan todas las respuestas con el
modelo evaluado y se guardan; luego se descarga y se carga el juez para calificarlas. Se valida el
juez a mano con una muestra de respuestas (concordancia con la anotación humana) y se declara como
limitación.

Con la ejecución secuencial nunca hay dos modelos en VRAM, así que la ventaja de memoria de usar el
mismo modelo como juez (opción B.2) es pequeña: queda solo el ahorro de un cambio de modelo. No
compensa el sesgo de autoevaluación. El juez distinto también debe caber en 12 GB por sí solo
(orden de 14B cuantizado a 4 bits), así que será de capacidad parecida al evaluado, no superior;
por eso la validación manual de una muestra es obligatoria. El mismo modelo como juez se usa solo
como **prueba de sensibilidad** opcional: si las puntuaciones casi no cambian entre los dos jueces,
es buena señal.

### 4. Diseño del script de evaluación

Pruebas y evaluaciones son cosas distintas y no se mezclan:

- **Tests (pytest):** pasan o fallan. Los que necesitan un modelo servido en local llevan el marcador
  **`llm`** (en la misma línea que `db`): se registra en `pyproject.toml` junto con
  `--strict-markers`, un fixture en `conftest.py` los salta si el motor no responde, y el CI los
  excluye con `-m "not db and not llm"` (igual que el target `test-fast` del Makefile). Ejemplos: el
  motor responde, la salida cumple el esquema pydantic, el SQL generado es un `SELECT`. Si más
  adelante hace falta separar el juez, se añade `llm_judge`.
- **Evaluaciones:** miden, no aprueban ni fallan (el umbral se fija tras la línea base). Son un
  comando propio, `python -m oncology_assistant.eval`, en tres subcomandos:
  1. `generate`: ejecuta el pipeline con el modelo evaluado y escribe un archivo con todo lo
     intermedio (pregunta, fragmentos recuperados, criterios extraídos, SQL y respuesta), con un
     identificador de corrida que fija modelo, prompt, semilla y commit.
  2. `judge --run <id>`: lee ese archivo, carga el juez y escribe las puntuaciones de la capa 5.
  3. `metrics --run <id>`: calcula las capas deterministas (extracción, SQL, cohorte) sobre el
     mismo archivo, sin ningún modelo.

Separar las fases permite **volver a juzgar sin regenerar** (cambiar de juez o repetir si falla),
**comparar dos jueces** sobre las mismas respuestas y retomar una corrida interrumpida. El costo es
que cambiar de modelo entre fases tarda: con Ollama basta descargarlo (`keep_alive: 0`), pero con
vLLM o SGLang suele ser necesario reiniciar el servidor. Esto es un criterio para el ADR-0004.

### 5. Línea base y comparación

- Toda mejora se compara con una **línea base simple** (por ejemplo, el LLM sin RAG y recuperación
  por palabras clave), para saber cuánto aporta cada pieza.
- Los **umbrales de aceptación se fijan después de medir la línea base**, no antes: con una muestra
  de 30–50 preguntas, inventar un umbral sería arbitrario.
- Con n pequeño se reportan **intervalos de confianza** (bootstrap) y comparaciones **pareadas** por
  pregunta; una diferencia dentro del intervalo no se declara mejora.

### 6. Separación desarrollo/prueba

El ground truth se divide en un conjunto de **desarrollo** (para iterar prompts y chunking) y uno
de **prueba** congelado, que se corre una vez por candidato para la decisión final. Evita ajustar el
sistema a las mismas preguntas con que se juzga. La proporción y la forma de construirlos se definen
en ADR-0003.

## Consecuencias

- **Buenas:** se sabe en qué capa falla el sistema; la métrica final de cohorte es objetiva; los
  resultados son reproducibles y auditables; CI sigue siendo rápido y sin GPU.
- **Costos:** hay que construir un arnés (`src/oncology_assistant/eval/`) y un directorio
  `eval/results/`; la evaluación completa es lenta (dos pasadas con cambio de modelo); `ragas` es una
  dependencia pesada que se añade solo como extra opcional y con versión acotada.
- **Riesgos y límites:**
  - El juez LLM es la parte más débil: puede tener sesgos propios. Mitigación: modelo distinto,
    validación manual de una muestra y declararlo en `docs/LIMITACIONES.md`.
  - Un solo anotador (ver ADR-0003): sin acuerdo entre anotadores no se puede medir la fiabilidad del
    ground truth.
  - Los datos son sintéticos y los umbrales clínicos del módulo salen de memoria: la corrección de la
    cohorte es respecto al ground truth del proyecto, no respecto a la realidad clínica.
  - La API de Ragas cambia entre versiones: acotar la versión al implementar.

## Preguntas abiertas

- ¿Cuántas preguntas por capa? (ADR-0003.)
- ¿Qué embeddings usa la capa 1? (Depende del ADR del motor/LLM.)
- ¿Qué modelo actúa de juez? (Se decide en ADR-0005 junto con el LLM evaluado.)
- ¿Cuánto cuesta el cambio de modelo entre fases con cada motor? (Criterio para ADR-0004.)
- ¿Qué proporción desarrollo/prueba? (ADR-0003.)
