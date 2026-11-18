# Política de uso

- **Estado:** borrador (2026-11-17), proyecto académico (Modalidad D, curso de ciencia de datos). Es una
  declaración del autor de para qué sí y para qué no debe usarse este asistente; **no es asesoría legal**.
- **Relacionado:** `docs/LIMITACIONES.md` (qué no hace bien), `docs/USO_DE_IA.md` (qué IA se usó y licencias).

## 1. Qué es y qué no es

El **Local Oncology Assistant** es un prototipo de investigación para **explorar el tamizaje de elegibilidad**
a ensayos clínicos en cáncer gástrico: recupera criterios de los protocolos con citas verificadas y cuenta
cuántos pacientes **sintéticos** de una base OMOP cumplen los criterios que los datos pueden comprobar.

**No es** un dispositivo médico, un sistema de apoyo a la decisión clínica ni una herramienta para decidir
a quién tratar o a quién incluir en un ensayo. No ha sido validado clínicamente y no está pensado para
estarlo sin un trabajo regulatorio que este proyecto no hace.

## 2. Para qué sí

- **Investigación y docencia:** estudiar cómo combinar recuperación de texto con consultas sobre OMOP, y
  reproducir las mediciones del proyecto.
- **Explorar protocolos:** leer, con las citas literales a la vista, qué piden los criterios de inclusión y
  exclusión de los ensayos del corpus (88 documentos).
- **Estimar la viabilidad de manera ilustrativa** sobre la población sintética (los conteos son de datos
  generados por Synthea, no de pacientes).
- **Desarrollar sobre él**, con la licencia del repositorio y las de los modelos (`docs/USO_DE_IA.md` §3).

## 3. Para qué no

1. **Decisiones clínicas** sobre pacientes reales: diagnóstico, tratamiento, pronóstico, derivación o
   inclusión/exclusión en un ensayo. Las respuestas y los conteos **no deben informar** ninguna de ellas.
2. **Datos de pacientes reales.** El repositorio y los modelos se usaron solo con datos sintéticos y texto
   público. No cargues historiales reales: el sistema no se diseñó ni auditó para ello (privacidad, trazabilidad,
   consentimiento).
3. **Presentar un conteo como elegibilidad real.** "N pacientes cumplen" es un límite superior sobre datos
   sintéticos: solo aplica los criterios que los datos pueden comprobar y no incluye analíticas,
   comorbilidades, lesión medible ni consentimiento (`docs/LIMITACIONES.md`).
4. **Confiar sin verificar.** Una cita marcada "ok" significa que el texto está en el fragmento; **no**
   garantiza que respalde lo afirmado. Una respuesta sin cita, o con una marcada "NOT FOUND", no debe usarse.
5. **Usos que prohíben las licencias de los modelos.** Gemma (Prohibited Use Policy) y MedGemma (Health AI
   Developer Foundations) tienen restricciones propias, y MedGemma advierte que no está pensado para informar
   directamente un diagnóstico o una decisión de tratamiento (`docs/USO_DE_IA.md` §3).
6. **Sustituir la revisión de un profesional.** El sistema asiste la lectura de protocolos; no reemplaza a
   un clínico ni a un equipo de ensayos.

## 4. Cómo leer las salidas

| Salida | Qué significa | Qué hacer |
|---|---|---|
| Respuesta con fuentes "ok in the passage" | Cada cita es una copia literal del fragmento recuperado | Leer el fragmento: la cita puede no respaldar la afirmación |
| Fuente "NOT FOUND" / aviso "do not trust" | La cita no es literal o no está | No usar la respuesta |
| "The retrieved passages do not contain the answer" | No se recuperó la evidencia, o el modelo se negó | No es una respuesta de que el dato no exista; ver `LIMITACIONES.md` |
| "Cohort of NCT… : N patients" | Conteo sobre la población sintética con los criterios evaluables | Leer los filtros listados; es un límite superior |
| "There is no cohort defined for NCT…" | Solo hay cohorte para 8 ensayos | Usar la pregunta sobre el texto |

## 5. Responsabilidades y datos

- **Datos:** todo es local; ningún dato sale de la máquina para generar respuestas. Los asistentes de IA usados
  para desarrollar el proyecto (Claude Code, Gemini) son servicios en la nube que procesan el contenido que se
  les muestra, sin datos de pacientes reales (`docs/USO_DE_IA.md` §6).
- **Atribución de las fuentes:** las fichas de ClinicalTrials.gov se versionan con atribución y fecha
  (`docs/corpus.md`); los resúmenes de PubMed no se redistribuyen.
- **Responsabilidad:** el software se ofrece **tal cual**, sin garantía de ningún tipo. Quien lo use o lo adapte
  es responsable de su uso, de validarlo para su caso y de cumplir la normativa aplicable (privacidad, dispositivos
  médicos, protección de datos).
- **Cambios de alcance:** cualquier uso sobre datos reales o con consecuencias clínicas exigiría, como mínimo,
  validación clínica, evaluación de privacidad, revisión regulatoria y supervisión humana documentada;
  **no es el alcance de este proyecto**.

## 6. Cumplimiento y reporte

- Si encuentras una respuesta peligrosa o engañosa, repórtala como *issue* del repositorio indicando la
  pregunta, la salida y los fragmentos (`make ask-text`). Se añade a las limitaciones.
- Esta política se revisa al cambiar el alcance del proyecto, de los modelos o de los datos.
