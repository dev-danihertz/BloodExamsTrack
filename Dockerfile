FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Criar pasta para o banco de dados se necessário
RUN mkdir -p /app/data

# Variável de ambiente para o SQLite persistir no volume do Fly
ENV DATABASE_URL=sqlite:////app/data/blood_exams.db

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
