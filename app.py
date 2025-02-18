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

                document_status[name] = status
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
        with open(SOURCES_FILE, "a", encoding="utf-8") as file:
            file.write(new_url + "\n")
        new_data = scrape_legislation(new_url)
        global legislativa_db
        legislativa_db = pd.concat([legislativa_db, new_data], ignore_index=True)
    return redirect(url_for('index'))

# ✅ AI odpovídá na základě všech dostupných dokumentů (zpracovává je po blocích)
def ask_openrouter(question):
    API_URL = "https://openrouter.ai/api/v1/chat/completions"

    extracted_texts = " ".join(legislativa_db["Původní obsah"].tolist())
    
    # ✅ Rozdělíme text na bloky (každý max 3000 znaků)
    chunks = [extracted_texts[i:i+3000] for i in range(0, len(extracted_texts), 3000)]

    HEADERS = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    final_answer = ""

    for i, chunk in enumerate(chunks):
        print(f"🟡 Posílám část {i+1}/{len(chunks)} AI...")

        DATA = {
            "model": "deepseek/deepseek-r1:free",
            "messages": [
                {"role": "system", "content": "Jsi AI expert na legislativu. Odpovídej pouze na základě níže uvedených dokumentů."},
                {"role": "user", "content": f"Dokumenty:\n{chunk}\n\nOtázka: {question}"}
            ],
            "max_tokens": 500
        }

        try:
            response = requests.post(API_URL, headers=HEADERS, json=DATA, timeout=15)
            response.raise_for_status()
            response_json = response.json()
            final_answer += response_json["choices"][0]["message"]["content"] + "\n\n"
        except requests.exceptions.Timeout:
            final_answer += "⚠️ Omlouvám se, ale jedna část odpovědi trvala příliš dlouho.\n"
        except requests.exceptions.RequestException as e:
            final_answer += f"⚠️ Chyba při zpracování jedné části: {e}\n"

    return final_answer.strip()

# ✅ API pro AI asistenta
@app.route('/ask', methods=['POST'])
def ask():
    question = request.form.get("question", "").strip()
    if not question:
        return jsonify({"error": "Zadejte otázku!"})
    return jsonify({"answer": ask_openrouter(question)})

# ✅ Hlavní webová stránka
@app.route('/')
def index():
    return render_template('index.html', documents=legislativa_db.to_dict(orient="records"), sources=load_sources(), document_status=document_status)

if __name__ == '__main__':
    app.run(debug=True)
