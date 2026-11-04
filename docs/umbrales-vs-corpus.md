# Umbrales del módulo gástrico frente al corpus

- **Estado:** borrador para revisión (2026-11-04). No se ha cambiado ningún parámetro del generador ni
  de la cohorte: esto solo documenta qué respalda el corpus y qué no.
- **Fuentes:** 39 resúmenes de PubMed (`data/raw/corpus/pubmed/`, solo locales) y 39 fichas de
  ClinicalTrials.gov no distractoras (`corpus/clinicaltrials/`, 4 pivotales + 35 candidatos). Las
  citas llevan PMID o NCT.
- **Parámetros:** `PARAMS` en `synthea/build_gastric_cancer.py` y criterios de
  `docs/cohorte-zolbetuximab.md`.
- **Límite del método:** los resúmenes no traen las tablas de características basales ni los
  apéndices. Muchas prevalencias que se recuerdan de los artículos completos (por ejemplo, el
  porcentaje de CPS ≥ 5 en CheckMate 649) **no están en el corpus**; no las doy por confirmadas.

Leyenda: **✓** respaldado por el corpus · **~** parcialmente o con matices · **✗** el corpus apunta a
otro valor · **?** el corpus no permite evaluarlo.

## Probabilidades de biomarcadores (`PARAMS`)

| Parámetro | Valor | Qué dice el corpus | Veredicto |
|---|---|---|---|
| `p_her2_positive` | 20 % | 22,1 % de positividad en el cribado de ToGA (PMID 25038874); "aproximadamente 15–20 %" en gástrico y UGE avanzados (PMID 37329891). | ✓ |
| `p_cldn18_positive` | 38 % | Tres estudios con el corte del ensayo (≥ 75 % de células, tinción moderada-fuerte): **34,4 %** (PMID 39306800, estadios II–IV), **31,3 %** tras considerar la heterogeneidad (PMID 39615405, n = 400) y **29,9 %** (PMID 42232601, cohorte occidental resecada). El 38 % del cribado de SPOTLIGHT/GLOW no aparece en los resúmenes del corpus. | ✗ (el corpus da 30–34 %) |
| `p_cps_high` (CPS ≥ 5) | 60 % | CheckMate 649 (PMID 34102137) usa CPS ≥ 5 como población primaria, pero el resumen no da qué fracción de los 1 581 aleatorizados la cumple. Otro estudio (PMID 37963317, perioperatorio) halló **58 % con CPS ≥ 1**, lo que haría imposible un 60 % con CPS ≥ 5 en esa población. | ? (con una señal en contra en cohortes resecables) |
| `p_msi_high` | 5 % | 8 % (23 pacientes) en un ensayo perioperatorio de esofagogástrico (PMID 37963317). No hay cifra para enfermedad avanzada en el corpus. | ~ |
| `ecog` (ECOG ≥ 2 = 15 %) | 0: 35, 1: 50, 2: 10, 3: 4, 4: 1 | Ningún texto da la distribución real, porque los ensayos solo reclutan ECOG 0–1. En el alcance clínico (§4) ya figuraba como "elegido para la atrición". | ? (por diseño) |
| `p_cardia` | 20 % | Ningún texto da la proporción. Sí hay una relación útil: HER2 es más frecuente en UGE que en estómago (32,2 % frente a 21,4 %) y en intestinal que en difuso (31,8 % frente a 6,1 %), según PMID 25038874. | ? |

**Correlaciones que el módulo no modela (v1 independiente):** CLDN18.2 es *menos* frecuente en HER2
positivo (P = 0,005) y *más* en EBV y PD-L1 CPS ≥ 5 (P = 0,014); es rara en adenocarcinoma mucinoso
(2,8 %) y muy frecuente en carcinomas con estroma linfoide (90,9 %) (PMID 39306800). Con CLDN18.2 y
HER2 independientes, la cohorte de zolbetuximab (HER2 − y CLDN18 +) sale algo mayor que con la
correlación real. Ya está documentado en `docs/alcance-clinico-modulo-gastrico.md` §4.1 y
`docs/LIMITACIONES.md`.

## Flujo clínico (`PARAMS`)

