# ADR-0006: Estrategia de chunking e indexación

- **Estado:** Propuesto. La implementación existe; la comparación B frente a C con recall@k queda
  pendiente del ground truth (ADR-0003).
- **Fecha:** 2026-11-05
- **Decisores:** Jorge (autor), con asistencia de Claude Code
- **Relacionado:** ADR-0002 (recall@k de recuperación, el conjunto de desarrollo es donde se itera el
  chunking), ADR-0003 (ground truth), ADR-0005 (LLM), `docs/corpus.md`

## Contexto

El LLM local (12 GB de VRAM) no puede leer los 88 documentos en cada pregunta. El RAG recupera los
trozos más cercanos a la pregunta y se los entrega como contexto. Cómo se parte el corpus decide si el
criterio correcto aparece entre los resultados y si llega completo.

El corpus es pequeño y muy estructurado (medido el 2026-11-05):

- **49 fichas de ClinicalTrials.gov:** criterios de 539 a 15 392 caracteres (mediana 3 740), con
  secciones de inclusión y exclusión en 47 de 49 y unas 24 viñetas por ficha (5 a 71). La numeración
  viene en Markdown, a veces escapada (`1\.`, `18\~75`), y alguna ficha agrupa todo en una viñeta o en
  una línea con `1) … 2) …`.
- **39 resúmenes de PubMed:** de 680 a 5 063 caracteres (mediana 2 279), la mayoría con secciones
  etiquetadas (`METHODS:`, `RESULTS:`…) y 13 sin etiquetas.

## Opciones consideradas

1. **A. Tamaño fijo con solapamiento.** Simple, pero corta viñetas y separa una exclusión de su
   encabezado: "ECOG 0–1" bajo *Exclusion* significa otra cosa que bajo *Inclusion*.
2. **B. Estructural.** Un chunk por criterio (con su sección y sus sub-viñetas) y uno por sección de
   resumen.
3. **C. Documento completo.** Un chunk por documento.
4. **D. Jerárquico.** Chunks pequeños para buscar y el padre para dar contexto. Con documentos tan
   cortos aporta poco a cambio de bastante complejidad.

## Decisión

Implementar **B** y **C** sobre los mismos documentos, en dos colecciones de ChromaDB
(`gastric_structural`, `gastric_whole`), y compararlas con recall@k sobre el conjunto de desarrollo
del ground truth. C es la línea base: sin ella no hay forma de saber si B mejora algo.

Reglas de B (`src/oncology_assistant/chunking.py`):

- Un criterio empieza en una viñeta sin sangría y **incluye sus sub-viñetas**, para que alternativas
  del tipo "no puede tener hijos O usa anticonceptivos" no se separen.
- Cada chunk guarda `section` (`inclusion`, `exclusion`, `other`), `identifier` (NCT o PMID), `role`
  (pivotal, candidate, distractor, reference) y `position`. Esos metadatos permiten filtrar y citar la
  fuente exacta de una respuesta.
- Un criterio de más de 1 500 caracteres se divide en sus sub-viñetas (repitiendo la frase
  introductoria) o en su numeración en línea. Con esa regla ningún chunk de ficha supera ese tamaño.
- Los resúmenes se parten por etiqueta; los no etiquetados quedan en un solo chunk. No se parten por
  tamaño (el más largo mide 2 799 caracteres).
- Para el embedding, el texto del chunk lleva una cabecera con el título y la sección; lo que se
  almacena y devuelve es el texto sin cabecera.
- La colección se **reconstruye entera** en cada ejecución: el índice es función pura del corpus y del
  código de chunking.

Resultado: 1 373 chunks estructurales (mediana de 153 caracteres, p95 de 892) frente a 88 de la línea
base. 29 chunks tienen menos de 25 caracteres ("Measurable disease"); se mantienen porque son
criterios completos.

## Consecuencias

- **A favor:** cada chunk corresponde a un criterio, que es la unidad del ground truth de nivel *a*
  (ADR-0003) y de la trazabilidad: se puede mostrar qué línea de qué protocolo respalda una respuesta.
  El chunking es determinista y se prueba sin modelo (`tests/test_chunking.py` comprueba, en las 49
  fichas, que no se pierde ni una palabra).
- **En contra:** hay un parser que mantener y cada nueva fuente (guías NCCN/ESMO) necesitará el suyo.
  Un criterio muy corto ("HER2-positive tumors") tiene poco contexto propio; la cabecera con título y
  sección lo mitiga pero no lo elimina.
- **Riesgo:** los chunks atómicos pueden perder referencias entre criterios ("según el criterio 4").
  Se mide en la evaluación; si molesta, se pasa a D.
- **Modelo de embeddings (decisión pendiente, ADR aparte):** por ahora se usa el modelo por defecto de
  ChromaDB (all-MiniLM-L6-v2, ONNX, local tras una descarga única). Es un modelo generalista en inglés
  y el corpus está en inglés, pero no es biomédico. Se compararán alternativas con el mismo ground truth.
- **Criterio de revisión:** si en el conjunto de desarrollo B no supera a C en recall@5 por al menos
  5 puntos, se descarta la complejidad de B y se vuelve a decidir.
