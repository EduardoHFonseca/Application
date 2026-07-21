import os
import sys
import time
import glob
import subprocess
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# Carrega variáveis de ambiente ANTES de importar módulos que dependem delas
ENV_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".env"))
load_dotenv(ENV_FILE)

import database
from ai_brain import AIBrain

# Configuração da página Streamlit
st.set_page_config(
    page_title="Application - Dashboard de Candidaturas",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilização visual inspirada na identidade Kantar / AdInsights
st.markdown("""
    <style>
    .main {
        background-color: #f8fafc;
    }
    .stApp {
        font-family: 'Inter', sans-serif;
    }
    .metric-card {
        background-color: #ffffff;
        padding: 1.25rem;
        border-radius: 0.75rem;
        border: 1px solid #e2e8f0;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
        text-align: center;
    }
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        color: #0F21FD;
    }
    .metric-label {
        font-size: 0.875rem;
        color: #64748b;
        font-weight: 500;
    }
    .stButton>button {
        background-color: #0F21FD;
        color: white;
        border-radius: 0.5rem;
        font-weight: 600;
        border: none;
        padding: 0.5rem 1rem;
    }
    .stButton>button:hover {
        background-color: #0012c4;
        color: white;
    }
    </style>
""", unsafe_allow_html=True)

# Inicializa o banco PostgreSQL se necessário
try:
    database.init_db()
except Exception as e:
    st.error(f"Erro ao conectar no PostgreSQL: {e}")

st.title("💼 Application: Automação Agentics & OpenClaw")
st.caption("Painel Executivo de Candidaturas no LinkedIn, Gestão de Competências e Audit Trail")

# ---------------------------------------------------------
# KPIs MÉTIRCAS SUPERIORES
# ---------------------------------------------------------
jobs_list = database.get_all_jobs()
df_jobs = pd.DataFrame(jobs_list) if jobs_list else pd.DataFrame()

total_jobs = len(df_jobs)
applied_jobs = len(df_jobs[df_jobs["status"] == "aplicado"]) if not df_jobs.empty else 0
failed_jobs = len(df_jobs[df_jobs["status"] == "falha"]) if not df_jobs.empty else 0
in_progress_jobs = total_jobs - applied_jobs - failed_jobs

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown(f'<div class="metric-card"><div class="metric-value">{total_jobs}</div><div class="metric-label">Vagas Processadas</div></div>', unsafe_allow_html=True)
with col2:
    st.markdown(f'<div class="metric-card"><div class="metric-value" style="color: #10b981;">{applied_jobs}</div><div class="metric-label">Candidaturas Concluídas</div></div>', unsafe_allow_html=True)
with col3:
    st.markdown(f'<div class="metric-card"><div class="metric-value" style="color: #ef4444;">{failed_jobs}</div><div class="metric-label">Falhas / Interrompidas</div></div>', unsafe_allow_html=True)
with col4:
    st.markdown(f'<div class="metric-card"><div class="metric-value" style="color: #f59e0b;">{in_progress_jobs}</div><div class="metric-label">Em Processamento</div></div>', unsafe_allow_html=True)

st.divider()

# ---------------------------------------------------------
# NAVEGAÇÃO POR ABAS
# ---------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Histórico & Audit Trail",
    "🎯 Candidatura Sob Demanda",
    "⚙️ Filtros & Configurações",
    "📄 Acervo & Matriz Competencias.MD"
])

