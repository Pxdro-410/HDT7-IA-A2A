import time
import json
import sys
import os
from dotenv import load_dotenv

# Asegurar carga de variables de entorno
load_dotenv()

# Importar la lógica desacoplada del agente centralizado
from centralized import run_agent_turn

def call_api(prompt: str, options: dict = None, context: dict = None):
    """
    Función de entrada para Promptfoo Custom Python Provider.
    Recibe:
        prompt: Texto o consulta del usuario
        options: Opciones adicionales pasadas por promptfoo
        context: Contexto de ejecución (vars, etc.)
    Retorna:
        dict con formato compatible con Promptfoo:
        {
            "output": str,
            "metadata": dict
        }
    """
    start_time = time.time()
    try:
        # Ejecutar un turno completo del agente supervisor con sus workers
        result = run_agent_turn(prompt)
        elapsed_ms = int((time.time() - start_time) * 1000)

        output_text = result.get("output", "")
        tools_called = result.get("tools_called", [])
        tool_args = result.get("tool_args", [])

        return {
            "output": output_text,
            "metadata": {
                "tools_called": tools_called,
                "tool_args": tool_args,
                "latency_ms": elapsed_ms
            }
        }
    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        return {
            "error": str(e),
            "output": f"Error ejecutando agente: {str(e)}",
            "metadata": {
                "tools_called": [],
                "tool_args": [],
                "latency_ms": elapsed_ms
            }
        }

if __name__ == "__main__":
    # Prueba rápida desde consola
    test_query = sys.argv[1] if len(sys.argv) > 1 else "¿Cuál es el correo de soporte de Parachute S.A.?"
    print(f"Ejecutando prueba con: '{test_query}'\n")
    res = call_api(test_query)
    print(json.dumps(res, indent=2, ensure_ascii=False))
