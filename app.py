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

# ✅ Načtení API klíče z .env souboru
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ✅ Inicializace Groq klienta
client = Groq(api_key=GROQ_API_KEY)

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ✅ Nastavení logování
logging.basicConfig(level=logging.DEBUG, filename='app.log', filemode='a', format='%(asctime)s - %(levelname)s - %(message)s')

# ✅ Funkce pro sledování využití paměti
def get_memory_usage():
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    return mem_info.rss / (1024 * 1024)  # Vrátí MB

# ✅ Cesty pro soubory
SOURCES_FILE = "sources.txt"
HISTORY_DIR = "historie_pdfs"

if not os.path.exists(HISTORY_DIR):
    os.makedirs(HISTORY_DIR)

# ✅ Inicializace databáze
columns = ["Název dokumentu", "Kategorie", "Datum vydání / aktualizace", "Odkaz na zdroj", "Shrnutí obsahu", "Soubor", "Klíčová slova", "Původní obsah"]
legislativa_db = pd.DataFrame(columns=columns)
document_status = {}

# ✅ Načtení seznamu legislativních webových zdrojů
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

# ✅ Stáhneme seznam legislativních dokumentů z webu a kontrolujeme změny
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

# ✅ Funkce pro komunikaci s Groq API (LLaMA 3.1-8B-Instant)
def ask_groq(question):
    """ Posílá dotaz na Groq API s modelem LLaMA 3.1-8B-Instant bez omezení délky vstupního textu. """
    try:
        # ✅ Vezmeme celý text ze všech uložených dokumentů
        extracted_texts = " ".join(legislativa_db["Původní obsah"].tolist())

        # ✅ Sestavení promptu
        prompt = f"Dokumenty:\n{extracted_texts}\n\nOtázka: {question}\nOdpověď:"

        # ✅ Odeslání dotazu do Groq API
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",  # ✅ Nahrazeno Mistral → LLaMA
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,  # Mírně kreativní odpovědi, ale stále přesné
            max_tokens=4096,  # ✅ Zvýšení maximální délky odpovědi
            top_p=1,
            stream=False,  # ✅ Nepoužíváme streamování
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
