# CLAUDE.md — Local Oncology Assistant

Este archivo le da contexto a Claude Code sobre el proyecto. Vive en la raíz del repo.
Actualízalo conforme el proyecto avanza — es la memoria persistente del proyecto, no un documento que se escribe una vez y se olvida.

---

## 0. Cómo debe comportarse Claude Code en este proyecto (leer primero)

Este proyecto es parte de mi transición de la academia a la industria (ciencia de datos, con mira
en farmacéutica/biotech). No busco solo que el código funcione — busco aprender a trabajar como
se trabaja en la industria. Por lo tanto:

1. **Explica el "por qué", no solo el "qué".** Antes de implementar algo no trivial, explica
   brevemente las alternativas que consideraste y por qué elegiste una. Si es una decisión de
   arquitectura relevante, sugiere registrarla como ADR (ver sección 6) en vez de solo codificarla.
2. **Conecta las prácticas con la industria real.** Cuando apliques algo (tests, logging,
   versionado de datos, ADRs, model cards, etc.), menciona en una línea por qué esto importa en un
   entorno regulado/farmacéutico o en una entrevista técnica — no como cátedra larga, como nota
   al margen.
3. **No tomes decisiones de arquitectura grandes en silencio.** Si algo requiere elegir entre
   enfoques con trade-offs reales (modelo LLM, motor de inferencia, estrategia de chunking,
   metodología de ground truth), pregúntame o preséntame opciones antes de implementar, no
   asumas y avances.
4. **Prioriza siempre la sección 7 (datos y privacidad) sobre la velocidad.** Ninguna excepción.
5. **Sigue la disciplina de ingeniería de la sección 8** (tests, commits, documentación) incluso
   si eso hace las cosas "más lentas" al principio — ese es precisamente el hábito que quiero
   construir.
6. **Actualiza la sección 11 (estado actual)** cuando completemos un hito, para que este archivo
   siga siendo la fuente de verdad del progreso real.
7. Todo el proyecto y sus respuestas van en **español**; el código, nombres de variables,
   commits y SQL en **inglés** (convención estándar en la industria).

---

## 1. Contexto del proyecto

- **Nombre:** `Local_Oncology_Assistant`
- **Repositorio:** público en GitHub — https://github.com/JorgeHRE/Local_Oncology_Assistant
- **Curso:** Proyecto final de ciencia de datos (migración academia → industria)
- **Modalidad elegida:** D — Aplicación de IA generativa en biomedicina (NL2SQL + RAG sobre
  protocolos), integrada obligatoriamente con SQL sobre OMOP CDM.
- **Propósito:** Asistente de tamizaje de elegibilidad clínica (*clinical trial feasibility /
  protocol screening*) para **cáncer gástrico**. Toma protocolos de ensayos clínicos y guías
  terapéuticas (texto no estructurado), extrae semánticamente criterios de inclusión/exclusión,
  y los traduce a consultas SQL ejecutables sobre una base de pacientes sintéticos en formato
  OMOP CDM.
- **Por qué importa el enfoque "local":** en la industria farmacéutica/salud, los datos de
  pacientes (incluso sintéticos, por hábito y por política) casi nunca pueden salir a APIs de
  terceros. Ejecutar el LLM localmente no es un capricho técnico — es exactamente la restricción
  de gobernanza de datos que existirías en un entorno real. Diséñalo pensando en eso.

---

## 2. Arquitectura objetivo

### 2.1 Motor RAG (datos no estructurados)
- **Corpus:** protocolos de ClinicalTrials.gov + guías NCCN/ESMO para cáncer gástrico (texto/JSON).
- **Base vectorial:** ChromaDB local, con metadatos indexados (biomarcadores, fase del ensayo,
  dianas terapéuticas como HER2, Claudina 18.2).
- **Inferencia LLM:** modelo abierto ejecutado localmente sobre GPU (ver sección 3 — hardware).
  **Decisión pendiente de ADR:** qué modelo y qué motor de inferencia (ver sección 6).

### 2.2 Capa de datos clínicos (datos estructurados)
- **Fuente:** población sintética generada con **Synthea**, mapeada a **OMOP CDM v5.4** vía
  **ETL-Synthea**. **Eunomia** (OMOP en SQLite) para prototipar consultas rápido antes de correr
  contra la base completa.
- **Lógica SQL:** scripts versionados en `sql/` (`01_concept_sets.sql`, `02_cohorte.sql`,
  `03_features.sql`), aplicando los filtros clínicos recuperados por el RAG y generando la tabla
  de atrición (cuántos pacientes se pierden en cada filtro y por qué — estándar en estudios de
  cohorte, y algo que se pregunta mucho en entrevistas de epidemiología/RWE).

