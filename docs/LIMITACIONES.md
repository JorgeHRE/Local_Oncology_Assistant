# Limitaciones

Documento vivo: se completa conforme avanza el proyecto. Cada limitación dice qué afecta y qué no.

## Datos sintéticos del módulo gástrico

Los datos salen de `synthea/modules/gastric_cancer.json` (ver `docs/alcance-clinico-modulo-gastrico.md`).
**No son un modelo epidemiológico**: las probabilidades se eligieron para que haya pacientes en cada
rama de la tabla de atrición, no para reproducir la prevalencia real.

| Limitación | Qué afecta | Qué no afecta |
|---|---|---|
| **CLDN18.2 se aproxima con LOINC 105011-1 (*Claudin 18 Ag [Interpretation] in Tissue by Immune stain, Narrative*).** Ese código designa Claudina 18 en general, no la isoforma 18.2, y no define el umbral (≥ 75 % de células tumorales con tinción moderada o intensa) que usan SPOTLIGHT y GLOW. Aceptado por el profesor el 2026-10-14. | La elegibilidad para zolbetuximab: "CLDN18.2 positivo" en la base significa *resultado positivo del código 105011-1*, no verificado contra el umbral del ensayo. | La estructura de la consulta SQL: si se cambia a un código específico, solo cambia el concept set. |
| Probabilidades de biomarcadores (HER2+ 20 %, CLDN18.2+ 38 %, CPS ≥ 5 60 %, MSI-H 5 %, ECOG ≥ 2 15 %) escritas de memoria, **pendientes de verificar con el corpus**. | El número de pacientes en cada paso de la atrición. | La lógica de los criterios. |
| Los biomarcadores se sortean **de forma independiente**; en la realidad hay correlaciones (p. ej. MSI-H con CPS alto). | Casos combinados poco realistas. | |
| **Edad y sexo no se pueden reponderar** (Synthea fija la demografía antes de simular): edad al diagnóstico ~uniforme (mediana ~54, no ~65) y ~50 % mujeres (real ~33 %). | Estadísticas descriptivas de la cohorte. | La elegibilidad: los biomarcadores no dependen de edad ni sexo, por decisión. |
| Estadio **solo agrupado I–IV**; sin TNM ni subestadios (no se usa Cancer Modifier). | Criterios que pidan T/N/M o subestadio. | Estadio IV vs. no IV. |
| La unión gastroesofágica entra **solo como neoplasia maligna del cardias** (20 % de los diagnósticos). | Representatividad de tumores de la UGE. | |
| La exposición previa a FLOT o a platino adyuvante es **un solo evento simple**, sin cirugía, ciclos ni respuesta. | Criterios sobre tiempo desde la última dosis o sobre respuesta. | "Sin tratamiento sistémico previo para enfermedad avanzada" (se evalúa por fechas). |
| Solo **primera línea**; sin segunda línea, radioterapia, toxicidades ni ajustes de dosis. Sin sitio de metástasis (solo estadio IV). Sin histología de Lauren. | Preguntas sobre líneas posteriores. | |
| **Muertes que el ETL descarta (4 de 690).** La tabla `death` de ETL-Synthea sale de los encuentros de certificación y exige causa SNOMED estándar: 3 muertes por sobredosis (módulo de opioides de Synthea, `55680006`) y 1 sin certificado quedan fuera. | `cdm.death` tiene 686 filas y no 690; `patients.deathdate` de `native` sí las conserva. | Las 657 muertes por cáncer gástrico. |
| Sin progresión registrada: tras la primera línea solo se modela la muerte (70 %). | Supervivencia libre de progresión. | |
