import os
import sys
import logging
import datetime
from fastmcp import FastMCP
from services import search_knowledge_base as _search_kb, check_weather_for_skydive as _check_weather

# servidor MCP (Model Context Protocol) 
# Expone las herramientas del sistema de paracaidismo como herramientas MCP en http://127.0.0.1:8000/mcp
# Configuración de logs con formato legible para consola
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [MCP-SERVER] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("mcp_server")

# Inicialización del servidor FastMCP
mcp = FastMCP("Parachute MCP Server")

@mcp.tool()
def search_knowledge_base(query: str, limit: int = 3) -> str:
    """Consulta la base de conocimientos vectorial de Parachute S.A. sobre preguntas frecuentes, precios, requisitos y politicas."""
    logger.info(f">>> [TOOL CALL] search_knowledge_base(query='{query}', limit={limit})")
    try:
        result = _search_kb(query, limit)
        logger.info(f"<<< [TOOL SUCCESS] search_knowledge_base retorno {len(result)} caracteres.")
        return result
    except Exception as e:
        logger.error(f"xxx [TOOL ERROR] Error en search_knowledge_base: {e}")
        return f"Error ejecutando busqueda de conocimientos: {str(e)}"

@mcp.tool()
def check_weather_for_skydive(date_str: str) -> str:
    """Verifica si las condiciones climaticas son aptas para saltar en paracaidas en una fecha especifica (formato YYYY-MM-DD)."""
    logger.info(f">>> [TOOL CALL] check_weather_for_skydive(date_str='{date_str}')")
    try:
        result = _check_weather(date_str)
        logger.info(f"<<< [TOOL SUCCESS] check_weather_for_skydive completado exitosamente para {date_str}.")
        return result
    except Exception as e:
        logger.error(f"xxx [TOOL ERROR] Error en check_weather_for_skydive: {e}")
        return f"Error verificando clima: {str(e)}"

if __name__ == "__main__":
    print("\n")
    print("  Servidor MCP via HTTP")
    print("  Host: 127.0.0.1 | Puerto: 8000 | Endpoint: /mcp")
    print("  Herramientas expuestas:")
    print("    - search_knowledge_base (RAG pgvector)")
    print("    - check_weather_for_skydive (Open-Meteo API)")
    print(" ")
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8000, path="/mcp")