### 2.3 Evaluación y calidad
- **Ground truth:** set de validación propio (30-50 preguntas clínicas complejas con respuesta de
  referencia). Ver metodología detallada en sección 6 (pendiente de ADR) — esto necesita **dos
  niveles** de ground truth, no uno: (a) criterios correctos extraídos por protocolo, (b) el
  conjunto exacto de `patient_id` que cumple esos criterios en la base OMOP.
- **Métricas:** evaluación por capas — retrieval (recall@k), extracción de criterios (contra
  ground truth a), corrección de SQL (ejecuta sin error), corrección de cohorte (precision/recall
  de `patient_id` contra ground truth b — esto es determinístico, no requiere LLM-as-judge), y
  fidelidad del RAG (`faithfulness`, `context_precision` vía Ragas/DeepEval — aquí sí aplica
  LLM-as-judge).
- **Reproducibilidad:** pytest + CI en GitHub Actions, contenedorización con
  `Dockerfile`/`compose.yml`.

---

## 3. Stack técnico y hardware

- **Hardware:** Intel Core i5-14400F · NVIDIA RTX 5070 (**12 GB VRAM**, arquitectura Blackwell) ·
  48 GB RAM DDR5 · 3 TB NVMe · Pop!_OS.
  - Restricción real a respetar: con 12 GB VRAM, el presupuesto cómodo para el LLM local es de
    modelos ~7-14B cuantizados (4-bit). No asumas que hay VRAM ilimitada al elegir modelo o
    tamaño de batch/contexto.
- **Lenguaje:** Python ≥ 3.10.
- **Entorno:** paquete modular con `pyproject.toml`, instalado en modo editable (`pip install -e .`).
- **Librerías clave ya declaradas:** `chromadb`, `pandas`, `pydantic`.
- **Pendientes de agregar conforme se necesiten:** `pytest`, `ragas` o `deepeval`, `sqlalchemy` o
  driver de Postgres, `ruff`/`black` (linting/formato), motor de inferencia elegido (ver sección 6).
- **Prototipado permitido, ejecución no:** Google AI Studio se usa solo como copiloto de código
  para generar scripts/depurar — la ejecución y entrega final del proyecto es 100% local y
  reproducible. Documentar esto también responde al requisito de "declaración de uso de IA"
  (ver sección 5).

---

## 4. Estructura del repositorio

```
Local_Oncology_Assistant/
├── CLAUDE.md              # ✅ contexto del proyecto para Claude Code (versionado)
├── README.md              # ⚠️ solo tiene el título — pendiente, ver sección 5
├── Dockerfile / compose.yml   # ⚠️ no existe aún
├── pyproject.toml         # ✅ existe
├── .gitignore              # ✅ existe
├── .github/workflows/ci.yml  # ⚠️ no existe aún
├── sql/
│   ├── 01_concept_sets.sql   # ⚠️ no existe aún
│   ├── 02_cohorte.sql        # ⚠️ no existe aún
│   └── 03_features.sql       # ⚠️ no existe aún
├── src/oncology_assistant/  # ⚠️ solo __init__.py, falta código real
├── tests/                  # ⚠️ no existe aún
├── synthea/                 # ✅ configuración de Synthea (keep modules; módulo gástrico pendiente)
├── notebooks/               # exploración únicamente, nunca lógica de producción
├── docs/
│   ├── protocolo.md         # ✅ existe (subido para hito de Sesión 10)
│   ├── features.md           # ⚠️ diccionario de datos — no existe aún
│   ├── MODEL_CARD.md         # ⚠️ no existe aún
│   ├── LIMITACIONES.md       # ⚠️ no existe aún
│   ├── USO_DE_IA.md           # ⚠️ no existe aún — declarar uso de Gemini y Claude
│   └── adr/                  # ✅ existe — 0001 en borrador; ver sección 6
└── figuras/                 # ⚠️ no existe aún
```

Cuando crees un archivo o carpeta de esta lista, actualiza este árbol quitando la ⚠️.

---

## 5. Checklist de requisitos mínimos del curso (todas las modalidades)

- [ ] Historial de commits real (no un commit gigante al final) — **actualmente en riesgo: solo 2
      commits hasta ahora.** Insiste en commits pequeños y frecuentes desde ya.
