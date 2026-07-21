import sys
import os
import logging
from dotenv import load_dotenv
load_dotenv("/home/efonseca/workspace/Application/.env")

from email_service import EmailService

logging.basicConfig(level=logging.INFO)
srv = EmailService()
res = srv.send_cv_generated_email("Vaga Teste Einstein", "/home/efonseca/workspace/Application/custom_cv.pdf")
print("RESULT:", res)
