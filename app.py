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
import difflib
from groq import Groq

# ✅ Načtení environmentálních proměnných
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ✅ Inicializace Groq klienta
client = Groq(api_key=GROQ_API_KEY)

# ✅ Konfigurace Flask aplikace
app = Flask(__name__)
app.secret_key = "supersecretkey"

# ✅ Logování do souboru
logging.basicConfig(level=logging.DEBUG, filename='app.log', filemode='a', format='%(asctime)s - %(levelname)s - %(message)s')

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

# ✅ Uložení webových zdrojů
def save_sources(sources):
    with open(SOURCES_FILE, "w", encoding="utf-8") as file:
        for source in sources:
            file.write(source + "\n")

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
        sources = load_sources()
        if new_url not in sources:
            sources.append(new_url)
            save_sources(sources)
            new_data = scrape_legislation(new_url)
            global legislativa_db
            legislativa_db = pd.concat([legislativa_db, new_data], ignore_index=True)
    return redirect(url_for('index'))

# ✅ Odstranění zdroje
@app.route('/remove_source', methods=['POST'])
def remove_source():
    url_to_remove = request.form.get("url").strip()
    sources = load_sources()
    if url_to_remove in sources:
        sources.remove(url_to_remove)
        save_sources(sources)
        global legislativa_db
        legislativa_db = legislativa_db[legislativa_db["Odkaz na zdroj"] != url_to_remove]
    return redirect(url_for('index'))

# ✅ AI odpovídá na základě dokumentů pomocí Groq API
def ask_groq(question, source):
    logging.debug(f"🔍 Dotaz na AI: {question}")
    logging.debug(f"📂 Zdroj: {source}")

    selected_docs = legislativa_db[legislativa_db["Odkaz na zdroj"] == source]

    if selected_docs.empty:
        logging.warning("⚠️ Nebyly nalezeny žádné dokumenty pro tento zdroj.")
        return "⚠️ Nebyly nalezeny žádné dokumenty pro tento zdroj."

    extracted_texts = " ".join(selected_docs["Původní obsah"].tolist())

    try:
        # ✅ Odesíláme dotaz na Groq API
        completion = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[
                {"role": "system", "content": "Jsi AI expert na legislativu."},
                {"role": "user", "content": f"Dokumenty:\n{extracted_texts[:3000]}\n\nOtázka: {question}"}
            ],
            temperature=1,
            max_tokens=512,
            top_p=1
        )

        logging.debug(f"🟢 Odpověď Groq API: {completion}")

        if not completion.choices:
            logging.error("❌ Groq API nevrátilo žádnou odpověď!")
            return "⚠️ Groq API nevrátilo žádnou odpověď."

        return completion.choices[0].message.content

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
