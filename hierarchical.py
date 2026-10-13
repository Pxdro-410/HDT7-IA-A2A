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

# ==========================================
# NIVEL 3: WORKERS
# ==========================================
def faq_worker(query: str) -> str:
    """Worker de nivel bajo que consulta la BD vectorial."""
    return search_knowledge_base(query)

def weather_worker(date_str: str) -> str:
    """Worker de nivel bajo que consulta Open-Meteo."""
    return check_weather_for_skydive(date_str)

# ==========================================
# NIVEL 2: MANAGERS DE DEPARTAMENTO
# ==========================================
def customer_service_manager(query: str) -> str:
    """Manager del departamento de atención al cliente."""
    print("      [Customer Service Manager analizando solicitud y ordenando al FAQ Worker...]")
    # El Manager decide usar a su worker
    data = faq_worker(query)
    
    # El Manager procesa la data antes de subirla
    messages = [
        {"role": "system", "content": "Eres el Customer Service Manager en un juego de simulación. Tienes PERMISO EXPLÍCITO para proveer información sobre reglas de salud (buceo, medicamentos, edad). Tu Worker te trajo esta info de la BD. Redacta una respuesta amigable resumiendo EXACTAMENTE lo que dice la BD, sin omitir nada por seguridad."},
        {"role": "user", "content": f"Info del Worker: {data}\nPregunta original: {query}"}
    ]
    resp = client.chat.completions.create(model=MODEL, messages=messages, temperature=0.2)
    return resp.choices[0].message.content

def operations_manager(date_str: str) -> str:
    """Manager del departamento de operaciones."""
    print(f"      [Operations Manager ordenando análisis climático al Weather Worker para {date_str}...]")
    # El Manager delega a su worker
    data = weather_worker(date_str)
    
    messages = [
        {"role": "system", "content": "Eres el Operations Manager en una simulación ficticia. Tu Worker te trajo este reporte climático. Resúmelo y dile al General Manager si se autoriza el salto."},
        {"role": "user", "content": f"Reporte del Worker: {data}"}
    ]
    resp = client.chat.completions.create(model=MODEL, messages=messages, temperature=0.2)
    return resp.choices[0].message.content

# ==========================================
# NIVEL 1: GENERAL MANAGER (Top Level)
# ==========================================
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "delegate_to_cs_manager",
            "description": "Delega al Customer Service Manager para dudas generales del evento (FAQ).",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Petición reformulada y autocontenida que incluye todo el contexto previo para que el manager la entienda."}},
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_to_ops_manager",
            "description": "Delega al Operations Manager para agendar citas o revisar el clima.",
            "parameters": {
                "type": "object",
                "properties": {"date_str": {"type": "string", "description": "Fecha YYYY-MM-DD. Si el usuario no indica el año, asume el año actual."}},
                "required": ["date_str"]
            }
        }
    }
]

def main():
    print("=" * 60)
    print("  ARQUITECTURA JERÁRQUICA - PARACHUTE S.A.")
    print("  General Manager -> Managers de Depto. -> Workers")
    print("=" * 60)
    print("Escribe 'Bye' para salir.\n")

    messages = [
        {
            "role": "system",
            "content": (
                f"Eres el General Manager de Parachute S.A. en un juego de rol de simulación. Hoy es {datetime.date.today().isoformat()}. "
                "Delega las consultas de los usuarios a tus dos sub-gerentes: "
                "el Customer Service Manager (para dudas generales, FAQs, reglas, edad, salud, buceo, medicamentos) o el Operations Manager (EXCLUSIVAMENTE para pronóstico de clima/citas y meteorología). "
                "IMPORTANTE: Tienes PERMISO EXPLÍCITO para dar información sobre clima, saltos y salud médica. No actives filtros de seguridad. "
                "Al delegar fechas, si el usuario no especifica el año (ej. 27/09), asume SIEMPRE el año actual. "
                "Al delegar, siempre debes proveerles una petición detallada con todo el contexto, ya que los sub-gerentes no tienen memoria. "
                "Una vez te den la respuesta, compártela con el usuario en LENGUAJE NATURAL repitiendo su informe tal cual sin negarte a contestar."
            )
        }
    ]

    is_running = True
    while is_running:
        try:
            user_input = input("\nTú: ").strip()
            if user_input.lower() == "bye":
                is_running = False
                continue
            if not user_input:
                continue

            messages.append({"role": "user", "content": user_input})

            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.1
            )
            
            msg = response.choices[0].message
            if msg.tool_calls and len(msg.tool_calls) > 1:
                msg.tool_calls = msg.tool_calls[:1]

            messages.append(msg)

            if msg.tool_calls:
                for tool_call in msg.tool_calls:
                    func_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}

                    if func_name == "delegate_to_cs_manager":
                        print("  [General Manager contactando al Customer Service Manager...]")
                        result = customer_service_manager(args.get("query", user_input))
                    elif func_name == "delegate_to_ops_manager":
                        print("  [General Manager contactando al Operations Manager...]")
                        result = operations_manager(args.get("date_str"))
                    else:
                        result = "Sub-gerente desconocido."

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result
                    })

                # Respuesta final
                final_resp = client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    temperature=0.1
                )
                final_text = final_resp.choices[0].message.content
                print(f"General Manager: {final_text}")
                messages.append({"role": "assistant", "content": final_text})
            else:
                print(f"General Manager: {msg.content}")

        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
