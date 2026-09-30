# Alcance clínico del módulo Synthea de cáncer gástrico (borrador)

- **Estado:** Borrador para revisar con el profesor. Cierra la pregunta abierta "Alcance clínico del
  módulo" de ADR-0001.
- **Fecha:** 2026-09-29
- **Relacionado:** `docs/adr/0001-datos-sinteticos-cancer-gastrico.md`, `docs/protocolo.md`

## 1. Objetivo

Definir el **mínimo clínico** que el módulo GMF `gastric_cancer.json` tiene que simular para que:

1. Los criterios de inclusión/exclusión que el RAG extrae de guías y ensayos se puedan evaluar sobre
   la base OMOP.
2. La cohorte de la Sesión 18 tenga una **tabla de atrición con pérdidas en cada paso**, no una
   cohorte donde todos cumplen todo.

No es un modelo epidemiológico. Las probabilidades se eligen para que haya pacientes en cada rama; la
prevalencia no es realista (ver "Consecuencias" en ADR-0001).

## 2. Población

| Parámetro | Propuesta | Comentario |
|---|---|---|
| Sexo | Ambos (`-g` sin fijar) | En la prueba de mama se usó solo F; el gástrico es más frecuente en hombres (~2:1). |
| Edad al diagnóstico | 30–85 años, con más peso en edades mayores (mediana ~65) | Se incluye la cola de inicio temprano (<50 años), donde predomina el tipo difuso. Ver §4.1. |
| Enfermedad | Adenocarcinoma gástrico | La unión gastroesofágica (UGE) queda fuera de v1 (ver §7). |
| Selección | *Keep module*: pacientes con diagnóstico de adenocarcinoma gástrico | Igual que en la prueba de mama. |

## 3. Criterios que el módulo tiene que permitir evaluar

Salen de los ensayos pivotales que respaldan cada tratamiento de primera línea. Son los criterios
que el RAG debería recuperar del corpus.

| Criterio | Ensayo / guía de origen | Qué tiene que existir en OMOP |
|---|---|---|
| Adenocarcinoma gástrico localmente avanzado irresecable o metastásico | Todos | Diagnóstico + estadio |
| Sin tratamiento sistémico previo para enfermedad avanzada | SPOTLIGHT, GLOW, CheckMate 649, ToGA | `drug_exposure` con fechas |
| ECOG 0–1 | Todos | Medición de ECOG |
| HER2 positivo (IHC 3+ o IHC 2+ con FISH+) | ToGA (trastuzumab) | Medición HER2 |
| HER2 negativo **y** CLDN18.2 positivo (≥75 % de células tumorales, tinción moderada/intensa) | SPOTLIGHT, GLOW (zolbetuximab) | HER2 + CLDN18.2 |
| HER2 negativo y PD-L1 CPS ≥ 5 | CheckMate 649 (nivolumab, indicación EMA) | HER2 + PD-L1 CPS |
| MSI-H / dMMR | Guías NCCN/ESMO (inmunoterapia) | Medición MSI |

> ⚠️ Los umbrales vienen de memoria, no del corpus. **Hay que confirmarlos con las guías y artículos
> que se van a indexar en el RAG** antes de fijarlos en el módulo, porque son justo el ground truth.

## 4. Flujo del módulo (estados mínimos)

```
Inicio ─► Diagnóstico (adenocarcinoma gástrico)
            │
            ├─► Estadio: localizado (I–III)  ~30 %  ─► FLOT perioperatorio ─► vigilancia / recaída ─┐
            │                                                                                       │
            └─► Estadio: avanzado (IV)       ~70 %  ◄──────────────────────────────────────────────┘
                     │
                     ▼
               Panel de biomarcadores + ECOG (misma visita)
                     │
                     ├─ ECOG ≥ 2 (~15 %) ─────────────► solo quimioterapia o soporte  (exclusión)
                     │
                     ├─ HER2+                         ─► CAPOX/FOLFOX + trastuzumab
                     ├─ HER2−, CLDN18.2+              ─► CAPOX/FOLFOX + zolbetuximab ┐ si es CLDN18.2+ y
                     ├─ HER2−, CPS ≥ 5                ─► CAPOX/FOLFOX + nivolumab    ┘ CPS ≥ 5: 50/50
                     └─ HER2−, CLDN18.2−, CPS < 5     ─► CAPOX/FOLFOX solo
                     │
                     ▼
               Progresión ─► (2.ª línea: fuera de v1) ─► Muerte
```

