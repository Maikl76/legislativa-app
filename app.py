from flask import Flask, render_template, request, flash, jsonify
import os
import pandas as pd
import requests
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
import threading
import time
import yagmail  # Bezpečné odesílání e-mailů
import difflib
from dotenv import load_dotenv

# Načtení environmentálních proměnných
load_dotenv()

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Cesty pro ukládání dat
SOURCES_FILE = "sources.txt"
HISTORY_DIR = "historie_pdfs"

if not os.path.exists(HISTORY_DIR):
    os.makedirs(HISTORY_DIR)

# Načtení e-mailových údajů
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")

# Inicializace databáze
columns = ["Název dokumentu", "Kategorie", "Datum vydání / aktualizace", "Odkaz na zdroj", "Shrnutí obsahu", "Soubor", "Klíčová slova", "Původní obsah"]
legislativa_db = pd.DataFrame(columns=columns)
document_status = {}

def load_sources():
    if os.path.exists(SOURCES_FILE):
        with open(SOURCES_FILE, "r", encoding="utf-8") as file:
            return [line.strip() for line in file.readlines()]
    return []

def save_source(url):
    with open(SOURCES_FILE, "a", encoding="utf-8") as file:
        file.write(url + "\n")

def extract_text_from_pdf(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            pdf_document = fitz.open(stream=response.content, filetype="pdf")
            return "\n".join([page.get_text("text") for page in pdf_document]).strip()
    except Exception as e:
        print("Chyba při zpracování PDF:", e)
    return ""

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

def update_legislation():
    global legislativa_db, document_status
    urls = load_sources()
    new_data = pd.concat([scrape_legislation(url) for url in urls], ignore_index=True)
    
    for index, row in new_data.iterrows():
        doc_name = row["Název dokumentu"]
        new_text = row["Původní obsah"]
        
        if doc_name not in legislativa_db["Název dokumentu"].values:
            document_status[doc_name] = "Nový ✅"
        else:
            old_text = legislativa_db.loc[legislativa_db["Název dokumentu"] == doc_name, "Původní obsah"].values[0]
            if old_text != new_text:
                document_status[doc_name] = "Aktualizováno 🟡"
                save_version(doc_name, old_text)
            else:
                document_status[doc_name] = "Beze změny ⚪"

    legislativa_db = new_data

@app.route('/')
def index():
    sources = load_sources()
    return render_template('index.html', documents=legislativa_db.to_dict(orient="records"), sources=sources, document_status=document_status)

@app.route('/search', methods=['POST'])
def search():
    query = request.form.get("query", "").strip().lower()
    results = []

    if not query:
        return jsonify({"error": "Zadejte hledaný výraz!"})

    for _, doc in legislativa_db.iterrows():
        text = doc["Původní obsah"]
        paragraphs = text.split("\n\n")
        for paragraph in paragraphs:
            if query in paragraph.lower():
                results.append({"text": paragraph.strip(), "document": doc["Název dokumentu"], "source": doc["Odkaz na zdroj"]})

    return jsonify(results)

if __name__ == '__main__':
    thread = threading.Thread(target=update_legislation, daemon=True)
    thread.start()
    app.run(debug=True)
