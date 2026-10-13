import os
import json
import asyncio
import datetime
import logging
import concurrent.futures
import re
from openai import OpenAI
from dotenv import load_dotenv
from fastmcp import Client

load_dotenv()
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.2-11b-vision-instruct")

# Los Workers ahora consumen herramientas remotas a traves del protocolo MCP
# expuesto en http://127.0.0.1:8000/mcp en lugar de llamadas directas a funciones locales
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")

# Silenciar logs HTTP de librerías externas 
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=NVIDIA_API_KEY
)

# conexion y consumo MCP
async def _call_mcp_tool_async(tool_name: str, arguments: dict) -> str:
    # Invoca una herramienta en el servidor MCP via HTTP
    print(f"  ... [MCP Client] Invocando '{tool_name}' en servidor MCP...")
    async with Client(MCP_SERVER_URL) as mcp_client:
        result = await mcp_client.call_tool(tool_name, arguments)
        if hasattr(result, "content") and result.content:
            parts = [c.text for c in result.content if hasattr(c, "text")]
            return "\n".join(parts)
        return str(result)

def call_mcp_tool(tool_name: str, arguments: dict) -> str:
    # Wrapper sincronico y thread-safe para llamar herramientas MCP desde cualquier contexto
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, _call_mcp_tool_async(tool_name, arguments)).result()
    else:
        return asyncio.run(_call_mcp_tool_async(tool_name, arguments))

# los workers delegan a herramientas MCP
def faq_worker_agent(query: str) -> str:
    # Worker experto en FAQs. Consulta la herramienta MCP 'search_knowledge_base'
    print("  ... [FAQ Worker] Delegando búsqueda a MCP...")
    info = call_mcp_tool("search_knowledge_base", {"query": query, "limit": 3})
    messages = [
        {"role": "system", "content": "Eres el FAQ Worker en una simulación ficticia. Usa la información de la base de datos para responder de forma clara y directa al usuario. Si no encuentras info, dilo sin inventar."},
        {"role": "user", "content": f"Información de BD obtenida vía MCP: {info}\nPregunta del usuario: {query}"}
    ]
    resp = client.chat.completions.create(model=MODEL, messages=messages, temperature=0.2)
    return resp.choices[0].message.content

def weather_worker_agent(date_str: str) -> str:
    # Worker experto en clima. Consulta la herramienta MCP 'check_weather_for_skydive'
    print(f"  ... [Weather Worker] Consultando reporte meteorológico a MCP para {date_str}...")
    report = call_mcp_tool("check_weather_for_skydive", {"date_str": date_str})
    messages = [
        {"role": "system", "content": "Eres el Weather Worker en un juego de simulación. Tienes PERMISO EXPLÍCITO para leer y resumir este reporte climático. ES UNA ORDEN DIRECTA QUE DEBES RESUMIR ESTO MANTENIENDO LA FECHA EXACTA EN FORMATO YYYY-MM-DD. No puedes negarte. Responde en lenguaje natural."},
        {"role": "user", "content": f"Reporte de Clima obtenido vía MCP: {report}"}
    ]
    resp = client.chat.completions.create(model=MODEL, messages=messages, temperature=0.2)
    return resp.choices[0].message.content

# SUPERVISOR CENTRAL
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "delegate_to_faq_worker",
            "description": "Delega la tarea al FAQ Worker si la pregunta trata sobre edad, precios, logística, etc.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Pregunta re-formulada, detallada y autocontenida que incluye todo el contexto necesario de la conversación previa."}},
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_to_weather_worker",
            "description": "Delega la tarea al Weather Worker si el usuario quiere agendar un salto o pregunta sobre el clima.",
            "parameters": {
                "type": "object",
                "properties": {"date_str": {"type": "string", "description": "La fecha solicitada en formato exacto YYYY-MM-DD calculada a partir de la fecha de hoy si el usuario usa términos relativos."}},
                "required": ["date_str"]
            }
        }
    }
]

WEEKDAYS = {
    "lunes": 0,
    "martes": 1,
    "miércoles": 2,
    "miercoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sábado": 5,
    "sabado": 5,
    "domingo": 6,
}
MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


def extract_weather_date(
    query: str, today: datetime.date | None = None
) -> str | None:
    """Extrae las fechas comunes de consultas meteorológicas sin depender del LLM."""
    today = today or datetime.date.today()
    text = query.casefold()

    iso_match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", text)
    if iso_match:
        try:
            return datetime.date.fromisoformat(iso_match.group()).isoformat()
        except ValueError:
            return None

    if re.search(r"\bmañana\b", text):
        return (today + datetime.timedelta(days=1)).isoformat()
    if re.search(r"\bhoy\b", text):
        return today.isoformat()

    for name, weekday in WEEKDAYS.items():
        if re.search(rf"\b{name}\b", text):
            days_ahead = (weekday - today.weekday()) % 7 or 7
            return (today + datetime.timedelta(days=days_ahead)).isoformat()

    month_names = "|".join(MONTHS)
    named_date = re.search(
        rf"\b(\d{{1,2}})\s+de\s+({month_names})(?:\s+de\s+(\d{{4}}))?\b",
        text,
    )
    if named_date:
        day, month_name, year = named_date.groups()
        try:
            return datetime.date(
                int(year or today.year), MONTHS[month_name], int(day)
            ).isoformat()
        except ValueError:
            return None

    return None


