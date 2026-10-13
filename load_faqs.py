import os
import re
import json
import sys
import psycopg2
from psycopg2.extras import Json
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "parachute_faqs")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgrespassword")
CORPUS_FILE = "Corpus_FAQs_Parachute_SA_2026.txt"
MODEL_NAME = "all-MiniLM-L6-v2"

def get_db_connection():
    """Establece la conexión con PostgreSQL y registra pgvector."""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        return conn
    except Exception as e:
        print(f"Error al conectar a PostgreSQL: {e}")
        print("Asegúrate de que el contenedor de Docker esté corriendo con 'docker compose up -d'")
        sys.exit(1)

def setup_database(conn):
    """Crea la extensión pgvector y la tabla de FAQs si no existen."""
    with conn.cursor() as cur:
        # Habilitar extensión pgvector
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        
        # Crear tabla de FAQs
        cur.execute("""
            CREATE TABLE IF NOT EXISTS faqs (
                id VARCHAR(50) PRIMARY KEY,
                category VARCHAR(150),
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                metadata JSONB,
                search_text TEXT,
                embedding vector(384)
            );
        """)
        
        # Crear índice HNSW para búsquedas por similitud coseno
        cur.execute("""
            CREATE INDEX IF NOT EXISTS faqs_embedding_hnsw_idx 
            ON faqs USING hnsw (embedding vector_cosine_ops);
        """)
    conn.commit()
    # Registrar soporte de pgvector en la conexión
    register_vector(conn)
    print("Base de datos configurada con extensión pgvector y tabla 'faqs'.")

def parse_corpus(filepath):
    """Lee y parsea las preguntas frecuentes del archivo de corpus."""
    if not os.path.exists(filepath):
        print(f"Archivo no encontrado: {filepath}")
        sys.exit(1)
        
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    pattern = re.compile(
        r'ID:\s*(FAQ-\d+)\s*\n'
        r'CATEGORÍA:\s*(.*?)\s*\n'
        r'PREGUNTA:\s*(.*?)\s*\n'
        r'RESPUESTA:\s*(.*?)\s*\n'
        r'METADATA:\s*({.*?})\s*\n'
        r'-{30,}',
        re.DOTALL
    )

    matches = pattern.findall(content)
    faqs = []
    for match in matches:
        faq_id, category, question, answer, metadata_raw = match
        try:
            metadata = json.loads(metadata_raw)
        except Exception:
            metadata = {}

        search_text = f"Categoría: {category.strip()}. Pregunta: {question.strip()} Respuesta: {answer.strip()}"
        faqs.append({
            "id": faq_id.strip(),
            "category": category.strip(),
            "question": question.strip(),
            "answer": answer.strip(),
            "metadata": metadata,
            "search_text": search_text
        })

    print(f"Corpus parseado: {len(faqs)} preguntas encontradas.")
    return faqs

def main():
    print("=" * 60)
    print("  CARGADOR DE EMBEDDINGS - PARACHUTE S.A.")
    print("=" * 60)

    # 1. Parsear archivo de texto
    faqs = parse_corpus(CORPUS_FILE)
    if not faqs:
        print("No se encontraron FAQs para cargar.")
        return

    # 2. Conectar a la base de datos
    print(f"Conectando a PostgreSQL ({DB_HOST}:{DB_PORT}/{DB_NAME})...")
    conn = get_db_connection()
    setup_database(conn)

    # 3. Cargar modelo de embeddings
    print(f"Cargando modelo de embeddings '{MODEL_NAME}'...")
    try:
        embed_model = SentenceTransformer(MODEL_NAME, local_files_only=True)
    except Exception:
        embed_model = SentenceTransformer(MODEL_NAME)

    # 4. Generar embeddings
    print("Generando embeddings para las FAQs...")
    texts_to_embed = [faq["search_text"] for faq in faqs]
    embeddings = embed_model.encode(texts_to_embed, show_progress_bar=True, batch_size=32)

    # 5. Insertar en PostgreSQL
    print("Guardando registros y vectores en PostgreSQL...")
    with conn.cursor() as cur:
        for faq, embedding in zip(faqs, embeddings):
            cur.execute("""
                INSERT INTO faqs (id, category, question, answer, metadata, search_text, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    category = EXCLUDED.category,
                    question = EXCLUDED.question,
                    answer = EXCLUDED.answer,
                    metadata = EXCLUDED.metadata,
                    search_text = EXCLUDED.search_text,
                    embedding = EXCLUDED.embedding;
            """, (
                faq["id"],
                faq["category"],
                faq["question"],
                faq["answer"],
                Json(faq["metadata"]),
                faq["search_text"],
                embedding
            ))
    conn.commit()

    # 6. Verificar carga
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM faqs;")
        count = cur.fetchone()[0]
        print(f"Carga completada con éxito. Total de FAQs en la base de datos: {count}")

    conn.close()
    print("=" * 60)

if __name__ == "__main__":
    main()
