import os
import pandas as pd
import logging
import time
import asyncio
import re  # ✅ Pro hledání klíčových slov v dokumentu
from flask import Flask, render_template, request, jsonify
from bs4 import BeautifulSoup
import fitz
from dotenv import load_dotenv
from groq import Groq

# ✅ Načtení API klíče
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ✅ Inicializace klienta Groq
client = Groq(api_key=GROQ_API_KEY)

app = Flask(__name__)
app.secret_key = "supersecretkey"

logging.basicConfig(level=logging.DEBUG, filename='app.log', filemode='a', format='%(asctime)s - %(levelname)s - %(message)s')

def extract_relevant_paragraphs(text, query, max_paragraphs=5):
    """
    Vyhledá odstavce obsahující klíčová slova dotazu.
    Pokud žádné nenajde, vrátí první 2-3 nejdelší odstavce.
    """
    paragraphs = text.split("\n\n")  # Rozdělení na odstavce
    keywords = query.lower().split()  # Rozdělení otázky na jednotlivá slova

    relevant_paragraphs = [
        para for para in paragraphs if any(word in para.lower() for word in keywords)
    ]

    # Pokud žádný relevantní odstavec nenajdeme, vezmeme nejdelší odstavce
    if not relevant_paragraphs:
        relevant_paragraphs = sorted(paragraphs, key=len, reverse=True)[:max_paragraphs]

    return "\n\n".join(relevant_paragraphs[:max_paragraphs])  # Vrátíme maximálně `max_paragraphs` odstavců

async def ask_groq(question, document):
    """ Pošleme dotaz s pouze relevantními odstavci. """
    text = document["Původní obsah"]
    
    # ✅ Vyhledáme pouze relevantní odstavce
    relevant_text = extract_relevant_paragraphs(text, question)

    # ✅ Kontrola délky tokenů před odesláním
    token_count = len(relevant_text.split()) + len(question.split())
    print(f"📊 Odesíláme {token_count} tokenů")
    
    if token_count > 1500:
        print("⚠️ Text je stále příliš dlouhý, redukujeme ho na 1000 tokenů!")
        relevant_text = " ".join(relevant_text.split()[:1000])

    prompt = f"{relevant_text}\n\nOtázka: {question}\nOdpověď:"

    completion = client.chat.completions.create(
        model="deepseek-r1-distill-qwen-32b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.6,
        max_tokens=500,  # ✅ Každá odpověď max. 500 tokenů
        top_p=0.95,
        stream=False
    )

    return completion.choices[0].message.content.strip()

@app.route('/ask', methods=['POST'])
async def ask():
    question = request.form.get("question", "").strip()
    selected_source = request.form.get("source", "").strip()

    if not question:
        return jsonify({"error": "Zadejte otázku!"})
    if not selected_source:
        return jsonify({"error": "Vyberte webovou stránku!"})

    selected_docs = [doc for doc in legislativa_db.to_dict(orient="records") if doc["Odkaz na zdroj"] == selected_source]

    if not selected_docs:
        return jsonify({"error": "Žádné dokumenty nenalezeny pro vybraný zdroj."})

    tasks = [ask_groq(question, doc) for doc in selected_docs]
    answers = await asyncio.gather(*tasks)
    return jsonify({"answer": "\n\n".join(answers)})

if __name__ == '__main__':
    app.run(debug=True)
