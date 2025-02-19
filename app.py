import requests
import json
import os
import pandas as pd
import psutil  
import logging
from flask import Flask, render_template, request, jsonify
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
from dotenv import load_dotenv
import difflib  

# Načtení environmentálních proměnných
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ✅ Nastavení logování
logging.basicConfig(level=logging.DEBUG, filename='app.log', filemode='a', format='%(asctime)s - %(levelname)s - %(message)s')

# ✅ Funkce pro sledování využití paměti
def get_memory_usage():
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    return mem_info.rss / (1024 * 1024)  # Vrátí MB

# Cesty pro soubory
SOURCES_FILE = "sources.txt"
HISTORY_DIR = "historie_pdfs"

if not os.path.exists(HISTORY_DIR):
    os.makedirs(HISTORY_DIR)

# Inicializace databáze
columns = ["Název dokumentu", "Kategorie", "Datum vydání / aktualizace", "Odkaz na zdroj", "Shrnutí obsahu", "Soubor", "Klíčová slova", "Původní obsah"]
legislativa_db = pd.DataFrame(columns=columns)
document_status = {}

# ✅ Načteme seznam webových zdrojů
def load_sources():
    if os.path.exists(SOURCES_FILE):
        with open(SOURCES_FILE, "r", encoding="utf-8") as file:
            return [line.strip() for line in file.readlines()]
    return []

# ✅ Stáhneme PDF dokument a extrahujeme text
def extract_text_from_pdf(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            pdf_document = fitz.open(stream=response.content, filetype="pdf")
            return "\n".join([page.get_text("text") for page in pdf_document]).strip()
    except Exception as e:
        logging.error(f"Chyba při zpracování PDF: {e}")
    return ""

# ✅ Stáhneme seznam právních předpisů z webu a kontrolujeme změny
def scrape_legislation(url):
    response = requests.get(url)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        data = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if href.endswith(".pdf"):
                name = link.text.strip()
                full_url = href if href.startswith("http") else url[:url.rfind("/")+1] + href
                new_text = extract_text_from_pdf(full_url)
                document_status[name] = "Nový ✅"
                data.append([name, "Legislativa", "N/A", url, "", full_url, "předpisy", new_text])
        return pd.DataFrame(data, columns=columns)
    return pd.DataFrame(columns=columns)

# ✅ Načteme legislativní dokumenty
def load_initial_data():
    global legislativa_db
    urls = load_sources()
    legislativa_db = pd.concat([scrape_legislation(url) for url in urls], ignore_index=True)

load_initial_data()

# ✅ Funkce pro komunikaci s Groq AI
def ask_groq(question):
    API_URL = "https://api.groq.com/openai/v1/chat/completions"
    HEADERS = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}

    # ✅ Pouze posledních 5 dokumentů
    extracted_texts = " ".join(legislativa_db["Původní obsah"].tolist()[-5:])

    # ✅ Zkrácení textu na 2000 slov (~2500 tokenů)
    words = extracted_texts.split()
    truncated_text = " ".join(words[-2000:]) if len(words) > 2000 else extracted_texts

    PROMPT = f"Dokumenty:\n{truncated_text}\n\nOtázka: {question}\nOdpověď:"

    DATA = {
        "model": "mixtral-8x7b-32768",
        "messages": [{"role": "user", "content": PROMPT}]
    }

    try:
        response = requests.post(API_URL, headers=HEADERS, json=DATA, timeout=15)
        response_json = response.json()

        if "choices" in response_json and len(response_json["choices"]) > 0:
            return response_json["choices"][0]["message"]["content"]
        elif "error" in response_json:
            return f"❌ Chyba API: {response_json['error'].get('message', 'Neznámá chyba')}"
        else:
            return "❌ Chyba: Neočekávaný formát odpovědi od API."

    except requests.exceptions.RequestException as e:
        logging.error(f"⛔ Chyba při volání Groq API: {e}")
        return f"❌ Chyba při komunikaci s AI: {str(e)}"

# ✅ API pro AI asistenta
@app.route('/ask', methods=['POST'])
def ask():
    question = request.form.get("question", "").strip()
    if not question:
        return jsonify({"error": "Zadejte otázku!"})
    return jsonify({"answer": ask_groq(question)})

# ✅ Hlavní webová stránka
@app.route('/')
def index():
    return render_template('index.html', documents=legislativa_db.to_dict(orient="records"), sources=load_sources(), document_status=document_status)

if __name__ == '__main__':
    app.run(debug=True)
