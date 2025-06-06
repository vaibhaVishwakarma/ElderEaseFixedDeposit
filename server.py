from typing import Optional
from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from LLM_query_resolver import QueryResponder
import os
import uvicorn
from dotenv import load_dotenv
load_dotenv()

MODEL_NAME =  os.getenv("MODEL_NAME", "qwen/qwen3-32b:free")
PORT = int(os.getenv("PORT",7711))

query_resolver = QueryResponder()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    text: str
    session_id: Optional[str] = None

@app.get("/")
async def greet():
    return {"Message":"Hi!"}

@app.post("/resolve-query")
async def resolve_query(request: QueryRequest):
    try:
        answer = query_resolver.resolve_query(request.text)
        return {
                "response": answer,
                "session_id": request.session_id
            }
    
    except Exception as e:
        return  {
                "response": "Error Resolvign Query! Internal Server Error",
                "session_id": request.session_id
            }



if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=PORT, reload=True)
