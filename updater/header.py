import numpy as np 
import pandas as pd 
import re
import requests
import time
import os 
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from supabase import create_client, Client

load_dotenv()

URL = os.getenv("SUPABASE_URL")
KEY = os.getenv("SUPABASE_KEY")

MINUTES = 1

def get_html(url):
        response = requests.get(url)
        html_content = response.text
        return BeautifulSoup(html_content, 'html.parser')