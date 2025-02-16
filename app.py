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

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Vytvoření základní struktury databáze
columns = ["Název dokumentu", "Kategorie", "Datum vydání / aktualizace", "Odkaz na zdroj", "Shrnutí obsahu", "Soubor", "Klíčová slova", "Původní obsah"]
urls = ["https://cuni.cz/UK-146.html", "https://ftvs.cuni.cz/FTVS-83.html"]
legislativa_db = pd.concat([scrape_legislation(url) for url in urls], ignore_index=True)

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

# Funkce pro porovnání verzí dokumentů
def compare_versions(old_text, new_text):
    diff = difflib.unified_diff(old_text.splitlines(), new_text.splitlines(), lineterm="")
    return "\n".join(diff)

# Funkce pro automatickou kontrolu aktualizací
def update_legislation():
    global legislativa_db
    urls = ["https://cuni.cz/UK-146.html", "https://ftvs.cuni.cz/FTVS-83.html"]
    while True:
        print("Kontrola aktualizací předpisů...")
        new_data = pd.concat([scrape_legislation(url) for url in urls], ignore_index=True)
        
        if not new_data.equals(legislativa_db):
            print("Byly nalezeny nové nebo aktualizované předpisy. Aktualizace databáze...")
            message = "Byly nalezeny nové nebo změněné předpisy na stránkách UK a FTVS. Zkontrolujte je ve vaší aplikaci."
            send_email_update(message)
            flash("Byly nalezeny nové předpisy! Databáze byla aktualizována.", "info")
            legislativa_db = new_data
        time.sleep(86400)  # Kontrola jednou denně

# Spuštění automatické kontroly v samostatném vlákně
thread = threading.Thread(target=update_legislation, daemon=True)
thread.start()

@app.route('/')
def index():
    return render_template('index.html', documents=legislativa_db.to_dict(orient="records"))

@app.route('/compare/<int:doc_id>')
def compare(doc_id):
    if doc_id < len(legislativa_db):
        old_content = legislativa_db.iloc[doc_id]["Původní obsah"]
        new_content = "Nový obsah dokumentu zde"  # Zde by bylo nutné stáhnout a extrahovat obsah dokumentu
        changes = compare_versions(old_content, new_content)
        return render_template("compare.html", changes=changes, document=legislativa_db.iloc[doc_id])
    return "Dokument nelze porovnat."

if __name__ == '__main__':
    app.run(debug=True)
