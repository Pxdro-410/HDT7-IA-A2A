import os
import json
import datetime
import httpx
import psycopg2
from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer

load_dotenv()

# Configuración de base de datos PostgreSQL
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "parachute_faqs")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgrespassword")
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

print(f"[Services] Cargando modelo local de embeddings '{EMBEDDING_MODEL_NAME}'...")
try:
    embed_model = SentenceTransformer(EMBEDDING_MODEL_NAME, local_files_only=True)
except Exception:
    embed_model = SentenceTransformer(EMBEDDING_MODEL_NAME)

def get_db_connection():
    """Establece conexión con la base de datos PostgreSQL."""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        register_vector(conn)
        return conn
    except Exception as e:
        print(f"Error conectando a PostgreSQL: {e}")
        return None

def search_knowledge_base(query: str, limit: int = 3) -> str:
    """
    Consulta la base de conocimientos vectorial de Parachute S.A.
    """
    conn = get_db_connection()
    if not conn:
        return "Error: No se pudo conectar a la base de datos de conocimientos."

    try:
        query_embedding = embed_model.encode(query)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, category, question, answer, 1 - (embedding <=> %s) AS similarity
                FROM faqs
                ORDER BY embedding <=> %s
                LIMIT %s;
            """, (query_embedding, query_embedding, limit))
            results = cur.fetchall()

        conn.close()

        if not results:
            return "No se encontraron registros relevantes en la base de conocimientos."

        formatted_results = []
        for r in results:
            faq_id, category, question, answer, similarity = r
            formatted_results.append(
                f"- [Ficha: {faq_id}] (Categoría: {category}, Similitud: {similarity:.2f})\n"
                f"  Pregunta: {question}\n"
                f"  Respuesta oficial: {answer}"
            )

        return "\n\n".join(formatted_results)
    except Exception as e:
        if conn:
            conn.close()
        return f"Error ejecutando búsqueda vectorial: {e}"

def check_weather_for_skydive(date_str: str) -> str:
    """
    Verifica si el clima es adecuado para saltar en paracaídas en la fecha dada.
    date_str debe estar en formato 'YYYY-MM-DD'.
    """
    try:
        target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        today = datetime.date.today()
        delta_days = (target_date - today).days

        if delta_days < 0:
            return f"Error: La fecha proporcionada ({date_str}) ya pasó. Por favor ingresa una fecha futura o la de hoy."
        if delta_days > 16:
            return f"Error: No se puede predecir el clima para fechas posteriores a 16 días. Solicitaste {date_str}, lo cual supera el límite."

        # Llamar a Open-Meteo
        lat, lon = 14.013722, -90.771611
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&daily=temperature_2m_max,wind_speed_10m_max,wind_gusts_10m_max,precipitation_sum,precipitation_hours"
            f"&timezone=America/Guatemala"
            f"&start_date={date_str}&end_date={date_str}"
        )
        
        # Alternativamente, para usar "hourly" y calcular el máximo durante horas de luz (e.g. 8am-5pm),
        # pero usar daily simplifica y se adhiere a los valores máximos del día.
        
        # Como Open-Meteo current no da predicciones para fechas específicas de manera fácil, 
        # y daily agrupa, pediremos datos horarios (hourly) y evaluaremos si en algún punto de luz (8 a 17) es apto.
        url_hourly = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&hourly=temperature_2m,wind_speed_10m,wind_gusts_10m,precipitation,cloud_cover"
            f"&timezone=America/Guatemala"
            f"&start_date={date_str}&end_date={date_str}"
        )

        response = httpx.get(url_hourly)
        response.raise_for_status()
        data = response.json()

        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        
        if not times:
            return "No se pudieron obtener datos del clima para esta fecha."

        # Analizamos las horas de operación: de 08:00 a 17:00
        # times formato: "2023-10-14T00:00"
        
        valid_indices = []
        for i, t_str in enumerate(times):
            hour = int(t_str.split("T")[1].split(":")[0])
            if 8 <= hour <= 17:
                valid_indices.append(i)
                
        if not valid_indices:
            return "No se encontraron horas de luz operativas para evaluar."

        # Extraemos promedios o máximos para el periodo operativo
        wind_speeds = [hourly["wind_speed_10m"][i] for i in valid_indices]
        wind_gusts = [hourly["wind_gusts_10m"][i] for i in valid_indices]
        precipitations = [hourly["precipitation"][i] for i in valid_indices]
        cloud_covers = [hourly["cloud_cover"][i] for i in valid_indices]
        temperatures = [hourly["temperature_2m"][i] for i in valid_indices]

        max_wind_speed = max(wind_speeds)
        max_wind_gust = max(wind_gusts)
        max_precip = max(precipitations)
        avg_cloud_cover = sum(cloud_covers) / len(cloud_covers)
        avg_temp = sum(temperatures) / len(temperatures)

        # Reglas
        # Velocidad viento
        if max_wind_speed > 28:
            wind_status = "NO APTO / NO RECOMENDADO (Difícil de controlar)"
            safe_to_jump = False
        elif 20 <= max_wind_speed <= 28:
            wind_status = "Marginal (Solo tándem experimentado)"
            safe_to_jump = True
        else:
            wind_status = "Ideal"
            safe_to_jump = True

        # Ráfagas
        if max_wind_gust > 35:
            gust_status = "NO APTO / NO RECOMENDADO"
            safe_to_jump = False
        else:
            gust_status = "Seguro"

        # Precipitación
        if max_precip > 0.0:
            precip_status = "NO APTO (Presencia de lluvia)"
            safe_to_jump = False
        else:
            precip_status = "Seguro (Sin lluvia)"

        # Nubes
        if avg_cloud_cover > 75:
            cloud_status = "NO APTO (Nubosidad alta)"
            safe_to_jump = False
        elif 30 <= avg_cloud_cover <= 75:
            cloud_status = "Marginal (Nubes dispersas)"
        else:
            cloud_status = "Ideal (Visibilidad clara)"

        conclusion = "El clima ESTÁ PERMITIDO (condiciones ideales o marginales)." if safe_to_jump else "El clima NO ES RECOMENDADO (condiciones adversas)."

        report = (
            f"=== REPORTE METEOROLÓGICO PARACHUTE S.A. ===\n"
            f"Fecha: {date_str} (Horario operativo 08:00 - 17:00)\n"
            f"Velocidad de viento: {max_wind_speed:.1f} km/h -> {wind_status}\n"
            f"Ráfagas máximas: {max_wind_gust:.1f} km/h -> {gust_status}\n"
            f"Precipitación máxima: {max_precip:.1f} mm -> {precip_status}\n"
            f"Visibilidad (Nubes): {avg_cloud_cover:.1f}% -> {cloud_status}\n"
            f"Temperatura promedio: {avg_temp:.1f} °C\n\n"
            f"CONCLUSIÓN: {conclusion}"
        )
        return report

    except Exception as e:
        return f"Error consultando el clima: {str(e)}"
