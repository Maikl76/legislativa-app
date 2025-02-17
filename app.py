from flask import Flask, render_template, request, send_file, flash
import os
import pandas as pd
import requests
from bs4 import BeautifulSoup
from fpdf import FPDF
import threading
import time
import smtplib
from email.mime.text import MIMEText
import difflib
import fitz  # PyMuPDF for PDF text extraction
from transformers import pipeline, AutoModelForQuestionAnswering, AutoTokenizer

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Vytvoření základní struktury databáze
columns = ["Název dokumentu", "Kategorie", "Datum vydání / aktualizace", "Odkaz na zdroj", "Shrnutí obsahu", "Soubor", "Klíčová slova", "Původní obsah"]

# Nastavení e-mailu
EMAIL_ADDRESS = "tvuj.email@gmail.com"
EMAIL_PASSWORD = "tvé_heslo"
RECIPIENT_EMAIL = "prijemce.email@gmail.com"

def send_email_update(message):
    msg = MIMEText(message)
    msg["Subject"] = "Aktualizace legislativních předpisů"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = RECIPIENT_EMAIL
    
    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, RECIPIENT_EMAIL, msg.as_string())
        server.quit()
        print("Email s aktualizacemi byl úspěšně odeslán.")
    except Exception as e:
        print("Chyba při odesílání e-mailu:", e)

# Funkce pro stahování seznamu předpisů ze stránek UK a FTVS
def scrape_legislation(url):
    response = requests.get(url)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        data = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if href.endswith(".pdf"):
                name = link.text.strip()
                full_url = url[:url.rfind("/")+1] + href if href.startswith("/") else href
                data.append([name, "UK/FTVS", "N/A", url, "", full_url, "předpisy, univerzita, UK/FTVS", ""])
        return pd.DataFrame(data, columns=columns)
    return pd.DataFrame(columns=columns)

# Funkce pro extrakci textu z PDF
def extract_text_from_pdf(pdf_path):
    text = ""
    try:
        with fitz.open(pdf_path) as doc:
            for page in doc:
                text += page.get_text("text") + "\n"
    except Exception as e:
        print(f"Chyba při extrakci textu z PDF {pdf_path}: {e}")
    return text

# Inicializace databáze při startu aplikace
urls = ["https://cuni.cz/UK-146.html", "https://ftvs.cuni.cz/FTVS-83.html"]
legislativa_db = pd.concat([scrape_legislation(url) for url in urls], ignore_index=True)

# Extrakce textu z uložených PDF dokumentů
pdf_texts = {}
for doc in legislativa_db["Soubor"]:
    pdf_texts[doc] = extract_text_from_pdf(doc)

# Inicializace jazykového modelu pro otázky a odpovědi
model_name = "deepset/roberta-base-squad2"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForQuestionAnswering.from_pretrained(model_name)
qa_pipeline = pipeline("question-answering", model=model, tokenizer=tokenizer)

def search_pdf_content(question):
    results = []
    for doc, content in pdf_texts.items():
        if question.lower() in content.lower():
            results.append((doc, content))
    return results

def generate_answer(question):
    results = search_pdf_content(question)
    if not results:
        return "Odpověď nebyla nalezena v dostupných dokumentech."
    
    best_result = results[0][1]  # Nejrelevantnější nalezený text
    answer = qa_pipeline(question=question, context=best_result)
    
    return answer["answer"]

@app.route('/')
def index():
    return render_template('index.html', documents=legislativa_db.to_dict(orient="records"))

@app.route('/search', methods=['POST'])
def search():
    question = request.form.get("question", "")
    answer = generate_answer(question)
    return render_template("index.html", documents=legislativa_db.to_dict(orient="records"), answer=answer)

if __name__ == '__main__':
    app.run(debug=True)
