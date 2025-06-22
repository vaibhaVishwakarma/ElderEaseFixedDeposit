from dotenv import load_dotenv
import psycopg2
import requests
import json
import os
from supabase import create_client
load_dotenv()

class QueryResponder:
    def generate_embedding(self , text:str):
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
    
    def create_connection(self):
        connection = psycopg2.connect(
            host=os.getenv("db_host", "localhost"),
            port=int(os.getenv("db_port", "5432")),
            dbname=os.getenv("dbname", "pgvector"),
            user=os.getenv("db_user", "postgres"),
            password=os.getenv("db_password", "postres")
            )
        return connection , connection.cursor()

    def __init__(self , * , model_name = "qwen/qwen3-235b-a22b:free"):
        self.SUPABASE_URL , self.SUPABASE_KEY = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY")
        self.supabase = create_client(self.SUPABASE_URL,self.SUPABASE_KEY)
        self.OPENROUTER_API_URL , self.OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_URL") , os.getenv("OPENROUTER_API_KEY")
        self.MODEL_NAME = model_name

    def query_relevant_data(self, table_name , querry_text):
        connection , cursor = self.create_connection()
        querry_embedding = self.generate_embedding(querry_text)
        cursor.execute(
        f"""
            SELECT * FROM {table_name} 
            ORDER BY embedding <=> '{querry_embedding}'
            LIMIT 5;
        """)
        
        to_return = cursor.fetchall()
        
        cursor.close()
        connection.close()

        return to_return
    
    def resolve_query(self , query):
        context = self._context_fetcher(query)
        print(context[:500])

        return self.get_llm_response(query , context)


    def get_llm_response(self , query, context):
        response = requests.post(
        url="https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {self.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            

        },
        data=json.dumps({
            "top_k":3,
            "temprature":0.4,
            "model": self.MODEL_NAME,
            "messages": [
            {
                "role": "user",
                "content": [
                {
                    "type": "text",
                    "text": f"context: {context}"
                },
                {
                    "type": "system",
                    "text": """
                            ROLE : fixed deposite investment expert. studies the context. abides the following 5 rules.
                            RULE : 1. resolve query which are only generic, calculation based, refering to banks [HDFC, ICICI, SBI, KOTAK] only.
                                   2. give disclaimer with calculation.
                                   3. Make sure your numbers are correct and match the table given to the 2 decimal values, any ranges is not entertained unless asked.
                                   4. refrain any query apart from this.
                                   5. your first priority is any query regarding Fixed deposite rates.
                            WHOM YOU ARE TAKING TO : Elderly person with little to intermediate knowledge regards fixed deposite investment.
                            """
                },
                {
                    "type": "text",
                    "text": f"persons question: {query}"
                },
                           ]
                }
                ],
            
            })
        )
        
        if response.ok :
            return response.json()["choices"][0]["message"]["content"]
        print(response)
        return "Error Connecting."
    
    def _context_fetcher(self,query):
        try:

            total_context = ""

            banks = ["HDFC","ICICI" ,"SBI", "KOTAK"]
  
            #fetch Interest Rates
            for bank in banks:
                if bank in query.upper():
                    try:
                        response = self.supabase.table(bank).select("tenure_start,tenure_end,rate").execute()
                        data = response.data
                        for row in data:
                            row["number_of_days_in_tenure"] = row.pop("tenure_end")
                            row["interest_rate"] = row.pop("rate") 
                        total_context += f"""
                                        {bank} Fixed deposite rates are:
                                        --------------------------
                                        {data}
                                        __________________________
                                        """
                    except Exception as e:
                        continue
            #fetch Terms & Conditions
            for bank in banks:
                if bank in query.upper():
                    terms = "\\n".join([chunk[1] for chunk in self.query_relevant_data(bank,f"{query} regarding the bank {bank}")])
                    data = terms if len(terms) > 50 else f"No Terms & Conditions Available for the bank {bank}."
                    total_context+= f"""
                                    {bank} Terms And Conditions:
                                    ---------------------------
                                    {data}
                                    ---------------------------
                                    """
                        
            return total_context
        except Exception as e:
            return "No relevent data in DataBase"
        


if __name__=="__main__" :
    obj = QueryResponder()
    print(obj.resolve_query(query = "Help Me with ICICI bank fd rates"))               
    
        












    
