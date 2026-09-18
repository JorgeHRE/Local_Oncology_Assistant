# Protocolo de Investigación: Asistente RAG Local y Análisis de Cohorte OMOP en Cáncer Gástrico

## 1. Título del Proyecto
Evaluación de elegibilidad y caracterización de cohorte en adenocarcinoma gástrico mediante un sistema RAG biomédico local y consultas SQL sobre OMOP CDM.

## 2. Justificación y Antecedentes
La adopción de modelos de lenguaje grande (LLMs) en entornos clínicos y farmacéuticos se ve limitada por estrictas normativas de privacidad de datos y el riesgo de alucinaciones en información biomédica compleja. Este proyecto implementa una arquitectura 100% local y segura para asistir en la revisión de protocolos oncológicos y guías de práctica clínica, vinculando la evidencia no estructurada con datos observacionales estandarizados bajo el modelo OMOP CDM.

## 3. Pregunta de Investigación
¿Cómo optimizar de forma reproducible la identificación y validación de criterios de inclusión/exclusión para pacientes con adenocarcinoma gástrico avanzado mediante la integración de recuperación de literatura (*RAG*) y la ejecución de consultas estructuradas en una base de datos OMOP CDM?

## 4. Población Objetivo y Datos
* **Datos No Estructurados (RAG):** Corpus de guías clínicas (NCCN/ESMO) y abstracts/protocolos de ensayos clínicos sobre biomarcadores en cáncer gástrico (HER2, Claudina 18.2, MSI-H). Almacenados en una base vectorial local (ChromaDB).
* **Datos Estructurados (OMOP CDM):** Población sintética oncológica generada mediante Synthea y cargada en un esquema OMOP CDM v5.4 local mediante PostgreSQL en contenedor Docker.

## 5. Metodología y Entregables
1. **Módulo RAG Local:** Ingesta, *chunking* e indexación de literatura biomédica para consultas técnicas ejecutadas mediante un LLM abierto local con aceleración por GPU.
2. **Definición de Cohorte SQL:** Creación de scripts SQL (`01_concept_sets.sql` y `02_cohorte.sql`) para extraer la cohorte de pacientes con cáncer gástrico, incluyendo una tabla de atrición.
3. **Evaluación Cuantitativa:** Construcción de un set de validación propio (*Ground Truth*) con 30 preguntas clínicas para medir la fidelidad de recuperación con métricas automatizadas (`Ragas`) y pruebas unitarias con `pytest`.
4. **Reproducibilidad:** Entorno completamente containerizado mediante Docker Compose y controlado con GitHub Actions.

## 6. Limitaciones Previstas
* Dependencia de la calidad del etiquetado y realismo de los datos sintéticos de Synthea en comparación con historiales clínicos electrónicos reales de pacientes oncológicos.
* Acotación del corpus documental a guías y protocolos seleccionados debido a restricciones de procesamiento local.
