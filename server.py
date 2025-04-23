from fastapi import FastAPI
from pydantic import BaseModel
import os
import subprocess
import threading
import time
import re
from supabase import create_client, Client
from dotenv import load_dotenv
from groq import Groq
from langchain.text_splitter import CharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_groq import ChatGroq
from langchain.chains import RetrievalQA
from fastapi.middleware.cors import CORSMiddleware
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Load environment variables
load_dotenv()



# Initialize Supabase and Groq clients
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
EMBEDDING_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
CHAT_MODEL = "llama3-8b-8192"
HOURS = 12 # can be decreased if api is purchased, for free this frequency is adequate

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
client = Groq(api_key=GROQ_API_KEY)

# Initialize Groq API and setup LLM
llm = ChatGroq(model='llama3-70b-8192', api_key=GROQ_API_KEY)

# List of known banks
BANKS = ["HDFC", "ICICI", "SBI", "KOTAK"]

# Extract Tenure from query
def extract_tenure(query):
    """Extracts tenure (in days) from user query."""
    tenure_pattern = re.compile(r'(\d+)\s*(day|days|month|months|year|years)', re.IGNORECASE)
    tenure_match = tenure_pattern.search(query)

    if tenure_match:
        tenure_value, unit = tenure_match.groups()
        tenure_value = int(tenure_value)
        if unit.lower() in ["day", "days"]:
            return (tenure_value, tenure_value)
        elif unit.lower() in ["month", "months"]:
            return (tenure_value * 30, tenure_value * 30)
        elif unit.lower() in ["year", "years"]:
            return (tenure_value * 365, tenure_value * 365)

    return None

# Extract minimum FD rate from query
def extract_min_rate(query):
    """Extracts minimum FD rate from user query."""
    rate_pattern = re.compile(r'(?:greater than|at least|>=)\s*([\d.]+)', re.IGNORECASE)
    rate_match = rate_pattern.search(query)
    return float(rate_match.group(1)) if rate_match else None

# Fetch FD data from Supabase for a specific bank
def fetch_fd_data(bank, tenure_days=None, min_rate=None):
    """Fetch FD data for a specific bank with optional filters."""
    try:
        response = supabase.table(bank).select("*").execute()
        data = response.data
        
        if not data:
            return None

        # Apply tenure filter
        if tenure_days:
            data = [row for row in data if row["tenure_start"] <= tenure_days[0] <= row["tenure_end"] or row["tenure_start"] <= tenure_days[1] <= row["tenure_end"]]

        # Apply rate filter
        if min_rate:
            data = [row for row in data if float(row["rate"]) >= min_rate]

        return data if data else None
    except Exception as e:
        print(f"⚠️ Error fetching FD data from {bank}: {e}")
        return None

