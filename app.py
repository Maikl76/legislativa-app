import os
import pandas as pd
import logging
import psutil
from flask import Flask, render_template, request, jsonify, redirect, url_for
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
from dotenv import load_dotenv
import difflib
from groq import Groq

# ✅ Načtení environmentálních proměnných
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ✅ Nastavení logování
logging.basicConfig(level=logging.DEBUG, filename='app.log', filemode='a', format='%(asctime)s - %(levelname)s - %(message)s')

# ✅ Funkce pro sledování využití paměti
def get_memory_usage():
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    return mem_info.rss / (1024 * 1024)  # Vrátí využití paměti v MB

# ✅ Připojení ke Groq API pomocí oficiálního SDK
client = Groq(api_key=GROQ_API_KEY)

# ✅ AI odpovídá na základě dokumentů z konkrétního webu pomocí Groq SDK
def ask_groq(question, source):
    if not GROQ_API_KEY:
        logging.error("❌ Chybí API klíč pro Groq!")
        return "⚠️ Groq API klíč není nastaven."

    selected_docs = legislativa_db[legislativa_db["Odkaz na zdroj"] == source]

    if selected_docs.empty:
        logging.warning("⚠️ Nebyly nalezeny žádné dokumenty pro tento zdroj.")
        return "⚠️ Nebyly nalezeny žádné dokumenty pro tento zdroj."

    final_answer = ""

    for i in range(0, len(selected_docs), 3):
        batch = selected_docs.iloc[i:i+3]
        extracted_texts = " ".join(batch["Původní obsah"].tolist())

        chunks = [extracted_texts[i:i+500] for i in range(0, len(extracted_texts), 500)]

        for j, chunk in enumerate(chunks):
            logging.debug(f"🟡 Odesílám část {j+1}/{len(chunks)} AI... Paměť: {get_memory_usage()} MB")

            try:
                # ✅ Použití oficiálního Groq klienta
                completion = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": "Jsi AI expert na legislativu."},
                        {"role": "user", "content": f"Dokumenty:\n{chunk}\n\nOtázka: {question}"}
                    ],
                    temperature=1,
                    max_tokens=512,
                    top_p=1,
                    stream=False
                )

                response_text = completion.choices[0].message.content
                final_answer += response_text + "\n\n"
                logging.debug(f"🟢 Odpověď AI: {response_text}")

            except Exception as e:
                logging.error(f"⛔ Chyba při volání Groq API: {e}")
                return f"⚠️ Chyba při volání Groq API: {e}"

    return final_answer.strip() if final_answer else "⚠️ AI nevrátila žádnou odpověď."

# ✅ API pro AI asistenta
@app.route('/ask', methods=['POST'])
def ask():
    question = request.form.get("question", "").strip()
    source = request.form.get("source", "").strip()
    if not question or not source:
        return jsonify({"error": "Zadejte otázku a vyberte zdroj!"})
    return jsonify({"answer": ask_groq(question, source)})

# ✅ Hlavní webová stránka
@app.route('/')
def index():
    return render_template('index.html', documents=legislativa_db.to_dict(orient="records"), sources=load_sources())

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
