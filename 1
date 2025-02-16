from flask import Flask, render_template, request, send_file
import os
import pandas as pd
import requests
from fpdf import FPDF

app = Flask(__name__)

# Vytvoření základní struktury databáze
columns = ["Název dokumentu", "Kategorie", "Datum vydání / aktualizace", "Odkaz na zdroj", "Shrnutí obsahu", "Soubor"]
legislativa_db = pd.DataFrame(columns=columns)

# Přidání základních legislativních dokumentů
data = [
    ["Zákon č. 111/1998 Sb., o vysokých školách", "VŠ obecně", "2021-01-01", "https://www.msmt.cz/dokumenty/zakon-c-111-1998-sb-o-vysokych-skolach", "Upravuje postavení a organizaci VŠ v ČR.", "https://www.msmt.cz/file/54263/"],
    ["Statut Univerzity Karlovy", "UK", "2020-11-01", "https://cuni.cz/UK-146.html", "Definuje poslání a organizační strukturu UK.", "https://cuni.cz/UK-146-version1-2020_statut.pdf"],
    ["Studijní a zkušební řád Univerzity Karlovy", "UK", "2017-10-01", "https://cuni.cz/UK-146.html", "Stanovuje pravidla pro organizaci studia na UK.", "https://cuni.cz/UK-146-version1-2017_studijni_a_zkusebni_rad.pdf"],
    ["Disciplinární řád pro studenty UK", "UK", "2017-10-01", "https://cuni.cz/UK-146.html", "Upravuje disciplinární přestupky studentů.", "https://cuni.cz/UK-146-version1-2017_disciplinarni_rad_pro_studenty.pdf"],
    ["Statut FTVS UK", "FTVS", "2017-07-01", "https://ftvs.cuni.cz/FTVS-83.html", "Definuje organizační strukturu FTVS.", "https://ftvs.cuni.cz/FTVS-83-version1-2017_statut.pdf"],
    ["Organizační řád FTVS UK", "FTVS", "2024-04-30", "https://ftvs.cuni.cz/FTVS-83.html", "Upravuje vnitřní organizaci fakulty.", "https://ftvs.cuni.cz/FTVS-83-version1-2024_organizacni_rad.pdf"],
]

# Přidání dat do databáze
legislativa_db = pd.DataFrame(data, columns=columns)

def download_pdf(pdf_url, filename):
    response = requests.get(pdf_url, stream=True)
    if response.status_code == 200:
        with open(filename, "wb") as file:
            file.write(response.content)
        return filename
    return None

def export_to_pdf(dataframe, filename):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    for i, row in dataframe.iterrows():
        pdf.cell(200, 10, txt=f"{row['Název dokumentu']} - {row['Datum vydání / aktualizace']}", ln=True)
    pdf.output(filename)
    return filename

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    keyword = request.form.get("keyword", "").lower()
    results = legislativa_db[legislativa_db.apply(lambda row: keyword in row.to_string().lower(), axis=1)]
    return render_template('index.html', results=results.to_dict(orient="records"))

@app.route('/download/<int:doc_id>')
def download(doc_id):
    if doc_id < len(legislativa_db):
        pdf_url = legislativa_db.iloc[doc_id]["Soubor"]
        filename = f"downloaded_{doc_id}.pdf"
        filepath = download_pdf(pdf_url, filename)
        if filepath:
            return send_file(filepath, as_attachment=True)
    return "Soubor nelze stáhnout."

@app.route('/export_excel')
def export_excel():
    filename = "legislativa_export.xlsx"
    legislativa_db.to_excel(filename, index=False)
    return send_file(filename, as_attachment=True)

@app.route('/export_filtered_excel', methods=['POST'])
def export_filtered_excel():
    keyword = request.form.get("keyword", "").lower()
    filtered_results = legislativa_db[legislativa_db.apply(lambda row: keyword in row.to_string().lower(), axis=1)]
    filename = "legislativa_filtered_export.xlsx"
    filtered_results.to_excel(filename, index=False)
    return send_file(filename, as_attachment=True)

@app.route('/export_filtered_pdf', methods=['POST'])
def export_filtered_pdf():
    keyword = request.form.get("keyword", "").lower()
    filtered_results = legislativa_db[legislativa_db.apply(lambda row: keyword in row.to_string().lower(), axis=1)]
    filename = "legislativa_filtered_export.pdf"
    filepath = export_to_pdf(filtered_results, filename)
    return send_file(filepath, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
