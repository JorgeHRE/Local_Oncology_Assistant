# Limitaciones

Documento vivo: se completa conforme avanza el proyecto. Cada limitación dice qué afecta y qué no.

## Datos sintéticos del módulo gástrico

Los datos salen de `synthea/modules/gastric_cancer.json` (ver `docs/alcance-clinico-modulo-gastrico.md`).
**No son un modelo epidemiológico**: las probabilidades se eligieron para que haya pacientes en cada
rama de la tabla de atrición, no para reproducir la prevalencia real.

| Limitación | Qué afecta | Qué no afecta |
|---|---|---|
| **CLDN18.2 se aproxima con LOINC 105011-1 (*Claudin 18 Ag [Interpretation] in Tissue by Immune stain, Narrative*).** Ese código designa Claudina 18 en general, no la isoforma 18.2, y no define el umbral (≥ 75 % de células tumorales con tinción moderada o intensa) que usan SPOTLIGHT y GLOW. Aceptado por el profesor el 2026-10-14. | La elegibilidad para zolbetuximab: "CLDN18.2 positivo" en la base significa *resultado positivo del código 105011-1*, no verificado contra el umbral del ensayo. | La estructura de la consulta SQL: si se cambia a un código específico, solo cambia el concept set. |
| Probabilidades de biomarcadores: HER2+ 20 % y CLDN18.2+ 33 % respaldados por el corpus; CPS ≥ 5 60 %, MSI-H 5 % y ECOG ≥ 2 15 % **sin respaldo suficiente** (ver `docs/umbrales-vs-corpus.md`); estadios, recaída, muerte y proporciones de tratamiento son supuestos de modelado. | El número de pacientes en cada paso de la atrición. | La lógica de los criterios. |
| Los biomarcadores se sortean **de forma independiente**; en la realidad hay correlaciones (p. ej. MSI-H con CPS alto). | Casos combinados poco realistas. | |
| **Edad y sexo no se pueden reponderar** (Synthea fija la demografía antes de simular): edad al diagnóstico ~uniforme (mediana ~54, no ~65) y ~50 % mujeres (real ~33 %). | Estadísticas descriptivas de la cohorte. | La elegibilidad: los biomarcadores no dependen de edad ni sexo, por decisión. |
| Los otros módulos de Synthea (colorrectal, mama, pulmón) añaden quimioterapia sistémica a algunos pacientes gástricos (p. ej. un FOLFOX previo). Las consultas deben contar fármacos **por ingrediente**, no por los 8 códigos del módulo. | Criterio de tratamiento previo. | |
| Estadio **solo agrupado I–IV**; sin TNM ni subestadios (no se usa Cancer Modifier). | Criterios que pidan T/N/M o subestadio. | Estadio IV vs. no IV. |
| La unión gastroesofágica entra **solo como neoplasia maligna del cardias** (20 % de los diagnósticos). | Representatividad de tumores de la UGE. | |
| La exposición previa a FLOT o a platino adyuvante es **un solo evento simple**, sin cirugía, ciclos ni respuesta. | Criterios sobre tiempo desde la última dosis o sobre respuesta. | "Sin tratamiento sistémico previo para enfermedad avanzada" (se evalúa por fechas). |
| Solo **primera línea**; sin segunda línea, radioterapia, toxicidades ni ajustes de dosis. Sin sitio de metástasis (solo estadio IV). Sin histología de Lauren. | Preguntas sobre líneas posteriores. | |
| **Muertes que el ETL descarta (3 de 710).** La tabla `death` de ETL-Synthea sale de los encuentros de certificación y exige causa SNOMED estándar: 2 muertes por sobredosis (módulo de opioides de Synthea, `55680006`) y 1 sin certificado quedan fuera. | `cdm.death` tiene 707 filas y no 710; `patients.deathdate` de `native` sí las conserva. | Las 675 muertes por cáncer gástrico. |
| Sin progresión registrada: tras la primera línea solo se modela la muerte (70 %). | Supervivencia libre de progresión. | |

## Corpus del RAG

| Limitación | Qué afecta | Qué no afecta |
|---|---|---|
| **88 documentos:** 49 fichas de ClinicalTrials.gov **recortadas** (título, estado, condición y criterios de elegibilidad) y 39 resúmenes de PubMed (solo el abstract, no el texto completo; no se versionan). **No hay guías NCCN/ESMO** (0 documentos; requieren descarga manual). | Preguntas que necesiten una guía, un resultado de un artículo o una cifra que solo está en el texto completo (por ejemplo, el CPS ≥ 5 de CheckMate 649: `docs/umbrales-vs-corpus.md`). | Preguntas sobre los criterios de elegibilidad de los ensayos incluidos. |
| El corpus es pequeño y está en **inglés**; incluye 10 ensayos distractores (otros tumores). | La cobertura: una pregunta sobre un ensayo que no está devuelve "no contiene la respuesta" o, peor, el criterio de otro ensayo parecido. | La verificación de citas. |
| Las fichas son una **instantánea** (fecha y SHA-256 en `corpus/manifest.json`); los ensayos cambian. | Que lo recuperado coincida con la web de hoy. | La reproducibilidad: manda la copia congelada. |

