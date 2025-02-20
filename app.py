import os
import requests
import json
import pandas as pd
import logging
import psutil
from flask import Flask, render_template, request, jsonify, redirect, url_for
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
from dotenv import load_dotenv

# ✅ Načtení environmentálních proměnných
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ✅ Konfigurace Flask aplikace
app = Flask(__name__)
app.secret_key = "supersecretkey"

# ✅ Logování do souboru
logging.basicConfig(level=logging.DEBUG, filename='app.log', filemode='a', format='%(asctime)s - %(levelname)s - %(message)s')

# ✅ Funkce pro sledování využití paměti
def get_memory_usage():
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    return mem_info.rss / (1024 * 1024)  # Vrátí využití paměti v MB

# ✅ Cesty pro soubory
SOURCES_FILE = "sources.txt"
HISTORY_DIR = "historie_pdfs"

if not os.path.exists(HISTORY_DIR):
    os.makedirs(HISTORY_DIR)

# ✅ Databáze dokumentů
columns = ["Název dokumentu", "Kategorie", "Datum vydání", "Odkaz na zdroj", "Soubor", "Klíčová slova", "Původní obsah", "Status"]
legislativa_db = pd.DataFrame(columns=columns)
document_status = {}

# ✅ Načtení webových zdrojů
def load_sources():
    if os.path.exists(SOURCES_FILE):
        with open(SOURCES_FILE, "r", encoding="utf-8") as file:
            return [line.strip() for line in file.readlines()]
    return []

# ✅ Extrahování textu z PDF
def extract_text_from_pdf(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            pdf_document = fitz.open(stream=response.content, filetype="pdf")
            return "\n".join([page.get_text("text") for page in pdf_document]).strip()
    except Exception as e:
        logging.error(f"❌ Chyba při zpracování PDF: {e}")
    return ""

# ✅ Stažení dokumentů a kontrola změn
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
                new_content = extract_text_from_pdf(full_url)

                # Kontrola změn dokumentů
                status = "Nový ✅"
                if name in document_status:
                    old_content = document_status[name]
                    if old_content != new_content:
                        status = "Aktualizován 🟡"
                    else:
                        status = "Beze změny ⚪"
                document_status[name] = new_content

                data.append([name, "Legislativa", "N/A", url, full_url, "předpisy", new_content, status])

        return pd.DataFrame(data, columns=columns)
    return pd.DataFrame(columns=columns)

# ✅ Načtení dokumentů
def load_initial_data():
    global legislativa_db
    urls = load_sources()
    legislativa_db = pd.concat([scrape_legislation(url) for url in urls], ignore_index=True)

load_initial_data()

# ✅ Přidání nového zdroje
@app.route('/add_source', methods=['POST'])
def add_source():
    new_url = request.form.get("url").strip()
    if new_url:
        with open(SOURCES_FILE, "a", encoding="utf-8") as file:
            file.write(new_url + "\n")
        new_data = scrape_legislation(new_url)
        global legislativa_db
        legislativa_db = pd.concat([legislativa_db, new_data], ignore_index=True)
    return redirect(url_for('index'))

# ✅ AI odpovídá na základě dokumentů pomocí Groq API
def ask_groq(question, source):
    logging.debug(f"🔍 Dotaz na AI: {question}")
    logging.debug(f"📂 Zdroj: {source}")

    if not GROQ_API_KEY:
        logging.error("❌ Chybí API klíč pro Groq!")
        return "⚠️ Groq API klíč není nastaven."

    API_URL = "https://api.groq.com/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    # ✅ Vybrat pouze první 3 dokumenty pro snížení velikosti požadavku
    selected_docs = legislativa_db[legislativa_db["Odkaz na zdroj"] == source].head(3)

    if selected_docs.empty:
        logging.warning("⚠️ Nebyly nalezeny žádné dokumenty pro tento zdroj.")
        return "⚠️ Nebyly nalezeny žádné dokumenty pro tento zdroj."

    # ✅ Zkrácení textu dokumentů na max 1000 znaků
    extracted_texts = " ".join(selected_docs["Původní obsah"].str[:1000].tolist())

    data = {
        "model": "llama3-8b-8192",
        "messages": [
            {"role": "system", "content": "Jsi AI expert na legislativu."},
            {"role": "user", "content": f"Dokumenty:\n{extracted_texts}\n\nOtázka: {question}"}
        ],
        "max_tokens": 256  # ✅ Snížení limitu odpovědi
    }

    try:
        response = requests.post(API_URL, headers=headers, json=data)
        response_json = response.json()

        if "choices" not in response_json:
            logging.error(f"❌ Groq API nevrátilo žádnou odpověď: {response_json}")
            return "⚠️ Groq nevrátil odpověď."

        return response_json["choices"][0]["message"]["content"]

    except Exception as e:
        logging.error(f"⛔ Chyba při volání Groq API: {e}")
        return f"⚠️ Chyba při volání Groq API: {e}"

# ✅ API pro AI asistenta
@app.route('/ask', methods=['POST'])
def ask():
    question = request.form.get("question", "").strip()
    source = request.form.get("source", "").strip()
    if not question or not source:
        return jsonify({"error": "Zadejte otázku a vyberte zdroj!"})
    return jsonify({"answer": ask_groq(question, source)})

# ✅ Hlavní webová stránka
@app.route('/')
def index():
    return render_template('index.html', documents=legislativa_db.to_dict(orient="records"), sources=load_sources(), document_status=document_status)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
