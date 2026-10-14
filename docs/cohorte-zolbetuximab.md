# Cohorte piloto: candidatos a zolbetuximab en primera línea

- **Estado:** implementada y verificada (2026-10-14). Hito de la Sesión 18 (cohorte + tabla de atrición).
- **Código:** `sql/01_concept_sets.sql`, `sql/02_cohorte.sql`; se construye con `make cohort` y se
  imprime con `make attrition`. Los objetos viven en el esquema `results`.
- **Criterios de origen:** SPOTLIGHT y GLOW (`docs/alcance-clinico-modulo-gastrico.md` §3). Los
  umbrales vienen de memoria y hay que confirmarlos con el corpus.

## Decisiones de diseño

| Decisión | Elegido | Por qué |
|---|---|---|
| Fecha índice | Primer registro de **estadio 4** de la persona (al diagnóstico, o en la recaída si empezó en I–III) | Es el momento en que pasa a enfermedad avanzada y se le evalúa para primera línea |
| Estado vital | **No se filtra** por "vivo hoy" | El 51 % de los pacientes ha fallecido; eran elegibles cuando se les evaluó |
| Ventana de mediciones | ±30 días alrededor del índice | En estos datos coinciden el mismo día; la ventana es la tolerancia habitual de un ensayo |
| Lavado de tratamiento previo | Sin quimioterapia sistémica en los 180 días **previos** al índice | FLOT o platino adyuvante previos son válidos si terminaron hace ≥ 6 meses. Las dosis del mismo día del índice son la primera línea y no cuentan |
| Fármacos | Por **ingrediente** (con descendientes vía `concept_ancestor`), no por producto | Otros módulos de Synthea añaden otros productos de los mismos fármacos |
| Alcance | Una cohorte piloto (zolbetuximab) | Trastuzumab y nivolumab se añaden después con el mismo tronco |
| Atrición | Vista SQL acumulativa, en el orden de los criterios | Sin esquema de resultados materializados que gestionar |

## Tabla de atrición (base con 1 340 pacientes)

| Paso | Criterio | Quedan | Se pierden |
|---|---|---|---|
| 0 | Personas en la base | 1 340 | – |
| 1 | Diagnóstico de cáncer gástrico | 1 340 | 0 |
| 2 | Enfermedad avanzada (estadio 4 registrado) | 949 | 391 |
| 3 | Adulto (≥ 18) al índice | 949 | 0 |
| 4 | ECOG 0–1 | 807 | 142 |
| 5 | Sin tratamiento sistémico en los 180 días previos | 806 | 1 |
| 6 | HER2 negativo | 657 | 149 |
| 7 | CLDN18 positivo | **243** | 414 |

Los 243 están dentro del rango que anticipó el profesor (180–270). De ellos, 140 recibieron
zolbetuximab; la diferencia es información útil para el RAG, no un error.

## Verificación

`tests/test_cohort_zolbetuximab.py` recalcula la tabla completa desde los CSV de Synthea (pandas, sin
SQL ni `concept_id`) y exige que coincida paso a paso, además de ejecutar los scripts dos veces para
comprobar que se pueden repetir. Ya detectó un caso real: un paciente con un esquema FOLFOX previo de
otro módulo, que el SQL por ingrediente atrapa y un recuento por los 8 códigos del módulo no.

## Qué mide cada paso (y qué no)

- Los pasos 1 y 3 no pierden a nadie: Synthea no genera menores y todos tienen diagnóstico. Se
  mantienen porque son criterios reales de los protocolos y porque el LLM tendrá que generarlos.
- El paso 5 pierde solo 1 caso: el módulo pone la recaída ≥ 6 meses (≈ 180 días) después de la
  adyuvancia, así que casi nadie cae en el lavado. Es una limitación del módulo, no un resultado
  clínico; si se quiere más atrición ahí, se añade recaída temprana a `PARAMS`.
- CLDN18 positivo es Claudina 18, no la isoforma 18.2 (`docs/LIMITACIONES.md`).

## Pendiente

- `sql/03_features.sql` (variables por paciente) y las cohortes de trastuzumab y nivolumab.
- Confirmar los umbrales (ECOG, lavado, ventana) con el corpus.
