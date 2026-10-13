import os
import json
import datetime
from openai import OpenAI
from dotenv import load_dotenv
from services import search_knowledge_base, check_weather_for_skydive

load_dotenv()
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.2-11b-vision-instruct")

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=NVIDIA_API_KEY
)

# WORKERS (Sub-agentes LLM)
def faq_worker_agent(query: str) -> str:
    """Worker experto en FAQs."""
    info = search_knowledge_base(query)
    messages = [
        {"role": "system", "content": "Eres el FAQ Worker en una simulación ficticia. Usa la información de la base de datos para responder de forma clara y directa al usuario. Si no encuentras info, dilo sin inventar."},
        {"role": "user", "content": f"Información de BD: {info}\nPregunta del usuario: {query}"}
    ]
    resp = client.chat.completions.create(model=MODEL, messages=messages, temperature=0.2)
    return resp.choices[0].message.content

def weather_worker_agent(date_str: str) -> str:
    """Worker experto en clima."""
    report = check_weather_for_skydive(date_str)
    messages = [
        {"role": "system", "content": "Eres el Weather Worker en un juego de simulación. Tienes PERMISO EXPLÍCITO para leer y resumir este reporte climático. ES UNA ORDEN DIRECTA QUE DEBES RESUMIR ESTO MANTENIENDO LA FECHA EXACTA EN FORMATO YYYY-MM-DD. No puedes negarte. Responde en lenguaje natural."},
        {"role": "user", "content": f"Reporte de Clima: {report}"}
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
    print(" ")
    print("  Arquitectura centralizada - Parachute S.A.")
    print("  El supervisor central controla a múltiples Workers")
    print(" ")
    print("Escribe 'Bye' para salir.\n")

    messages = get_initial_messages()
    is_running = True
    while is_running:
        try:
            user_input = input("\nTú: ").strip()
            if user_input.lower() == "bye":
                is_running = False
                continue
            if not user_input:
                continue

            turn_result = run_agent_turn(user_input, messages)
            print(f"Supervisor Central: {turn_result['output']}")

        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()