| Parámetro | Valor | Qué dice el corpus | Veredicto |
|---|---|---|---|
| `stage` (IV de novo) | 55 % | Sin cifras en los resúmenes. | ? |
| `p_recurrence` | 15 / 30 / 45 % | Sin cifras (los resúmenes dan supervivencia, no tasas de recaída por estadio). | ? |
| `p_perioperative`, `p_flot_given_perioperative` | 80 % / 70 % | FLOT4 muestra que FLOT supera a ECF/ECX (HR 0,77; mediana de SG 50 frente a 35 meses; PMID 30982686) y la guía francesa 2026 (PMID 42054784) lo sitúa como base perioperatoria. Respaldan **que FLOT sea el esquema**, no las proporciones. | ~ |
| `p_capox` | 60 % (resto FOLFOX) | Sin cifras. | ? |
| `p_targeted_given_eligible`, `p_mono_given_poor_ecog`, `p_death` | 85 % / 60 % / 70 % | Sin respaldo en el corpus: son decisiones de modelado. | ? |
| `recurrence_delay_months` | 6–18 | Sin respaldo directo. Sí es coherente con el lavado de 6 meses (abajo). | ~ |
| `n_cycles` × `cycle_days` | 6 × 21 días para ambos esquemas | **Discrepancia:** CheckMate 649 y SPOTLIGHT describen **CAPOX cada 3 semanas y mFOLFOX6/FOLFOX cada 2 semanas** (PMID 34102137, 37068504). Un solo `cycle_days = 21` es correcto para CAPOX pero no para FOLFOX. | ✗ (para FOLFOX) |

## Criterios de la cohorte de zolbetuximab

| Criterio | Valor en la cohorte | Qué dice el corpus | Veredicto |
|---|---|---|---|
| ECOG 0–1 | 0–1 | 33 de las 39 fichas no distractoras piden ECOG 0–1 de forma explícita. Las 6 restantes: 4 no mencionan ECOG, 1 (NCT01041404, ToGA) no lo trae en la ficha recortada y 1 (NCT06203600) admite **Zubrod 0–2**. SPOTLIGHT y GLOW: "ECOG performance status 0 to 1" (NCT03504397, NCT03653507). | ✓ |
| HER2 negativo | Resultado de HER2 negativo | SPOTLIGHT/GLOW: "HER2-negative tumor as determined by local or central testing on a gastric or GEJ tumor specimen". | ✓ |
| CLDN18 positivo | Resultado positivo, sin umbral | SPOTLIGHT/GLOW exigen **≥ 75 % de células con tinción membranosa moderada-fuerte** por IHC central. La cohorte usa CLDN18 genérico, no 18.2 con ese corte (limitación ya declarada). | ~ |
| Lavado de 180 días | Sin quimioterapia sistémica 180 días antes del índice | SPOTLIGHT y GLOW: neo/adyuvante permitido si "was completed at least 6 months prior to randomization" (NCT03504397, NCT03653507). 28 de las 39 fichas mencionan 6 meses junto con adyuvante o perioperatorio (regex; incluye algún falso positivo). Variantes: algunas piden 12 meses (renal, distractor) o cuentan el tratamiento previo como primera línea si hubo recaída en 6 meses. | ✓ |
| Ventana de ±30 días | Mediciones ±30 días del índice | Las fichas usan ventanas **previas** a la aleatorización, no simétricas: "within 28 days" aparece 48 veces, "4 weeks" 36, "14 days" 31, "7 days" 26 y "30 days" 12; para ECOG, de 3 a 14 días. Ver recomendación 3. | ~ |

## Recomendaciones (para que decidas)

1. **`p_cldn18_positive`: bajar a ~33 %.** Es lo que sostienen tres estudios del corpus con el
   corte del ensayo. Sin correlación con HER2, el efecto sobre la cohorte sería modesto, pero
   cambiaría los 243 elegibles; habría que regenerar la población (1 340 pacientes, ~27 min de ETL).
   Si no se cambia, documentar que el 38 % viene de memoria y que el corpus indica 30–34 %.
2. **`cycle_days`: separar por esquema** (CAPOX 21 días, FOLFOX 14). Es un error de modelado, no
   una elección. Afecta a las fechas de las dosis, y por tanto al paso de lavado de la atrición.
3. **Ventana de mediciones:** pasar de ±30 días a una ventana previa de 28 días (más fiel a los
   protocolos) o mantener ±30 y declararlo como tolerancia propia. En los datos actuales las
   mediciones coinciden el mismo día, así que no cambia ningún número.
4. **`p_cps_high`:** no cambiarlo con este corpus. Falta la cifra de CheckMate 649 (texto completo).
   Hay que buscarla en el artículo completo o declarar que el 60 % no está verificado.
5. **Resto (estadios, recaída, muerte, tratamiento):** son supuestos de modelado sin respaldo en
   el corpus. Documentarlos como tales en `docs/LIMITACIONES.md` en lugar de buscar una fuente.
6. **Si se amplía el corpus:** añadir el texto completo (o la tabla basal) de CheckMate 649 y de
   SPOTLIGHT/GLOW cubriría CPS ≥ 5 y el 38 % de CLDN18.2.
