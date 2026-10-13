# Guía de Trabajo y Contexto para Agentes y Desarrolladores (HDT6 - Evals)

Este documento define la distribución equitativa de responsabilidades, la arquitectura de pruebas y el contexto técnico para los desarrolladores **Pedro Caso** y **Hugo Méndez** en la realización de la **Hoja de Trabajo 6: AI Evals** para el proyecto **Parachute S.A.**

---

## 1. Contexto del Proyecto

El sistema evaluado corresponde a los agentes conversacionales desarrollados para **Parachute S.A.** (empresa ficticia de paracaidismo tándem en Guatemala). El agente opera bajo dos dominios principales:
1. **Resolución de Preguntas Frecuentes (FAQs):** Consultas sobre requerimientos de salud (edad, buceo, medicamentos), logística, precios, ubicación y normas operativas respaldadas por una base de datos vectorial en PostgreSQL con `pgvector` y embeddings locales (`all-MiniLM-L6-v2`).
2. **Agendamiento y Factibilidad de Citas:** Evaluación de fechas de salto consultando la API meteorológica de **Open-Meteo** para verificar velocidad del viento (< 28 km/h), ráfagas (< 35 km/h), precipitación (0 mm) y nubosidad en la zona de salto.

### Estado Actual de Infraestructura
- **Docker:** Contenedor `parachute_pgvector` arriba y corriendo con 120 FAQs vectorizadas en la tabla `faqs`.
- **Entorno Python:** Entorno virtual `.venv` configurado con dependencias instaladas (`openai`, `python-dotenv`, `httpx`, `sentence-transformers`, `psycopg2-binary`, `pgvector`).
- **Arquitectura base a evaluar:** Arquitectura Centralizada (`centralized.py`) con Supervisor Central y Workers especializados (`faq_worker_agent`, `weather_worker_agent`).

---

## 2. Requerimientos de Evaluación (Promptfoo)

Según las directivas de `HDT6-IA.md`, se debe utilizar **Promptfoo** para evaluar ambas funcionalidades del agente. Para cada funcionalidad, es obligatorio implementar los siguientes 4 tipos de evaluadores (*graders*):

| Tipo de Eval | Objetivo | Ejemplo de Aserción Promptfoo |
| :--- | :--- | :--- |
| **1. Factuality** | Verificar que la información generada no contenga alucinaciones y sea fiel a la base documental o al reporte meteorológico. | `type: factuality` o `type: model-graded-closedqa` contrastando con la respuesta oficial. |
| **2. Determinísticos** | Validar presencia exacta o patrones de datos críticos (emails oficiales, formatos de fecha, precios, estados). | `type: contains` (ej. `soporte@parachutesa.gt`) y `type: regex` (ej. `\d{4}-\d{2}-\d{2}`). |
| **3. Latencia** | Asegurar que el tiempo total de respuesta (LLM + Tools + BD) se mantenga en márgenes aceptables. | `type: latency` con umbral máximo (`threshold: 8000`). |
| **4. Tool Execution** | Validar que el agente invoque la herramienta o worker correcto con los parámetros esperados. | `type: javascript` inspeccionando `context.metadata.tools_called` y sus argumentos. |

---

## 3. División Equitativa del Trabajo

```mermaid
graph TD
    subgraph Pedro Caso [Desarrollador 1: Pedro Caso]
        P1[Arquitectura del Custom Provider para Promptfoo]
        P2[Suite de Evals: Resolución de FAQs]
        P3[Validación de Factuality RAG y Determinísticos FAQs]
    end

    subgraph Hugo Méndez [Desarrollador 2: Hugo Méndez]
        H1[Estandarización del Flujo de Agendamiento/Clima]
        H2[Suite de Evals: Agendamiento y Clima]
        H3[Validación de Reglas Meteorológicas y Tool Execution Clima]
    end

    subgraph Conjunto [Trabajo Conjunto e Integración]
        J1[Unificación en promptfooconfig.yaml]
        J2[Ejecución de npx promptfoo eval]
        J3[Generación y Análisis del Reporte HTML/JSON]
        J4[Actualización de README.md y Entrega]
    end

    Pedro Caso --> Conjunto
    Hugo Méndez --> Conjunto
```

### Desarrollador 1: Pedro Caso (Core Provider & Dominio FAQs) - [COMPLETADO]