# ---------------------------------------------------------
# ABA 1: HISTÓRICO & AUDIT TRAIL
# ---------------------------------------------------------
with tab1:
    st.subheader("Histórico de Candidaturas & Perguntas/Respostas")
    
    if df_jobs.empty:
        st.info("Nenhuma candidatura registrada no banco de dados até o momento.")
    else:
        # Filtros de busca
        f_col1, f_col2 = st.columns([1, 3])
        with f_col1:
            status_filter = st.selectbox("Filtrar por Status:", ["Todos", "aplicado", "cv_gerado", "iniciado", "falha"])
        with f_col2:
            search_query = st.text_input("Buscar por Cargo ou Palavra-chave:", "")

        df_filtered = df_jobs.copy()
        if status_filter != "Todos":
            df_filtered = df_filtered[df_filtered["status"] == status_filter]
        if search_query:
            df_filtered = df_filtered[df_filtered["titulo"].str.contains(search_query, case=False, na=False)]

        # Tabela de Vagas
        st.dataframe(
            df_filtered[["id", "linkedin_job_id", "titulo", "status", "criado_em", "url"]],
            use_container_width=True,
            hide_index=True
        )

        st.divider()
        st.subheader("🔍 Detalhamento e Pergunta/Resposta da Vaga Selecionada")
        
        job_options = {f"#{row['id']} - {row['titulo']} (ID LinkedIn: {row['linkedin_job_id']})": row['id'] for _, row in df_filtered.iterrows()}
        if job_options:
            selected_option = st.selectbox("Selecione uma vaga para inspecionar:", list(job_options.keys()))
            selected_job_id = job_options[selected_option]
            
            job_detail = [j for j in jobs_list if j["id"] == selected_job_id][0]
            
            d_col1, d_col2 = st.columns(2)
            with d_col1:
                st.markdown(f"**Título:** {job_detail.get('titulo', 'N/A')}")
                st.markdown(f"**Status:** `{job_detail.get('status', 'N/A')}`")
                st.markdown(f"**URL:** [Acessar Vaga no LinkedIn]({job_detail.get('url', '#')})")
            with d_col2:
                st.markdown(f"**Data de Descoberta:** {job_detail.get('criado_em', 'N/A')}")
                pdf_path = job_detail.get("pdf_custom_path")
                if pdf_path and os.path.exists(pdf_path):
                    with open(pdf_path, "rb") as f:
                        st.download_button(
                            label="📥 Download do CV Customizado (PDF)",
                            data=f.read(),
                            file_name=os.path.basename(pdf_path),
                            mime="application/pdf"
                        )

            st.write("**Histórico de Perguntas e Respostas Preenchidas:**")
            qas = database.get_qa_for_job(selected_job_id)
            if qas:
                df_qas = pd.DataFrame(qas)
                st.dataframe(df_qas[["pergunta", "resposta", "origem", "respondido_em"]], use_container_width=True, hide_index=True)
            else:
                st.write("Nenhuma pergunta adicional foi exigida no formulário desta vaga.")

# ---------------------------------------------------------
# ABA 2: CANDIDATURA SOB DEMANDA
# ---------------------------------------------------------
with tab2:
    st.subheader("Candidatura Direta Sob Demanda")
    st.write("Insira a URL de uma vaga específica do LinkedIn para disparar o pipeline completo de candidatura imediata (extração, IA, customização de CV e submissão).")

    input_url = st.text_input("URL da Vaga no LinkedIn:", placeholder="https://www.linkedin.com/jobs/view/4123456789/")

    if st.button("🚀 Iniciar Candidatura Sob Demanda"):
        if not input_url.strip():
            st.warning("Por favor, informe uma URL válida.")
        else:
            st.info(f"Iniciando candidatura para: {input_url}")
            log_container = st.empty()
            
            cmd = [sys.executable, "playwright_bot.py", "--url", input_url.strip()]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=os.path.dirname(__file__))
            
            full_log = ""
            for line in proc.stdout:
                full_log += line
                log_container.code(full_log[-2000:], language="log")
            
            proc.wait()
            if proc.returncode == 0:
                st.success("Candidatura sob demanda processada com sucesso!")
            else:
                st.error("Ocorreu uma falha durante o processamento da candidatura. Verifique os logs acima.")