## Recuperación y respuesta (RAG)

| Limitación | Qué afecta | Qué no afecta |
|---|---|---|
| **Recuperación imperfecta.** Con la configuración desplegada, recall@5 = 0,83 en las 14 R de `test` (R-007, R-009 y R-011 no se recuperaron completas). Las preguntas muy generales o sin ensayo nombrado (del tipo "qué biomarcador excluye…" en un ensayo de decenas de criterios) fallan más. | Que la respuesta tenga la evidencia delante. | Los ensayos nombrados en la pregunta: se busca solo en ellos. |
| **El modelo se niega a veces teniendo la evidencia** (1 de 12 respuestas posibles en `test`) y **no sabe declarar una ausencia**: en una comparación de dos ensayos donde uno no menciona el tema, responde "no contiene la respuesta" en lugar de decir cuál lo menciona. | Preguntas comparativas y de ausencia. | Las preguntas de un solo dato con el ensayo nombrado. |
| **La verificación de citas es literal, no semántica.** Comprueba que la cita esté en el fragmento (ignorando espacios); no comprueba que ese texto respalde lo que el modelo afirma. En `test`, 11 de 12 respuestas tenían todas sus citas literales (sin reintento). La fidelidad semántica (capa 5 del ADR-0002, con Ragas o un juez LLM) **no se implementó**. | La confianza en que una respuesta con cita "ok" es correcta. | Detectar citas inventadas o modificadas. |
| **La corrección de las respuestas la juzga solo el anotador**, sobre una muestra pequeña; no hay métrica automática de corrección. | Cuánto se puede afirmar de la calidad de las respuestas. | |
| El LLM es **qwen3:8b cuantizado** (4 bits, ~8 mil millones de parámetros): menos capaz que un modelo grande en comparaciones y razonamiento. Temperatura 0 y semilla fija: reproducible en esta máquina, **no probado en otro hardware**. | Respuestas complejas. | La literalidad de las citas. |
| **Idioma:** el corpus y las preguntas del ground truth están en inglés. bge-m3 es multilingüe y una pregunta en español recupera y se responde, pero **no se evaluó** en español. | Resultados en español. | |
| **La reformulación de la pregunta** la hace el mismo LLM (≈ 1 s más) y puede añadir terminología que no pidió el usuario; se busca con la pregunta original y la reescrita. | Latencia y, a veces, el ranking. | |
| La estrategia de chunking C (documento entero) conserva escapes de Markdown (`\<`, `\>`) en el texto; el recall de C (1,00) es **trivial** porque cada fragmento es el documento. | La lectura de C como estrategia candidata. | La estrategia B (un fragmento por criterio), que es la usada. |

## Extracción de criterios y cohortes

