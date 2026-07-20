import os
import glob
import json
import logging
import requests
import pypdf
from typing import List, Dict, Tuple
from fpdf import FPDF
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

class AIBrain:
    @staticmethod
    def get_config() -> Dict[str, str]:
        return {
            "key": os.getenv("AZURE_OPENAI_KEY", ""),
            "endpoint": os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/"),
            "chat_deployment": os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o-mini"),
            "api_version": os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
        }

    @classmethod
    def call_llm(cls, messages: List[Dict[str, str]], response_format: str = "text") -> str:
        cfg = cls.get_config()
        if not cfg["key"]:
            raise ValueError("AZURE_OPENAI_KEY não configurada no .env")
        
        url = f"{cfg['endpoint']}/openai/deployments/{cfg['chat_deployment']}/chat/completions?api-version={cfg['api_version']}"
        
        headers = {
            "Content-Type": "application/json",
            "api-key": cfg["key"]
        }
        
        payload = {
            "messages": messages,
            "temperature": 0.1
        }
        if response_format == "json":
            payload["response_format"] = {"type": "json_object"}
            
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()

    @classmethod
    def get_base_cvs(cls) -> List[Dict[str, str]]:
        """
        Lê todos os PDFs na pasta source/ e extrai seus conteúdos textuais.
        """
        source_dir = "/home/efonseca/workspace/Application/source"
        pdf_files = glob.glob(os.path.join(source_dir, "*.pdf"))
        cvs = []
        for pdf_path in pdf_files:
            try:
                reader = pypdf.PdfReader(pdf_path)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() or ""
                cvs.append({
                    "filename": os.path.basename(pdf_path),
                    "path": pdf_path,
                    "content": text
                })
            except Exception as e:
                log.error(f"Erro ao ler PDF {pdf_path}: {e}")
        return cvs

    @classmethod
    def select_best_cv(cls, job_title: str, job_description: str) -> Dict[str, str]:
        """
        Usa LLM para analisar qual dos CVs base é o melhor match para a vaga.
        """
        cvs = cls.get_base_cvs()
        if not cvs:
            raise FileNotFoundError("Nenhum CV base em PDF encontrado na pasta source/")
            
        cv_options = "\n\n".join([
            f"--- FILENAME: {cv['filename']} ---\n{cv['content'][:1000]}..." 
            for cv in cvs
        ])
        
        system_prompt = (
            "Você é um recrutador e especialista em carreiras. "
            "Sua tarefa é analisar os currículos disponíveis e decidir qual deles é o melhor "
            "e mais adequado para a vaga descrita pelo usuário.\n"
            "Retorne a sua resposta obrigatoriamente em formato JSON puro, com a chave 'best_cv_filename'."
        )
        
        user_prompt = (
            f"VAGA:\nTítulo: {job_title}\nDescrição:\n{job_description}\n\n"
            f"OPÇÕES DE CURRÍCULO DISPONÍVEIS:\n{cv_options}\n\n"
            "Escolha o currículo com o perfil de idioma correto (se a vaga for em inglês, prefira o CV em inglês; "
            "se for em português, o CV em português) e com a especialidade mais aderente (ex: PO/PM, IT Manager, etc.)."
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            res_text = cls.call_llm(messages, response_format="json")
            res_json = json.loads(res_text)
            best_filename = res_json.get("best_cv_filename")
            for cv in cvs:
                if cv["filename"] == best_filename:
                    return cv
            # Fallback para o primeiro
            return cvs[0]
        except Exception as e:
            log.error(f"Erro ao selecionar melhor CV: {e}")
            return cvs[0]

    @classmethod
    def customize_cv_text(cls, cv: Dict[str, str], job_title: str, job_description: str) -> Dict[str, str]:
        """
        Usa o LLM para reescrever o resumo de qualificações e destacar as habilidades mais aderentes à vaga,
        mantendo os dados cadastrais e o histórico profissional originais do candidato intactos.
        """
        system_prompt = (
            "Você é um especialista em escrita de currículos e ATS (Applicant Tracking Systems). "
            "Sua tarefa é reescrever o Currículo fornecido para torná-lo extremamente personalizado para a vaga informada.\n"
            "Ajuste e customize prioritariamente a seção de RESUMO DE QUALIFICAÇÕES (SUMMARY) e HABILIDADES (SKILLS) para destacar "
            "exatamente as competências que a vaga exige. "
            "IMPORTANTE: Não invente experiências fictícias. Apenas enfatize e use as palavras-chave adequadas com base no currículo original do candidato.\n"
            "Retorne um JSON puro com as seguintes chaves:\n"
            "- 'title': Título profissional personalizado (ex: 'Senior Product Manager / Product Owner')\n"
            "- 'summary': Resumo profissional totalmente personalizado e adaptado para a vaga\n"
            "- 'highlighted_skills': Lista de habilidades mais relevantes para a vaga (ex: ['Agile', 'Scrum', 'Product Roadmap'])\n"
            "- 'experience_highlights': Uma breve seção destacando como as experiências anteriores se encaixam nesta vaga específica\n"
            "- 'full_original_experience': O histórico de experiências originais adaptado de forma limpa."
        )
        
        user_prompt = (
            f"VAGA:\nTítulo: {job_title}\nDescrição:\n{job_description}\n\n"
            f"CURRÍCULO ORIGINAL:\n{cv['content']}"
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            res_text = cls.call_llm(messages, response_format="json")
            return json.loads(res_text)
        except Exception as e:
            log.error(f"Erro ao customizar CV: {e}")
            return {
                "title": job_title,
                "summary": "Profissional experiente focado em resultados de negócios e tecnologia.",
                "highlighted_skills": ["Gestão", "Liderança", "Agilidade"],
                "experience_highlights": "Sólida experiência em cargos de gestão e liderança técnica.",
                "full_original_experience": cv["content"]
            }

    @classmethod
    def generate_pdf(cls, data: Dict[str, any], output_path: str):
        """
        Gera um PDF altamente polido e profissional com o CV customizado usando fpdf2.
        """
        class PDF(FPDF):
            def header(self):
                # Cabeçalho elegante
                self.set_fill_color(15, 33, 253) # Kantar Blue (#0F21FD)
                self.rect(0, 0, 210, 15, "F")
                self.ln(10)
                
            def footer(self):
                self.set_y(-15)
                self.set_font("Helvetica", "I", 8)
                self.set_text_color(128)
                self.cell(0, 10, f"Page {self.page_no()}", align="C")

        pdf = PDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)
        
        # Nome
        pdf.set_font("Helvetica", "B", 20)
        pdf.set_text_color(15, 33, 253)
        pdf.cell(0, 10, "Eduardo M. Hermes da Fonseca", new_x="LMARGIN", new_y="NEXT", align="L")
        
        # Informações de Contato
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(80)
        pdf.cell(0, 5, "Casado - Brasileiro | (+5511) 992 954 344 | fonseca.eduardo@terra.com.br", new_x="LMARGIN", new_y="NEXT", align="L")
        pdf.cell(0, 5, "LinkedIn: https://br.linkedin.com/in/eduardohermesdaf", new_x="LMARGIN", new_y="NEXT", align="L")
        pdf.ln(5)
        
        # Título Profissional Customizado
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(50)
        pdf.cell(0, 8, data.get("title", "Product Specialist"), new_x="LMARGIN", new_y="NEXT", align="L")
        pdf.ln(3)
        
        # Linha separadora
        pdf.set_draw_color(200)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)
        
        # Seção: Resumo Profissional
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(15, 33, 253)
        pdf.cell(0, 6, "PROFESSIONAL SUMMARY / RESUMO PROFISSIONAL", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(50)
        pdf.multi_cell(0, 5, data.get("summary", ""))
        pdf.ln(5)
        
        # Seção: Habilidades em Destaque
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(15, 33, 253)
        pdf.cell(0, 6, "HIGHLIGHTED SKILLS / PRINCIPAIS HABILIDADES", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(50)
        skills_str = ", ".join(data.get("highlighted_skills", []))
        pdf.multi_cell(0, 5, skills_str)
        pdf.ln(5)
        
        # Seção: Destaques de Experiência Adequada
        if data.get("experience_highlights"):
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(15, 33, 253)
            pdf.cell(0, 6, "EXPERIENCE ALIGNMENT / ALINHAMENTO DE EXPERIÊNCIA", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(50)
            pdf.multi_cell(0, 5, data.get("experience_highlights", ""))
            pdf.ln(5)
            
        # Seção: Histórico Profissional
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(15, 33, 253)
        pdf.cell(0, 6, "PROFESSIONAL EXPERIENCE & EDUCATION / HISTÓRICO PROFISSIONAL", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(50)
        
        # Multi_cell para todo o texto das experiências originais adaptadas de forma limpa
        original_exp = data.get("full_original_experience", "")
        # Remove eventuais cabeçalhos duplicados do original para o PDF ficar limpo
        lines = original_exp.split("\n")
        cleaned_lines = [l for l in lines if "Eduardo M." not in l and "Terra" not in l and "992" not in l]
        pdf.multi_cell(0, 5, "\n".join(cleaned_lines))
        
        # Salva o arquivo final
        pdf.output(output_path)
        log.info(f"PDF customizado gerado com sucesso em: {output_path}")

    @classmethod
    def answer_question(cls, question: str, job_title: str, job_description: str, cv_text: str, salary_target: str = "60,000") -> str:
        """
        Usa o LLM para responder à pergunta de Easy Apply baseando-se no currículo real do candidato.
        """
        system_prompt = (
            "Você é o assistente virtual do candidato Eduardo M. Hermes da Fonseca.\n"
            "Sua função é responder à pergunta de candidatura do LinkedIn fornecida de forma precisa, profissional e verdadeira, "
            "com base estritamente no currículo do candidato fornecido.\n\n"
            "DIRETRIZES DE RESPOSTA:\n"
            "- Se a pergunta for Sim/Não (ex: 'Você tem experiência com X?'): responda apenas com 'Yes' ou 'No' se possível. "
            "Se for em português, responda com 'Sim' ou 'Não'.\n"
            "- Se a pergunta pedir quantidade de anos de experiência (ex: 'Quantos anos de experiência você tem em gestão de produtos?'): "
            "calcule a quantidade real com base no currículo e responda apenas com o número inteiro (ex: '5' ou '10').\n"
            "- Se a pergunta for sobre pretensão salarial (ex: 'Qual a sua pretensão salarial?'): "
            f"responda com a pretensão desejada do candidato: '{salary_target}'.\n"
            "- Se a pergunta for de múltipla escolha (ex: 'Qual o seu nível de escolaridade?'): "
            "escolha a opção mais adequada com base no currículo.\n"
            "- Se você realmente NÃO conseguir deduzir a resposta a partir do currículo, retorne exatamente: 'UNANSWERED'."
        )
        
        user_prompt = (
            f"VAGA:\nTítulo: {job_title}\n\n"
            f"CURRÍCULO DO CANDIDATO:\n{cv_text}\n\n"
            f"PERGUNTA DA CANDIDATURA:\n{question}"
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            return cls.call_llm(messages).strip()
        except Exception as e:
            log.error(f"Erro ao responder à pergunta via LLM: {e}")
            return "UNANSWERED"
