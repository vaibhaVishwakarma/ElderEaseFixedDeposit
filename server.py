from fastapi import FastAPI
from pydantic import BaseModel
import os
import subprocess
import threading
import time
import re
import json
import logging
from uuid import uuid4
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from supabase import create_client, Client
from dotenv import load_dotenv
from groq import Groq
from fastapi.middleware.cors import CORSMiddleware

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize clients
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Configuration
BANK_ALIASES = {
    "HDFC": ["hdfc", "hdfc bank"],
    "ICICI": ["icici", "icici bank"],
    "SBI": ["sbi", "state bank", "state bank of india"],
    "KOTAK": ["kotak", "kotak mahindra", "kotak bank"]
}
FD_KEYPHRASES = [
    "fixed deposit", "fd rate", "interest rate", "deposit rate",
    "savings rate", "investment return", "yield", "annual percentage yield",
    "apy", "term deposit", "time deposit"
]

class MemoryManager:
    @staticmethod
    def create_session() -> str:
        session_id = str(uuid4())
        try:
            supabase.table("chat_sessions").insert({
                "session_id": session_id,
                "history": []
            }).execute()
            return session_id
        except Exception as e:
            logger.error(f"Session creation failed: {e}")
            return session_id

    @staticmethod
    def update_history(session_id: str, query: str, response: str) -> None:
        """Fetch, append, and update the chat history array in Supabase."""
        try:
            # Fetch current history
            result = supabase.table("chat_sessions").select("history").eq("session_id", session_id).execute()
            history = result.data[0]["history"] if result.data else []
            # Append new turn
            history.append({
                "timestamp": datetime.utcnow().isoformat(),
                "query": query,
                "response": response
            })
            # Update the row
            supabase.table("chat_sessions").update({
                "history": history,
                "last_accessed": datetime.utcnow().isoformat()
            }).eq("session_id", session_id).execute()
        except Exception as e:
            logger.error(f"History update failed: {e}")

    @staticmethod
    def get_history(session_id: str, max_items=5) -> List[dict]:
        try:
            result = supabase.table("chat_sessions").select("history").eq("session_id", session_id).execute()
            if not result.data:
                return []
            history = result.data[0].get("history", [])
            # Return last N items, oldest first
            return history[-max_items:]
        except Exception as e:
            logger.error(f"History retrieval failed: {e}")
            return []

class QueryProcessor:
    @staticmethod
    def classify_query(query: str) -> bool:
        prompt = f"""Classify if this query is related to bank interest rates:
        Query: {query}
        Respond ONLY with 'YES' or 'NO'"""
        try:
            response = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama3-8b-8192",
                temperature=0.0
            )
            return "YES" in response.choices[0].message.content.strip().upper()
        except:
            return any(phrase in query.lower() for phrase in FD_KEYPHRASES)

    @staticmethod
    def detect_bank(query: str) -> Optional[str]:
        query_lower = query.lower()
        for bank, aliases in BANK_ALIASES.items():
            if any(alias in query_lower for alias in aliases):
                return bank
        return None

    @staticmethod
    def parse_tenure(query: str) -> Optional[Tuple[int, int]]:
        patterns = [
            r"(\d+)\s*(day|week|month|year)s?",
            r"(\d+)\s*-\s*(\d+)\s*(day|week|month|year)s?",
            r"(?:for|of|over)\s*(\d+)\s*(?:to|and)\s*(\d+)\s*(day|week|month|year)s?"
        ]
        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) == 2:
                    value, unit = groups
                    days = QueryProcessor._to_days(int(value), unit.lower())
                    return (days, days)
                elif len(groups) == 3:
                    start, end, unit = groups
                    return (
                        QueryProcessor._to_days(int(start), unit.lower()),
                        QueryProcessor._to_days(int(end), unit.lower())
                    )
        return None

    @staticmethod
    def _to_days(value: int, unit: str) -> int:
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
            logger.error(f"Data fetch error for {bank}: {e}")
            return []

class ResponseGenerator:
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
        prompt = f"""Previous conversation:
{context}

New query: {query}

Bank data:
{structured_data}

Provide:
- Clear answer using data
- Contextual follow-ups
- Natural language format
- Rate change disclaimer"""
        try:
            response = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama3-70b-8192",
                temperature=0.3
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Response generation failed: {e}")
            return "Here's what I found:\n" + structured_data

def process_query(query: str, session_id: str) -> str:
    if not QueryProcessor.classify_query(query):
        return "I specialize in bank interest rates. How can I assist you with FD rates?"
    bank = QueryProcessor.detect_bank(query)
    tenure = QueryProcessor.parse_tenure(query)
    if bank:
        data = {bank: BankDataHandler.fetch_rates(bank, tenure)}
    else:
        data = {b: BankDataHandler.fetch_rates(b, tenure) for b in BANK_ALIASES}
    return ResponseGenerator.generate(query, data, session_id)

# FastAPI setup
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    text: str
    session_id: Optional[str] = None

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
        return {"error": "Processing failed"}, 500
