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

# ✅ Funkce pro komunikaci s DeepSeek R1 Distill Qwen-32B
def ask_groq(question):
    """ Posílá dotaz na Groq API s modelem DeepSeek R1 Distill Qwen-32B. """
    try:
        # ✅ Použijeme celý text posledních 5 dokumentů
        extracted_texts = " ".join(legislativa_db["Původní obsah"].tolist()[-5:])

        # ✅ Omezíme vstupní text na max. 25 000 tokenů (pokud model zvládne)
        words = extracted_texts.split()
        if len(words) > 25000:
            truncated_text = " ".join(words[:12500]) + "\n...\n" + " ".join(words[-12500:])
        else:
            truncated_text = extracted_texts

        # ✅ Sestavení promptu
        prompt = f"Dokumenty:\n{truncated_text}\n\nOtázka: {question}\nOdpověď:"

        # ✅ Odeslání dotazu do Groq API
        completion = client.chat.completions.create(
            model="deepseek-r1-distill-qwen-32b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=4096,  # ✅ Dlouhé odpovědi
            top_p=0.95,
            stream=False,
            stop=None
        )

        # ✅ Vrácení odpovědi AI
        return completion.choices[0].message.content.strip()

    except Exception as e:
        logging.error(f"⛔ Chyba při volání Groq API: {e}")
        return f"❌ Chyba při komunikaci s AI: {str(e)}"

# ✅ API endpoint pro dotazy na AI
@app.route('/ask', methods=['POST'])
def ask():
    question = request.form.get("question", "").strip()
    if not question:
        return jsonify({"error": "Zadejte otázku!"})
    return jsonify({"answer": ask_groq(question)})

# ✅ Hlavní webová stránka
@app.route('/')
def index():
    return render_template('index.html', documents=legislativa_db.to_dict(orient="records"), sources=load_sources(), document_status=document_status)

if __name__ == '__main__':
    app.run(debug=True)
