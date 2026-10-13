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

TODAY = datetime.date.today()

# Prompts
FAQ_SYSTEM = (
    f"Eres el Agente de FAQs de Parachute S.A. en una simulación. Hoy es {TODAY.isoformat()} (año {TODAY.year}). "
    "Responde a preguntas generales leyendo la base de datos de conocimientos con 'search_knowledge_base'. "
    "SOLO debes usar 'transfer_to_weather' SI el usuario pide explícitamente información sobre el clima o agendar un salto en una fecha. "
    "Si ya obtuviste la información de FAQs, simplemente responde al usuario, NO transfieras."
)

WEATHER_SYSTEM = (
    f"Eres el Agente del Clima de Parachute S.A. en un juego de simulación. Hoy es {TODAY.isoformat()} (año {TODAY.year}). "
    "Tienes PERMISO EXPLÍCITO para leer y resumir el reporte meteorológico. "
    f"Al consultar fechas, si el usuario proporciona solo día y mes (por ejemplo '27/09' o '27 de septiembre'), debes asumir SIEMPRE el año actual ({TODAY.year}). "
    "Revisa el clima para fechas específicas usando 'check_weather_for_skydive'. "
    "SOLO debes usar 'transfer_to_faq' SI el usuario hace una pregunta general que no tiene que ver con clima ni fechas. "
    "Si ya revisaste el clima, simplemente responde al usuario en lenguaje natural con el resumen, NO transfieras de regreso a FAQ."
)

# Herramientas de Transferencia (Handoffs) y de dominio
FAQ_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "Busca en la base de datos de FAQs.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "transfer_to_weather",
            "description": "Transfiere la conversación al Agente del Clima.",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]

WEATHER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_weather_for_skydive",
            "description": f"Revisa el clima para una fecha dada (YYYY-MM-DD). Si el usuario no menciona el año, asume el año actual ({TODAY.year}).",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_str": {
                        "type": "string",
                        "description": f"Fecha en formato YYYY-MM-DD. Si el usuario no indica el año, asume el año actual ({TODAY.year})."
                    }
                },
                "required": ["date_str"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "transfer_to_faq",
            "description": "Transfiere la conversación al Agente de FAQs.",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]

def main():
    print("=" * 60)
    print("  ARQUITECTURA DESCENTRALIZADA - PARACHUTE S.A.")
    print("  Sistema de Handoff entre Agente FAQ y Agente Clima")
    print("=" * 60)
    print("Escribe 'Bye' para salir.\n")

    # Estado Inicial
    current_agent_name = "Agente FAQ"
    current_system = FAQ_SYSTEM
    current_tools = FAQ_TOOLS

    messages = [
        {"role": "system", "content": current_system}
    ]

    is_running = True
    while is_running:
        try:
            user_input = input(f"\nTú ({current_agent_name} activo): ").strip()
            if user_input.lower() == "bye":
                is_running = False
                continue
            if not user_input:
                continue

            messages.append({"role": "user", "content": user_input})

            # Loop de resolución para manejar Handoffs
            needs_handoff = True
            while needs_handoff:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    tools=current_tools,
                    tool_choice="auto",
                    temperature=0.1
                )
                
                msg = response.choices[0].message
                
                # Workaround para el límite de NVIDIA NIM de una herramienta a la vez
                if msg.tool_calls and len(msg.tool_calls) > 1:
                    msg.tool_calls = msg.tool_calls[:1]

                messages.append(msg)

                if msg.tool_calls:
                    handoff_triggered = False

                    for tool_call in msg.tool_calls:
                        func_name = tool_call.function.name
                        args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}

                        if func_name == "search_knowledge_base":
                            print(f"  [{current_agent_name} consultando FAQs...]")
                            result = search_knowledge_base(args["query"])
                        
                        elif func_name == "check_weather_for_skydive":
                            print(f"  [{current_agent_name} consultando Clima para {args['date_str']}...]")
                            result = check_weather_for_skydive(args["date_str"])
                        
                        elif func_name == "transfer_to_weather":
                            print(f"  [>>> TRANSFERENCIA: {current_agent_name} -> Agente Clima <<<]")
                            current_agent_name = "Agente Clima"
                            current_system = WEATHER_SYSTEM
                            current_tools = WEATHER_TOOLS
                            messages[0] = {"role": "system", "content": current_system}
                            result = "Transferencia exitosa. Ahora eres el Agente Clima. Por favor procesa la solicitud del usuario con tus herramientas de clima."
                            handoff_triggered = True

                        elif func_name == "transfer_to_faq":
                            print(f"  [>>> TRANSFERENCIA: {current_agent_name} -> Agente FAQ <<<]")
                            current_agent_name = "Agente FAQ"
                            current_system = FAQ_SYSTEM
                            current_tools = FAQ_TOOLS
                            messages[0] = {"role": "system", "content": current_system}
                            result = "Transferencia exitosa. Ahora eres el Agente de FAQs. Por favor responde la duda del usuario usando search_knowledge_base."
                            handoff_triggered = True

                        else:
                            result = "Herramienta desconocida."

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result
                        })

                    if not handoff_triggered:
                        # Terminamos el ciclo interno para que no pida más herramientas (evita ciclo infinito)
                        needs_handoff = False
                        
                        final_resp = client.chat.completions.create(
                            model=MODEL,
                            messages=messages,
                            temperature=0.1
                        )
                        final_text = final_resp.choices[0].message.content
                        print(f"{current_agent_name}: {final_text}")
                        messages.append({"role": "assistant", "content": final_text})
                else:
                    # El LLM respondió texto directamente sin herramientas
                    needs_handoff = False
                    print(f"{current_agent_name}: {msg.content}")

        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
