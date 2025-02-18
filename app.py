import requests
import json
import os
import pandas as pd
import psutil
import logging
from flask import Flask, render_template, request, jsonify, redirect, url_for
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
from dotenv import load_dotenv
import difflib

# ✅ Načtení environmentálních proměnných
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
    return mem_info.rss / (1024 * 1024)  # Vrátí využití paměti v MB

# ✅ Cesty pro soubory
SOURCES_FILE = "sources.txt"
HISTORY_DIR = "historie_pdfs"

if not os.path.exists(HISTORY_DIR):
    os.makedirs(HISTORY_DIR)

# ✅ Inicializace databáze
columns = ["Název dokumentu", "Kategorie", "Datum vydání / aktualizace", "Odkaz na zdroj", "Shrnutí obsahu", "Soubor", "Klíčová slova", "Původní obsah"]
legislativa_db = pd.DataFrame(columns=columns)

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
        logging.error(f"❌ Chyba při zpracování PDF: {e}")
    return ""

# ✅ Stáhneme seznam legislativních dokumentů z webu
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
                text_content = extract_text_from_pdf(full_url)
                data.append([name, "Legislativa", "N/A", url, "", full_url, "předpisy", text_content])
        return pd.DataFrame(data, columns=columns)
    return pd.DataFrame(columns=columns)

# ✅ Načteme legislativní dokumenty
def load_initial_data():
    global legislativa_db
    urls = load_sources()
    legislativa_db = pd.concat([scrape_legislation(url) for url in urls], ignore_index=True)

load_initial_data()

# ✅ Přidání nového legislativního zdroje
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

# ✅ AI odpovídá na základě dokumentů z konkrétního webu pomocí Groq API
def ask_groq(question, source):
    API_URL = "https://api.groq.com/v1/chat/completions"

    if not GROQ_API_KEY:
        logging.error("❌ Chybí API klíč pro Groq!")
        return "⚠️ Groq API klíč není nastaven."

    selected_docs = legislativa_db[legislativa_db["Odkaz na zdroj"] == source]

    if selected_docs.empty:
        logging.warning("⚠️ Nebyly nalezeny žádné dokumenty pro tento zdroj.")
        return "⚠️ Nebyly nalezeny žádné dokumenty pro tento zdroj."

    final_answer = ""

    for i in range(0, len(selected_docs), 3):
        batch = selected_docs.iloc[i:i+3]
        extracted_texts = " ".join(batch["Původní obsah"].tolist())

        chunks = [extracted_texts[i:i+500] for i in range(0, len(extracted_texts), 500)]

        for j, chunk in enumerate(chunks):
            logging.debug(f"🟡 Odesílám část {j+1}/{len(chunks)} AI... Paměť: {get_memory_usage()} MB")

            DATA = {
                "model": "llama3-8b-8192",  # Nebo použij "gemma-7b-it"
                "messages": [
                    {"role": "system", "content": "Jsi AI expert na legislativu."},
                    {"role": "user", "content": f"Dokumenty:\n{chunk}\n\nOtázka: {question}"}
                ],
                "max_tokens": 300
            }

            try:
                logging.debug(f"🔵 Odesílám požadavek na Groq AI: {DATA}")
                response = requests.post(API_URL, headers={"Authorization": f"Bearer {GROQ_API_KEY}"}, json=DATA, timeout=60)
                response.raise_for_status()
                response_json = response.json()

                logging.debug(f"🟢 Celá odpověď Groq API: {response_json}")

                if "choices" not in response_json or not response_json["choices"]:
                    logging.error(f"❌ Groq API nevrátilo žádnou odpověď. Odpověď: {response_json}")
                    return f"⚠️ Groq nevrátil odpověď. Detaily: {response_json}"

                final_answer += response_json["choices"][0]["message"]["content"] + "\n\n"

            except requests.exceptions.RequestException as e:
                logging.error(f"⛔ Chyba při volání Groq API: {e}")
                return f"⚠️ Chyba při volání Groq API: {e}"
            except Exception as e:
                logging.error(f"⛔ Neočekávaná chyba: {e}")
                return f"⚠️ Neočekávaná chyba: {e}"

    return final_answer.strip() if final_answer else "⚠️ AI nevrátila žádnou odpověď."

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
    return render_template('index.html', documents=legislativa_db.to_dict(orient="records"), sources=load_sources())

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
