# Protocolo de Investigación: Asistente RAG Local y Análisis de Cohorte OMOP en Cáncer Gástrico

- **Versión:** 2 (2026-11-17), revisada tras el feedback del profesor (§7). La versión inicial (Sesión 10)
  tenía las secciones 1 a 6; se mantienen, con los cambios señalados.

## 1. Título del Proyecto
Evaluación de elegibilidad y caracterización de cohorte en adenocarcinoma gástrico mediante un sistema RAG biomédico local y consultas SQL sobre OMOP CDM.

## 2. Justificación y Antecedentes
La adopción de modelos de lenguaje grande (LLMs) en entornos clínicos y farmacéuticos se ve limitada por estrictas normativas de privacidad de datos y el riesgo de alucinaciones en información biomédica compleja. Este proyecto implementa una arquitectura 100% local y segura para asistir en la revisión de protocolos oncológicos y guías de práctica clínica, vinculando la evidencia no estructurada con datos observacionales estandarizados bajo el modelo OMOP CDM.

## 3. Pregunta de Investigación
¿Cómo optimizar de forma reproducible la identificación y validación de criterios de inclusión/exclusión para pacientes con adenocarcinoma gástrico avanzado mediante la integración de recuperación de literatura (*RAG*) y la ejecución de consultas estructuradas en una base de datos OMOP CDM?

## 4. Población Objetivo y Datos
* **Datos No Estructurados (RAG):** corpus de **88 documentos**: 49 fichas de elegibilidad de ensayos de ClinicalTrials.gov y 39 resúmenes de PubMed sobre biomarcadores en cáncer gástrico (HER2, Claudina 18.2, MSI-H, PD-L1), con fuente, versión, fecha y SHA-256 (`corpus/manifest.json`). Base vectorial local (ChromaDB). *Cambio:* las guías NCCN/ESMO no están en el corpus (requieren obtención manual; ver §6).
* **Datos Estructurados (OMOP CDM):** población sintética oncológica generada con Synthea (módulo gástrico propio) y cargada en OMOP CDM v5.4 local (PostgreSQL en Docker): 1 360 pacientes.

## 5. Metodología y Entregables
1. **Módulo RAG local:** ingesta, *chunking* (un fragmento por criterio) e indexación; recuperación híbrida con reformulación de la pregunta; respuesta con un LLM abierto local en GPU; **cada cita se verifica contra el texto** y se marca como no confiable si no es literal.
2. **Cohortes SQL:** scripts `sql/01_concept_sets.sql`, `sql/02_cohorte.sql` y un SQL por ensayo (`sql/cohort_*.sql`), cada uno con su tabla de atrición. Un asistente enruta las preguntas por pacientes a esas vistas, sin que el LLM escriba SQL ni toque los números.
3. **Evaluación cuantitativa:** ground truth propio de **40 preguntas** (*cambio:* eran 30) y métricas por capas (§7.4). *Cambio:* no se usa Ragas para la fidelidad (queda como capa pendiente); se mide la fidelidad por la verificación literal de citas y por el juicio del anotador.
4. **Reproducibilidad:** entorno containerizado con Docker Compose, flujo con `make` y CI en GitHub Actions (ruff y pytest).

## 6. Limitaciones Previstas
* Dependencia de la calidad del etiquetado y realismo de los datos sintéticos de Synthea frente a historiales clínicos reales (el módulo no puede reponderar edad ni sexo; CLDN18.2 es una aproximación: `docs/LIMITACIONES.md`).
* Acotación del corpus a fichas de ensayos y resúmenes seleccionados; sin guías NCCN/ESMO.
* **Un solo anotador** del ground truth: la fiabilidad medida es la propia (re-anotación a ciegas pendiente, ≥ una semana después de la primera pasada).
* **Muestras pequeñas** (6 R y 4 E de desarrollo; las E vienen de dos ensayos): las diferencias finas entre modelos no son concluyentes.
* El SQL de la cohorte C-007 (SPOTLIGHT) tiene su base escrita con Claude Code y fue revisado a mano (declarado en el ground truth); el recálculo independiente con pandas (ADR-0003) existe solo para la cohorte de zolbetuximab, también escrito con Claude Code; no está en el repositorio para las otras siete.
* Las cohortes solo aplican criterios que los datos pueden comprobar; existen para 8 ensayos.

## 7. Decisiones técnicas (respuesta al feedback del profesor)

> "Qué LLM vas a usar, cómo lo vas a ejecutar (SGLang, vLLM, Ollama, etc.), y especialmente cómo vas a construir el ground truth para comparar los modelos. Además, qué estrategia vas a utilizar para evaluar a los modelos y cómo la vas a implementar."

