import os
import time
import json
import logging
import random
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page, BrowserContext
from ai_brain import AIBrain
from telegram_bot import TelegramHumanFeedback
from email_service import EmailService

# Configura Logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

load_dotenv()

STATE_FILE = "state.json"

class PlaywrightEasyApplyBot:
    def __init__(self):
        self.username = os.getenv("LINKEDIN_USERNAME")
        self.password = os.getenv("LINKEDIN_PASSWORD")
        self.phone_number = os.getenv("LINKEDIN_PHONE_NUMBER", "")
        self.salary = os.getenv("LINKEDIN_SALARY", "60,000")
        
        # Carrega posições e localizações
        pos_str = os.getenv("LINKEDIN_POSITIONS", "Gerente de TI,Project Manager")
        loc_str = os.getenv("LINKEDIN_LOCATIONS", "Brazil,São Paulo,Remote")
        self.positions = [p.strip() for p in pos_str.split(",") if p.strip()]
        self.locations = [l.strip() for l in loc_str.split(",") if l.strip()]

        # Estado da vaga sendo processada para e-mail
        self.answers_this_job = {}
        self.current_cv_text = ""

        # Instancia e-mail
        self.email_srv = EmailService()

    def start(self):
        log.info("Iniciando Motor de Navegação Playwright...")
        with sync_playwright() as p:
            # Lança o navegador Chromium em modo headless para VM SSH
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--remote-debugging-port=9222"
                ]
            )

            # Persistência de Sessão
            if os.path.exists(STATE_FILE):
                log.info(f"Carregando sessão persistida do LinkedIn de {STATE_FILE}...")
                context = browser.new_context(
                    storage_state=STATE_FILE,
                    viewport={"width": 1920, "height": 1080}
                )
            else:
                log.info("Nenhuma sessão salva encontrada. Iniciando fluxo de login...")
                context = browser.new_context(viewport={"width": 1920, "height": 1080})
                self.login(context)

            page = context.new_page()
            
            # Executa o loop principal de busca e candidatura
            try:
                self.run_search_loop(page, context)
            finally:
                context.close()
                browser.close()

    def login(self, context: BrowserContext):
        page = context.new_page()
        log.info("Navegando para a página de login do LinkedIn...")
        page.goto("https://www.linkedin.com/login")
        
        try:
            # Seletores de e-mail/usuário resilientes e múltiplos
            page.locator("input[autocomplete='username']:visible, input[type='email']:visible").first.fill(self.username)
            # Seletores de senha resilientes e múltiplos
            page.locator("input[type='password']:visible").first.fill(self.password)
            # Seletores de botão de envio resilientes e múltiplos
            page.locator("button:has-text('Entrar'):visible, button:has-text('Sign in'):visible, button[type='submit']:visible").first.click()
        except Exception as e:
            page.screenshot(path="login_error.png")
            with open("login_page.html", "w") as f: f.write(page.content())
            log.error(f"Erro ao preencher dados de login: {e}")
            raise e
        
        # Espera o carregamento da página principal para garantir login bem-sucedido
        log.info("Aguardando carregamento após login...")
        try:
            page.wait_for_url("**/feed/**", timeout=15000)
        except Exception as e:
            page.screenshot(path="pos_login.png")
            with open("pos_login.html", "w") as f: f.write(page.content())
            raise e
        
        # Salva o estado da sessão
        context.storage_state(path=STATE_FILE)
        log.info(f"Sessão do LinkedIn salva com sucesso em {STATE_FILE}!")
        page.close()

    def run_search_loop(self, page: Page, context: BrowserContext):
        log.info(f"Iniciando busca para {len(self.positions)} cargos e {len(self.locations)} localizações.")
        
        for pos in self.positions:
            for loc in self.locations:
                log.info(f"Buscando vagas para '{pos}' em '{loc}'...")
                
                # f_LF=f_AL filtra exclusivamente por vagas com o botão "Easy Apply" (Candidatura Simplificada)
                search_url = f"https://www.linkedin.com/jobs/search/?f_LF=f_AL&keywords={pos}&location={loc}"
                try:
                    page.goto(search_url, timeout=60000)
                except Exception as e:
                    page.screenshot(path="search_error.png")
                    with open("search_error.html", "w") as f: f.write(page.content())
                    raise e
                try:
                    page.wait_for_load_state("networkidle")
                except Exception:
                    pass
                
                # Rolagem para carregar os cards de vagas à esquerda
                self.scroll_jobs_list(page)
                
                # Extrai os IDs das vagas carregadas
                job_ids = self.extract_job_ids(page)
                log.info(f"Encontradas {len(job_ids)} vagas elegíveis nesta página.")
                
                for job_id in job_ids:
                    try:
                        self.process_job_application(page, job_id)
                    except Exception as e:
                        log.error(f"Erro ao processar vaga {job_id}: {e}")
                    # Pequena pausa humana entre candidaturas
                    time.sleep(random.uniform(3, 7))

    def scroll_jobs_list(self, page: Page):
        """Rolagem para garantir o carregamento das vagas dinamicamente na barra lateral"""
        try:
            # Procura a barra lateral de resultados
            selector = ".jobs-search-results-list"
            if page.locator(selector).count() > 0:
                for i in range(1, 10):
                    page.evaluate(f"document.querySelector('{selector}').scrollTo(0, {i * 300})")
                    time.sleep(0.3)
        except Exception as e:
            log.debug(f"Erro ao rolar lista de vagas: {e}")

    def extract_job_ids(self, page: Page) -> list:
        job_ids = []
        try:
            # Localiza os elementos que contêm atributo 'data-job-id'
            elements = page.locator("[data-job-id]").all()
            for el in elements:
                job_id = el.get_attribute("data-job-id")
                if job_id and job_id.isdigit() and job_id not in job_ids:
                    job_ids.append(job_id)
        except Exception as e:
            log.error(f"Erro ao extrair IDs de vagas: {e}")
        return job_ids

    def process_job_application(self, page: Page, job_id: str):
        log.info(f"Analisando vaga ID: {job_id}...")
        
        # Abre a página direta do job
        page.goto(f"https://www.linkedin.com/jobs/view/{job_id}")
        page.wait_for_load_state("domcontentloaded")
        time.sleep(2)
        
        # Extrai título e descrição da vaga
        title_loc = page.locator(".job-details-jobs-unified-top-card__job-title, .jobs-unified-top-card__job-title")
        job_title = title_loc.first.text_content().strip() if title_loc.count() > 0 else page.title()
        
        desc_loc = page.locator(".jobs-description, .jobs-description-content")
        job_desc = desc_loc.first.text_content().strip() if desc_loc.count() > 0 else ""
        
        log.info(f"Vaga carregada: '{job_title}'")
        
        # [HOOK CÉREBRO IA] - Seleciona e gera o currículo em PDF dinamicamente
        log.info("Iniciando personalização do currículo com o Cérebro IA...")
        best_cv = AIBrain.select_best_cv(job_title, job_desc)
        log.info(f"Melhor currículo base selecionado: {best_cv['filename']}")
        self.current_cv_text = best_cv["content"]
        
        custom_data = AIBrain.customize_cv_text(best_cv, job_title, job_desc)
        custom_pdf_path = os.path.abspath("custom_cv.pdf")
        AIBrain.generate_pdf(custom_data, custom_pdf_path)
        
        # Reseta o dicionário de respostas dadas para esta vaga específica
        self.answers_this_job = {}

        # Verifica a presença do botão de Easy Apply
        apply_btn = page.locator("button.jobs-apply-button")
        if apply_btn.count() == 0:
            log.info("Vaga não possui botão de Candidatura Simplificada ativo (ou você já se candidatou). Pulando...")
            return
            
        log.info("Clicando no botão de 'Easy Apply'...")
        apply_btn.first.click()
        time.sleep(2)
        
        # Loop para preenchimento de formulários (passo a passo)
        submitted = self.fill_easy_apply_wizard(page, job_title, job_desc, custom_pdf_path)
        
        if submitted:
            log.info(f"Candidatura à vaga '{job_title}' SUBMETIDA com sucesso!")
            # [NOTIFICAÇÃO POR E-MAIL]
            try:
                log.info(f"Disparando e-mail de consolidação de candidatura para fonseca.eduardo@terra.com.br...")
                self.email_srv.send_application_email(
                    job_title=job_title,
                    qa_pairs=self.answers_this_job,
                    pdf_path=custom_pdf_path
                )
            except Exception as e:
                log.error(f"Falha ao enviar e-mail de notificação: {e}")
        else:
            log.info(f"Candidatura à vaga '{job_title}' não foi finalizada ou foi ignorada.")

    def fill_easy_apply_wizard(self, page: Page, job_title: str, job_desc: str, pdf_path: str) -> bool:
        max_steps = 10
        step = 0
        
        while step < max_steps:
            step += 1
            log.info(f"Processando etapa do formulário de candidatura (Passo {step})...")
            
            # Preenche perguntas adicionais se houver erros sinalizados
            self.fill_form_questions(page, job_title, job_desc)
            
            # Faz o upload do currículo se solicitado na tela atual
            self.upload_cv_if_requested(page, pdf_path)
            
            # Desmarca opção de seguir empresa se visível
            follow_checkbox = page.locator("label[for='follow-company-checkbox']")
            if follow_checkbox.count() > 0:
                try:
                    follow_checkbox.first.uncheck()
                except Exception:
                    pass

            # Localiza botões de ação na tela atual do wizard
            next_btn = page.locator("button[aria-label='Continue to next step']")
            review_btn = page.locator("button[aria-label='Review your application']")
            submit_btn = page.locator("button[aria-label='Submit application']")
            
            if submit_btn.count() > 0:
                log.info("Botão de submissão final encontrado! Clicando para enviar candidatura...")
                submit_btn.first.click()
                time.sleep(3)
                return True
                
            elif review_btn.count() > 0:
                log.info("Avançando para etapa de revisão...")
                review_btn.first.click()
                time.sleep(2)
                
            elif next_btn.count() > 0:
                log.info("Avançando para próxima página do formulário...")
                next_btn.first.click()
                time.sleep(2)
                
            else:
                # Se nenhum botão padrão for encontrado, verifica se houve erro insolúvel ou se a tela de sucesso foi mostrada
                if page.locator(".artdeco-inline-feedback--error").count() > 0:
                    log.warning("Erros de preenchimento pendentes impossibilitam o avanço. Cancelando esta candidatura.")
                    # Clica em fechar
                    close_btn = page.locator("button[aria-label='Dismiss']")
                    if close_btn.count() > 0:
                        close_btn.first.click()
                        # Confirma descarte do rascunho
                        discard_btn = page.locator("button[data-control-name='discard_application_confirm_btn']")
                        if discard_btn.count() > 0:
                            discard_btn.first.click()
                    return False
                break
                
        return False

    def fill_form_questions(self, page: Page, job_title: str, job_desc: str):
        """Encontra campos de formulário na etapa e preenche usando o Cérebro de IA ou Telegram"""
        try:
            # Agrupa os campos de formulário pelo container do LinkedIn
            sections = page.locator(".jobs-easy-apply-form-section__grouping").all()
            for sec in sections:
                label_loc = sec.locator("label")
                if label_loc.count() == 0:
                    continue
                question = label_loc.first.text_content().strip()
                
                # Se for número de telefone padrão, preenche automaticamente
                if "phone" in question.lower() or "celular" in question.lower():
                    inp = sec.locator("input[type='text']")
                    if inp.count() > 0 and not inp.first.input_value():
                        inp.first.fill(self.phone_number)
                    continue

                # Evita re-preenchimento de campos já válidos
                # Procura caixa de texto
                text_input = sec.locator("input[type='text'], textarea")
                if text_input.count() > 0:
                    if text_input.first.input_value():
                        continue  # Já preenchido
                    
                    # [IA / TELEGRAM] - Resolve resposta
                    answer = self.resolve_question_answer(question, job_title, job_desc)
                    text_input.first.fill(answer)
                    time.sleep(1)

                # Procura botões de rádio (ex: Sim/Não)
                radio_inputs = sec.locator("input[type='radio']")
                if radio_inputs.count() > 0:
                    # Verifica se algum já está selecionado
                    already_selected = False
                    for i in range(radio_inputs.count()):
                        if radio_inputs.nth(i).is_checked():
                            already_selected = True
                            break
                    if already_selected:
                        continue
                        
                    # Resolve resposta
                    answer = self.resolve_question_answer(question, job_title, job_desc)
                    # Seleciona o rádio button correspondente (compara valor Sim/Não/Yes/No)
                    matched = False
                    for i in range(radio_inputs.count()):
                        radio_label = sec.locator("label").nth(i + 1) # Primeiro label costuma ser a pergunta
                        if radio_label.count() > 0 and answer.lower() in radio_label.text_content().lower():
                            radio_inputs.nth(i).click()
                            matched = True
                            break
                    # Fallback para o primeiro se não encontrar match exato
                    if not matched and radio_inputs.count() > 0:
                        radio_inputs.first.click()
                    time.sleep(1)

                # Procura caixas de seleção (Select/Dropdown)
                select_input = sec.locator("select")
                if select_input.count() > 0:
                    # Resolve resposta
                    answer = self.resolve_question_answer(question, job_title, job_desc)
                    try:
                        select_input.first.select_option(label=answer)
                    except Exception:
                        # Fallback simples para a primeira opção válida
                        try:
                            select_input.first.select_option(index=1)
                        except Exception:
                            pass
                    time.sleep(1)

        except Exception as e:
            log.error(f"Erro ao preencher questões adicionais: {e}")

    def resolve_question_answer(self, question: str, job_title: str, job_desc: str) -> str:
        """Invoca a Inteligência Artificial e, caso ela não saiba, recorre ao Telegram do Usuário"""
        log.info(f"Analisando pergunta: '{question}'...")
        
        answer = "UNANSWERED"
        try:
            answer = AIBrain.answer_question(question, job_title, job_desc, self.current_cv_text, self.salary)
        except Exception as e:
            log.error(f"Erro ao obter resposta da IA para '{question}': {e}")
            
        if answer == "UNANSWERED" or not answer:
            log.info(f"A IA não soube responder à pergunta. Solicitando intervenção no Telegram...")
            telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
            telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
            
            if telegram_token and telegram_chat_id:
                answer = TelegramHumanFeedback.ask_human_for_answer(telegram_token, telegram_chat_id, question, job_title)
            else:
                log.warning("Configurações do Telegram ausentes. Usando resposta padrão automática.")
                answer = "Yes"

        log.info(f"Pergunta: '{question}' -> Resposta: '{answer}'")
        self.answers_this_job[question] = answer
        return answer

    def upload_cv_if_requested(self, page: Page, pdf_path: str):
        """Preenche o campo de upload de currículo na tela atual se solicitado"""
        try:
            # Procura campos de upload de arquivos (input type=file)
            file_inputs = page.locator("input[type='file']").all()
            for inp in file_inputs:
                accept_attr = inp.get_attribute("accept") or ""
                # Geralmente currículos aceitam PDF/Word
                if "pdf" in accept_attr.lower() or "document" in accept_attr.lower() or inp.get_attribute("name") == "file":
                    log.info(f"Campo de upload de currículo localizado! Fazendo upload de: {pdf_path}...")
                    inp.set_input_files(pdf_path)
                    time.sleep(2)
        except Exception as e:
            log.debug(f"Nenhum campo de upload de arquivos na tela atual ou erro no upload: {e}")

if __name__ == "__main__":
    bot = PlaywrightEasyApplyBot()
    bot.start()
