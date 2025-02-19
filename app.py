import requests
import os
import pandas as pd
import psutil  
import logging
from flask import Flask, render_template, request, jsonify
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
from dotenv import load_dotenv
from groq import Groq

# ✅ Načtení API klíče
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ✅ Inicializace klienta Groq
client = Groq(api_key=GROQ_API_KEY)

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ✅ Nastavení logování
logging.basicConfig(level=logging.DEBUG, filename='app.log', filemode='a', format='%(asctime)s - %(levelname)s - %(message)s')

# ✅ Cesty pro soubory
SOURCES_FILE = "sources.txt"
HISTORY_DIR = "historie_pdfs"

if not os.path.exists(HISTORY_DIR):
    os.makedirs(HISTORY_DIR)

# ✅ Inicializace databáze
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

# ✅ Stáhneme seznam legislativních dokumentů
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

# ✅ Vrátí seznam dokumentů pro konkrétní webovou stránku
@app.route('/get_documents', methods=['POST'])
def get_documents():
    selected_source = request.form.get("source", "").strip()
    if not selected_source:
        return jsonify({"error": "Vyberte webovou stránku."})

    filtered_docs = [doc for doc in legislativa_db.to_dict(orient="records") if doc["Odkaz na zdroj"] == selected_source]
    
    return jsonify({"documents": filtered_docs})

# ✅ Funkce pro komunikaci s DeepSeek R1 Distill Qwen-32B (rozdělení textu na části)
def ask_groq(question, documents):
    """ Posílá dotaz na Groq API po částech, aby nepřekročil 6000 tokenů. """
    try:
        # ✅ Spojíme texty vybraných dokumentů
        full_text = " ".join([doc["Původní obsah"] for doc in documents])

        # ✅ Rozdělíme text na části (max. 6000 tokenů)
        words = full_text.split()
        chunk_size = 6000  # Maximální počet tokenů
        chunks = [words[i:i + chunk_size] for i in range(0, len(words), chunk_size)]

        responses = []

        for i, chunk in enumerate(chunks):
            truncated_text = " ".join(chunk)
            prompt = f"Dokumenty (část {i+1}/{len(chunks)}):\n{truncated_text}\n\nOtázka: {question}\nOdpověď:"

            completion = client.chat.completions.create(
                model="deepseek-r1-distill-qwen-32b",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.6,
                max_tokens=1024,  # ✅ Každá odpověď max. 1024 tokenů
                top_p=0.95,
                stream=False,
                stop=None
            )

            responses.append(completion.choices[0].message.content.strip())

        # ✅ Spojíme odpovědi do jedné
        final_answer = "\n\n".join(responses)
        return final_answer

    except Exception as e:
        logging.error(f"⛔ Chyba při volání Groq API: {e}")
        return f"❌ Chyba při komunikaci s AI: {str(e)}"

# ✅ API endpoint pro AI dotaz (s výběrem webu)
@app.route('/ask', methods=['POST'])
def ask():
    question = request.form.get("question", "").strip()
    selected_source = request.form.get("source", "").strip()

    if not question:
        return jsonify({"error": "Zadejte otázku!"})
    if not selected_source:
        return jsonify({"error": "Vyberte webovou stránku!"})

    # ✅ Najdeme dokumenty z vybrané webové stránky
    selected_docs = [doc for doc in legislativa_db.to_dict(orient="records") if doc["Odkaz na zdroj"] == selected_source]

    if not selected_docs:
        return jsonify({"error": "Žádné dokumenty nenalezeny pro vybraný zdroj."})

    answer = ask_groq(question, selected_docs)
    return jsonify({"answer": answer})

# ✅ Hlavní webová stránka
@app.route('/')
def index():
    return render_template('index.html', documents=legislativa_db.to_dict(orient="records"), sources=load_sources(), document_status=document_status)

if __name__ == '__main__':
    app.run(debug=True)
