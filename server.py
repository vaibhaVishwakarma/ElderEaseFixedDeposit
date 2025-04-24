from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import re
import logging
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple
from supabase import create_client, Client
from dotenv import load_dotenv
import subprocess
import uvicorn
import sys
from groq import Groq
from pathlib import Path
import markdown

# APScheduler imports
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR  # NEW IMPORT

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize clients
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Configuration
BANK_CONFIG = {
    "HDFC": {"aliases": ["hdfc", "hdfc bank"]},
    "ICICI": {"aliases": ["icici", "icici bank"]},
    "SBI": {"aliases": ["sbi", "state bank", "state bank of india"]},
    "KOTAK": {"aliases": ["kotak", "kotak mahindra", "kotak bank"]}
}

FD_KEYPHRASES = [
    "fixed deposit", "fd rate", "interest rate", "deposit rate",
    "savings rate", "investment return", "yield", "annual percentage yield",
    "apy", "term deposit", "time deposit"
]

TERMS_KEYWORDS = [
    "terms and conditions", "rules", "regulation", "policy", "policies",
    "eligibility", "documentation", "requirement", "criteria"
]

class QueryRequest(BaseModel):
    text: str
    session_id: Optional[str] = None

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Periodic Script Runners ---
def run_runner_script():
    try:
        logger.info("Starting runner.py in background...")
        subprocess.Popen(
            [sys.executable, "runner.py"],
            cwd="RAG",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT
        )
    except Exception as e:
        logger.error(f"runner.py error: {e}")

def run_updater_script():
    try:
        logger.info("Starting updater.py in background...")
        subprocess.Popen(
            [sys.executable, "updater.py"],
            cwd="updater",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT
        )
    except Exception as e:
        logger.error(f"updater.py error: {e}")

# NEW SCHEDULER LISTENER FUNCTION
def scheduler_listener(event):
    """Logs scheduler job execution events"""
    if event.exception:
        logger.error(f"Job {event.job_id} FAILED with error: {event.exception}")
    else:
        logger.info(f"Job {event.job_id} EXECUTED successfully at {event.scheduled_run_time}")

scheduler = BackgroundScheduler()

@app.on_event("startup")
def start_scheduler():
    # Add the job listener
    scheduler.add_listener(
        scheduler_listener,
        EVENT_JOB_EXECUTED | EVENT_JOB_ERROR
    )
    
    # Add jobs
    scheduler.add_job(
        run_runner_script,
        'interval',
        minutes=30,
        id='runner_job',
        next_run_time=datetime.now(),
        max_instances=2
    )
    scheduler.add_job(
        run_updater_script,
        'interval',
        minutes=30,
        id='updater_job',
        next_run_time=datetime.now(),
        max_instances=2
    )
    
    scheduler.start()
    
    # Log scheduled jobs for verification
    logger.info("Scheduler started with jobs:")
    for job in scheduler.get_jobs():
        logger.info(f"• Job ID: {job.id} | Next run: {job.next_run_time}")

@app.on_event("shutdown")
def shutdown_scheduler():
    scheduler.shutdown()
    logger.info("APScheduler shut down.")

# --- Chatbot Logic (unchanged) ---
class MemoryManager:
    @staticmethod
    def create_session() -> str:
        session_id = str(uuid4())
        supabase.table("chat_sessions").insert({
            "session_id": session_id,
            "history": []
        }).execute()
        return session_id

    @staticmethod
    def update_history(session_id: str, query: str, response: str):
        result = supabase.table("chat_sessions").select("history").eq("session_id", session_id).execute()
        history = result.data[0]["history"] if result.data else []
        history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query": query,
            "response": response
        })
        supabase.table("chat_sessions").update({"history": history}).eq("session_id", session_id).execute()

    @staticmethod
    def get_history(session_id: str, max_items=5) -> List[dict]:
        result = supabase.table("chat_sessions").select("history").eq("session_id", session_id).execute()
        return result.data[0].get("history", [])[-max_items:] if result.data else []

