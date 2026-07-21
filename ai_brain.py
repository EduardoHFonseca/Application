import os
import glob
import json
import logging
import re
import zipfile
import xml.etree.ElementTree as ET
import requests
import pypdf
import docx
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
    def extract_file_text(cls, file_path: str) -> str:
        """Extrai texto de forma extensível de arquivos PDF, DOCX e DOC."""
        ext = os.path.splitext(file_path)[1].lower()
        text = ""
        
        if ext == ".pdf":
            try:
                reader = pypdf.PdfReader(file_path)
                for page in reader.pages:
                    text += (page.extract_text() or "") + "\n"
                return text.strip()
            except Exception as e:
                log.error(f"Erro ao ler PDF {file_path}: {e}")
                
        elif ext in [".docx", ".doc"]:
            # Tenta via python-docx primeiro
            try:
                doc = docx.Document(file_path)
                text = "\n".join([p.text for p in doc.paragraphs if p.text])
                if text.strip():
                    return text.strip()
            except Exception:
                pass
                
            # Tenta via zipfile (caso seja docx/openxml com extensão .doc)
            if zipfile.is_zipfile(file_path):
                try:
                    with zipfile.ZipFile(file_path) as z:
                        xml_content = z.read("word/document.xml")
                        tree = ET.fromstring(xml_content)
                        texts = [node.text for node in tree.iter() if node.text]
                        text = " ".join(texts)
                        if text.strip():
                            return text.strip()
                except Exception:
                    pass
                    
            # Fallback para regex de texto limpo em arquivo de texto/XML
            try:
                with open(file_path, "rb") as f:
                    content = f.read().decode("utf-8", errors="ignore")
                    text = re.sub(r"<[^>]+>", " ", content)
                    text = re.sub(r"\s+", " ", text).strip()
                    return text
            except Exception as e:
                log.error(f"Erro no fallback de leitura do arquivo {file_path}: {e}")
                
        return text.strip()

    @classmethod
    def get_base_cvs(cls) -> List[Dict[str, str]]:
        """
        Lê todos os PDFs e documentos Word na pasta source/ e extrai seus conteúdos textuais.
        """
        source_dir = "/home/efonseca/workspace/Application/source"
        all_files = glob.glob(os.path.join(source_dir, "*"))
        cvs = []
        for file_path in all_files:
            filename = os.path.basename(file_path)
            if filename.startswith(".") or filename.endswith(".pptx") or filename.endswith(".gitkeep"):
                continue
            text = cls.extract_file_text(file_path)
            if text:
                cvs.append({
                    "filename": filename,
                    "path": file_path,
                    "content": text
                })
        return cvs

    @classmethod
    def generate_competencias_md(cls, output_path: str = "/home/efonseca/workspace/Application/Competencias.MD") -> str:
        """
        Sintetiza todos os documentos de currículos e cartas de source/ em uma matriz unificada Competencias.MD.
        """
        log.info("Iniciando geração da matriz unificada Competencias.MD...")
        cvs = cls.get_base_cvs()
        if not cvs:
            raise FileNotFoundError("Nenhum documento encontrado na pasta source/")

        cv_texts = "\n\n".join([f"=== ARQUIVO: {cv['filename']} ===\n{cv['content'][:3000]}" for cv in cvs])

        system_prompt = (
            "Você é um arquiteto de carreiras e especialista em sintetizar perfis de liderança de TI e Gestão de Produtos.\n"
            "Sua tarefa é analisar todo o acervo de currículos e cartas de apresentação fornecidos e consolidar um único arquivo "
            "estruturado em Markdown chamado 'Competencias.MD'.\n\n"
            "ESTRUTURA OBRIGATÓRIA DO MARKDOWN:\n"
            "# MATRIZ CONSOLIDADA DE COMPETÊNCIAS & EXPERIÊNCIAS\n\n"
            "## 1. Perfil Profissional Executivo\n"
            "(Resumo das principais áreas de atuação: Gerente de TI, Product Manager/Owner, Consultor de Tecnologia)\n\n"
            "## 2. Matriz de Competências Técnicas & Metodológicas\n"
            "(Lista estruturada por tópicos: Agilidade/Scrum/Kanban, Gestão de Produtos, Governança de TI, Cloud/Infraestrutura, Dados e Analytics, etc.)\n\n"
            "## 3. Histórico de Carreiras & Conquistas Chave\n"
            "(Síntese cronológica das principais realizações e cargos ocupados)\n\n"
            "## 4. Formação Acadêmica, Idiomas & Certificações\n\n"
            "## 5. Respostas de Praxe & Parâmetros Padrão\n"
            "- Pretensão Salarial Inicial: R$ 60.000 / $ 10.000 USD\n"
            "- Localização / Trabalho Remoto: São Paulo, Brasil (Disponível para modelo Remoto ou Híbrido)\n"
            "- Autorização de Trabalho: Brasil / Aberto a processos com visto/sponsorship\n"
        )

        user_prompt = f"DOCUMENTOS DE ORIGEM:\n\n{cv_texts}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            content = cls.call_llm(messages)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)
            log.info(f"Arquivo Competencias.MD gerado com sucesso em: {output_path}")
            return content
        except Exception as e:
            log.error(f"Erro ao gerar Competencias.MD via LLM: {e}")
            fallback_content = "# MATRIZ CONSOLIDADA DE COMPETÊNCIAS\n\nEduardo M. Hermes da Fonseca\nProduct Owner / Product Manager / IT Manager"
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(fallback_content)
            return fallback_content

    @classmethod
    def get_competencias_context(cls) -> str:
        md_path = "/home/efonseca/workspace/Application/Competencias.MD"
        if not os.path.exists(md_path):
            return cls.generate_competencias_md(md_path)
        with open(md_path, "r", encoding="utf-8") as f:
            return f.read()

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
    def customize_cv_text(cls, competencias_text: str, job_title: str, job_description: str) -> Dict[str, str]:
        """
        Usa o LLM para sintetizar um currículo focado na vaga a partir da matriz de Competencias.MD.
        """
        system_prompt = (
            "Você é um especialista em escrita de currículos e ATS (Applicant Tracking Systems). "
            "Sua tarefa é extrair e sintetizar informações da MATRIZ DE COMPETÊNCIAS do candidato para criar um currículo "
            "extremamente personalizado para a vaga informada.\n"
            "Ajuste e customize prioritariamente a seção de RESUMO DE QUALIFICAÇÕES (SUMMARY) e HABILIDADES (SKILLS) para destacar "
            "as competências da vaga. "
            "IMPORTANTE 1: Não invente experiências fictícias. Use a Matriz original.\n"
            "IMPORTANTE 2: EVITE REPETIÇÕES EXAUSTIVAS. O modelo anterior cometeu o erro de repetir a mesma palavra-chave (como 'LGPD' ou 'IA') em quase todas as experiências. Seja elegante, consolide essas informações de forma orgânica e evite o 'keyword stuffing'. A redação deve soar humana e fluida.\n"
            "Retorne um JSON puro com as seguintes chaves:\n"
            "- 'title': Título profissional personalizado (ex: 'Senior Product Manager / Product Owner')\n"
            "- 'summary': Resumo profissional totalmente personalizado e adaptado para a vaga, sem repetições de jargões\n"
            "- 'highlighted_skills': Lista de habilidades mais relevantes para a vaga\n"
            "- 'experience_highlights': Breve seção destacando como as experiências se encaixam na vaga\n"
            "- 'full_original_experience': O histórico cronológico formatado OBRIGATORIAMENTE COMO UMA ÚNICA STRING CONTÍNUA com quebras de linha (\\n). JAMAIS retorne listas de objetos JSON."
        )
        
        user_prompt = (
            f"VAGA:\nTítulo: {job_title}\nDescrição:\n{job_description}\n\n"
            f"MATRIZ DE COMPETÊNCIAS DO CANDIDATO:\n{competencias_text}"
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
                "full_original_experience": competencias_text[:2000] # Fallback de segurança
            }

    @classmethod
    def generate_pdf(cls, data: Dict[str, any], output_path: str):
        """
        Gera um PDF altamente polido e profissional com o CV customizado usando fpdf2.
        """
        # Funcao auxiliar para sanitizar caracteres incompatíveis com a fonte padrão
        def sanitize_text(text: str) -> str:
            if not isinstance(text, str):
                text = str(text)
            return text.replace("–", "-").replace("—", "-").replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'").replace("•", "-")

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
        pdf.cell(0, 10, sanitize_text("Eduardo M. Hermes da Fonseca"), new_x="LMARGIN", new_y="NEXT", align="L")
        
        # Informações de Contato
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(80)
        pdf.cell(0, 5, sanitize_text("Casado - Brasileiro | (+5511) 992 954 344 | fonseca.eduardo@terra.com.br"), new_x="LMARGIN", new_y="NEXT", align="L")
        pdf.cell(0, 5, sanitize_text("LinkedIn: https://br.linkedin.com/in/eduardohermesdaf"), new_x="LMARGIN", new_y="NEXT", align="L")
        pdf.ln(5)
        
        # Título Profissional Customizado
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(50)
        pdf.cell(0, 8, sanitize_text(data.get("title", "Product Specialist")), new_x="LMARGIN", new_y="NEXT", align="L")
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
        pdf.multi_cell(0, 5, sanitize_text(data.get("summary", "")))
        pdf.ln(5)
        
        # Seção: Habilidades em Destaque
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(15, 33, 253)
        pdf.cell(0, 6, "HIGHLIGHTED SKILLS / PRINCIPAIS HABILIDADES", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(50)
        skills_str = ", ".join(data.get("highlighted_skills", []))
        pdf.multi_cell(0, 5, sanitize_text(skills_str))
        pdf.ln(5)
        
        # Seção: Destaques de Experiência Adequada
        if data.get("experience_highlights"):
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(15, 33, 253)
            pdf.cell(0, 6, "EXPERIENCE ALIGNMENT / ALINHAMENTO DE EXPERIÊNCIA", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(50)
            pdf.multi_cell(0, 5, sanitize_text(data.get("experience_highlights", "")))
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
        parsed_lines = []
        
        if isinstance(original_exp, list):
            for item in original_exp:
                if isinstance(item, dict):
                    # O LLM enviou um JSON estruturado para cada experiência
                    pos = item.get('position', item.get('title', item.get('role', '')))
                    period = item.get('period', item.get('date', item.get('duration', '')))
                    company = item.get('company', item.get('empresa', ''))
                    
                    header = str(pos)
                    if company: header += f" - {company}"
                    if period: header += f" | {period}"
                    
                    parsed_lines.append(header)
                    
                    resp = item.get('responsibilities', item.get('description', item.get('descricao', [])))
                    if isinstance(resp, list):
                        for r in resp:
                            parsed_lines.append(f"• {r}")
                    elif isinstance(resp, str):
                        parsed_lines.append(resp)
                        
                    parsed_lines.append("") # Linha em branco para separar
                else:
                    parsed_lines.extend(str(item).split("\n"))
            lines = parsed_lines
        else:
            lines = str(original_exp).split("\n")
            
        cleaned_lines = [sanitize_text(l) for l in lines if "Eduardo M." not in l and "Terra" not in l and "992" not in l]
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
        
        competencias_ctx = ""
        try:
            competencias_ctx = cls.get_competencias_context()
        except Exception:
            pass

        user_prompt = (
            f"VAGA:\nTítulo: {job_title}\n\n"
            f"CURRÍCULO SELECIONADO:\n{cv_text}\n\n"
            f"MATRIZ BASE DE COMPETÊNCIAS DO CANDIDATO:\n{competencias_ctx[:2000]}\n\n"
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
