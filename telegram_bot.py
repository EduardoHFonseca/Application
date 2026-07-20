import os
import time
import requests
import logging

log = logging.getLogger(__name__)

class TelegramHumanFeedback:
    @staticmethod
    def send_telegram_message(token: str, chat_id: str, text: str):
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        try:
            r = requests.post(url, json=payload, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log.error(f"Erro ao enviar mensagem para o Telegram: {e}")
            return None

    @classmethod
    def ask_human_for_answer(cls, token: str, chat_id: str, question: str, job_title: str, timeout_seconds: int = 300) -> str:
        """
        Envia a pergunta ao Telegram do usuário e aguarda ativamente (polling) por uma resposta.
        Retorna a resposta do usuário ou 'UNANSWERED' se houver timeout ou erro.
        """
        if not token or not chat_id:
            log.warning("Telegram_BOT_TOKEN ou TELEGRAM_CHAT_ID não configurados no .env. Pulando interação humana.")
            return "UNANSWERED"

        # 1. Obter o último ID de update para ignorar mensagens antigas
        get_updates_url = f"https://api.telegram.org/bot{token}/getUpdates"
        last_update_id = 0
        try:
            r = requests.get(get_updates_url, params={"limit": 1, "offset": -1}, timeout=15)
            if r.status_code == 200:
                results = r.json().get("result", [])
                if results:
                    last_update_id = results[0]["update_id"]
        except Exception as e:
            log.error(f"Erro ao obter atualizações iniciais do Telegram: {e}")

        # 2. Enviar a pergunta
        text = (
            f"❓ *PERGUNTA NÃO IDENTIFICADA NO LINKEDIN!*\n\n"
            f"💼 *Vaga:* {job_title}\n"
            f"📝 *Pergunta:* _{question}_\n\n"
            f"👉 Por favor, envie a resposta exata a ser inserida no formulário. (Timeout: {timeout_seconds // 60} min)"
        )
        cls.send_telegram_message(token, chat_id, text)

        # 3. Polling de respostas
        offset = last_update_id + 1
        start_time = time.time()
        log.info(f"Aguardando resposta do usuário no Telegram (chat_id: {chat_id})...")
        
        while time.time() - start_time < timeout_seconds:
            try:
                r = requests.get(get_updates_url, params={"offset": offset, "timeout": 20}, timeout=25)
                if r.status_code == 200:
                    updates = r.json().get("result", [])
                    for update in updates:
                        message = update.get("message", {})
                        from_chat = message.get("chat", {}).get("id")
                        text_reply = message.get("text")
                        
                        # Verifica se a mensagem veio do chat_id esperado
                        if str(from_chat) == str(chat_id) and text_reply:
                            # Envia confirmação
                            cls.send_telegram_message(
                                token, 
                                chat_id, 
                                f"✅ *Recebido!* Inserindo resposta:\n`{text_reply}`"
                            )
                            return text_reply
                        
                        offset = update["update_id"] + 1
                time.sleep(2)
            except Exception as e:
                log.error(f"Erro na escuta do Telegram: {e}")
                time.sleep(5)
                
        # Caso expire o timeout
        cls.send_telegram_message(
            token, 
            chat_id, 
            f"⏰ *Tempo esgotado!* Não recebi resposta a tempo para a vaga: *{job_title}*."
        )
        return "UNANSWERED"
