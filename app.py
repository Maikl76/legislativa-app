import os
import pandas as pd
import logging
import time
import asyncio
from flask import Flask, render_template, request, jsonify
from bs4 import BeautifulSoup
import fitz
from dotenv import load_dotenv
from groq import Groq
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer

# ✅ Načtení API klíče
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ✅ Inicializace klienta Groq
client = Groq(api_key=GROQ_API_KEY)

app = Flask(__name__)
app.secret_key = "supersecretkey"

logging.basicConfig(level=logging.DEBUG, filename='app.log', filemode='a', format='%(asctime)s - %(levelname)s - %(message)s')

def summarize_text(text, sentences=5):
    """ Shrne dlouhý text do 5 klíčových vět """
    parser = PlaintextParser.from_string(text, Tokenizer("english"))
    summarizer = LsaSummarizer()
    summary = summarizer(parser.document, sentences)
    return " ".join([str(sentence) for sentence in summary])

async def ask_groq(question, document):
    """ Pošleme dotaz pouze s relevantními informacemi """
    text = document["Původní obsah"]
    
    # ✅ Shrnutí textu před odesláním
    summarized_text = summarize_text(text, sentences=3) 

    prompt = f"{summarized_text}\n\n{question}"
    
    completion = client.chat.completions.create(
        model="deepseek-r1-distill-qwen-32b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.6,
        max_tokens=300,  # ✅ Každá odpověď max. 300 tokenů
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