#### Implementaciones Realizadas:
1. **Refactorización del Supervisor Central ([centralized.py](file:///c:/UVG/AI%20selectivo/HDT6%20AI/HDT6-IA-Evals/centralized.py)):**
   - Se extrajo la función `run_agent_turn(user_input: str, messages: list = None) -> dict`, permitiendo desacoplar la ejecución conversacional del loop interactivo de consola `main()`.
   - Retorna estructura completa con: `output`, `tools_called`, `tool_args`, `tool_results` y `messages`.
2. **Custom Provider para Promptfoo ([agent_provider.py](file:///c:/UVG/AI%20selectivo/HDT6%20AI/HDT6-IA-Evals/agent_provider.py)):**
   - Implementa `call_api(prompt, options, context)` para que Promptfoo invoque al agente directamente en Python y reciba la respuesta junto a metadatos de telemetría:
     ```python
     {
         "output": turn_result["output"],
         "metadata": {
             "tools_called": turn_result["tools_called"],
             "tool_args": turn_result["tool_args"],
             "latency_ms": latency_ms
         }
     }
     ```
3. **Suite de Evaluación de FAQs ([promptfooconfig.yaml](file:///c:/UVG/AI%20selectivo/HDT6%20AI/HDT6-IA-Evals/promptfooconfig.yaml)):**
   - 6 casos de prueba cubriendo los 4 tipos de evaluadores obligatorios:
     - `FAQ-01` (Factuality - `model-graded-closedqa`): Límite de peso estricto de 100 kg.
     - `FAQ-02` (Factuality - `model-graded-closedqa`): Edad mínima 18 años cumplidos.
     - `FAQ-03` (Determinístico - `icontains`): Espera obligatoria de 24 horas tras buceo.
     - `FAQ-04` (Determinístico - `regex`): Altura de salto de 3,000 m / 10,000 ft.
     - `FAQ-05` (Latencia - `latency`): Umbral de respuesta `< 25,000 ms`.
     - `FAQ-06` (Tool Execution - `javascript`): Verificación de llamada exclusiva a `delegate_to_faq_worker`.
   - **Resultado actual:** 6 de 6 aprobados (100% PASS).

---

### Desarrollador 2: Hugo Méndez (Dominio Agendamiento & Clima) - [COMPLETADO]

#### Responsabilidades para Completar el Proyecto:
1. **Alineación y Robustez del Flujo de Agendamiento/Clima ([centralized.py](file:///c:/UVG/AI%20selectivo/HDT6%20AI/HDT6-IA-Evals/centralized.py) / [services.py](file:///c:/UVG/AI%20selectivo/HDT6%20AI/HDT6-IA-Evals/services.py)):**
   - Asegurar que cuando el usuario mencione fechas futuras (ej. "el próximo sábado", "30 de septiembre"), el supervisor delegue a `delegate_to_weather_worker` con la fecha en formato ISO `YYYY-MM-DD`.
   - Comprobar que `check_weather_for_skydive` evalúe correctamente los parámetros meteorológicos de Open-Meteo y el supervisor reporte si la fecha es viable ("PERMITIDO") o riesgosa ("NO RECOMENDADO").
2. **Agregar los Tests de Citas y Clima a [promptfooconfig.yaml](file:///c:/UVG/AI%20selectivo/HDT6%20AI/HDT6-IA-Evals/promptfooconfig.yaml):**
   - Agregar bajo la sección `tests:` los casos de prueba para el dominio de citas:
     - **Factuality (`model-graded-closedqa`):** Validar que ante condiciones adversas (lluvia o viento > 28 km/h), el agente advierta que el salto no se recomienda por seguridad.
     - **Determinístico (`regex` o `contains`):** Validar que aparezca la fecha evaluada (`\d{4}-\d{2}-\d{2}`) y las palabras clave de viabilidad.
     - **Latencia (`latency`):** Validar que la consulta externa a Open-Meteo no exceda el umbral esperado (ej. `< 25000`).
     - **Tool Execution (`javascript`):** Inspeccionar que `context.metadata.tools_called.includes('delegate_to_weather_worker')` y que los argumentos contengan la fecha esperada.

---

## 4. Guía de Ejecución y Visualización de Promptfoo

### Requisitos Previos
1. Contenedor de PostgreSQL con pgvector arriba:
   ```powershell
   docker compose up -d
   ```
2. Entorno virtual activo con librerías instaladas:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```
3. Archivo `.env` configurado con `NVIDIA_API_KEY`, `OPENAI_API_KEY` y `OPENAI_BASE_URL` (puedes basarte en `.example_env`).

### Comandos de Ejecución

#### Ejecutar la suite de pruebas
Se utiliza el script configurado en `package.json`, el cual inyecta automáticamente el archivo `.env` para autenticar tanto al agente como al modelo juez:
```bash
npm run eval
```
*(Equivalente a: `.\node_modules\.bin\promptfoo.cmd eval --env-file .env -j 1 --no-cache -o eval_report.html`)*.

#### Ver el reporte interactivo en el navegador
Promptfoo incluye un visor web interactivo con filtros, análisis de latencia, costos de tokens y detalle de cada aserción:
```bash
npm run view
```
*(Se abrirá un servidor local en `http://localhost:15500`)*.

#### Reporte estático generado
Cada ejecución de `npm run eval` actualiza automáticamente el archivo:
- [eval_report.html](file:///c:/UVG/AI%20selectivo/HDT6%20AI/HDT6-IA-Evals/eval_report.html) (se puede abrir con doble clic en cualquier navegador).


