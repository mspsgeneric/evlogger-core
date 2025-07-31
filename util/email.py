import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("BREVO_API_KEY")
MAIL_FROM = os.getenv("MAIL_FROM")
MAIL_NAME = os.getenv("MAIL_NAME")

def enviar_email(destinatario: str, assunto: str, corpo_html: str):
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": API_KEY,
        "content-type": "application/json"
    }
    data = {
        "sender": {
            "name": MAIL_NAME,
            "email": MAIL_FROM
        },
        "to": [{"email": destinatario}],
        "subject": assunto,
        "htmlContent": corpo_html
    }

    response = requests.post(url, json=data, headers=headers)

    if response.status_code >= 200 and response.status_code < 300:
        print("✅ E-mail enviado com sucesso!")
    else:
        print("❌ Erro ao enviar e-mail:")
        print(response.status_code)
        print(response.text)