| Limitación | Qué afecta | Qué no afecta |
|---|---|---|
| **El LLM no declara bien lo no evaluable.** En `test`, el acuerdo en `evaluable` es 0,51 (la línea base "todo no evaluable" es 0,53) y en operador 0,47; en `dev` pasó igual con los tres modelos comparados. El prompt es el mismo para todos y no incluye ejemplos negativos. | Que un sistema sin revisión humana proponga qué criterios se pueden ejecutar sobre OMOP. | La cobertura de las citas (1,00) y la literalidad (0,97). |
| La evaluación de la extracción **usa la sección completa del ensayo** como entrada (todos sus fragmentos de la sección) y no mide el flujo extremo a extremo. | La conclusión sobre el pipeline completo. | La comparación entre modelos. |
| **No hay traducción automática de criterios a SQL** (NL2SQL): las 8 cohortes son SQL escrito a mano, una por ensayo (`sql/cohort_*.sql`). El asistente solo las lee. | Preguntas por pacientes de cualquier ensayo fuera de esos 8: el asistente lo dice y lista los disponibles. | Los conteos de las 8 cohortes: coinciden con el ground truth. |
| Las cohortes aplican **solo los criterios que los datos OMOP pueden comprobar** (diagnóstico, estadio, HER2, CLDN18, PD-L1 CPS, MSI, ECOG, edad, sexo, fármacos y fechas). Lo demás (analíticas, comorbilidades, lesión medible, embarazo…) no entra en el recuento. | Que "n pacientes cumplen" equivalga a "n pacientes serían elegibles": es un límite superior. | La coherencia con el ground truth. |
| **La portabilidad a otra población OMOP es una propiedad de diseño, no está probada.** Las cohortes son SQL sobre el esquema OMOP CDM v5.4, así que en principio se pueden ejecutar sobre otra base con el mismo modelo, pero solo se han ejecutado contra la población sintética de Synthea. Los *concept sets* (`sql/01_concept_sets.sql`) se eligieron para los códigos que genera el módulo gástrico (p. ej. CLDN18.2 ≈ LOINC 105011-1, HER2 LOINC 18474-7, estadio LOINC 42100-8 con valores Stage 1–4); en datos reales esos biomarcadores pueden estar codificados de otra forma, en texto libre o no estar. Además, el esquema `results` y las vistas `gc_*_cohort` están acoplados a esta base. | Que repetir un estudio con otra cohorte dé resultados comparables o utilizables sin adaptar los concept sets y revisarlos con un clínico. | La lógica de los criterios y la tabla de atrición, que son independientes de la población. Un uso con datos reales además exigiría aprobación ética y de gobernanza de datos (`docs/POLITICA_DE_USO.md`). |
| **El enrutado entre cohorte y texto es por palabras clave en inglés** ("which patients", "how many patients", "cohort"…). Una pregunta equivalente **en español** ("¿cuántos pacientes cumplen…?") se envía al RAG de textos y no a la cohorte. Los patrones se ajustaron viendo las preguntas del ground truth, incluidas las de `test`. **Tampoco tolera faltas de ortografía:** en una prueba exploratoria del autor (2026-11-19), "Hom many patients are eligible for NCT06346197?" se envió al RAG de textos en lugar de a la cohorte; con "How" se enrutó bien. Lo mismo pasa con "patiens". La interfaz muestra la ruta usada (etiqueta de color), lo que permite detectarlo. | Preguntas por pacientes en español, formuladas de otra manera o con errores de escritura. | Las 40 preguntas del ground truth (se enrutan bien); la pregunta con "Hom" del autor (falla). |
| **Recálculo independiente con pandas** (ADR-0003): solo existe para la cohorte de zolbetuximab (y se escribió con Claude Code); no está en el repositorio para las otras siete. C-007 usa un SQL con base de Claude Code, revisado a mano por el autor. | La independencia de la verificación de las cohortes. | |

## Ground truth y evaluación

| Limitación | Qué afecta | Qué no afecta |
|---|---|---|
| **Un solo anotador.** La fiabilidad medida es la propia, y la **re-anotación a ciegas** (10 preguntas, ≥ una semana después) está pendiente: no hay κ de Cohen. | La confianza en la referencia. | |
| **Muestras pequeñas:** 6 R y 4 E de desarrollo (las E, de solo 2 ensayos) y 14 R y 8 E de prueba, sin intervalos de confianza. Una pregunta mueve el recall 0,07. | Las diferencias finas (por ejemplo, 0,87 de solo vector frente a 0,83 de híbrida en `test` no se interpretan). | Descartar un modelo claramente peor. |
| **La referencia de `evaluable` se corrigió** tras ver el primer resultado (45 criterios de las E pasaron a no evaluables). La medición se repitió con la referencia corregida y el cambio está en el CHANGELOG del ground truth. | La primera medición de `evaluable`, descartada. | Las demás columnas, que no dependen de ese campo. |
| **El modelo se eligió con `dev`** (6 R y 4 E); `test` se usó **una sola vez**, solo con qwen3:8b. gemma3:12b y medgemma:4b no se corrieron en `test`. | Que qwen3:8b sea el mejor en `test`: no se midió. | La elección razonada por literalidad, tamaño y licencia (ADR-0005). |
| **Gemini** (otro LLM) tuvo acceso al repositorio y mostró los datos del ground truth, sin escribir ni proponer contenido; es de la misma familia que gemma3 y medgemma, dos de los modelos comparados (`docs/USO_DE_IA.md`). | La pureza de la comparación, en grado mínimo. | |

## Reproducibilidad y operación

| Limitación | Qué afecta | Qué no afecta |
|---|---|---|
| **El LLM corre en local con GPU** (RTX 5070, 12 GB), con Ollama instalado fuera de Docker, y los modelos se descargan a mano (`ollama pull`). El CI **no** ejecuta modelos: solo las pruebas con modelos falsos y `ruff`. | Que un tercero reproduzca las evaluaciones sin GPU ni descargas. | Las pruebas de software y la validación del ground truth. |
| Los resultados de `dev` (archivos de revisión de respuestas y de extracción) están en `data/processed/`, **no versionados**; solo la corrida de `test` está registrada en `eval/results/`. | Auditar las mediciones de desarrollo. | Las cifras que cita el ADR. |
| Los vocabularios de Athena (SNOMED, LOINC, RxNorm) **no se redistribuyen** y hay que descargarlos con la cuenta de cada usuario; sus términos no se revisaron aquí. | Reproducir la base OMOP desde cero. | El resto del código. |
