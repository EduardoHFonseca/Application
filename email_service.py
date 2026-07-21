import os
import base64
import requests
import logging
from typing import Dict, Any

log = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.api_key = os.getenv("AGENTMAIL_API_KEY")
        self.inbox_id = os.getenv("AGENTMAIL_INBOX_ID", "menond@agentmail.to")
        self.base_url = "https://api.agentmail.to/v0"

    def send_application_email(self, job_title: str, qa_pairs: Dict[str, str], pdf_path: str):
        """
        Envia um e-mail com o CV anexo, o título da vaga e as perguntas/respostas dadas.
        """
        if not self.api_key:
            log.warning("AGENTMAIL_API_KEY não configurada no .env. Não foi possível enviar o e-mail de notificação.")
            return None

        # Formata a lista de perguntas e respostas
        qa_lines = []
        for q, a in qa_pairs.items():
            qa_lines.append(f"- **Pergunta:** {q}\n  **Resposta:** {a}")
        formatted_qa = "\n\n".join(qa_lines) if qa_lines else "Nenhuma pergunta adicional foi preenchida."

        text_body = (
            f"Olá,\n\n"
            f"Uma nova candidatura no LinkedIn Easy Apply foi submetida com sucesso!\n\n"
            f"💼 Vaga: {job_title}\n\n"
            f"📝 Perguntas e Respostas Preenchidas:\n"
            f"{formatted_qa}\n\n"
            f"O PDF do currículo customizado gerado e enviado está em anexo."
        )

        html_body = (
            f"<h3>Olá,</h3>"
            f"<p>Uma nova candidatura no LinkedIn Easy Apply foi submetida com sucesso!</p>"
            f"<p>💼 <b>Vaga:</b> {job_title}</p>"
            f"<hr>"
            f"<h4>📝 Perguntas e Respostas Preenchidas:</h4>"
            f"<ul>"
        )
        for q, a in qa_pairs.items():
            html_body += f"<li><b>Pergunta:</b> {q}<br><b>Resposta:</b> <i>{a}</i></li><br>"
        if not qa_pairs:
            html_body += "<li>Nenhuma pergunta adicional foi preenchida.</li>"
        html_body += f"</ul><hr><p>O PDF do currículo customizado gerado e enviado está em anexo.</p>"

        # Prepara o anexo
        attachments = []
        if pdf_path and os.path.exists(pdf_path):
            try:
                with open(pdf_path, "rb") as f:
                    file_data = f.read()
                    base64_data = base64.b64encode(file_data).decode("utf-8")
                
                attachments.append({
                    "filename": os.path.basename(pdf_path),
                    "content_type": "application/pdf",
                    "content": base64_data,
                    "content_disposition": "attachment"
                })
            except Exception as e:
                log.error(f"Erro ao codificar PDF para anexo de e-mail: {e}")

        # Envia e-mail via AgentMail API
        # Direcionado para o e-mail oficial do projeto
        recipient = "fonseca.eduardo@terra.com.br"
        url = f"{self.base_url}/inboxes/{self.inbox_id}/messages/send"
        
        payload = {
            "to": recipient,
            "subject": f"[LinkedIn Easy Apply] Candidatura Submetida - {job_title}",
            "text": text_body,
            "html": html_body,
        }
        if attachments:
            payload["attachments"] = attachments

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            r = requests.post(url, json=payload, headers=headers, timeout=30)
            r.raise_for_status()
            log.info(f"E-mail de notificação de candidatura enviado com sucesso para {recipient}!")
            return r.json()
        except Exception as e:
            log.error(f"Erro ao enviar e-mail de notificação de candidatura: {e}")
            return None

    def send_cv_generated_email(self, job_title: str, pdf_path: str):
        """
        Envia um e-mail com o CV anexo logo após sua geração, para revisão manual caso a automação falhe.
        """
        if not self.api_key:
            log.warning("AGENTMAIL_API_KEY não configurada no .env. Não foi possível enviar o e-mail.")
            return None

        text_body = (
            f"Olá,\n\n"
            f"Um novo currículo customizado foi gerado com sucesso para a vaga: {job_title}\n\n"
            f"O PDF do currículo está em anexo. Caso o robô não consiga completar a candidatura "
            f"devido a bloqueios do LinkedIn, você pode utilizar este arquivo para se candidatar manualmente.\n"
        )

        html_body = (
            f"<h3>Olá,</h3>"
            f"<p>Um novo currículo customizado foi gerado com sucesso para a vaga: <b>{job_title}</b></p>"
            f"<p>O PDF do currículo está em anexo. Caso o robô não consiga completar a candidatura "
            f"devido a bloqueios do LinkedIn, você pode utilizar este arquivo para se candidatar manualmente.</p>"
        )

        attachments = []
        if pdf_path and os.path.exists(pdf_path):
            try:
                with open(pdf_path, "rb") as f:
                    file_data = f.read()
                    base64_data = base64.b64encode(file_data).decode("utf-8")
                
                attachments.append({
                    "filename": f"CV_{job_title.replace(' ', '_')[:30]}.pdf",
                    "content_type": "application/pdf",
                    "content": base64_data,
                    "content_disposition": "attachment"
                })
            except Exception as e:
                log.error(f"Erro ao codificar PDF: {e}")

        recipient = "fonseca.eduardo@terra.com.br"
        url = f"{self.base_url}/inboxes/{self.inbox_id}/messages/send"
        
        payload = {
            "to": recipient,
            "subject": f"[LinkedIn Easy Apply] CV Gerado (Revisão) - {job_title}",
            "text": text_body,
            "html": html_body,
        }
        if attachments:
            payload["attachments"] = attachments

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            r = requests.post(url, json=payload, headers=headers, timeout=30)
            r.raise_for_status()
            log.info(f"E-mail com CV recém-gerado enviado para {recipient}!")
            return r.json()
        except Exception as e:
            log.error(f"Erro ao enviar e-mail do CV: {e}")
            return None
