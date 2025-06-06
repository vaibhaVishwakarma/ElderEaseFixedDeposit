from crewai_tools import ScrapeWebsiteTool
import requests 
import os 
from dotenv import load_dotenv
import markdown as md
import os
import re
from dotenv import load_dotenv
import nltk
from nltk.corpus import stopwords
from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import CharacterTextSplitter

nltk.download('stopwords')


load_dotenv()
# Initialize Supabase Client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_API_URL = os.getenv("OPENROUTER_API_URL")
CUSTOM_SEARCH_API_KEY = os.getenv("CUSTOM_SEARCH_API_KEY")
CUSTOM_SEARCH_ENGINE_ID = os.getenv('CUSTOM_SEARCH_ENGINE_ID')

LIMIT_PAGES = 3
MODEL_NAME = "google/gemini-2.0-flash-exp:free"

banks = [
    "HDFC",
    "SBI",
    "KOTAK",
    "ICICI",
]

stop_words = set(stopwords.words('english'))

def get_terms_raw():

    def get_md(url):
        tool = ScrapeWebsiteTool()
        tool = ScrapeWebsiteTool(website_url=url)
        try: 
            res = tool.run()
        except Exception as e:
            return ""
        return res

    def get_terms_links(bank_name):
        search_query = f"{bank_name} fixed Deposites terms and conditions and penalities"
        url = f"https://www.googleapis.com/customsearch/v1?q={search_query}&key={CUSTOM_SEARCH_API_KEY}&cx={CUSTOM_SEARCH_ENGINE_ID}"

        response = requests.get(url)
        data = response.json()

        links = []
        for item in data.get("items", []):
            links.append(item["link"])
        return links[2:2+LIMIT_PAGES]

    for bank in banks:
        with open(f"DATA/RAW/{bank}_output.md", "w",encoding="utf-8") as file: 
            for link in get_terms_links(bank):
                text_data =md.markdown(get_md(link)) 
                text_data = re.sub(r'[^a-zA-Z0-9\\s+\-*%&.,]' , " " , re.sub("\\n+|\\s+" , " " , text_data))
                text_data = " ".join([word for word in text_data.split(" ") if word.lower() not in stop_words])
                file.write(text_data)



def read_markdown_file(filename):
    with open(filename, "r", encoding="utf-8") as file:
        return file.read()

def clean_text_with_llm(text):
    sentences = text.split(" ")
    n_sentences = 3000
    lower = min(n_sentences , len(sentences))
    text_chunks = [ " ".join(sentences)[idx-lower:idx]  for idx in range(lower,len(sentences)+1,n_sentences) ]
    total_output = ""


    for data in text_chunks :
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": MODEL_NAME,  # Use a suitable model from OpenRouter
            "messages": [
                {
                    "role":"user",
                    "content": [ 
                    {    
                    "type":"text",
                    "text": f"""
                    You are a legal assistant. Given the following messy, unstructured, or mixed textual data, extract **only** the sentences or clauses that are part of the "terms and conditions". 

                        ⚠️ Do not summarize, rewrite, or paraphrase. 
                        ⚠️ Do not alter any legal language.
                        ✅ Preserve the wording exactly as it appears.
                        ✅ Include all relevant clauses, even if they appear disorganized or embedded in unrelated text.

                        Input text:
                        ---
                        {data}
                        ---

                        Output:
                        - List only the exact sentences or clauses that are part of the terms and conditions.
                        - If some sentences are incomplete or split, reconstruct them **without changing** any part of the original language.
                            """
                    }    ]
                }

            ],
            "temperature": 0.67
        }
        
        response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload)
        
        if response.status_code == 200:
            result = response.json()
            print(result)
            try:
                total_output += result["choices"][0]["message"]["content"]
            except Exception as e:
                print("Error:", response.status_code, response.text)
                return None
        else:
            print("Error:", response.status_code, response.text)
            return None
    return total_output
        

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
    
    try :
        ps = [i for i in range(0,length,(int(10e5)-1000))]
        parts = [original_text[ps[i]:ps[i+1]] for i in range(len(ps)-1)] if length>10e5 else [original_text]
        parts.append(original_text[ps[-1]:])
    except Exception as e: 
        print(e)


    cleaned_text = "" 
    for part_text in parts:
        if part_text is None : continue
        cleaned_text += clean_text_with_llm(part_text) or ""
    
    if cleaned_text:
        # Write to new file
        filename = f"DATA/CLEANED/{bank_name}_output_cleaned.md"
        write_cleaned_markdown(filename= filename,text=cleaned_text)
        print("Cleaning complete. Check "+ filename)


def main():
    get_terms_raw()

    for bank in banks :
        cleaner(bank)


main()
        








