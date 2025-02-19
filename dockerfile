# Použití Python image
FROM python:3.10

# Nastavení pracovního adresáře
WORKDIR /app

# Zkopírování souborů
COPY . .

# Instalace závislostí
RUN pip install --no-cache-dir -r requirements.txt

# Exponování portu
EXPOSE 8000

# Spuštění FastAPI serveru
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