- [ ] `README.md` que permita a un tercero reproducir el trabajo
- [ ] Entorno containerizado (`Dockerfile` o `compose.yml`)
- [ ] Al menos una definición de cohorte en SQL sobre OMOP, documentada
- [ ] Pruebas automáticas con pytest y CI en GitHub Actions
- [ ] Diccionario de datos / documentación de variables (`docs/features.md`)
- [ ] Sección de limitaciones escrita honestamente (`docs/LIMITACIONES.md`)
- [ ] Declaración de uso de asistentes de IA (`docs/USO_DE_IA.md`) — mencionar Gemini (fase de
      planeación) y Claude/Claude Code (implementación)
- [ ] Cero credenciales y cero datos identificables en el repositorio

**Extra de Modalidad D:**
- [ ] Evaluación cuantitativa con set etiquetado propio (ver sección 2.3 y 6)
- [ ] Política de uso — para qué sí y para qué no debe usarse este asistente clínicamente, límites
      de responsabilidad (`docs/POLITICA_DE_USO.md`)

---

## 6. Decisiones técnicas pendientes (usar Architecture Decision Records)

En la industria, las decisiones de arquitectura con trade-offs reales se documentan como **ADRs**
(Architecture Decision Records): un archivo corto por decisión, con contexto, opciones
consideradas, decisión tomada y consecuencias. Esto es exactamente lo que mi profesor pidió como
feedback (justificar LLM, motor de ejecución, metodología de ground truth, estrategia de
evaluación) — así que vamos a resolver ese feedback *mediante* esta práctica.

Cuando trabajemos cualquiera de estas decisiones, crea un archivo en `docs/adr/NNNN-titulo.md`
(formato corto: contexto → opciones → decisión → consecuencias) antes de implementar:

1. **ADR pendiente:** qué LLM usar para extracción/NL2SQL (candidatos a evaluar: modelo
   generalista instruction-tuned reciente vs. modelo biomédico especializado — pesar la
   capacidad de seguir formato estructurado vs. conocimiento clínico interno, dado que el RAG ya
   aporta el conocimiento de dominio).
2. **ADR pendiente:** motor de inferencia local (Ollama vs. vLLM vs. SGLang). Nota: SGLang tiene
   un argumento técnico específico para este proyecto por su soporte de generación estructurada
   repetida (RadixAttention) — vale la pena evaluarlo en serio, no solo usar Ollama por default.
3. **ADR pendiente:** metodología de construcción del ground truth (dos niveles: extracción de
   criterios y cohorte esperada; protocolo de anotación explícito; cómo se documenta que solo hay
   un anotador; separación dev/test).
4. **ADR pendiente:** estrategia de evaluación por capas (retrieval, extracción, SQL, cohorte,
   fidelidad RAG) y cómo se automatiza cada capa como test en CI.

No avances la implementación de estas piezas sin haber cerrado el ADR correspondiente conmigo.

---

## 7. Reglas de datos y privacidad (no negociables)

- **Ningún dato identificable de paciente entra al repositorio. Nunca.**
- Solo datos sintéticos (Synthea/Eunomia) — cero excepciones sin discutirlo explícitamente conmigo.
- Cero credenciales, API keys o tokens en el repo, ni siquiera en el historial de commits (revisa
  antes de hacer commit; si algo se filtra, hay que reescribir historial, no solo borrar el archivo).
- Toda fuente de datos debe declarar: **fuente, versión, fecha de descarga** — sin eso el trabajo
  no es reproducible y no cumple el requisito del curso.
- Antes de cualquier commit, revisa que no se esté subiendo nada de `data/` real (usa `.gitignore`
  agresivo para esa carpeta).

---

## 8. Buenas prácticas de ingeniería esperadas en este proyecto

- **Commits pequeños y semánticos.** Prefiere convención tipo `feat:`, `fix:`, `docs:`, `test:`,
  `chore:` — es común en equipos de industria y facilita el historial que pide el curso.
- **Tests antes o junto con el código**, no después. Cada script de `sql/` o módulo de
  `src/oncology_assistant/` debería tener su prueba correspondiente en `tests/`.
- **Type hints y docstrings** en todo código Python — no opcional.
- **Logging, nunca `print()`**, para cualquier código que no sea un notebook exploratorio.
- **Reproducibilidad:** dependencias fijadas (versión exacta o rango acotado en `pyproject.toml`),
  semillas fijas donde haya aleatoriedad.
- **Documentación como parte del trabajo, no al final** — si agregas una variable/feature nueva,
  actualiza `docs/features.md` en el mismo PR/commit, no "después".
- **CI en cada push**, no solo al final del proyecto — así detectamos regressions temprano, que es
  el punto de tener CI.