# ---------------------------------------------------------
# ABA 3: FILTROS & CONFIGURAÇÕES (.ENV)
# ---------------------------------------------------------
with tab3:
    st.subheader("Parâmetros do Robô & Variáveis de Ambiente")
    st.write("Ajuste as preferências de busca, cargos, regiões e chaves de API sem precisar alterar o código.")

    with st.form("env_form"):
        st.write("### 🔍 Preferências de Busca de Vagas")
        positions_val = st.text_input("Cargos Desejados (separados por vírgula):", value=os.getenv("LINKEDIN_POSITIONS", ""))
        locations_val = st.text_input("Localizações (separados por vírgula):", value=os.getenv("LINKEDIN_LOCATIONS", ""))
        salary_val = st.text_input("Pretensão Salarial:", value=os.getenv("LINKEDIN_SALARY", "60,000"))
        interval_val = st.number_input("Intervalo do Scheduler (horas):", min_value=1.0, max_value=24.0, value=float(os.getenv("CRAWLER_INTERVAL_HOURS", "4")), step=1.0)

        st.divider()
        st.write("### 🔑 Credenciais do LinkedIn")
        user_val = st.text_input("Usuário / E-mail:", value=os.getenv("LINKEDIN_USERNAME", ""))
        pass_val = st.text_input("Senha:", value=os.getenv("LINKEDIN_PASSWORD", ""), type="password")
        phone_val = st.text_input("Telefone de Contato:", value=os.getenv("LINKEDIN_PHONE_NUMBER", ""))

        st.divider()
        st.write("### 🤖 Telegram & AgentMail")
        tg_token = st.text_input("Telegram Bot Token:", value=os.getenv("TELEGRAM_BOT_TOKEN", ""))
        tg_chat = st.text_input("Telegram Chat ID:", value=os.getenv("TELEGRAM_CHAT_ID", ""))
        agentmail_key = st.text_input("AgentMail API Key:", value=os.getenv("AGENTMAIL_API_KEY", ""))

        submit_env = st.form_submit_button("💾 Salvar Configurações no .env")

        if submit_env:
            new_env_content = f"""# OpenAI Azure Configuration (Cérebro IA)
AZURE_OPENAI_KEY={os.getenv('AZURE_OPENAI_KEY', '')}
AZURE_OPENAI_ENDPOINT={os.getenv('AZURE_OPENAI_ENDPOINT', '')}
AZURE_OPENAI_CHAT_DEPLOYMENT={os.getenv('AZURE_OPENAI_CHAT_DEPLOYMENT', 'gpt-4o-mini')}
AZURE_OPENAI_EMBEDDING_DEPLOYMENT={os.getenv('AZURE_OPENAI_EMBEDDING_DEPLOYMENT', 'text-embedding-3-small')}
AZURE_OPENAI_API_VERSION={os.getenv('AZURE_OPENAI_API_VERSION', '2024-02-15-preview')}

# Telegram Human-in-the-Loop Configuration
TELEGRAM_BOT_TOKEN={tg_token}
TELEGRAM_CHAT_ID={tg_chat}

# AgentMail Email Notification Configuration
AGENTMAIL_API_KEY={agentmail_key}
AGENTMAIL_INBOX_ID={os.getenv('AGENTMAIL_INBOX_ID', 'menond@agentmail.to')}

# LinkedIn Credentials Configuration
LINKEDIN_USERNAME={user_val}
LINKEDIN_PASSWORD={pass_val}
LINKEDIN_PHONE_NUMBER={phone_val}

# PostgreSQL Database Configuration
DATABASE_URL={os.getenv('DATABASE_URL', 'postgresql://efonseca:123456@localhost:5432/application_db')}

# Crawler Scheduler Configuration
CRAWLER_INTERVAL_HOURS={interval_val}

# LinkedIn Search Preferences
LINKEDIN_POSITIONS={positions_val}
LINKEDIN_LOCATIONS={locations_val}
LINKEDIN_SALARY={salary_val}
"""
            with open(ENV_FILE, "w", encoding="utf-8") as f:
                f.write(new_env_content)
            st.success("Arquivo .env atualizado com sucesso!")
            load_dotenv(ENV_FILE, override=True)

# ---------------------------------------------------------
# ABA 4: ACERVO & MATRIZ COMPETENCIAS.MD
# ---------------------------------------------------------
with tab4:
    st.subheader("Gestão do Acervo de CVs & Matriz de Competências")
    st.write("Adicione novos currículos/cartas de apresentação ou regenere a matriz de competências unificada do candidato.")

    source_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "source"))
    files = [os.path.basename(f) for f in glob.glob(os.path.join(source_dir, "*")) if not os.path.basename(f).startswith(".") and not f.endswith(".pptx")]

    col_a, col_b = st.columns([1, 1])
    with col_a:
        st.write("### 📁 Arquivos no Acervo (`source/`):")
        for file in files:
            st.markdown(f"- 📄 `{file}`")

        uploaded_files = st.file_uploader("Upload de Novos Currículos ou Cartas (.pdf, .doc, .docx):", accept_multiple_files=True, type=["pdf", "doc", "docx"])
        if uploaded_files:
            for uploaded_file in uploaded_files:
                save_path = os.path.join(source_dir, uploaded_file.name)
                with open(save_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                st.success(f"Arquivo `{uploaded_file.name}` salvo em `source/`!")

    with col_b:
        st.write("### 🧠 Matriz Unificada (`Competencias.MD`)")
        if st.button("⚡ Regenerar Matriz via LLM"):
            with st.spinner("Analisando acervo e sintetizando matriz via Azure OpenAI..."):
                try:
                    AIBrain.generate_competencias_md()
                    st.success("Matriz Competencias.MD regenerada com sucesso!")
                except Exception as e:
                    st.error(f"Erro ao regenerar matriz: {e}")

        md_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "Competencias.MD"))
        if os.path.exists(md_path):
            with open(md_path, "r", encoding="utf-8") as f:
                md_content = f.read()
            st.markdown(md_content)
        else:
            st.info("Arquivo Competencias.MD não encontrado. Clique no botão acima para gerá-lo.")