class TermsLoader:
    @staticmethod
    def load_terms(bank: str) -> str:
        file_path = Path(f"RAG/DATA/CLEANED/{bank.upper()}_output_cleaned.md")
        if not file_path.exists():
            return "Terms and conditions are currently unavailable for this bank."
        try:
            with file_path.open(encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error loading terms for {bank}: {e}")
            return "Could not retrieve terms at this time. Please try again later."

class QueryProcessor:
    @staticmethod
    def is_terms_query(query: str) -> bool:
        return any(keyword in query.lower() for keyword in TERMS_KEYWORDS)

    @staticmethod
    def classify_query(query: str) -> bool:
        prompt = f"""Classify if this query relates to bank interest rates:
        Query: {query}
        Respond ONLY with 'YES' or 'NO'"""
        
        try:
            response = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama3-8b-8192",
                temperature=0.0
            )
            return "YES" in response.choices[0].message.content.strip().upper()
        except Exception as e:
            logger.error(f"Classification error: {e}")
            return any(phrase in query.lower() for phrase in FD_KEYPHRASES)

    @staticmethod
    def detect_bank(query: str) -> Optional[str]:
        query_lower = query.lower()
        for bank, config in BANK_CONFIG.items():
            if any(alias in query_lower for alias in config["aliases"]):
                return bank
        return None

    @staticmethod
    def parse_tenure(query: str) -> Optional[Tuple[int, int]]:
        patterns = [
            r"(\d+)\s*(day|week|month|year)s?",
            r"(\d+)\s*-\s*(\d+)\s*(day|week|month|year)s?"
        ]
        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) >= 2:
                    value = int(groups[0])
                    unit = groups[1].lower()
                    return (QueryProcessor._to_days(value, unit), QueryProcessor._to_days(value, unit))
        return None

    @staticmethod
    def _to_days(value: int, unit: str) -> int:
        unit = unit.lower()
        if "week" in unit: return value * 7
        if "month" in unit: return value * 30
        if "year" in unit: return value * 365
        return value

class BankDataHandler:
    @staticmethod
    def fetch_rates(bank: str, tenure: Optional[Tuple[int, int]] = None) -> List[dict]:
        try:
            query = supabase.table(bank).select("*")
            if tenure:
                query = query.lte("tenure_start", tenure[1]).gte("tenure_end", tenure[0])
            return query.execute().data
        except Exception as e:
            logger.error(f"Data fetch error: {e}")
            return []

class ResponseGenerator:
    @staticmethod
    def generate_terms_response(query: str, bank: str) -> str:
        if not bank:
            return "Please specify the bank for terms and conditions."
        terms_content = TermsLoader.load_terms(bank)
        return f"**{bank} Terms and Conditions**\n\n{terms_content}"

    @staticmethod
    def generate(query: str, data: dict, session_id: str) -> str:
        history = MemoryManager.get_history(session_id)
        context = "\n".join([f"User: {h['query']}\nAssistant: {h['response']}" for h in history])
        
        structured_data = "\n".join(
            f"{bank} Rates:\n" + "\n".join(
                f"- {row['rate']}% ({row['tenure_start']}-{row['tenure_end']} days)"
                for row in rows
            )
            for bank, rows in data.items() if rows
        )
        
        prompt = f"""Conversation Context:
{context}

New Query: {query}

Bank Data:
{structured_data}

Provide detailed, accurate response with rate disclaimers."""
        
        try:
            response = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama3-70b-8192",
                temperature=0.3
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Response generation failed: {e}")
            return "Current rates:\n" + structured_data

def process_query(query: str, session_id: str) -> str:
    if QueryProcessor.is_terms_query(query):
        bank = QueryProcessor.detect_bank(query)
        return ResponseGenerator.generate_terms_response(query, bank)
    
    if not QueryProcessor.classify_query(query):
        return "I specialize in bank interest rates. How can I assist with FD rates?"
    
    bank = QueryProcessor.detect_bank(query)
    tenure = QueryProcessor.parse_tenure(query)
    
    data = {bank: BankDataHandler.fetch_rates(bank, tenure)} if bank else {
        b: BankDataHandler.fetch_rates(b, tenure) for b in BANK_CONFIG
    }
    
    return ResponseGenerator.generate(query, data, session_id)

@app.post("/query")
async def handle_query(request: QueryRequest):
    try:
        session_id = request.session_id or MemoryManager.create_session()
        response = process_query(request.text, session_id)
        MemoryManager.update_history(session_id, request.text, response)
        return {
            "response": response,
            "session_id": session_id
        }
    except Exception as e:
        logger.error(f"API error: {e}")
        return {"error": str(e)}, 500

@app.get("/")
async def serve_ui():
    return FileResponse("static/index.html")

app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=11001, log_level="info")