**Casos puestos a propósito para la atrición:**
- Pacientes en estadio localizado que nunca progresan: se excluyen por no tener enfermedad avanzada.
- ECOG ≥ 2: se excluyen por el estado funcional.
- HER2+ y CLDN18.2+ a la vez: no son elegibles para zolbetuximab aunque sean CLDN18.2+.
- Una fracción de los biomarcador-positivos que **no** reciben el fármaco dirigido, igual que los 11
  HER2+ sin trastuzumab de la prueba de mama.

### Probabilidades propuestas (a validar)

| Variable | Probabilidad | Referencia aproximada (a verificar) |
|---|---|---|
| HER2+ | 20 % | ~22 % de positivos en el cribado de ToGA |
| CLDN18.2+ (≥75 %) | 38 % | ~38 % en el cribado de SPOTLIGHT/GLOW |
| PD-L1 CPS ≥ 5 | 60 % | ~60 % en CheckMate 649 |
| MSI-H | 5 % | 3–5 % en enfermedad avanzada |
| ECOG ≥ 2 | 15 % | Elegido para la atrición |

En v1, los biomarcadores se sortean **de forma independiente**. En la realidad hay correlaciones
(por ejemplo, MSI-H con CPS alto), pero modelarlas complica el GMF sin aportar a la evaluación.

### 4.1 Edad, histología y CLDN18.2: por qué no se correlacionan en v1

- El tipo **difuso** de Lauren es más frecuente en pacientes jóvenes y, entre ellos, en mujeres; aun
  así, el tipo **intestinal** es el más común en el total de pacientes. El rango 30–85 con mediana
  ~65 refleja las dos cosas sin forzar ninguna.
- En el TCGA (2014), el subtipo **genómicamente estable (GS)** está enriquecido en histología difusa,
  aparece a edades más jóvenes y concentra las **fusiones CLDN18–ARHGAP26/6**.
- Esa fusión **no equivale** a CLDN18.2 positivo por IHC (≥75 % de células tumorales), que es lo
  que define la elegibilidad para zolbetuximab. La asociación entre CLDN18.2 por IHC y el tipo
  difuso, la edad o el sexo es inconsistente entre estudios.
- **Decisión:** no subir la probabilidad de CLDN18.2+ en jóvenes ni en mujeres. Hacerlo sesgaría la
  cohorte a favor de la hipótesis con evidencia débil. Si se modela la histología (v2, ver §7), se
  hace sin ligarla a CLDN18.2.

> ⚠️ Cifras de memoria; verificar contra el artículo del TCGA y los ensayos SPOTLIGHT/GLOW si entran
> al corpus.

## 5. Codificación (verificada contra el vocabulario cargado, Athena v5.0 29-AUG-26)

Todos los códigos son conceptos estándar (`S`), como exige la regla de ADR-0001.

**Diagnóstico**

| Concepto | Código | `concept_id` |
|---|---|---|
| Adenocarcinoma of stomach | SNOMED 408647009 | 4248802 |

**Mediciones**

| Medición | LOINC | `concept_id` | Tipo de valor |
|---|---|---|---|
| HER2 IHC | 18474-7 | 3019066 | Positive / Negative (9191 / 9189) |
| CLDN18 IHC | 105011-1 | 1091409 | Positive / Negative |
| PD-L1 CPS | 105303-2 (*Tumor cells+Macrophages+Lymphocytes PD-L1 / viable tumor cells, ratio*) | 1091860 | **Numérico** |
| MSI | 81695-9 | 21493972 | Positive / Negative (o *Detected / Not detected*) |
| ECOG | 89247-1 | 36305384 | **Numérico** (0–4) |
| Estadio AJCC | 42100-8 | 3031548 | Stage 1–4 (4121054, 4106768, 4121176, 4123017) |

