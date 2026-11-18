# ADR-0005: Modelo de lenguaje (LLM) para responder con los textos

- **Estado:** Aceptado (2026-11-17): el autor elige **qwen3:8b**. La confirmación sobre `test` (una sola
  corrida, ADR-0003) y la mejora del prompt de extracción para `evaluable` quedan pendientes y no cambian la
  decisión, salvo que la corrida de `test` mostrara un problema grave.
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
| qwen3:8b | 4/4 | 0,97 | **0,98** | **1,12** | 0,56 | **0,78** | 0,38 | 12,2 |
| gemma3:12b | 4/4 | 0,97 | 0,94 | 1,92 | **0,78** | 0,66 | **0,54** | 27,4 |
| medgemma:4b | 4/4 | 0,91 | 0,87 | 1,41 | 0,27 | 0,58 | 0,31 | **9,0** |

Cobertura = parte de las citas de referencia que algún criterio extraído cita; operador, valor y `evaluable`
son el acuerdo con la referencia sobre los criterios cubiertos (50/51 para qwen3 y gemma3, 48/51 para
medgemma). Un cociente de criterios cercano a 1 indica que el modelo separa las condiciones como el anotador.

Lectura:
- **qwen3:8b** es el más fiel al texto (0,98 de citas literales) y el que más se parece al anotador en la
  granularidad (1,12), con el mejor acuerdo en el valor.
- **gemma3:12b** parte casi cada criterio en dos (1,92) y tarda el doble, aunque acierta más el operador.
- **medgemma:4b**, el biomédico, es el más débil en operador y en citas literales; solo gana en velocidad.
- `evaluable` (tras corregir la referencia, ver más abajo): ahora **sí discrimina**. La referencia de `dev`
  quedó con 16 de 51 criterios en True (0,31); "todo True" daría 0,31 y "todo False" 0,69. **Ningún modelo
  llega a 0,69**: gemma3:12b es el mejor (0,54), qwen3:8b (0,38) y medgemma:4b (0,31, igual que marcar todo
  como evaluable) casi no declaran nada como no evaluable, aunque el prompt les da la lista de la guía.
  Marcan True en el 89 % (qwen3:8b), 77 % (gemma3:12b) y 97 % (medgemma:4b) de sus criterios, frente al 31 %
  de la referencia. Es el punto débil de qwen3:8b y el de todos.
- El acuerdo en **operador** depende de convenciones (por ejemplo `=` frente a `present`), así que es la
  cifra más frágil.

## Corrección de la referencia de `evaluable` (2026-11-17)

La primera medición de la extracción usó una referencia con 41 de 51 criterios en True, de los que unos 24
contradecían la tabla del §4 de la guía (lesión medible, embarazo, metástasis del SNC, analíticas...). Con ese
sesgo, "todo True" daba 0,80 y los tres modelos (0,76 a 0,79) quedaban por debajo, así que la columna no medía
nada. El anotador revisó los flags con la ayuda de `make review-evaluable` (que solo lista; los cambios son
suyos, ADR-0003): **45 criterios de las E pasaron a no evaluables** y la referencia de `dev` quedó en 16 de 51.
Las demás columnas no cambiaron (no dependen de este campo); `evaluable` se repitió con la referencia corregida
(tabla de arriba).

## Pendiente antes de decidir

1. **Corrección de las respuestas**, que solo puede juzgar el anotador: `data/processed/llm_comparison_dev.md`
   lista cada pregunta, su respuesta de referencia y la de cada modelo, con un hueco "Correcta (sí / parcial /
   no)". Un juez automático con modelos de las mismas familias estaría sesgado.
2. Mejorar el prompt de extracción para que declare no evaluable lo que la guía lista (por ejemplo con
   ejemplos de casos negativos) y repetir la medición, sin tocar `test`.
3. Confirmar con las R de `test` en **una sola** corrida (ADR-0003).

## Límites

- **Muestras pequeñas:** 6 R y 4 E. En las R, las diferencias de un caso son ruido. Las E suman 51
  criterios, pero vienen de solo 2 ensayos (NCT06123494 y NCT06177041): miden el estilo de esas fichas.
- El prompt de extracción es el mismo para los tres modelos y no incluye ejemplos; el bajo acuerdo en
  `evaluable` puede deberse al prompt y no a los modelos.
- La extracción de criterios hacia SQL aún no está integrada en el asistente; esta medición justifica el
  modelo para esa tarea, no el flujo completo.
- No se probaron otros modelos (por ejemplo, de 14B cuantizados), ni se afinó el prompt por modelo.

## Decisión

**qwen3:8b** (decisión del autor, 2026-11-17), servido por Ollama (ADR-0004) con salida JSON con esquema,
temperatura 0 y semilla fija. Razones, con los datos de `dev`:

- No dio ninguna respuesta con una cita inventada en las R; en la extracción es el más literal (0,98) y el
  más parecido al anotador en granularidad (1,12), y el mejor en el valor (0,78).
- Ya está integrado en el asistente, y ocupa 5,2 GB frente a 8,2 GB de gemma3:12b: deja VRAM libre para el
  embedder (bge-m3, ADR-0007) y para la reformulación de las preguntas.
- El RAG reintenta las citas no literales y las marca como no confiables, lo que compensa sus negativas.
- El modelo biomédico (medgemma:4b) no aportó ventaja en ninguna de las dos tareas: el conocimiento clínico
  lo aporta la recuperación.
- **Licencia:** qwen3:8b es Apache-2.0, sin restricciones de uso que trasladar; gemma3:12b y medgemma:4b
  tienen licencias propias de Google (Gemma Terms of Use y Health AI Developer Foundations), que exigen
  trasladar restricciones si se redistribuyen o derivan. Revisadas el 2026-11-17 (`docs/USO_DE_IA.md` §3).

**Matices que se aceptan:**
- En `evaluable` qwen3:8b es peor que gemma3:12b (0,38 frente a 0,54), y ningún modelo llega a la línea base
  de "todo False" (0,69). La declaración de no evaluable queda como trabajo pendiente de la extracción (prompt
  con ejemplos negativos o una regla determinista sobre el concepto).
- La evidencia es pequeña (6 R y 4 E de dos ensayos). Las diferencias finas entre modelos no son concluyentes.

**Se reevalúa si:** la corrida única sobre `test` muestra un problema grave; cambia el hardware (por ejemplo,
más VRAM permitiría un modelo mayor); o aparece un candidato claramente mejor.
