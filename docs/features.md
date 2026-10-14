# Diccionario de datos

Variables clínicas que emite el módulo `gastric_cancer.json` y cómo quedan en OMOP CDM v5.4 tras el
ETL (`etl/`) y el paso `etl/post_etl/01_value_as_concept.sql`. Los `concept_id` son de Athena v5.0
(29-AUG-26). Actualizar en el mismo commit en que cambie el módulo.

## Condiciones (`condition_occurrence`)

| Variable | Código | `concept_id` | Notas |
|---|---|---|---|
| Adenocarcinoma gástrico | SNOMED 408647009 | 4248802 | 80 % de los diagnósticos |
| Neoplasia maligna del cardias | SNOMED 187732006 | 4094856 | 20 %; aproximación a la UGE (ver limitaciones) |

## Mediciones (`measurement`)

| Variable | LOINC | `concept_id` | Valor | Notas |
|---|---|---|---|---|
| Estadio agrupado | 42100-8 | 3031548 | `value_as_concept_id`: Stage 1–4 (4121054, 4106768, 4121176, 4123017) | Un registro al diagnóstico; los recaídos tienen otro Stage 4 en la recaída. Sin subestadios |
| HER2 (IHQ) | 18474-7 | 3019066 | Positive (9191) / Negative (9189) | Solo en enfermedad avanzada |
| **CLDN18.2 (aprox.)** | 105011-1 | 1091409 | Positive / Negative | **Es Claudin 18, no la isoforma 18.2; escala Narrative; sin umbral ≥ 75 %.** Ver `docs/LIMITACIONES.md` |
| PD-L1 CPS | 105303-2 | 1091860 | `value_as_number` 0–100, unidad `{score}` | CPS ≥ 5 en ~60 % |
| MSI | 81695-9 | 21493972 | Positive (= MSI-H) / Negative | |
| ECOG | 89247-1 | 36305384 | `value_as_number` 0–4, unidad `{score}` | |

## Fármacos (`drug_exposure`; ingrediente vía `concept_ancestor`)

| Fármaco | Producto RxNorm (código) | Dónde aparece |
|---|---|---|
| oxaliplatino | 1736786 | FLOT previo, CAPOX/FOLFOX previo, primera línea |
| capecitabina | 200328 | CAPOX adyuvante previo, primera línea (CAPOX o monoterapia) |
| fluorouracilo, leucovorina | 1791704, 1803937 | FLOT previo, FOLFOX |
| docetaxel | 1860617 | Solo FLOT previo (marca la exposición perioperatoria) |
| trastuzumab | 1922509 | Primera línea, HER2+ |
| zolbetuximab | 2695876 | Primera línea, HER2− y CLDN18.2+ |
| nivolumab | 1657193 | Primera línea, HER2− y CPS ≥ 5 |

Un esquema no se codifica como tal: se reconoce por los ingredientes administrados el mismo día.
