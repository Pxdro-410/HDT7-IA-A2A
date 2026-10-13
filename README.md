# HDT7: Sistema Multiagente Compatible con A2A

Implementación para **Parachute S.A.** en la que la terminal interactúa como cliente **A2A (Agent-to-Agent)**, un servidor A2A expone el sistema multiagente centralizado bajo el protocolo JSON-RPC, y los workers especializados consumen las herramientas expuestas a través del protocolo **MCP (Model Context Protocol)**.

---

## Integrantes

- **Pedro Caso** - 241286
- **Hugo Méndez** - 241265

---

## Arquitectura del Sistema

```text
       Terminal (Cliente A2A)
                 |
                 | A2A JSON-RPC (:9999)
                 v
   Servidor A2A (FastAPI / Starlette)
                 |
                 v
         Supervisor Central
        /                  \
       v                    v
  FAQ Worker          Weather Worker
       \                    /
        v                  v
     Cliente MCP (Streamable HTTP)
                 |
                 | Protocolo MCP (:8000/mcp)
                 v
           Servidor MCP (FastMCP)
          /                      \
         v                        v
Base de Datos PostgreSQL     API Meteorológica
 (pgvector: FAQs RAG)          (Open-Meteo)
```

---

## Estructura del Repositorio

- **`mcp_server.py`**: Servidor FastMCP que publica las herramientas remotas (`search_knowledge_base` y `check_weather_for_skydive`) en `http://127.0.0.1:8000/mcp`.
- **`a2a_server.py`**: Servidor A2A que expone la Agent Card en `/.well-known/agent-card.json` y gestiona las solicitudes de los clientes vía JSON-RPC.
- **`a2a_client.py`**: Cliente oficial de A2A con soporte de contexto conversacional continuo y timeout configurable para llamadas multi-agente.
- **`centralized.py`**: Orquestador central (Supervisor Central) con delegación a los workers (`FAQ Worker` y `Weather Worker`) que consumen las herramientas MCP.
- **`services.py`**: Lógica de búsqueda vectorial en PostgreSQL (`pgvector`) y validación de reglas climáticas con Open-Meteo.
- **`load_faqs.py`**: Script de inicialización y carga de embeddings de FAQs a la base de datos PostgreSQL.
- **`docker-compose.yml`**: Configuración del contenedor Docker para PostgreSQL 16 con extensión `pgvector`.
- **`tests/`**: Suite de pruebas unitarias que valida la Agent Card, el ejecutor A2A y la delegación de herramientas.

---

## Requisitos Previos

- **Python 3.10 o superior** (probado y recomendado con **Python 3.11**).
- **Docker y Docker Compose** (para PostgreSQL con `pgvector`).
- Una API Key válida de NVIDIA NIM configurada en `.env`.

---

## Instalación y Configuración

### 1. Entorno virtual y dependencias

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configurar variables de entorno

Copia el archivo de ejemplo y completa tus credenciales (en especial `NVIDIA_API_KEY`):

```bash
cp .example_env .env
```

### 3. Base de datos con pgvector

Asegúrate de que Docker Desktop esté abierto y levanta el contenedor de PostgreSQL:

```bash
cp docker-compose.example.yml docker-compose.yml
docker compose up -d
```

Poblar la base de datos con las 120 FAQs y sus embeddings (se ejecuta una sola vez):

```bash
python load_faqs.py
```

---

## Guía de Ejecución y Demostración

Para la demostración completa, abre **tres terminales** independientes, activa el entorno virtual en cada una (`source .venv/bin/activate`) y ejecuta los servicios en el siguiente orden:

### Terminal 1: Servidor MCP
```bash
python mcp_server.py
```
- Escucha en `http://127.0.0.1:8000/mcp`.
- Muestra logs en tiempo real de cada llamada a herramienta (`[TOOL CALL]`) y su resultado (`[TOOL SUCCESS]`).

### Terminal 2: Servidor A2A
```bash
python a2a_server.py
```
- Escucha en `http://127.0.0.1:9999`.
- Publica su Agent Card en `http://127.0.0.1:9999/.well-known/agent-card.json`.
- Registra el `context_id`, la latencia de respuesta y las herramientas invocadas.

Para comprobar la Agent Card:
```bash
curl http://127.0.0.1:9999/.well-known/agent-card.json
```

### Terminal 3: Cliente A2A (Terminal Interactiva)
```bash
python centralized.py
```
*(También puede ejecutarse como `python a2a_client.py`)*.

El cliente descubre la Agent Card, establece conexión A2A y mantiene el contexto entre preguntas:

```text
Tú: ¿Cuál es el peso máximo para saltar?
Supervisor Central: El peso máximo permitido para saltar es de 100 kg...

Tú: ¿Puedo saltar el próximo sábado?
Supervisor Central: Lo siento, pero el clima para el próximo sábado no es recomendado debido a condiciones adversas...

Tú: Bye
```

---

## Pruebas Unitarias

Para ejecutar la suite de pruebas del cliente/servidor A2A y la lógica del supervisor:

```bash
python -m unittest discover -s tests -v
```

---

## Variables de Entorno

| Variable | Valor por defecto | Descripción |
| --- | --- | --- |
| `NVIDIA_API_KEY` | *(requerido)* | Llave de API para NVIDIA NIM / Llama-3.2 |
| `NVIDIA_MODEL` | `meta/llama-3.2-11b-vision-instruct` | Modelo LLM utilizado por el supervisor y workers |
| `MCP_SERVER_URL` | `http://127.0.0.1:8000/mcp` | Endpoint HTTP del servidor FastMCP |
| `A2A_SERVER_URL` | `http://127.0.0.1:9999` | Dirección del servidor A2A consumido por el cliente |
| `A2A_PUBLIC_URL` | `http://127.0.0.1:9999` | URL anunciada en la Agent Card |
| `A2A_HOST` | `127.0.0.1` | Host de escucha del servidor A2A |
| `A2A_PORT` | `9999` | Puerto de escucha del servidor A2A |
| `A2A_CLIENT_TIMEOUT` | `60.0` | Timeout en segundos para solicitudes del cliente A2A |
| `DB_HOST` | `localhost` | Host de la base de datos PostgreSQL |
| `DB_PORT` | `5432` | Puerto de PostgreSQL |
| `DB_NAME` | `parachute_faqs` | Nombre de la base de datos |
| `DB_USER` | `postgres` | Usuario de PostgreSQL |
| `DB_PASSWORD` | `postgrespassword` | Contraseña de PostgreSQL |

---

## Referencias Oficiales

- [Protocolo A2A - Documentación Oficial](https://a2a-protocol.org/)
- [Crear e iniciar un servidor A2A en Python](https://a2a-protocol.org/latest/tutorials/python/5-start-server/)
- [Interactuar con el servidor usando el cliente Python A2A](https://a2a-protocol.org/latest/tutorials/python/6-interact-with-server/)
- [Repositorio Oficial A2A SDK Python](https://github.com/a2aproject/a2a-python)
- [FastMCP para Python](https://github.com/jlowin/fastmcp)