Cada decisión está en un ADR (`docs/adr/`) con contexto, opciones y consecuencias. Aquí, el resumen.

### 7.1 LLM: **qwen3:8b** (ADR-0005, Aceptado)
Se compararon tres candidatos que caben en 12 GB de VRAM, con los mismos fragmentos recuperados y temperatura 0: qwen3:8b (generalista), gemma3:12b (generalista mayor) y medgemma:4b (biomédico). Sobre el conjunto de desarrollo:
- **Respuesta (6 preguntas):** qwen3:8b y medgemma:4b no dieron ninguna cita inventada (se niegan más); gemma3:12b nunca se niega y en 2 de 6 respuestas la cita no es literal.
- **Extracción de criterios (4 secciones, 51 criterios):** qwen3:8b es el más literal (0,98 de citas) y el más parecido al anotador en granularidad (1,12 criterios por criterio de referencia); gemma3:12b sobre-divide (1,92) y tarda el doble; medgemma:4b es el más débil. En `evaluable` ningún modelo supera el 0,54 y la línea base de "todo no evaluable" es 0,69: declarar no evaluable es la debilidad de todos.
- El modelo biomédico no aportó ventaja: el conocimiento clínico lo aporta la recuperación.
Decisión: qwen3:8b (5,2 GB, deja VRAM al embedder). Confirmación sobre el conjunto de prueba: pendiente (una sola corrida).

### 7.2 Motor de ejecución: **Ollama** (ADR-0004, Propuesto)
Se midieron Ollama 0.40.4 y llama.cpp b11624 en la RTX 5070: 110 y 107 tokens/s, 10 de 10 salidas con esquema JSON válidas en ambos, y misma salida con semilla fija. Se elige Ollama (descarga y carga de modelos por API, versiones fijadas por SHA-256) y llama.cpp queda como respaldo. vLLM y SGLang no se probaron: la carga es secuencial (unas 120 llamadas por pasada) y se reevaluarán si una corrida pasa de 30 minutos o hacen falta peticiones concurrentes. Un cliente compatible con OpenAI aísla las diferencias entre motores.

### 7.3 Ground truth (ADR-0003, Propuesto; ejecutado)
40 preguntas anotadas por el autor leyendo los textos, **sin ningún LLM** (el modelo solo se evalúa contra él): 20 R (recuperación y respuesta), 12 E (extracción de criterios atómicos con valores literales, `evaluable` y cita exacta) y 8 C (cohorte: SQL de referencia y recuento esperado, con el identificador del conjunto de datos). Guía de anotación v1.0, esquema validado con pydantic (`make gt-validate-final`), citas literales verificadas, partición por documento (6/14 en R, 4/8 en E, 2/6 en C para desarrollo y prueba) y grupos de documentos casi idénticos en la misma partición. Los criterios `evaluable` se revisaron contra la tabla de la guía (45 pasaron a no evaluables). Una sola persona anota; se declara y se mide la consistencia propia con una re-anotación a ciegas (pendiente).

### 7.4 Evaluación (ADR-0002, Propuesto; ADR-0006 y ADR-0007 para la recuperación)

| Capa | Qué mide | Cómo se implementa | Estado |
|---|---|---|---|
| 1 Recuperación | ¿Se recuperan las citas relevantes? | recall@k (`make eval-retrieval`) | Medido en desarrollo (abajo) |
| 2 Extracción | Criterios atómicos frente al anotador | cobertura de citas, citas literales, operador, valor, `evaluable` (`make eval-extraction`) | Medido en desarrollo |
| 3-4 SQL y cohorte | Recuentos exactos por ensayo | vistas SQL frente al recuento esperado (pytest, marca `db`) | Las 8 cohortes coinciden |
| 5 Fidelidad | La respuesta se apoya en los fragmentos | verificación literal de citas; juicio del anotador | Parcial; sin juez LLM |

Recuperación (recall@10, 6 R de desarrollo, estrategia por criterio): all-MiniLM-L6-v2 0,33; con búsqueda híbrida 0,50; **bge-m3 0,67; bge-m3 con reformulación de la pregunta 0,83** (ADR-0007). El conjunto de prueba está congelado: se evalúa **una sola vez** al final y no se usa para iterar. Las pruebas de software (pytest) usan modelos falsos y corren en el CI; las evaluaciones con modelo corren en local con GPU.

## 8. Estado y pendientes
- Hecho: corpus, índice, ground truth completo, cohortes, asistente con enrutado, comparación de LLM y embeddings en desarrollo.
- Pendiente: corrida única sobre el conjunto de prueba; re-anotación a ciegas; recálculo independiente con pandas de las otras siete cohortes; mejorar la declaración de no evaluable en la extracción; interfaz de demostración.
