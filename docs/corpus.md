# Corpus del RAG

- **Estado:** fuentes públicas descargadas (2026-10-15); guías NCCN/ESMO pendientes de que las descargues.
- **Código:** `src/oncology_assistant/corpus.py`; selección en `corpus/selection.json`; registro en
  `corpus/manifest.json`. Comandos: `make corpus`, `make corpus-verify`
  (y `python -m oncology_assistant.corpus verify --committed-only`, lo que corre el CI).

## Qué contiene

| Fuente | Documentos | Para qué |
|---|---|---|
| ClinicalTrials.gov (API v2) | 49: 4 pivotales, 35 candidatos y 10 distractores | Criterios de inclusión/exclusión: preguntas de extracción (E) y de cohorte (C) del ground truth (ADR-0003) |
| PubMed (resúmenes) | 39: 36 de referencia y 3 distractores | Preguntas de recuperación (R): biomarcadores, guías, esquemas |
| Guías (NCCN, ESMO) | 0 por ahora | Las descargas tú a mano (ver abajo) |

- **Pivotales:** SPOTLIGHT (NCT03504397), GLOW (NCT03653507), CheckMate 649 (NCT02872116) y ToGA
  (NCT01041404), que respaldan los criterios del módulo gástrico (`docs/alcance-clinico-modulo-gastrico.md` §3).
  Las fichas de CheckMate 649 y de ToGA tienen poco texto de criterios (1,1 k y 0,5 k caracteres).
- **Candidatos:** 35 ensayos de fase 3 de cáncer gástrico/UGE, elegidos a mano de una lista de
  candidatos puntuada (fase 3, enfermedad avanzada, texto de criterios suficiente, menciones de
  HER2, claudina, PD-L1/CPS, MSI y ECOG). Predominan primera línea y ensayos recientes, con algunos de
  otras líneas para contrastar. Seis consultas de la API produjeron los candidatos (ver
  `corpus/selection.json` para la lista final).
- **Distractores:** 10 fichas y 3 resúmenes de otros cánceres (colorrectal MSI-H, pulmón, mama HER2+,
  esófago, biliar, melanoma, cabeza y cuello, riñón, hígado) con criterios muy parecidos, para que la
  recuperación tenga que distinguir. Sin ellos, el retrieval sería artificialmente fácil.
- **Resúmenes:** 36 de referencia sobre claudina 18.2, HER2, PD-L1, MSI, primera línea, FLOT, guías,
  estadificación, Lauren, FGFR2b y líneas posteriores, más las cuatro publicaciones pivotales. Se
  quitaron los registros sin resumen en PubMed (guías ESMO y un artículo del NEJM): sin texto no aportan.

## Qué se versiona y qué no

| Qué | Dónde | En git |
|---|---|---|
| Fichas de ClinicalTrials.gov (49) | `corpus/clinicaltrials/NCTxxxxxxxx.json` | **Sí**, muy recortadas (376 KB en total); términos de uso revisados (ver final) |
| Resúmenes de PubMed (39) y guías | `data/raw/corpus/` | No: pueden tener derechos de autor |
| Qué descargar | `corpus/selection.json` | Sí |
| Registro de lo descargado | `corpus/manifest.json` | Sí: fuente, URL, **versión de la fuente** (fecha de última actualización), **fecha de descarga**, tamaño y **SHA-256** de cada documento |

El manifiesto cumple la regla de `CLAUDE.md` §7 (fuente, versión y fecha de descarga).

**Por qué las fichas sí están en el repo.** Los criterios de inclusión/exclusión que se anotan en el
ground truth no pueden cambiar debajo de las anotaciones, y las fichas se actualizan en línea. Con la
foto fechada y su SHA-256 versionados, cualquiera puede reproducir exactamente lo anotado, y el CI
comprueba que nadie las haya tocado (`test_committed_clinicaltrials_snapshots_match_the_manifest`).

**Qué guarda cada ficha.** Solo lo que necesita el ground truth: número NCT y título, estado y fecha
de última actualización, condición y criterios de elegibilidad (376 KB en total). Se descartan la
descripción en prosa, los brazos e intervenciones, el diseño, el patrocinador, los resultados y las
listas de contactos y sedes. Es lo más voluminoso, lo que más se parece a texto con autoría del
patrocinador y lo único que nombra personas.

