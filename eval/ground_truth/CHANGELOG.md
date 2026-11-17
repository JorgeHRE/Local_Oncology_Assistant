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