# Generate natural language response based on FD data
def generate_natural_response(user_query, data, bank_name=None):
    """Uses Groq API to generate a natural response based on the raw data."""
    if not data:
        return "❌ Sorry, no matching FDs found."

    # Format data for the response
    if isinstance(data, list):  # Single bank case (list)
        data_str = "\n".join([ 
            f"{bank_name}: {row['rate']}% for tenure {row['tenure_start']} to {row['tenure_end']} days" 
            for row in data
        ])
    else:  # Multiple banks case (dictionary)
        data_str = "\n".join([
            f"{bank}: {row['rate']}% for tenure {row['tenure_start']} to {row['tenure_end']} days" 
            for bank, fd_list in data.items()
            for row in fd_list
        ])

    # Create prompt for Groq API
    prompt = f"Based on the following fixed deposit data, answer the user query in a natural and helpful way. The user query is: '{user_query}'. The data is: {data_str}."

    try:
        chat_completion = client.chat.completions.create(
            messages=[ 
                {
                    "role": "user", 
                    "content": prompt,
                }
            ], 
            model=CHAT_MODEL, 
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        return f"⚠️ Error generating response from Groq API: {e}"

# Load and split text for non-FD queries
def load_and_split_text(chunk_size=1000, chunk_overlap=200):
    all_docs = []  

    for bank in BANKS:
        filename = f"RAG/DATA/CLEANED/{bank}_output_cleaned.md"
        with open(filename, 'r',encoding='utf-8') as file:
            docs = file.read()
        
        # Create the text splitter
        text_splitter = CharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        
        # Split the document into chunks (if needed)
        split_docs = text_splitter.create_documents([docs])  # Split the document into chunks
        
        # Append the split documents to the all_docs list
        all_docs.extend(split_docs)
    
    return all_docs 

def update_context():
    policies = load_and_split_text()
    # Embed and store chunks in a vector store
    embeddings = HuggingFaceEmbeddings(model_name = EMBEDDING_MODEL_NAME )
    db = Chroma.from_documents(policies, embeddings)
    retriever = db.as_retriever()
    # Create a question-answering chain with sources
    return RetrievalQA.from_chain_type(llm=llm, chain_type="stuff", retriever=retriever)

qa = update_context()

# Handle user queries
def chat_with_ai(user_query):
    """Processes user queries dynamically and fetches relevant FD data."""
    if user_query is None:
        return "❌ Sorry, I could not understand your query. Please try again."

    lower_query = user_query.lower()

    # Check if the query is related to FDs
    fd_keywords = ["fd", "fixed deposit", "interest rate", "tenure", "maturity", "best bank", "bank", "fd rate", "highest FD"]
    is_fd_related = any(keyword in lower_query for keyword in fd_keywords)

    if not is_fd_related:
        # If not FD-related, use QA retrieval
        return qa.run(user_query)  # Here is where qa.run() is utilized!

    # Extract key details from query
    tenure_days = extract_tenure(user_query)
    min_rate = extract_min_rate(user_query)

    # Identify bank (if mentioned)
    bank_match = re.search(r'\b(' + "|".join(BANKS) + r')\b', lower_query, re.IGNORECASE)
    bank_name = bank_match.group(1).upper() if bank_match else None

    # Fetch FD Data
    if bank_name:
        data = fetch_fd_data(bank_name, tenure_days, min_rate)
        if data is None:
            return f"❌ Sorry, I couldn't find FD rates for {bank_name} that match your criteria."
    else:
        data = fetch_fd_data("HDFC", tenure_days, min_rate)  # Example: Fetch data from HDFC, can be expanded to all banks
        if not data:
            return "❌ Sorry, no matching FDs found."
    
    # Generate response
    return generate_natural_response(user_query, data, bank_name)



def regular_updater():
    # updates the data every 12 hours || HOURS specifed 

    counter = 1
    while True:
        print("updater started at -> ", time.strftime("%H:%M:%S",time.localtime()))
        time.sleep(60*60*HOURS)
        try: 
            run_subprocess("runner.py" , "RAG")
        except Exception as e:
            print(e)

        try: 
            run_subprocess("updater.py" , "updater")
        except Exception as e:
            print(e)
        try:
            update_context()
        except Exception as e:
            print(e)
        print(f"updater finished {counter} rounds")
        count+=1

thread = threading.Thread(target=regular_updater , daemon=True) # using deamon makes it run simultaneouly in background || without deamon it will run along the main process
# If daemon=False (default), Python waits for that thread to finish before exiting.
# If daemon=True, Python does NOT wait for that thread. It will be killed when the main thread and other non-daemon threads finish.
 

thread.start()

# FastAPI setup (if needed for API integration)
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # List of allowed origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)

# Define model for POST requests
class Item(BaseModel):
    text: str

@app.get("/")
async def root():
    return {"message": "Hello, world!"}

@app.post("/")
async def create_item(item: Item):
    return {"message": chat_with_ai(item.text)}


def run_subprocess(filename , cwd):
    # This will run the process in a subprocess
    subprocess.run(["python", filename] , cwd = cwd)


thread.join()

print("EXITING PROGRAM...")




# Example usage
# if __name__ == "__main__":
#     print(chat_with_ai("What is the best FD rate offered by HDFC?"))
#     print(chat_with_ai("Tell me about the terms and conditions of SBI"))
