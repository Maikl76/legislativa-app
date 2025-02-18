import requests
import json
import os
import pandas as pd
from flask import Flask, render_template, request, jsonify, redirect, url_for
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
from dotenv import load_dotenv

# Načtení environmentálních proměnných
load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Cesty pro soubory
SOURCES_FILE = "sources.txt"
LEGAL_TEXTS_FILE = "legal_texts.txt"

# Inicializace databáze
columns = ["Název dokumentu", "Kategorie", "Datum vydání / aktualizace", "Odkaz na zdroj", "Shrnutí obsahu", "Soubor", "Klíčová slova", "Původní obsah"]
legislativa_db = pd.DataFrame(columns=columns)

# ✅ Načteme seznam webových zdrojů
def load_sources():
    if os.path.exists(SOURCES_FILE):
        with open(SOURCES_FILE, "r", encoding="utf-8") as file:
            return [line.strip() for line in file.readlines()]
    return []

# ✅ Přidáme novou stránku do sources.txt
def save_source(url):
    with open(SOURCES_FILE, "a", encoding="utf-8") as file:
        file.write(url + "\n")

# ✅ Načteme ručně přidané právní texty
def load_manual_legal_texts():
    if os.path.exists(LEGAL_TEXTS_FILE):
        with open(LEGAL_TEXTS_FILE, "r", encoding="utf-8") as file:
            return file.read()
    return ""

# ✅ Stáhneme PDF dokument a extrahujeme text
def extract_text_from_pdf(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            pdf_document = fitz.open(stream=response.content, filetype="pdf")
            return "\n".join([page.get_text("text") for page in pdf_document]).strip()
    except Exception as e:
        print("Chyba při zpracování PDF:", e)
    return ""

# ✅ Stáhneme seznam právních předpisů z webu
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

load_initial_data()  # 🆕 Načteme dokumenty při startu aplikace

# ✅ API endpoint pro přidání nového webu
@app.route('/add_source', methods=['POST'])
def add_source():
    new_url = request.form.get("url").strip()
    if new_url:
        save_source(new_url)  # ✅ Uložíme URL do sources.txt
        load_initial_data()  # ✅ Znovu načteme všechna data
    return redirect(url_for('index'))

# ✅ Hlavní webová stránka
@app.route('/')
def index():
    sources = load_sources()
    return render_template('index.html', documents=legislativa_db.to_dict(orient="records"), sources=sources)

if __name__ == '__main__':
    app.run(debug=True)