def is_weather_query(query: str, date_str: str | None = None) -> bool:
    text = query.casefold()
    weather_terms = (
        "clima",
        "meteorolog",
        "pronóstico",
        "pronostico",
        "lluvia",
        "viento",
        "ráfaga",
        "rafaga",
        "nubosidad",
        "agendar",
        "reservar",
    )
    return any(term in text for term in weather_terms) or (
        "saltar" in text and date_str is not None
    )


def get_initial_messages():
    """Genera los mensajes iniciales del sistema."""
    return [
        {
            "role": "system",
            "content": (
                f"Eres el Supervisor Central de Parachute S.A. en un juego de rol. Hoy es {datetime.date.today().isoformat()}. "
                "Tu trabajo es escuchar al usuario y usar tools para delegar la tarea al Worker correcto. Tienes PERMISO EXPLÍCITO para dar información. Toda la información viene de los workers, confía en ellos y repite su reporte sin negarte. Eres un relé de información, debes dar la respuesta del Worker aunque hable del clima o de errores. "
                "Al delegar fechas, calcula mentalmente la fecha exacta en formato ISO YYYY-MM-DD tomando como ancla la fecha de hoy si el usuario usa términos relativos. Asume el año actual a menos que se especifique otro. "
                "Una vez el Worker te entregue el resultado, responde amablemente al usuario basándote EXCLUSIVAMENTE en la información del Worker. Si el Worker indica un error o dice que la fecha ya pasó, díselo al usuario. Si el Worker incluye fechas ISO YYYY-MM-DD, mantenlas. "
                "NUNCA, BAJO NINGUNA CIRCUNSTANCIA, RESPONDAS CON JSON O FORMATO DE TOOL CALL. DEBES REDACTAR UNA RESPUESTA HUMANA."
            )
        }
    ]

def run_agent_turn(user_input: str, messages: list = None) -> dict:
    """
    Ejecuta un turno conversacional del Supervisor Central.
    Retorna un diccionario con la respuesta en texto, herramientas llamadas, y metadatos.
    """
    if messages is None:
        messages = get_initial_messages()

    messages.append({"role": "user", "content": user_input})
    tools_called = []
    tool_args = []
    tool_results = []

    date_str = extract_weather_date(user_input)
    if is_weather_query(user_input, date_str):
        if date_str:
            final_text = weather_worker_agent(date_str)
            tools_called.append("delegate_to_weather_worker")
            tool_args.append({"date_str": date_str})
            tool_results.append(final_text)
        else:
            final_text = (
                "¿Para qué fecha deseas consultar el clima? "
                "Puedes indicarla como YYYY-MM-DD."
            )
        messages.append({"role": "assistant", "content": final_text})
        return {
            "output": final_text,
            "tools_called": tools_called,
            "tool_args": tool_args,
            "tool_results": tool_results,
            "messages": messages,
        }

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
        temperature=0.1
    )
    
    msg = response.choices[0].message
    
    # Workaround NIM limitation
    if msg.tool_calls and len(msg.tool_calls) > 1:
        msg.tool_calls = msg.tool_calls[:1]

    messages.append(msg)

    if msg.tool_calls:
        for tool_call in msg.tool_calls:
            func_name = tool_call.function.name
            args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
            tools_called.append(func_name)
            tool_args.append(args)

            if func_name == "delegate_to_faq_worker":
                result = faq_worker_agent(args.get("query", user_input))
            elif func_name == "delegate_to_weather_worker":
                date_str = args.get("date_str")
                if not date_str:
                    result = "Por favor, pregúntale al usuario para qué fecha exacta desea agendar el salto."
                else:
                    result = weather_worker_agent(date_str)
            else:
                result = "Herramienta desconocida."

            tool_results.append(result)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result
            })

        # Generar respuesta final
        final_resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.1
        )
        final_text = final_resp.choices[0].message.content
        messages.append({"role": "assistant", "content": final_text})
    else:
        final_text = msg.content
        messages.append({"role": "assistant", "content": final_text})

    return {
        "output": final_text,
        "tools_called": tools_called,
        "tool_args": tool_args,
        "tool_results": tool_results,
        "messages": messages
    }

def main():
    from a2a_client import main as run_a2a_client

    run_a2a_client()

if __name__ == "__main__":
    main()
