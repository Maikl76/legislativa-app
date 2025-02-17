from flask import Flask, render_template, request, flash
import os
import pandas as pd
import requests
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
import threading
import time
import smtplib
import yagmail  # Bezpečné odesílání e-mailů
import difflib
from dotenv import load_dotenv

# Načteme environment proměnné
load_dotenv()

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Cesty pro ukládání dat
SOURCES_FILE = "sources.txt"
HISTORY_DIR = "historie_pdfs"

# Vytvoření složky pro historii PDF, pokud neexistuje
if not os.path.exists(HISTORY_DIR):
    os.makedirs(HISTORY_DIR)

# Načtení e-mailových údajů
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")

# Inicializace databáze
columns = ["Název dokumentu", "Kategorie", "Datum vydání / aktualizace", "Odkaz na zdroj", "Shrnutí obsahu", "Soubor", "Klíčová slova", "Původní obsah"]
legislativa_db = pd.DataFrame(columns=columns)


def load_sources():
    """ Načte seznam sledovaných URL. """
    if os.path.exists(SOURCES_FILE):
        with open(SOURCES_FILE, "r", encoding="utf-8") as file:
            return [line.strip() for line in file.readlines()]
    return []

def save_source(url):
    """ Přidá novou URL do souboru. """
    with open(SOURCES_FILE, "a", encoding="utf-8") as file:
        file.write(url + "\n")

def extract_text_from_pdf(url):
    """ Stáhne PDF a extrahuje text. """
    try:
        response = requests.get(url)
        if response.status_code == 200:
            pdf_document = fitz.open(stream=response.content, filetype="pdf")
            return "\n".join([page.get_text("text") for page in pdf_document]).strip()
    except Exception as e:
        print("Chyba při zpracování PDF:", e)
    return ""

def scrape_legislation(url):
    """ Stáhne seznam PDF dokumentů z webové stránky. """
    response = requests.get(url)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        data = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if href.endswith(".pdf"):
                name = link.text.strip()
                full_url = url[:url.rfind("/")+1] + href if href.startswith("/") else href
                text_content = extract_text_from_pdf(full_url)
                data.append([name, "Legislativa", "N/A", url, "", full_url, "předpisy", text_content])
        return pd.DataFrame(data, columns=columns)
    return pd.DataFrame(columns=columns)

def compare_versions(old_text, new_text):
    """ Porovnání dvou verzí dokumentu. """
    diff = difflib.unified_diff(old_text.splitlines(), new_text.splitlines(), lineterm="")
    return "\n".join(diff)

def save_version(document_name, text_content):
    """ Uloží starou verzi dokumentu. """
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    filename = f"{HISTORY_DIR}/{document_name.replace(' ', '_')}_{timestamp}.txt"
    with open(filename, "w", encoding="utf-8") as file:
        file.write(text_content)

def send_email_update(message):
    """ Odeslání upozornění e-mailem. """
    try:
        yag = yagmail.SMTP(EMAIL_ADDRESS)
        yag.send(to=RECIPIENT_EMAIL, subject="Aktualizace legislativních předpisů", contents=message)
        print("Email s aktualizacemi byl odeslán.")
    except Exception as e:
        print("Chyba při odesílání e-mailu:", e)

@app.route('/')
def index():
    sources = load_sources()
    return render_template('index.html', documents=legislativa_db.to_dict(orient="records"), sources=sources)

@app.route('/add_source', methods=['POST'])
def add_source():
    new_url = request.form.get("new_url")
    if new_url and new_url.startswith("http"):
        save_source(new_url)
        flash(f"Nový zdroj '{new_url}' byl přidán!", "success")
    else:
        flash("Neplatná URL adresa!", "danger")
    return index()

@app.route('/check_updates', methods=['POST'])
def check_updates():
    global legislativa_db
    urls = load_sources()
    new_data = pd.concat([scrape_legislation(url) for url in urls], ignore_index=True)

    if not new_data.equals(legislativa_db):
        flash("Byly nalezeny nové nebo aktualizované předpisy!", "success")
        send_email_update("Byly nalezeny nové předpisy.")
        legislativa_db = new_data
    else:
        flash("Žádné nové předpisy nebyly nalezeny.", "info")

    return index()

if __name__ == '__main__':
    thread = threading.Thread(target=check_updates, daemon=True)
    thread.start()
    app.run(debug=True)
