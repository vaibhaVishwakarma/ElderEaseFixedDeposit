from fastapi import FastAPI
from pydantic import BaseModel
import os
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
            model="llama3-8b-8192", 
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        return f"⚠️ Error generating response from Groq API: {e}"

# Load and split text for non-FD queries
def load_and_split_text(filename='mytext.txt', chunk_size=1000, chunk_overlap=200):
    with open(filename, 'r') as file:
        docs = file.read()
    text_splitter = CharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    docs = text_splitter.create_documents([docs])  # No need to split documents again
    return docs

texts = load_and_split_text('mytext.txt')

# Embed and store chunks in a vector store
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/paraphrase-multilingual-mpnet-base-v2")
db = Chroma.from_documents(texts, embeddings)
retriever = db.as_retriever()

# Create a question-answering chain with sources
qa = RetrievalQA.from_chain_type(llm=llm, chain_type="stuff", retriever=retriever)

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

@app.post("/")
async def create_item(item: Item):
    return {"message": chat_with_ai(item.text)}

# Example usage
# if __name__ == "__main__":
#     print(chat_with_ai("What is the best FD rate offered by HDFC?"))
#     print(chat_with_ai("Tell me about the terms and conditions of SBI"))
