from crewai_tools import ScrapeWebsiteTool
import requests 
import json
import time 
import os 
from dotenv import load_dotenv
import markdown as md
from supabase import create_client, Client
import os
from dotenv import load_dotenv

load_dotenv()
# Initialize Supabase Client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Define storage details
BUCKET_NAME = "pdtracker-bucket"





load_dotenv()

MINUTES = 60

banks = [
    "HDFC",
    "ICICI",
    "SBI",
    "KOTAK"
]

def get_terms_raw():

    def get_md(url):
        tool = ScrapeWebsiteTool()
        tool = ScrapeWebsiteTool(website_url=url)
        try: 
            res = tool.run()
        except Exception as e:
            return ""
        return res

    CUSTOM_SEARCH_API_KEY = os.getenv("CUSTOM_SEARCH_API_KEY")
    CUSTOM_SEARCH_ENGINE_ID = os.getenv('CUSTOM_SEARCH_ENGINE_ID')
    def get_terms_links(bank_name):
        search_query = f"{bank_name} fixed Deposites terms and conditions and penalities"
        url = f"https://www.googleapis.com/customsearch/v1?q={search_query}&key={CUSTOM_SEARCH_API_KEY}&cx={CUSTOM_SEARCH_ENGINE_ID}"

        response = requests.get(url)
        data = response.json()

        links = []
        for item in data.get("items", []):
            links.append(item["link"])
        return links

    for bank in banks:
        with open(f"DATA/RAW/{bank}_output.md", "w",encoding="utf-8") as file: 
            for link in get_terms_links(bank):
                file.write(md.markdown(get_md(link)))


OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_API_URL = os.getenv("OPENROUTER_API_URL")

def read_markdown_file(filename):
    with open(filename, "r", encoding="utf-8") as file:
        return file.read()

def clean_text_with_llm(text):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "google/gemini-2.0-flash-lite-preview-02-05:free",  # Use a suitable model from OpenRouter
        "messages": [
            {"role": "system", "content": """You are textual garbage removal agent, you must protect the terms and conditions 
             passed to you, make sure no modification is made and mustremove any stand alone, un-contextual words. 
             you may also encounter some special characters such as emoji, letters other than alphabets , digits , brackets or spaces """},

            {"role": "user", "content": f"Clean this text and remove garbage values:\n{text}"}
        ],
        "temperature": 0.2
    }
    
    response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload)
    
    if response.status_code == 200:
        result = response.json()
        print(result)
        try:
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            print("Error:", response.status_code, response.text)
            return None
    else:
        print("Error:", response.status_code, response.text)
        return None

# Function to write cleaned text to a new markdown file
def write_cleaned_markdown(filename="output_cleaned.md", text=""):
    with open(filename, "w", encoding="utf-8") as file:
        file.write(text)

def cleaner(bank_name):
    # Read content
    src_filename = f"DATA/RAW/{bank_name}_output.md"
    original_text = read_markdown_file(src_filename)
    
    # Clean using LLM
    length = len(original_text)
    
    ps = [i for i in range(0,length,(int(10e5)-1000))]
    parts = [original_text[ps[i]:ps[i+1]] for i in range(len(ps)-1)] if length>10e5 else [original_text]
    parts.append(original_text[ps[-1]:])

    cleaned_text = ""
    for part_text in parts:
        if part_text is None : continue
        cleaned_text += clean_text_with_llm(part_text)
    
    if cleaned_text:
        # Write to new file
        filename = f"DATA/CLEANED/{bank_name}_output_cleaned.md"
        write_cleaned_markdown(filename= filename,text=cleaned_text)
        print("Cleaning complete. Check "+ filename)



def update_md():
    for bank in banks:
        FILE_PATH = f"{bank}_output_cleaned.md"  # Path in Supabase Storage
        NEW_FILE = rf"DATA\CLEANED\{bank}_output_cleaned.md"  # Local file to upload
        try:
            supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
            with open(NEW_FILE, "rb") as f:
                upload_result = supabase.storage.from_(BUCKET_NAME).update(FILE_PATH, f,file_options={"cacheControl": "3600", "upsert": True})
        except Exception as e:
            print(f"Failed Uploading {FILE_PATH}")



if __name__ == "__main__":
    while True:

        get_terms_raw()

        for bank in banks :
            cleaner(bank)

        update_md()    

        time.sleep(60*MINUTES)








