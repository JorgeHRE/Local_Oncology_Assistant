# ADR-0004: Motor de inferencia local

- **Estado:** Propuesto. Medido en la máquina del proyecto (RTX 5070); vLLM y SGLang descartados por
  ahora con un criterio explícito para reevaluarlos.
- **Fecha:** 2026-10-14
- **Decisores:** Jorge (autor), con asistencia de Claude Code
- **Relacionado:** ADR-0002 (evaluación en dos pasadas), ADR-0005 (LLM), `eval/spike/` (scripts de la
  prueba), `docs/protocolo.md` (feedback del profesor)

## Contexto

El profesor preguntó "cómo lo vas a ejecutar (SGLang, vLLM, Ollama, etc.)". `CLAUDE.md` pedía
evaluar SGLang en serio por su generación estructurada repetida (RadixAttention), no usar Ollama
por defecto.

Requisitos que salen de los ADR anteriores:

- Salida **estructurada** con esquema JSON (extracción de criterios, ADR-0002 capa 2).
- **Reproducible:** misma entrada, semilla y temperatura 0 → misma salida (ADR-0002 §2).
- **Dos fases** con modelos distintos (generar y juzgar) en 12 GB de VRAM: hay que poder descargar un
  modelo y cargar otro rápido (ADR-0002 §4).
- Correr en la **RTX 5070** (Blackwell, capacidad de cómputo 12.0, driver 595.84, 12 227 MiB).
- Datos que no salen de la máquina.

## Opciones consideradas

1. **Ollama** (demonio con registro de modelos).
2. **llama.cpp `llama-server`** (binario y archivo GGUF).
3. **vLLM.**
4. **SGLang.**

### Prueba en la máquina (2026-10-14)

Modelo de prueba: `qwen3:8b` (Q4, 5,2 GB), **solo para medir el motor** (la elección del LLM es el
ADR-0005). Binarios nativos descargados y verificados por SHA-256; scripts en `eval/spike/`.

| Medida | Ollama 0.40.4 | llama.cpp b11624 |
|---|---|---|
| Corre en `sm_120` | Sí (CUDA 12.0, 11,5 GiB detectados) | Sí (binario precompilado CUDA 12.8) |
| Generación | 110 tokens/s | 107 tokens/s |
| Extracción con esquema JSON | 10/10 válidas, 3,2 s | 10/10 válidas, 3,5 s |
| Misma salida, semilla fija, temperatura 0 | Sí (5/5) | Sí (5/5) |
| VRAM con el modelo cargado | 6,2 GB | 6,2 GB |
| Descargar / recargar | 0 s / 2 s | Reiniciar proceso: 2 s |
| Primera carga desde disco | 23,5 s | No medida |

Notas: la primera generación en frío fue lenta (23,7 tokens/s) por la carga; las siguientes, no. El
endpoint `/v1/chat/completions` de Ollama acepta `response_format` con `json_schema`, igual que
llama.cpp. La salida es válida por construcción (generación restringida por gramática): lo que
varía entre modelos es la calidad del contenido, no la validez. Las cifras son de un solo equipo,
un modelo y una semilla; son orden de magnitud, no un benchmark.

### vLLM y SGLang: no probados

- Sin probar en esta GPU. Los reportes que encontré (2025) indican que las ruedas y las imágenes
  oficiales de vLLM fallaban en las RTX 50 con errores "no kernel image" y que se recomendaba
  compilar desde el código con CUDA 12.8 o superior; para SGLang no encontré información sobre
  `sm_120`. Puede haber cambiado.
- Su ventaja es el **rendimiento con muchas peticiones simultáneas** y el reuso de prefijos. Nuestra
  carga es secuencial: unas 120 llamadas por pasada de generación × ~3,3 s ≈ **7 minutos**. El
  rendimiento no es el cuello de botella.
- No medimos el reuso de prefijo de prompt (RadixAttention en SGLang; `llama-server` también cachea
  el prompt, sin probar). Es el único argumento técnico a favor que no pudimos descartar con datos.

## Decisión

### 1. Ollama por defecto; llama.cpp como alternativa documentada

- **Ollama** para desarrollo y evaluación: rendimiento igual al de llama.cpp, modelos descargados por
  nombre y verificados por *digest*, y descarga/carga por API, que es lo que necesitan las dos
  fases del ADR-0002.
- **llama.cpp `llama-server`** queda probado como respaldo con los mismos resultados. Se elige si hay
  que fijar la versión del motor por número de build y el GGUF por SHA-256 sin demonio.
- **Versiones fijadas:** Ollama `v0.40.4` (SHA-256 del tarball `15f31e95…ed3740a`); llama.cpp `b11624`
  (`a63b56fc…ad74baa`, más el paquete `cudart` `a2f14f43…af070d0`); modelo de prueba por digest del GGUF
  (`a3de86cd…686f`). Cada corrida de evaluación registra la versión del motor (ADR-0002).

### 2. Un cliente compatible con OpenAI

Todo el código habla `/v1/chat/completions` con `response_format`; cambiar de motor es cambiar una
URL y la comparación entre motores sale casi gratis. Dos diferencias menores se aíslan en un
**adaptador de motor**:

- **Ciclo de vida:** descargar un modelo no está en la API de OpenAI. Con Ollama es
  `keep_alive: 0`; con llama.cpp, reiniciar el proceso. Solo el adaptador conoce esto.
- **Modelos con "razonamiento":** apagarlo se pide distinto (`reasoning_effort: "none"` en Ollama,
  `chat_template_kwargs` en llama.cpp).

### 3. Cuándo reevaluar vLLM o SGLang

Se prueban (con una compilación verificada para `sm_120`) si ocurre alguno de estos:

- una corrida completa de evaluación pasa de **30 minutos**;
- se necesitan **peticiones concurrentes** (por ejemplo, una aplicación con varios usuarios);
- se quiere medir el reuso de prefijo con prompts largos y repetidos;
- las versiones oficiales documentan soporte de `sm_120` sin compilar.

> 💡 **Por qué esto importa en la industria:** elegir la herramienta más potente sin medir si el
> problema la necesita es un error común. Aquí el motor "de producción" (vLLM/SGLang) resolvería un
> cuello de botella que no existe, a cambio de una instalación frágil. Documentar el criterio para
> reevaluar deja la decisión abierta sin pagar el costo hoy.

## Consecuencias

- **Buenas:** funcionamiento medido en la GPU real; evaluación reproducible; motores
  intercambiables; el modelo y el motor quedan fijados por versión.
- **Costos y límites:**
  - **Docker con GPU no está probado.** El runtime de NVIDIA no está instalado en Docker (solo
    `runc`); haría falta el NVIDIA Container Toolkit (con permisos de administrador). Hasta
    entonces el motor corre **nativo**, fuera de `compose.yml`, y el README debe decirlo. Es una
    excepción al "todo en Docker" de ADR anteriores.
  - El adaptador de motor es código adicional a mantener.
  - Los binarios del motor y los modelos viven en `data/raw/engines/` (ignorado por git, ~5 GB).
  - Las medidas son de un solo equipo y un solo modelo.
- **No se descarta** SGLang: se difiere con criterio. La afirmación de `CLAUDE.md` de que tiene un
  argumento técnico específico sigue sin comprobarse con datos.

## Preguntas abiertas

- ¿Se instala el NVIDIA Container Toolkit para llevar el motor a `compose.yml`?
- ¿Qué modelo, y qué tamaño de contexto, usa cada capa? (ADR-0005.)
- ¿Qué modelo de embeddings usa el retrieval? Ollama y llama.cpp pueden servirlo.