**Decisión de diseño:** donde se pueda, el valor es **numérico** (CPS, ECOG). Así termina en
`value_as_number`, que ETL-Synthea sí llena, y no depende del paso posterior al ETL para
`value_as_concept_id`. Ese paso solo hace falta para Positive/Negative y el estadio, es decir, una
tabla de unas 8 filas.

**Fármacos (ingrediente RxNorm; todos estándar)**

| Fármaco | Ingrediente `concept_id` | Producto candidato (Clinical Drug) |
|---|---|---|
| oxaliplatino | 1318011 | 35604084 oxaliplatin 100 MG Injection |
| capecitabina | 1337620 | 19023530 capecitabine 500 MG Oral Tablet |
| fluorouracilo | 955632 | 42628976 fluorouracil 50 MG/ML Injection |
| leucovorina | 1388796 | 40220873 leucovorin 200 MG Injection |
| docetaxel | 1315942 | 1718787 docetaxel 10 MG/ML Injection |
| trastuzumab | 1387104 | 1594432 trastuzumab 150 MG Injection |
| zolbetuximab | 1735539 | 1735544 zolbetuximab-clzb 100 MG Injection |
| nivolumab | 45892628 | 46276086 nivolumab 10 MG/ML Injection |

Los esquemas (FLOT, CAPOX, FOLFOX) no se codifican como tal: se registran los fármacos que los
componen en el mismo día. La cohorte SQL los reconoce por sus ingredientes vía `concept_ancestor`.

## 6. Fuera de alcance en v1

- Unión gastroesofágica y adenocarcinoma de esófago.
- Segunda línea y posteriores (ramucirumab + paclitaxel, trifluridina/tipiracilo, trastuzumab
  deruxtecan).
- Cirugía detallada, radioterapia, toxicidades, ajustes de dosis.
- TNM detallado y subestadios (dependen de Cancer Modifier, ver §7).
- Histología de Lauren (intestinal/difuso) y carcinoma de células en anillo de sello (candidato a
  v2, ver §7).

## 7. Preguntas para el profesor

1. **Alcance:** ¿basta con primera línea en enfermedad avanzada, o la pregunta de investigación
   necesita también la perioperatoria (FLOT) con más detalle o la segunda línea?
2. **UGE:** ¿se incluye la unión gastroesofágica? SPOTLIGHT, GLOW y CheckMate 649 la incluyen. No
   encontré un concepto SNOMED estándar con ese nombre exacto; habría que buscarlo mejor.
3. **Estadio:** ¿alcanza con el estadio agrupado (I–IV), que es estándar, o se necesita TNM o
   subestadios? En ese caso hay que descargar **Cancer Modifier** de Athena.
4. **Metástasis:** ¿hace falta registrar el sitio (hígado, peritoneo) como condición aparte, o
   alcanza con estadio IV?
5. **CLDN18.2:** el LOINC 105011-1 es "Claudin 18", no específicamente la isoforma 18.2, y es de
   escala *Narrative*. ¿Se acepta como aproximación documentada en las limitaciones?
6. **Histología de Lauren (v2):** ¿vale la pena modelar intestinal vs. difuso, con el difuso más
   probable en jóvenes y en mujeres? Existe el concepto SNOMED estándar 1268556005 (*Histologic type
   of primary adenocarcinoma of stomach using Lauren classification technique*, 37167604). Hoy no es
   criterio de elegibilidad en ningún ensayo pivotal, pero daría preguntas interesantes al RAG. Ver
   §4.1 para por qué no se ligaría a CLDN18.2.
7. **Tamaño:** ¿cuántos pacientes gástricos se quieren en la cohorte final? Con ~70 % avanzados y
   las probabilidades de arriba, 300 pacientes dan unos 50 CLDN18.2+ elegibles para zolbetuximab
   (300 × 0.70 avanzados × 0.85 ECOG 0–1 × 0.80 HER2− × 0.38 CLDN18.2+ ≈ 54).