**Licencia: revisada el 2026-11-04.** Los términos de ClinicalTrials.gov permiten redistribuir con
atribución, fecha de descarga y declaración de las modificaciones (ver *Atribución y términos de uso*
al final). Queda un riesgo residual: parte del contenido puede ser de terceros, y esto no es asesoría
legal. Si se decidiera no versionarlas, es un cambio de una línea: `COMMIT_CT_SNAPSHOTS = False` en
`corpus.py`, `git rm -r corpus/clinicaltrials` y `make corpus`. El manifiesto sigue detectando
cambios en la copia local.

**Resúmenes y guías (solo locales).** Se pueden volver a descargar con `make corpus`, pero los
resúmenes de PubMed también se revisan: si cambia el SHA-256, `make corpus-verify` lo avisa. La
copia de referencia de estos es la del autor.

## Cómo añadir guías (NCCN, ESMO)

NCCN exige cuenta gratuita y ESMO se publica con derechos de autor: no se descargan automáticamente.

1. Descarga el PDF a `data/raw/corpus/guidelines/` (por ejemplo `nccn_gastric_2026.pdf`).
2. Junto a él, un archivo `nccn_gastric_2026.pdf.meta.json` con **todos** estos campos (la regla de
   datos exige fuente, versión y fecha):

   ```json
   {"title": "NCCN Guidelines: Gastric Cancer", "publisher": "NCCN", "version": "2026 v2",
    "url": "https://www.nccn.org/...", "downloaded_on": "2026-10-15"}
   ```

3. `make corpus` los registra en el manifiesto (los que no tengan el archivo `.meta.json` completo se
   omiten con un aviso). Después, haz commit del manifiesto actualizado; el PDF no se sube.

## Límites

- Sesgo de selección: pocos ensayos de fase 3 completados con resultados; muchos reclutando y varios
  chinos. Representa lo que hay registrado, no la literatura completa.
- Solo resúmenes de PubMed, no textos completos: preguntas que dependan de tablas o apéndices no se
  pueden responder con este corpus.
- Los umbrales clínicos del módulo gástrico (ECOG, CPS ≥ 5, lavado, ventana) siguen sin contrastarse
  con este corpus: es el siguiente paso, y condiciona el ground truth de nivel *a*.

## Atribución y términos de uso

Texto que acompaña a lo redistribuido (fichas de ClinicalTrials.gov y manifiesto). Se reproduce en
inglés porque son las frases que piden los términos:

- **Atribución:** "Data obtained from ClinicalTrials.gov. Courtesy of the U.S. National Library of Medicine."
- **Copia congelada:** "These records were retrieved and processed on [fecha de descarga: `retrieved_at`
  del manifiesto]. This dataset is a frozen snapshot for academic reproducibility and does not
  reflect the most current/accurate data available from NLM / ClinicalTrials.gov."
- **Modificaciones:** "Original study records from the ClinicalTrials.gov API v2 were modified by
  trimming all fields except NCT ID, title, recruitment status, conditions, and eligibility criteria."
- **Sin respaldo ni garantías:** "NLM and the U.S. Government do not endorse this project, do not
  review or approve the safety and science of listed studies, make no warranties expressed or
  implied, and assume no liability for the use of these data."

### Revisión de términos de uso (hecha por el autor el 2026-11-04)

**Conclusión:** se pueden versionar las 49 fichas recortadas y el manifiesto (con los títulos de
PubMed); los resúmenes de PubMed y las guías siguen solo locales. Condiciones: incluir el bloque de
arriba, mostrar la fecha de descarga y declarar la modificación. Frases citadas por el autor; no las
he verificado yo (las páginas se cargan con JavaScript).

**A. Términos de ClinicalTrials.gov** — <https://clinicaltrials.gov/about-site/terms-conditions>
(última actualización de la página: 2023-01-31).

