# ADR-0005: Modelo de lenguaje (LLM) para responder con los textos

- **Estado:** Propuesto. Faltan dos cosas: el juicio de corrección de las respuestas R por el anotador
  (las tablas de abajo son automáticas) y la corrida única sobre `test`.
- **Fecha:** 2026-11-17
- **Decisores:** Jorge (autor), con asistencia de Claude Code
- **Relacionado:** ADR-0002 (evaluación por capas), ADR-0003 (ground truth; `test` se evalúa una vez),
  ADR-0004 (motor: Ollama), ADR-0007 (embeddings y reformulación)

## Contexto

`CLAUDE.md` §6 pide justificar el LLM: un modelo generalista reciente frente a uno biomédico
especializado, pesando la capacidad de seguir un formato estructurado frente al conocimiento clínico
propio, dado que el RAG ya aporta el conocimiento del dominio. Restricciones: 12 GB de VRAM (RTX 5070),
datos que no salen de la máquina, salida JSON con esquema (ADR-0004) y respuestas que citen el texto.

Hasta ahora **qwen3:8b** era un marcador de posición, elegido para medir el motor (ADR-0004).

## Opciones comparadas

| Modelo | Tipo | Tamaño en disco | Notas |
|---|---|---|---|
| qwen3:8b | generalista | 5,2 GB | el marcador de posición actual |
| gemma3:12b | generalista, más grande | 8,2 GB | cabe, pero con poco margen junto al embedder (~1,2 GB) |
| medgemma:4b | biomédico (Google) | 3,3 GB | variante pequeña; la de 27B no cabe en 12 GB |

## Método

Dos tareas del LLM, sobre el conjunto de `dev`. **Respuesta** (`make eval-generation`, `eval_generation.py`): las 6 R. El retriever, la reformulación (con
qwen3:8b en todos los casos) y los fragmentos son **idénticos** para los tres modelos; solo cambia la
generación. Temperatura 0 y semilla fija; la latencia excluye una llamada de calentamiento que carga el
modelo. Sin reintento de citas, para ver el comportamiento crudo.

## Resultados automáticos (6 R de `dev`)

| Modelo | JSON válido | Respondió | Respondió con citas literales | Se negó | Se negó con la evidencia presente* | s/respuesta |
|---|---|---|---|---|---|---|
| qwen3:8b | 6/6 | 4 | **4 de 4** | 2 | 1 | 1,2 |
| gemma3:12b | 6/6 | 6 | 4 de 6 | 0 | 0 | 2,7 |
| medgemma:4b | 6/6 | 4 | **4 de 4** | 2 | **2** | **0,9** |

\* 5 de las 6 preguntas tenían alguna cita de referencia entre los fragmentos recuperados.

Lectura de los números:
- Los tres siguen el formato JSON sin fallos.
- **gemma3:12b** no se niega nunca, pero en 2 de 6 respuestas la cita no es literal: contesta con
  seguridad algo que no puede respaldar en el texto.
- **qwen3:8b** y **medgemma:4b** nunca dieron una respuesta con cita inventada; en cambio se niegan más
  (medgemma lo hizo 2 veces teniendo la evidencia).
- El modelo biomédico no mostró una ventaja: el conocimiento clínico lo aporta la recuperación.

## Extracción de criterios (4 E de `dev`, 51 criterios de referencia)

`make eval-extraction` (`eval_extraction.py`): cada modelo recibe la sección de inclusión o exclusión de un
ensayo (todos los chunks de ese ensayo y sección, en orden, como los traería un filtro de metadatos) y
devuelve criterios atómicos con el formato de la guía. Se puntúa contra los criterios del anotador, sin
juez automático: emparejando por la cita que respalda cada criterio.

| Modelo | JSON válido | Cobertura de citas | Citas literales | Criterios extraídos / referencia | Operador | Valor | `evaluable` | s/sección |
|---|---|---|---|---|---|---|---|---|
| qwen3:8b | 4/4 | 0,97 | **0,98** | **1,12** | 0,56 | **0,78** | (0,76)† | 13,6 |
| gemma3:12b | 4/4 | 0,97 | 0,94 | 1,92 | **0,78** | 0,66 | (0,76)† | 27,4 |
| medgemma:4b | 4/4 | 0,91 | 0,87 | 1,41 | 0,27 | 0,58 | (0,79)† | **9,3** |

