import requests
import json
import os
import pandas as pd
from flask import Flask, render_template, request, jsonify, redirect, url_for
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
from dotenv import load_dotenv
import difflib  # Pro porovnání změn v dokumentech

# Načtení environmentálních proměnných
load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Cesty pro soubory
SOURCES_FILE = "sources.txt"
LEGAL_TEXTS_FILE = "legal_texts.txt"
HISTORY_DIR = "historie_pdfs"

if not os.path.exists(HISTORY_DIR):
    os.makedirs(HISTORY_DIR)

# Inicializace databáze
columns = ["Název dokumentu", "Kategorie", "Datum vydání / aktualizace", "Odkaz na zdroj", "Shrnutí obsahu", "Soubor", "Klíčová slova", "Původní obsah"]
legislativa_db = pd.DataFrame(columns=columns)
document_status = {}  # Slovník pro sledování změn dokumentů

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

# ✅ Uložíme původní verzi dokumentu
def save_original_content(doc_name, content):
    file_path = os.path.join(HISTORY_DIR, f"{doc_name}.txt")
    with open(file_path, "w", encoding="utf-8") as file:
        file.write(content)

# ✅ Načteme původní verzi dokumentu, pokud existuje
def load_original_content(doc_name):
    file_path = os.path.join(HISTORY_DIR, f"{doc_name}.txt")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as file:
            return file.read()
    return ""

# ✅ Porovnáme starý a nový text dokumentu
def compare_versions(old_text, new_text):
    if not old_text:
        return "Nový ✅"
    if old_text == new_text:
        return "Beze změny ⚪"
    return "Aktualizováno 🟡"

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

                # ✅ Načteme starý obsah a zjistíme změny
                old_text = load_original_content(name)
                status = compare_versions(old_text, new_text)

                # ✅ Uložíme nový obsah do historie
                save_original_content(name, new_text)

                document_status[name] = status  # Uložíme status dokumentu
                data.append([name, "Legislativa", "N/A", url, "", full_url, "předpisy", new_text])
        return pd.DataFrame(data, columns=columns)
    return pd.DataFrame(columns=columns)

# ✅ Načteme legislativní dokumenty
def load_initial_data():
    global legislativa_db
    urls = load_sources()
    legislativa_db = pd.concat([scrape_legislation(url) for url in urls], ignore_index=True)

load_initial_data()

# ✅ API pro přidání nového webu
@app.route('/add_source', methods=['POST'])
def add_source():
    new_url = request.form.get("url").strip()
    if new_url:
        save_source(new_url)
        new_data = scrape_legislation(new_url)
        global legislativa_db
        legislativa_db = pd.concat([legislativa_db, new_data], ignore_index=True)
    return redirect(url_for('index'))

# ✅ AI odpovídá na základě právních textů
def ask_openrouter(question):
    """ Odesílá dotaz na OpenRouter API a hledá ve více dokumentech """
    API_URL = "https://openrouter.ai/api/v1/chat/completions"

    extracted_texts = " ".join(legislativa_db["Původní obsah"].tolist()[:5])  # Prvních 5 dokumentů
    manual_texts = ""  # Možnost přidat ruční texty

    # ✅ Omezíme délku vstupu na max. 10 000 znaků
    context = (extracted_texts + "\n\n" + manual_texts)[:10000]

    HEADERS = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    DATA = {
        "model": "deepseek/deepseek-r1:free",
        "messages": [
            {"role": "system", "content": 
                "Jsi AI expert na legislativu. Odpovídej POUZE na základě níže uvedených dokumentů. "
                "Pokud odpověď není jasná, pokus se ji odvodit na základě poskytnutých informací. "
                "Nepřidávej vymyšlené informace."},
            {"role": "user", "content": f"Dokumenty:\n{context}\n\nOtázka: {question}"}
        ],
        "max_tokens": 750
    }

    print(f"🟡 Odesílám API request s dotazem: {question}")

    response = requests.post(API_URL, headers=HEADERS, json=DATA)

    if response.status_code == 200:
        response_json = response.json()
        answer = response_json["choices"][0]["message"]["content"]
        print(f"🟢 AI Odpověď: {answer}")
        return answer
    else:
        print(f"🔴 Chyba API {response.status_code}: {response.text}")
        return f"Omlouvám se, došlo k chybě: {response.status_code} - {response.text}"

# ✅ API pro AI asistenta
@app.route('/ask', methods=['POST'])
def ask():
    question = request.form.get("question", "").strip()
    if not question:
        return jsonify({"error": "Zadejte otázku!"})

    answer = ask_openrouter(question)
    return jsonify({"answer": answer})

# ✅ Hlavní webová stránka
@app.route('/')
def index():
    sources = load_sources()
    return render_template('index.html', documents=legislativa_db.to_dict(orient="records"), sources=sources, document_status=document_status)

if __name__ == '__main__':
    app.run(debug=True)