| Pregunta | Qué dicen | Consecuencia |
|---|---|---|
| Alcance | "apply to all data obtained from ClinicalTrials.gov, independent of format and method of acquisition" | Incluye la API v2 |
| Derechos | Los patrocinadores envían los datos a la NLM; "Some ClinicalTrials.gov data may be subject to the copyright of third parties"; no se puede reclamar derechos propietarios ni presentar la base como algo distinto de una base del Gobierno de EE. UU. | Hay riesgo residual en contenido de terceros (escalas, adjuntos); las fichas recortadas no los incluyen |
| Redistribuir / uso comercial | Datos gratis para todos; regula "any publication or distribution of these data". Única prohibición: usar correos extraídos para marketing | Permitido; sin restricción no comercial. Las fichas ya no llevan contactos |
| Atribución | "Attribute the source of the data as ClinicalTrials.gov"; no usar el nombre o logo de la NLM para implicar respaldo | Bloque de atribución de arriba |
| Mantener actualizada | "Update the data such that they are current at all times" y "Clearly display the date the data were processed" (redactado como *should*) | Se combina con el punto E: o se actualiza, o se declara que no es lo más actual |
| Modificaciones | "State any modifications made to the content of the data, along with a complete description of the modifications" | Declaración de modificaciones de arriba |
| Garantías | La NLM no da garantías ni asume responsabilidad | Incluido en el bloque de arriba |
| Software / aprendizaje automático | No se menciona ni se restringe | Sin obligación adicional |

**B. API de datos** — <https://clinicaltrials.gov/data-api/api> y
<https://clinicaltrials.gov/data-api/about-api>. Pública, sin clave, sujeta a los mismos términos.
El autor anota un límite aproximado de 50 peticiones por minuto por IP (cifra no verificada por mí).
Una descarga completa son 49 peticiones con pausa de 0,2 s (unos 10 s), es decir, justo en el
límite, y durante el desarrollo se repitió unas cuatro veces. La pausa de `corpus.py` pasó a 1 s
(`CT_DELAY_S`; menos de un minuto en total, con margen).

**C. Aviso legal** — <https://clinicaltrials.gov/about-site/disclaimer> (2023-08-03). El gobierno de
EE. UU. no revisa ni aprueba la seguridad y ciencia de todos los estudios; no supervisa ni financia
todos; los datos los aportan patrocinadores o investigadores, responsables de que sean completos y
exactos. Cubierto en la frase "Sin respaldo ni garantías".

**D. Políticas web de la NLM** — <https://www.nlm.nih.gov/web_policies.html>. Una ficha enviada por
un patrocinador es información de terceros bajo mandato federal (FDAAA 801) dentro de una base de
datos gubernamental. Lo que se guarda (título, estado, condición y criterios) son datos factuales del
estudio, no texto literario, y su redistribución está autorizada bajo las condiciones de A. Es la
lectura del autor, no asesoría legal.

**E. Términos de descarga de datos de la NLM** —
<https://www.nlm.nih.gov/databases/download/terms_and_conditions.html>. Hablan de FTP, pero los
términos de ClinicalTrials.gov (A) abarcan cualquier método de adquisición, así que se cumplen ambos:
frase "Courtesy of the U.S. National Library of Medicine", fecha de descarga y aviso de copia
congelada.

**F. PubMed y E-utilities** — <https://www.ncbi.nlm.nih.gov/home/about/policies/> y
<https://www.ncbi.nlm.nih.gov/books/NBK25497/> (actualizada 2022-11-17).
- La NLM no reclama derechos sobre los resúmenes ("journal publishers or authors may"). Los datos
  bibliográficos (PMID, título, DOI) del manifiesto son factuales y se pueden publicar; los
  resúmenes siguen solo en local.
- `tool` y `email` no son obligatorios para que la petición funcione, pero sin ellos NCBI no
  desbloquea una IP bloqueada. `email` debe ser el del desarrollador y solo se usa para avisar antes
  de bloquear. Con 39 artículos a menos de 3 peticiones por segundo no hay riesgo.
- **Decisión:** no poner el correo personal en el código. Implementado: `NCBI_EMAIL`
  es una variable de entorno opcional (vacía en `.env.example`) y `tool` se envía siempre.

**G. Precedente (no es permiso):** AACT redistribuye copias de ClinicalTrials.gov
(<https://aact.ctti-clinicaltrials.org/>) citando la fuente y la fecha. No se escribió al soporte de
la NLM.
