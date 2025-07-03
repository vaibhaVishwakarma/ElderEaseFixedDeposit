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
    
class LLMQuery(BaseModel):
    query: str
    context: str

@app.get("/")
async def greet():
    return {"Message":"Hi!"}

@app.post("/resolve-query")
async def resolve_query(request: QueryRequest):
    try:
        answer = query_resolver.resolve_query(request.text)
        return {
                "response": answer,
            }
    
    except Exception as e:
        return  {
                "response": "Error Resolving Query! Internal Server Error",
            }
@app.post("/query-llm")
async def get_query(request: LLMQuery):
    try:
        ans = query_resolver.get_llm_response(request.query , request.context)
        return {"response": ans}
    except Exception as e:
        return {"response": "Error fetching llm response"}
@app.post("/simple-request")
async def simple_request(request: QueryRequest):
    import requests
    r = requests.post('https://httpbin.org/post', data ={'key':'value'})
    print(r.json())
    return {"ok":"done"}

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=PORT, reload=True)
