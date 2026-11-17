# ADR-0007: Modelo de embeddings del retriever

- **Estado:** Propuesto. Medido con solo 6 preguntas R de desarrollo; falta confirmarlo con una
  sola corrida sobre `test` y probar un modelo biomédico.
- **Fecha:** 2026-11-17
- **Decisores:** Jorge (autor), con asistencia de Claude Code
- **Relacionado:** ADR-0002 (recall@k, capa de recuperación), ADR-0003 (ground truth; `test` se evalúa
  una vez), ADR-0004 (motor: Ollama), ADR-0006 (chunking; esta decisión era la "pendiente" ahí)

## Contexto

La prueba anecdótica del índice (PR #11) mostró que el embedder inicial, all-MiniLM-L6-v2 (ONNX, solo
inglés, generalista), clasifica mal consultas con símbolos y abreviaturas (CLDN18.2, PD-L1, HER2),
justo de lo que tratan las preguntas. Con el ground truth completo se puede medir: recall@k de las R
(fracción de citas de referencia que están en los k primeros chunks), con la recuperación restringida
a los ensayos nombrados en la pregunta, estrategia B (un chunk por criterio).

## Opciones medidas (6 R de `dev`, `make eval-retrieval`)

| Embedder | Tamaño | recall@1 | @3 | @5 | @10 |
|---|---|---|---|---|---|
| all-MiniLM-L6-v2 (por defecto), vector | 23 M | 0,25 | 0,33 | 0,33 | 0,33 |
| all-MiniLM-L6-v2, híbrida (BM25 + vector) | 23 M | 0,25 | 0,33 | 0,33 | 0,50 |
| **bge-m3**, vector | 568 M | **0,42** | 0,42 | 0,50 | **0,67** |
| bge-m3, híbrida | 568 M | 0,25 | 0,25 | 0,67 | 0,67 |
| qwen3-embedding:0.6b, vector | 600 M | 0,17 | 0,42 | 0,42 | 0,67 |
| qwen3-embedding:0.6b, híbrida | 600 M | 0,42 | 0,42 | 0,42 | 0,67 |

Los modelos nuevos se sirven con el mismo Ollama (ADR-0004), cada uno con su índice
(`data/processed/chroma_<modelo>`), construido con los mismos chunks.

## Reformulación de la pregunta (2026-11-17)

Antes de buscar, el LLM local reescribe la pregunta como consulta de búsqueda (conserva los NCT y los
números, expande abreviaturas y nombra el biomarcador como lo hacen los criterios). Se busca con la
pregunta original y con la reformulada y se fusionan por rango (RRF). Con **bge-m3**, 6 R de `dev`:

| Búsqueda | recall@1 | @3 | @5 | @10 |
|---|---|---|---|---|
| vector, sin reformular | 0,42 | 0,42 | 0,50 | 0,67 |
| vector, **con reformulación** | 0,42 | **0,75** | **0,75** | **0,83** |
| híbrida, con reformulación | 0,25 | 0,58 | 0,83 | 0,83 |

Solo falla R-002 (una pregunta muy general sobre "qué biomarcador excluye" en un ensayo de 37
chunks). Cuesta una llamada extra al LLM (~1 s). La reformulación no ve el ground truth: solo recibe
el texto de la pregunta.

## Decisión

Usar **bge-m3** por defecto (variable `RAG_EMBEDDER`; `default` vuelve al ONNX), con búsqueda
solo vectorial y con reformulación de la pregunta (`--no-rewrite` la desactiva). Razones: es el mejor en recall@1 y @10 junto con el otro modelo nuevo, es
multilingüe (el RAG responde preguntas en español: el MiniLM es solo inglés) y se ejecuta en la
misma GPU y el mismo servidor que el LLM. La búsqueda híbrida (BM25) ayudó con el MiniLM pero no
mejora de forma consistente con los modelos nuevos; queda disponible (`hybrid.py`) y activada por
defecto en `rag.retrieve`, pendiente de decidir con más datos.

Prueba cualitativa: una pregunta sin NCT ("What CLDN18.2 expression threshold is required in
zolbetuximab trials?"), que fallaba con el MiniLM, ahora recupera el criterio de ≥ 75 % y la cita
se verifica.

## Consecuencias y límites

- **Muestra mínima:** 6 preguntas; las diferencias entre bge-m3 y qwen3-embedding (@1, @5) son ruido.
  Con las 20 R (14 de `test`) habría que repetir la medición **una sola vez** (ADR-0003 §4).
- Las R-001 y R-002 (ensayo de 37 chunks) siguen sin recuperarse a k = 10 con ninguno.
- No se probó un modelo biomédico (por ejemplo, un BioBERT/PubMedBERT adaptado a embeddings): no está en
  el registro de Ollama; requeriría otra vía de ejecución.
- Hay que reconstruir el índice al cambiar de modelo: `make index-embed MODEL=bge-m3` (~30 s).
- Coste: ~1,2 GB de disco y ~1,2 GB más de VRAM mientras el modelo está cargado (el LLM ocupa ~5,6 GB).
