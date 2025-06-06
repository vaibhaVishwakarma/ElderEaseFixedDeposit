import os 
from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import CharacterTextSplitter
from dotenv import load_dotenv
import psycopg2
import requests
import re

load_dotenv()
BASE = os.getenv("TEXT_EMBEDDING_FOLDER","RAG/DATA/CLEANED")
BANKS = os.getenv("BANKS",["HDFC","ICICI","SBI","KOTAK"])

def generate_embedding(text:str):
    url = "https://lamhieu-lightweight-embeddings.hf.space/v1/embeddings"
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json"
    }
    data = {
        "model": "snowflake-arctic-embed-l-v2.0",
        "input": text
    }

    response = requests.post(url, headers=headers, json=data)
    if response.ok:
        return response.json()["data"][0]["embedding"]
    else:
        raise Exception("No response")
    
def create_connection():
    connection = psycopg2.connect(
        host=os.getenv("db_host", "localhost"),
        port=int(os.getenv("db_port", "5432")),
        dbname=os.getenv("dbname", "pgvector"),
        user=os.getenv("db_user", "postgres"),
        password=os.getenv("db_password", "postres")
        )
    return connection , connection.cursor()

connection, cursor = create_connection()

def check_table_exists(table_name):
    table_name = table_name.strip().lower()
    cursor.execute("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables 
            WHERE table_name = %s
        );""", (table_name,))    
    return cursor.fetchone()[0]

def create_table(table_name,*,vector_size=1024):
    table_name = table_name.strip().lower()
    cursor.execute(
    f"""
        CREATE TABLE {table_name} (
            id bigint primary key generated always as identity,
            chunk text,
            embedding vector({vector_size})
        ) WITH (OIDS=FALSE);
    """
    )
    connection.commit()

def insert_text_data(table_name , chunk):
    embedding = generate_embedding(chunk)
    embedding_str = embedding.__repr__().lower()
    cursor.execute(
    f"""
        INSERT INTO {table_name}(chunk, embedding) 
        VALUES ('{chunk}', '{embedding_str}');
    """)
    connection.commit()


def drop_table(table_name):
    table_name = table_name.strip().lower()
    cursor.execute(f"drop table {table_name};")
    connection.commit()

def close_db():
    cursor.close()
    connection.close()

close_db()

def chunk_creater(filepath, * , chunk_size=900 , overlap = 100):
    loader = TextLoader(filepath)
    documents = loader.load()
    documents[0].page_content = re.sub(r'[^a-zA-Z0-9\\s+\-*%&.]' , " " , re.sub("\\n+|\\s+" , " ",documents[0].page_content))    
    text_splitter = CharacterTextSplitter(chunk_size=chunk_size, chunk_overlap= overlap)
    docs = text_splitter.split_documents(documents)
    print("Numer of chunks : ", len(docs))
    return docs

def chunk_inserter(table_name, docs):
    for doc in docs:
        insert_text_data(table_name,doc.page_content)

text_files = list(os.listdir(BASE))

for bank in BANKS:
    try:
        connection , cursor = create_connection()
        docs = chunk_creater(f"{BASE}/{bank}_output_cleaned.md")
        if check_table_exists(bank):
            drop_table(bank)

        create_table(bank)
        chunk_inserter(bank,docs)
        print(f"[DONE] --|-- uploading {bank} embeddings")
    except Exception as e:
        print(f"[ERROR] --|-- uploading {bank} embedding {e},{e.__traceback__.tb_lineno}")

    finally :
        close_db()