† **La columna `evaluable` no es interpretable** (ver el aviso de abajo): no se resalta ninguna cifra.

Cobertura = parte de las citas de referencia que algún criterio extraído cita; operador, valor y `evaluable`
son el acuerdo con la referencia sobre los criterios cubiertos (50/51 para qwen3 y gemma3, 48/51 para
medgemma). Un cociente de criterios cercano a 1 indica que el modelo separa las condiciones como el anotador.

Lectura:
- **qwen3:8b** es el más fiel al texto (0,98 de citas literales) y el que más se parece al anotador en la
  granularidad (1,12), con el mejor acuerdo en el valor.
- **gemma3:12b** parte casi cada criterio en dos (1,92) y tarda el doble, aunque acierta más el operador.
- **medgemma:4b**, el biomédico, es el más débil en operador y en citas literales; solo gana en velocidad.
- `evaluable`: **no se saca ninguna conclusión**. La referencia de `dev` tiene el 80 % de los criterios en
  True (41 de 51), y aproximadamente 24 de ellos contradicen la tabla del §4 de la guía (lesión medible,
  embarazo, metástasis del sistema nervioso central, analíticas, comorbilidades no modeladas, radioterapia
  y cirugía previas...). Un modelo que marcara todo como evaluable tendría un acuerdo de 0,80, así que los
  tres (0,76 a 0,79) están por debajo de esa línea base trivial. No es solo medgemma: marca True en el 97 %
  de sus criterios, qwen3:8b en el 89 % y gemma3:12b en el 77 %.
- El acuerdo en **operador** depende de convenciones (por ejemplo `=` frente a `present`), así que es la
  cifra más frágil.

## Aviso: la referencia de `evaluable` está sin revisar (2026-11-17)

La revisión de los flags de `evaluable` de las E (y de las C) encontró criterios marcados True que la guía
§4 lista como no evaluables. Hasta que el anotador los corrija, la columna `evaluable` de la extracción no
debe usarse para elegir modelo, y deberá repetirse la medición (`make eval-extraction`, ~5 min) con la
referencia corregida. Las demás columnas y las medidas sobre las R no dependen de esto. El listado de
criterios a revisar sale de `make review-evaluable`; los cambios en el ground truth los hace el anotador
(ADR-0003).

## Pendiente antes de decidir

1. **Corrección de las respuestas**, que solo puede juzgar el anotador: `data/processed/llm_comparison_dev.md`
   lista cada pregunta, su respuesta de referencia y la de cada modelo, con un hueco "Correcta (sí / parcial /
   no)". Un juez automático con modelos de las mismas familias estaría sesgado.
2. Corregir los flags de `evaluable` y repetir la medición de extracción (ver el aviso de arriba).
3. Confirmar con las R de `test` en **una sola** corrida (ADR-0003).

## Límites

- **Muestras pequeñas:** 6 R y 4 E. En las R, las diferencias de un caso son ruido. Las E suman 51
  criterios, pero vienen de solo 2 ensayos (NCT06123494 y NCT06177041): miden el estilo de esas fichas.
- La referencia de `evaluable` de las E está sin revisar (ver el aviso); la comparación de extracción se
  repetirá cuando se corrija.
- La extracción de criterios hacia SQL aún no está integrada en el asistente; esta medición justifica el
  modelo para esa tarea, no el flujo completo.
- No se probaron otros modelos (por ejemplo, de 14B cuantizados), ni se afinó el prompt por modelo.

## Decisión

*(Pendiente del juicio de corrección de las R.)* Con las dos tareas, la preferencia razonada por estos
datos es **qwen3:8b**: no inventa citas en las R, en la extracción es el más literal y el más parecido al
anotador en granularidad, es el que ya está integrado, deja VRAM libre para el embedder (5,2 GB frente a
8,2 GB de gemma3:12b) y el RAG reintenta las citas no literales. El modelo biomédico no aporta ventaja en
ninguna de las dos tareas.
