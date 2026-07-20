import os
import unittest
from unittest.mock import patch, MagicMock
from ai_brain import AIBrain
from telegram_bot import TelegramHumanFeedback

class TestAIBrain(unittest.TestCase):
    def setUp(self):
        # Mocks para o Azure OpenAI .env
        os.environ["AZURE_OPENAI_KEY"] = "fake_key"
        os.environ["AZURE_OPENAI_ENDPOINT"] = "https://fake.openai.azure.com/"
        os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"] = "gpt-4o-mini"
        os.environ["AZURE_OPENAI_API_VERSION"] = "2024-02-15-preview"

    def test_get_base_cvs(self):
        cvs = AIBrain.get_base_cvs()
        self.assertIsInstance(cvs, list)
        if len(cvs) > 0:
            self.assertIn("filename", cvs[0])
            self.assertIn("content", cvs[0])

    @patch("ai_brain.AIBrain.call_llm")
    def test_select_best_cv(self, mock_call_llm):
        # Mock do retorno da LLM
        mock_call_llm.return_value = '{"best_cv_filename": "CV-EHF-ENG-PO-PM-21.pdf"}'
        
        best_cv = AIBrain.select_best_cv("Product Manager", "Looking for a PM with Agile experience")
        self.assertIsNotNone(best_cv)
        # Deve ter selecionado um CV válido da lista ou retornado o padrão
        self.assertTrue(best_cv["filename"].endswith(".pdf"))

    @patch("ai_brain.AIBrain.call_llm")
    def test_customize_cv_text(self, mock_call_llm):
        mock_call_llm.return_value = (
            '{"title": "Senior Product Manager", '
            '"summary": "Experiente em Agile e Scrum.", '
            '"highlighted_skills": ["Agile", "Scrum"], '
            '"experience_highlights": "Forte fit com a vaga.", '
            '"full_original_experience": "Empresa X, Empresa Y"}'
        )
        fake_cv = {"filename": "test.pdf", "content": "Original text"}
        custom_data = AIBrain.customize_cv_text(fake_cv, "Senior PM", "Agile position")
        
        self.assertEqual(custom_data["title"], "Senior Product Manager")
        self.assertEqual(custom_data["summary"], "Experiente em Agile e Scrum.")
        self.assertIn("Agile", custom_data["highlighted_skills"])

    def test_generate_pdf(self):
        data = {
            "title": "Senior Product Manager",
            "summary": "Resumo de teste altamente personalizado para demonstrar que o PDF é gerado perfeitamente.",
            "highlighted_skills": ["Agile", "Scrum", "Product Roadmap"],
            "experience_highlights": "Destaques das experiências anteriores em liderança.",
            "full_original_experience": "Eduardo M. Hermes da Fonseca\n2020-2024: Product Manager na Empresa Exemplo."
        }
        output_path = "/home/efonseca/workspace/Application/test_custom_cv.pdf"
        
        if os.path.exists(output_path):
            os.remove(output_path)
            
        AIBrain.generate_pdf(data, output_path)
        self.assertTrue(os.path.exists(output_path))
        self.assertGreater(os.path.getsize(output_path), 0)
        
        # Limpa arquivo temporário de teste
        if os.path.exists(output_path):
            os.remove(output_path)

    @patch("ai_brain.AIBrain.call_llm")
    def test_answer_question(self, mock_call_llm):
        mock_call_llm.return_value = "Yes"
        ans = AIBrain.answer_question("Do you have 5 years of Agile experience?", "PM", "Agile Job", "CV content")
        self.assertEqual(ans, "Yes")

        mock_call_llm.return_value = "UNANSWERED"
        ans = AIBrain.answer_question("What is your favorite color?", "PM", "Agile Job", "CV content")
        self.assertEqual(ans, "UNANSWERED")


class TestTelegramHumanFeedback(unittest.TestCase):
    @patch("requests.post")
    def test_send_telegram_message(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        mock_post.return_value = mock_response

        res = TelegramHumanFeedback.send_telegram_message("token", "12345", "Hello")
        self.assertIsNotNone(res)
        self.assertTrue(res["ok"])

    @patch("requests.get")
    @patch("telegram_bot.TelegramHumanFeedback.send_telegram_message")
    def test_ask_human_for_answer_timeout(self, mock_send, mock_get):
        # Simula erro de conexão ou timeout sem mensagens novas
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": []}
        mock_get.return_value = mock_response

        ans = TelegramHumanFeedback.ask_human_for_answer("token", "12345", "What is your target salary?", "PM Vaga", timeout_seconds=1)
        self.assertEqual(ans, "UNANSWERED")


from email_service import EmailService

class TestEmailService(unittest.TestCase):
    def setUp(self):
        os.environ["AGENTMAIL_API_KEY"] = "fake_agentmail_key"
        os.environ["AGENTMAIL_INBOX_ID"] = "fake_inbox@agentmail.to"

    @patch("requests.post")
    def test_send_application_email(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        mock_post.return_value = mock_response

        # Cria um PDF temporário para anexo no teste
        temp_pdf = "/home/efonseca/workspace/Application/temp_test_attachment.pdf"
        with open(temp_pdf, "w") as f:
            f.write("Fake PDF Content")

        email_srv = EmailService()
        res = email_srv.send_application_email(
            job_title="Senior Product Manager",
            qa_pairs={"Years of experience?": "5", "Sponsorship?": "No"},
            pdf_path=temp_pdf
        )

        self.assertIsNotNone(res)
        self.assertTrue(res["success"])

        # Limpeza
        if os.path.exists(temp_pdf):
            os.remove(temp_pdf)


from playwright_bot import PlaywrightEasyApplyBot

class TestPlaywrightEasyApplyBot(unittest.TestCase):
    def setUp(self):
        os.environ["LINKEDIN_USERNAME"] = "eduardo.fonseca@terra.com.br"
        os.environ["LINKEDIN_PASSWORD"] = "357M@gnum"
        os.environ["LINKEDIN_PHONE_NUMBER"] = "+5511992954344"
        os.environ["LINKEDIN_POSITIONS"] = "Gerente de TI,Project Manager"
        os.environ["LINKEDIN_LOCATIONS"] = "Brazil,São Paulo,Remote"
        os.environ["LINKEDIN_SALARY"] = "60,000"

    def test_bot_initialization(self):
        bot = PlaywrightEasyApplyBot()
        self.assertEqual(bot.username, "eduardo.fonseca@terra.com.br")
        self.assertEqual(bot.password, "357M@gnum")
        self.assertEqual(bot.phone_number, "+5511992954344")
        self.assertIn("Gerente de TI", bot.positions)
        self.assertIn("Brazil", bot.locations)


if __name__ == "__main__":
    unittest.main()
