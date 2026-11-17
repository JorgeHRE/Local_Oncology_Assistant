# Registro de cambios del ground truth

Formato: versión, fecha, qué cambió y por qué (`docs/guia-anotacion.md` §8).

## Sin versión (2026-11-05)

- Archivo `ground_truth.jsonl` creado vacío; esquema, validador y guía de anotación v0.1.
- `split_groups.json`: grupo de zolbetuximab (SPOTLIGHT, GLOW, NCT06901531, NCT07673887), porque GLOW
  comparte 30 de sus 35 criterios con SPOTLIGHT.
- Guía v0.2: cómo se formula cada tipo, ejemplos inventados (NCT00000000) y paso a paso.

## Sin versión (2026-11-17)

- Partición: NCT07103668, NCT06123494 y NCT02477826 pasan a `dev` (ensayos de las preguntas piloto del
  anotador); CheckMate 649 (NCT02872116) se queda en `test`.
- `split_groups.json`: grupo `checkmate-648-649` (NCT02872116 y NCT03143153), porque comparten 7 de
  los 11 criterios de CheckMate 649.
- Guía v1.0: congelada tras el piloto (3 R y 2 E válidas con `make gt-validate`). Cuota de E por
  sección completa confirmada; tiempos medidos (R ~5 min, E ~15 min) en §10.
- Validador: `\<`, `\^` y `\&` se tratan como escapes de Markdown (`chunking._ESCAPED`), porque las
  fichas del corpus los traen (`\<50%`) y una cita sin la barra no se encontraba. Requiere rehacer
  el índice (`make index`).
- Archivo: R-001 a R-003 y E-001 y E-002 (todos `dev`).

## Sin versión (2026-11-17)

- Archivo: añadidas R-004 a R-020 y E-003 a E-012. Con ellas están completas las cuotas de R (6/14) y E
  (4/8); faltan las 8 C. `make gt-validate` pasa; `gt-validate-final` solo falla por las C.
- Guía §10: tiempos medidos de toda la tanda (R ~5 min, E ~6 min intercaladas con las R).
- Archivo: añadidas C-001 a C-008 (2 `dev`: NCT06123494, NCT06177041; 6 `test`: NCT01041404,
  NCT02872116, NCT06346197, NCT07221149, NCT03504397, NCT05427383) con sus archivos SQL independientes
  en `sql/cohort_*.sql` (`sql/02_cohorte.sql` para NCT03504397), `dataset_id` y `expected_count`
  verificados contra los CSV de Synthea. `make gt-validate-final` pasa con las 40 preguntas completas.

## Sin versión (2026-11-17, declaración)

- C-007: declarado en `notes` y en la guía (preguntas abiertas) que `sql/02_cohorte.sql` tiene su base
  escrita con Claude Code (contra el ADR-0003) y que el anotador lo revisó manualmente. Limitación a
  mencionar al informar los resultados de C-007. El resto de C usa SQL propio del anotador.
