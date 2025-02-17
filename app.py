from flask import Flask, render_template, request, jsonify
import os
import pandas as pd
import requests
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
from dotenv import load_dotenv

# Načtení environmentálních proměnných
load_dotenv()

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Načtení API klíče pro OpenRouter
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Cesty pro ukládání dat
SOURCES_FILE = "sources.txt"
HISTORY_DIR = "historie_pdfs"

if not os.path.exists(HISTORY_DIR):
    os.makedirs(HISTORY_DIR)

# Inicializace databáze
columns = ["Název dokumentu", "Kategorie", "Datum vydání / aktualizace", "Odkaz na zdroj", "Shrnutí obsahu", "Soubor", "Klíčová slova", "Původní obsah"]
legislativa_db = pd.DataFrame(columns=columns)
document_status = {}

def load_sources():
    """ Načte seznam sledovaných URL ze souboru sources.txt. """
    if os.path.exists(SOURCES_FILE):
        with open(SOURCES_FILE, "r", encoding="utf-8") as file:
            return [line.strip() for line in file.readlines()]
    return []

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
    """ Stáhne seznam PDF dokumentů a jejich obsah. """
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

def load_initial_data():
    """ Načte data při startu aplikace """
    global legislativa_db
    urls = load_sources()
    legislativa_db = pd.concat([scrape_legislation(url) for url in urls], ignore_index=True)

load_initial_data()  # 🆕 Načteme dokumenty při startu aplikace

def ask_openrouter(question, context):
    """ Odesílá dotaz na OpenRouter API (zdarma AI odpovědi) """
    API_URL = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}

    data = {
        "model": "mistral/mistral-7b-instruct",  # 🆓 Zdarma model Mistral 7B
        "messages": [
            {"role": "system", "content": "Jsi AI expert na legislativu. Odpovídej jasně a přesně."},
            {"role": "user", "content": f"Zde je kontext: {context}\n\nOtázka: {question}"}
        ],
        "max_tokens": 500
    }

    response = requests.post(API_URL, headers=headers, json=data)

    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"]
    else:
        return "Omlouvám se, došlo k chybě při zpracování odpovědi."

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

@app.route('/ask', methods=['POST'])
def ask():
    question = request.form.get("question", "").strip()
    if not question:
        return jsonify({"error": "Zadejte otázku!"})
    
    context = " ".join(legislativa_db["Původní obsah"].tolist()[:3])  # 🆕 Použijeme první 3 dokumenty jako kontext
    answer = ask_openrouter(question, context)
    
    return jsonify({"answer": answer})

if __name__ == '__main__':
    app.run(debug=True)