---

## 9. Cómo debe enseñar Claude Code (modo mentor)

Cada vez que hagamos algo con relevancia más allá de este proyecto específico (una decisión de
diseño, un patrón de testing, una práctica de gobernanza de datos, un concepto de MLOps), agrega
una nota breve tipo:

> 💡 **Por qué esto importa en la industria:** ...

Ejemplos del tipo de conexión que busco (no las repitas literalmente, adáptalas al contexto real
de lo que estemos haciendo):
- Por qué las farmacéuticas versionan datos, modelos *y* prompts, no solo código.
- Por qué un Model Card no es burocracia sino trazabilidad exigible en auditorías.
- Por qué "funciona en mi máquina" no es suficiente cuando hay de por medio decisiones que afectan
  la elegibilidad de un paciente a un ensayo clínico (explicabilidad y trazabilidad de por qué el
  sistema incluyó/excluyó a alguien).
- Por qué separar ambiente de desarrollo/prueba es una práctica que se pregunta en entrevistas de
  MLE/DS en salud.

No conviertas cada respuesta en una clase — una o dos líneas de contexto son suficientes. Si quiero
profundizar en algo, yo pregunto.

---

## 10. Comandos clave

*(completar conforme se implementen; mantener esta sección actualizada)*

```bash
# Instalación
pip install -e .

# Tests
pytest

# Levantar entorno (pendiente Dockerfile/compose.yml)
docker compose up -d

# Correr suite de evaluación (pendiente de implementar)
# python -m oncology_assistant.eval --ground-truth docs/ground_truth_v1.json
```

---

## 11. Estado actual del proyecto

*(actualizar después de cada sesión de trabajo)*

- **Última actualización:** 2026-09-28 — `CLAUDE.md` movido a la raíz del repo y versionado.
- **Hito actual del curso:** Sesión 10 completada (protocolo subido) → trabajando hacia Sesión 18
  (cohorte definida, implementada, con tabla de atrición).
- **Completado:** estructura básica de carpetas, config inicial (`pyproject.toml`, `.gitignore`),
  `docs/protocolo.md` inicial.
- **Entorno:** Docker 29.8.1 + Compose v5.5.1 instalados (2026-09-28, repo oficial de Docker).
- **En progreso:** ADRs de la sección 6 (LLM, motor de inferencia, ground truth, evaluación).
- **Bloqueadores / riesgo principal:** Synthea no trae (hasta donde sabemos) un módulo de cáncer
  gástrico ni biomarcadores (HER2, CLDN18.2, MSI-H) → sin resolver esto, la cohorte de la
  Sesión 18 podría quedar vacía. Requiere ADR-0001 de estrategia de datos sintéticos.
- **Decisiones pendientes para la próxima sesión (en orden):**
  1. ADR-0001 (`docs/adr/0001-...md`, borrador): se propone (a) módulo GMF propio; falta la Fase 2
     del spike (vocab Athena + ETL-Synthea). Antes: (a) módulo GMF propio de Synthea vs.
     (b) Synthea estándar + inyección de pacientes vía script con semilla fija.
  2. ~~Renombrar el paquete `miproyecto`~~ → ✅ renombrado a `oncology_assistant` (2026-09-28).
  3. Esqueleto de CI desde ya (ruff + test de humo + GitHub Actions).
  4. Acotar versiones de dependencias en `pyproject.toml`.
  5. ADRs del profesor (LLM, motor, ground truth, evaluación).
  6. Menor: el repo está anidado en una carpeta padre vacía — ¿aplanar?

---

## 12. Calendario del curso

| Sesión | Hito |
|---|---|
| 10 | Propuesta de 1 página (✅ hecho) |
| 18 | Cohorte definida, implementada y con tabla de atrición ← **estamos aquí** |
| 24 | Avance intermedio: revisión de 15 min con el profesor |
| 30 | Entrega del repositorio final |
| 31 | Presentación de 12 min + 5 de preguntas |

---

## 13. Feedback pendiente de atender (del profesor, recibido tras Sesión 10)

> "Profundiza más en el protocolo: qué LLM vas a usar, cómo lo vas a ejecutar (SGLang, vLLM,
> Ollama, etc.), y especialmente cómo vas a construir el ground truth para comparar los modelos.
> Además, qué estrategia vas a utilizar para evaluar a los modelos y cómo la vas a implementar."

Este feedback se resuelve directamente completando los ADRs de la sección 6. No se considera
atendido hasta que `docs/protocolo.md` incluya esas cuatro decisiones justificadas.
