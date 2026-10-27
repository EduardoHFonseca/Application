import os
import sys
import time
import glob
import json
import subprocess
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# Carrega variáveis de ambiente ANTES de importar módulos que dependem delas
ENV_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".env"))
load_dotenv(ENV_FILE)

import database
from ai_brain import AIBrain
import crawler
from sources import registry as source_registry

# Configuração da página Streamlit
st.set_page_config(
    page_title="Application - Dashboard de Candidaturas",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilização visual inspirada na identidade IBOPE / AdInsights
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
if not df_jobs.empty:
    for column in ("fonte", "source_job_id", "apply_mode"):
        if column not in df_jobs.columns:
            df_jobs[column] = ""

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
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Histórico & Audit Trail",
    "🎯 Candidatura Sob Demanda",
    "🧩 Curação da Base Mestra",
    "⚙️ Filtros & Configurações",
    "📄 Acervo Original & Fontes",
    "🌐 Fontes & Crawler"
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
        f_col1, f_col2, f_col3 = st.columns([1, 1, 3])
        with f_col1:
            status_filter = st.selectbox(
                "Filtrar por Status:",
                ["Todos", "descoberto", "cv_gerado", "aplicado", "iniciado", "falha", "ignorado"],
            )
        with f_col2:
            fonte_options = ["Todas"] + sorted(
                [str(value) for value in df_jobs["fonte"].dropna().unique()]
            )
            fonte_filter = st.selectbox("Filtrar por Fonte:", fonte_options)
        with f_col3:
            search_query = st.text_input("Buscar por Cargo ou Palavra-chave:", "")

        df_filtered = df_jobs.copy()
        if status_filter != "Todos":
            df_filtered = df_filtered[df_filtered["status"] == status_filter]
        if fonte_filter != "Todas":
            df_filtered = df_filtered[df_filtered["fonte"] == fonte_filter]
        if search_query:
            df_filtered = df_filtered[df_filtered["titulo"].str.contains(search_query, case=False, na=False)]

        # Tabela de Vagas
        display_columns = [
            "id", "fonte", "source_job_id", "titulo", "empresa",
            "localizacao", "status", "criado_em",
        ]
        display_columns = [column for column in display_columns if column in df_filtered.columns]
        st.dataframe(
            df_filtered[display_columns],
            use_container_width=True,
            hide_index=True
        )

        st.divider()
        st.subheader("🔍 Detalhamento e Pergunta/Resposta da Vaga Selecionada")
        
        job_options = {
            f"#{row['id']} - {row['titulo']} [{row.get('fonte', '')}:{row.get('source_job_id', '')}]": row['id']
            for _, row in df_filtered.iterrows()
        }
        if job_options:
            selected_option = st.selectbox("Selecione uma vaga para inspecionar:", list(job_options.keys()))
            selected_job_id = job_options[selected_option]
            
            job_detail = [j for j in jobs_list if j["id"] == selected_job_id][0]
            
            d_col1, d_col2 = st.columns(2)
            with d_col1:
                st.markdown(f"**Título:** {job_detail.get('titulo', 'N/A')}")
                st.markdown(f"**Fonte:** `{job_detail.get('fonte', 'linkedin')}` / `{job_detail.get('source_job_id', job_detail.get('linkedin_job_id', ''))}`")
                st.markdown(f"**Status:** `{job_detail.get('status', 'N/A')}`")
                st.markdown(f"**URL:** [Acessar Vaga]({job_detail.get('url', '#')})")
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
    st.subheader("Candidatura Direta Sob Demanda & Geração de CV")
    st.write("Escolha o formato de origem da vaga: por URL pública do LinkedIn ou colando o descritivo direto de uma vaga interna, WhatsApp ou documento.")

    mode = st.radio(
        "Selecione o Modo de Origem da Vaga:",
        ["🌐 URL do LinkedIn (Crawler & Aplicação Automática)", "📝 Descritivo Direto / Vaga Interna (Copy + Paste)"],
        index=0
    )

    st.divider()

    if mode.startswith("🌐"):
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

    else:
        st.write("Cole o título e a descrição completa de uma vaga interna ou recebida por mensagem/documento para gerar um currículo customizado (PDF & ATS) instantaneamente.")

        col_v1, col_v2, col_v3 = st.columns([2, 1, 1])
        with col_v1:
            f_titulo = st.text_input("Título do Cargo / Vaga:", placeholder="Ex: AI Product Manager / Head de TI")
        with col_v2:
            f_empresa = st.text_input("Empresa / Depto:", value="Vaga Interna")
        with col_v3:
            f_lang = st.selectbox("Idioma do CV:", ["🌐 Auto-detectar pelo Idioma da Vaga", "🇺🇸 Forçar Inglês", "🇧🇷 Forçar Português"])

        f_descricao = st.text_area("Descritivo Completo & Requisitos da Vaga (Copy + Paste):", height=250, placeholder="Cole aqui as responsabilidades, requisitos e detalhes da vaga...")

        if st.button("🚀 Gerar Currículo Customizado (PDF & ATS)", type="primary"):
            if not f_titulo.strip() or not f_descricao.strip():
                st.warning("Por favor, preencha o Título do Cargo e o Descritivo da Vaga.")
            else:
                custom_job_id = f"manual_{int(time.time())}"
                output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "custom_cvs"))
                os.makedirs(output_dir, exist_ok=True)
                pdf_path = os.path.join(output_dir, f"cv_vaga_{custom_job_id}.pdf")

                lang_param = "en" if "Inglês" in f_lang else ("pt" if "Português" in f_lang else "auto")

                with st.spinner("Analisando descritivo e sintetizando currículo via Base Mestra Fact-Based no PostgreSQL..."):
                    try:
                        cv_data = AIBrain.customize_cv_text(
                            competencias_text="",
                            job_title=f_titulo.strip(),
                            job_description=f_descricao.strip(),
                            language=lang_param
                        )
                        AIBrain.generate_pdf(cv_data, pdf_path)

                        db_job_id = database.save_or_update_job(
                            linkedin_job_id=custom_job_id,
                            url="manual/interna",
                            titulo=f_titulo.strip(),
                            empresa=f_empresa.strip(),
                            localizacao="Interna/Remoto",
                            descricao=f_descricao.strip(),
                            status="cv_gerado",
                            pdf_custom_path=pdf_path
                        )

                        st.success("🎉 Currículo customizado gerado com sucesso!")
                        st.session_state["last_generated_cv"] = {
                            "title": f_titulo,
                            "cv_data": cv_data,
                            "pdf_path": pdf_path,
                            "job_id": db_job_id
                        }
                    except Exception as e:
                        st.error(f"Erro ao gerar currículo: {e}")

        # Exibe a prévia e botão de download se houver um CV recém-gerado
        last_cv = st.session_state.get("last_generated_cv")
        if last_cv and os.path.exists(last_cv["pdf_path"]):
            st.divider()
            st.subheader("📄 Prévia do Currículo Gerado para a Vaga Interna")

            cv_data = last_cv["cv_data"]

            p_col1, p_col2 = st.columns([3, 1])
            with p_col1:
                st.markdown(f"**Título Profissional Customizado:** `{cv_data.get('title', last_cv['title'])}`")
                st.markdown(f"**Resumo Profissional Executivo:**\n{cv_data.get('summary', '')}")
                skills_list = cv_data.get('highlighted_skills', [])
                st.markdown(f"**Habilidades Chave ATS:** " + ", ".join([f"`{s}`" for s in skills_list]))
            with p_col2:
                with open(last_cv["pdf_path"], "rb") as f:
                    st.download_button(
                        label="📥 Download do CV (PDF)",
                        data=f.read(),
                        file_name=f"Curriculo_{last_cv['title'].replace(' ', '_')}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                        type="primary"
                    )

            with st.expander("🔍 Inspecionar Histórico e Experiências Selecionadas no PDF"):
                exp_text = cv_data.get("full_original_experience", "")
                st.text(exp_text)

# ---------------------------------------------------------
# ABA 3: CURAÇÃO DA BASE MESTRA (FACT-BASED & COPILOTO IA)
# ---------------------------------------------------------
with tab3:
    st.subheader("🧩 Curação da Base Mestra & Copiloto de Enriquecimento IA")
    st.caption("Ajuste e enriqueça a 'Fonte Única da Verdade' do seu histórico profissional no PostgreSQL com o suporte da IA.")

    cur_sub1, cur_sub2, cur_sub3 = st.tabs([
        "👤 1. Acervo de Qualificações Mestre",
        "💼 2. Janelas de Experiência Cronológica",
        "🎓 3. Acervo de Formação & Certificações"
    ])

    # --- SUB-ABA 1: QUALIFICAÇÕES MESTRE ---
    with cur_sub1:
        st.write("### 👤 Acervo de Qualificações e Competências Executivas")
        st.info("Este texto é o repositório amplo onde o motor consulta suas competências de liderança, táticas e metodológicas para montar o Resumo Profissional da vaga.")
        
        q_data = database.get_curacao_qualificacoes()
        
        with st.form("form_qualificacoes"):
            q_texto_input = st.text_area("Acervo de Qualificações (Texto Amplo):", value=q_data.get("texto_acervo", ""), height=250)
            q_tags_input = st.text_input("Tags / Marcadores (separados por vírgula):", value=", ".join(q_data.get("tags", []) or []))
            
            btn_save_q = st.form_submit_button("💾 Salvar Qualificações no Banco", type="primary")
            if btn_save_q:
                tags_list = [t.strip() for t in q_tags_input.split(",") if t.strip()]
                database.save_curacao_qualificacoes(q_texto_input, tags_list)
                st.success("Qualificações salvas com sucesso no PostgreSQL!")
                st.rerun()

    # --- SUB-ABA 2: JANELAS DE EXPERIÊNCIA CRONOLÓGICA (COPILOTO IA) ---
    with cur_sub2:
        st.write("### 💼 Janelas de Experiência Cronológica (Iceberg de Realizações)")
        st.caption("Janelas e cargos são imutáveis na linha do tempo. Adicione todos os detalhes e use o Copiloto IA para expandir siglas (ex: SPB -> Operações Bancárias BACEN).")

        exps_list = database.get_curacao_experiencias()
        
        if not exps_list:
            st.warning("Nenhuma experiência cadastrada no banco. Clique no botão abaixo para rodar o seed inicial do acervo.")
            if st.button("🚀 Iniciar Ingestão / Seed de Experiências"):
                cmd = [sys.executable, "seed_curacao.py"]
                subprocess.run(cmd, cwd=os.path.dirname(__file__))
                st.rerun()
        else:
            exp_options = {f"[{idx+1}/{len(exps_list)}] {e['empresa']} | {e['cargo']} ({e['periodo_inicio']} - {e['periodo_fim']})": e['id'] for idx, e in enumerate(exps_list)}
            selected_exp_label = st.selectbox("Selecione a Janela de Experiência para Curação:", list(exp_options.keys()))
            selected_exp_id = exp_options[selected_exp_label]
            exp_curr = [e for e in exps_list if e['id'] == selected_exp_id][0]

            # Layout 2 Colunas Lado a Lado (60% / 40%)
            col_form, col_copilot = st.columns([3, 2])

            with col_form:
                st.markdown(f"#### 🏢 Editando: **{exp_curr['empresa']}**")
                
                with st.form(f"form_exp_{exp_curr['id']}"):
                    f_empresa = st.text_input("Empresa:", value=exp_curr['empresa'])
                    f_cargo = st.text_input("Cargo:", value=exp_curr['cargo'])
                    
                    c_p1, c_p2 = st.columns(2)
                    with c_p1:
                        f_inicio = st.text_input("Ano / Período Início:", value=str(exp_curr['periodo_inicio']))
                    with c_p2:
                        f_fim = st.text_input("Ano / Período Fim:", value=str(exp_curr['periodo_fim']))
                        
                    f_contexto = st.text_area("Contexto & Escopo (Time, Budget, Faturamento):", value=exp_curr.get('contexto_escopo', ''), height=80)
                    
                    # Bullets
                    bullets_raw = exp_curr.get('bullets_acervo', []) or []
                    if isinstance(bullets_raw, str):
                        try: bullets_raw = json.loads(bullets_raw)
                        except: bullets_raw = [bullets_raw]
                    
                    bullets_text = st.text_area("Bullets / Realizações / Métricas (um por linha):", value="\n".join(bullets_raw), height=200)
                    
                    # Siglas & Projetos (JSON string)
                    siglas_map = exp_curr.get('siglas_projetos', {}) or {}
                    if isinstance(siglas_map, str):
                        try: siglas_map = json.loads(siglas_map)
                        except: siglas_map = {}
                    siglas_text = st.text_area("Dicionário de Siglas & Projetos (Formato CHAVE = VALOR, um por linha, ex: SPB = Sistema de Pagamentos Brasileiro, Operações Bancárias):", value="\n".join([f"{k} = {v}" for k, v in siglas_map.items()]), height=100)
                    
                    # Tags de Domínio
                    tags_arr = exp_curr.get('tags_dominio', []) or []
                    f_tags = st.text_input("Tags de Domínio & Área de Atuação (separadas por vírgula):", value=", ".join(tags_arr))

                    btn_save_exp = st.form_submit_button("💾 Salvar Alterações na Janela", type="primary", use_container_width=True)
                    
                    if btn_save_exp:
                        # Parse Bullets
                        b_list = [b.strip() for b in bullets_text.split("\n") if b.strip()]
                        
                        # Parse Siglas
                        s_dict = {}
                        for line in siglas_text.split("\n"):
                            if "=" in line:
                                k, v = line.split("=", 1)
                                s_dict[k.strip()] = v.strip()
                        
                        # Parse Tags
                        t_list = [t.strip() for t in f_tags.split(",") if t.strip()]
                        
                        database.save_curacao_experiencia(
                            exp_id=exp_curr['id'],
                            empresa=f_empresa.strip(),
                            cargo=f_cargo.strip(),
                            periodo_inicio=f_inicio.strip(),
                            periodo_fim=f_fim.strip(),
                            ordem=exp_curr.get('ordem', 0),
                            contexto_escopo=f_contexto.strip(),
                            bullets_acervo=b_list,
                            siglas_projetos=s_dict,
                            tags_dominio=t_list
                        )
                        st.success(f"Janela de **{f_empresa}** atualizada com sucesso no PostgreSQL!")
                        st.rerun()

            # --- COLUNA DO COPILOTO IA ---
            with col_copilot:
                st.markdown("#### 🤖 Copiloto de Enriquecimento IA")
                st.info("Analisa este bloco procurando siglas ocultas (ex: SPB, CIP, STR) e sugere injeção de palavras-chave para passar nos robôs ATS.")

                if st.button("⚡ Executar Copiloto neste Bloco", use_container_width=True):
                    with st.spinner("Analisando bloco e consultando dicionário de domínio via Azure OpenAI..."):
                        b_list_curr = [b.strip() for b in bullets_text.split("\n") if b.strip()]
                        t_list_curr = [t.strip() for t in f_tags.split(",") if t.strip()]
                        
                        exp_data_payload = {
                            "empresa": exp_curr['empresa'],
                            "cargo": exp_curr['cargo'],
                            "periodo_inicio": exp_curr['periodo_inicio'],
                            "periodo_fim": exp_curr['periodo_fim'],
                            "contexto_escopo": exp_curr.get('contexto_escopo', ''),
                            "bullets_acervo": b_list_curr,
                            "tags_dominio": t_list_curr
                        }
                        copilot_res = AIBrain.analyze_block_copilot(exp_data_payload)
                        st.session_state[f"copilot_res_{exp_curr['id']}"] = copilot_res

                copilot_stored = st.session_state.get(f"copilot_res_{exp_curr['id']}")
                if copilot_stored:
                    st.divider()
                    
                    # 1. Siglas Detectadas
                    siglas_det = copilot_stored.get("siglas_detectadas", [])
                    if siglas_det:
                        st.write("##### 📌 Siglas & Tecnologias Detectadas:")
                        for s in siglas_det:
                            st.markdown(f"**{s.get('sigla')}**: {s.get('significado')}")
                            if s.get('conceitos'):
                                st.caption(f"Conceitos ATS: {', '.join(s.get('conceitos', []))}")
                                
                        if st.button("➕ Injetar Siglas & Conceitos no Dicionário do Bloco", key=f"btn_apply_siglas_{exp_curr['id']}", type="primary"):
                            current_siglas = dict(siglas_map) if isinstance(siglas_map, dict) else {}
                            for s in siglas_det:
                                s_key = s.get('sigla')
                                s_val = f"{s.get('significado')}"
                                if s.get('conceitos'):
                                    s_val += f" ({', '.join(s.get('conceitos'))})"
                                current_siglas[s_key] = s_val
                                
                            database.save_curacao_experiencia(
                                exp_id=exp_curr['id'],
                                empresa=exp_curr['empresa'],
                                cargo=exp_curr['cargo'],
                                periodo_inicio=exp_curr['periodo_inicio'],
                                periodo_fim=exp_curr['periodo_fim'],
                                ordem=exp_curr.get('ordem', 0),
                                contexto_escopo=exp_curr.get('contexto_escopo', ''),
                                bullets_acervo=bullets_raw,
                                siglas_projetos=current_siglas,
                                tags_dominio=tags_arr
                            )
                            st.success("Siglas e conceitos de IA/Tecnologia injetados com sucesso!")
                            st.rerun()
                    
                    st.write(" ")
                    # 2. Tags Sugeridas
                    tags_sug = copilot_stored.get("tags_sugeridas", [])
                    if tags_sug:
                        st.write("##### 🏷️ Sugestão de Palavras-Chave de Domínio & Tech:")
                        st.write(", ".join([f"`{t}`" for t in tags_sug]))
                        
                        if st.button("➕ Aplicar Sugestões de Tags ao Bloco", key=f"btn_apply_tags_{exp_curr['id']}"):
                            current_tags = [t.strip() for t in f_tags.split(",") if t.strip()]
                            for ts in tags_sug:
                                if ts not in current_tags:
                                    current_tags.append(ts)
                                    
                            database.save_curacao_experiencia(
                                exp_id=exp_curr['id'],
                                empresa=exp_curr['empresa'],
                                cargo=exp_curr['cargo'],
                                periodo_inicio=exp_curr['periodo_inicio'],
                                periodo_fim=exp_curr['periodo_fim'],
                                ordem=exp_curr.get('ordem', 0),
                                contexto_escopo=exp_curr.get('contexto_escopo', ''),
                                bullets_acervo=bullets_raw,
                                siglas_projetos=siglas_map,
                                tags_dominio=current_tags
                            )
                            st.success("Tags aplicadas com sucesso!")
                            st.rerun()

                    st.write(" ")
                    # 3. Perguntas Provocativas
                    pergs = copilot_stored.get("perguntas_provocativas", [])
                    if pergs:
                        st.write("##### ❓ Perguntas da IA para Resgatar Memórias:")
                        for p in pergs:
                            st.markdown(f"👉 *{p}*")

    # --- SUB-ABA 3: FORMAÇÃO & CERTIFICAÇÕES ---
    with cur_sub3:
        st.write("### 🎓 Acervo de Formação, MBAs & Certificações")
        
        forms_list = database.get_curacao_formacao()
        if forms_list:
            df_forms = pd.DataFrame(forms_list)
            st.dataframe(df_forms[["id", "tipo", "instituicao", "titulo", "ano", "relevancia_tags"]], use_container_width=True, hide_index=True)
            
        st.divider()
        st.write("#### ➕ Cadastrar / Editar Formação ou Certificação:")
        with st.form("form_add_formacao"):
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                f_tipo = st.selectbox("Tipo:", ["graduacao", "pos_mba", "certificacao", "curso"])
                f_inst = st.text_input("Instituição:", placeholder="Ex: USP / PMI / Scrum Alliance")
                f_ano = st.text_input("Ano / Período:", placeholder="Ex: 2022")
            with col_f2:
                f_titulo = st.text_input("Título / Nome:", placeholder="Ex: PMP / Certified Scrum Master")
                f_tags_form = st.text_input("Tags de Relevância (separadas por vírgula):", placeholder="Ex: Agilidade, Governança, PMP")
                
            btn_save_form = st.form_submit_button("➕ Salvar Formação no Banco", type="primary")
            if btn_save_form:
                if not f_inst or not f_titulo:
                    st.warning("Preencha Instituição e Título.")
                else:
                    t_arr = [t.strip() for t in f_tags_form.split(",") if t.strip()]
                    database.save_curacao_formacao(None, f_tipo, f_inst, f_titulo, f_ano, t_arr)
                    st.success("Formação salva com sucesso!")
                    st.rerun()

# ---------------------------------------------------------
# ABA 4: FILTROS & CONFIGURAÇÕES (.ENV)
# ---------------------------------------------------------
with tab4:
    st.subheader("Parâmetros do Robô & Variáveis de Ambiente")
    st.write("Ajuste as preferências de busca, cargos, regiões e chaves de API sem precisar alterar o código.")

    with st.form("env_form"):
        st.write("### 🔍 Preferências de Busca de Vagas")
        positions_val = st.text_input("Cargos Desejados (separados por vírgula):", value=os.getenv("LINKEDIN_POSITIONS", ""))
        locations_val = st.text_input("Localizações (separados por vírgula):", value=os.getenv("LINKEDIN_LOCATIONS", ""))
        salary_val = st.text_input("Pretensão Salarial:", value=os.getenv("LINKEDIN_SALARY", "60,000"))
        interval_val = st.number_input("Intervalo do Scheduler (horas):", min_value=1.0, max_value=24.0, value=float(os.getenv("CRAWLER_INTERVAL_HOURS", "4")), step=1.0)
        keywords_env = st.text_input("Palavras-chave do crawler multi-fonte:", value=os.getenv("SEARCH_KEYWORDS", ""))
        sources_env = st.text_input("Fontes habilitadas (CRAWLER_SOURCES):", value=os.getenv("CRAWLER_SOURCES", "remotive,wwr,workingnomads"))

        st.divider()
        st.write("### 📄 Geração de Currículo (PDF)")
        template_val = st.selectbox(
            "Template do PDF gerado:",
            options=["harvard", "corporate"],
            index=0 if os.getenv("CV_TEMPLATE", "harvard").strip().lower() != "corporate" else 1,
            help="harvard = layout denso single-column otimizado para ATS (padrão) | corporate = layout legado com faixa de cor",
        )

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

# Roteador local de LLMs livres (FreeLLM-router)
LLM_BASE_URL={os.getenv('LLM_BASE_URL', '')}
LLM_API_KEY={os.getenv('LLM_API_KEY', '')}
LLM_MODEL={os.getenv('LLM_MODEL', 'auto')}

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

# PDF Curriculum Template (harvard | corporate)
CV_TEMPLATE={template_val}

# Crawler Scheduler Configuration
CRAWLER_INTERVAL_HOURS={interval_val}

# Crawler Multi-Fonte
CRAWLER_SOURCES={sources_env}
SEARCH_KEYWORDS={keywords_env}
SEARCH_LOCATIONS={locations_val}
CRAWLER_LIMIT_PER_SOURCE={os.getenv('CRAWLER_LIMIT_PER_SOURCE', '50')}

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
# ABA 5: ACERVO ORIGINAL & FONTES
# ---------------------------------------------------------
with tab5:
    st.subheader("Gestão do Acervo de CVs Originais & Fontes")
    st.write("Adicione novos currículos/cartas de apresentação em PDF ou Word na pasta `source/`.")

    source_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "source"))
    files = [os.path.basename(f) for f in glob.glob(os.path.join(source_dir, "*")) if not os.path.basename(f).startswith(".") and not f.endswith(".pptx")]

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

# ---------------------------------------------------------
# ABA 6: FONTES & CRAWLER MULTI-SITE
# ---------------------------------------------------------
with tab6:
    st.subheader("Crawler Multi-Fonte")
    st.write(
        "Descubra vagas em Remotive, We Work Remotely e Working Nomads, "
        "filtre por cargo/localização e gere CV personalizado sob demanda."
    )

    crawler_config = source_registry.load_config()
    sources_table = pd.DataFrame(source_registry.source_summary(crawler_config))
    st.write("### 📚 Catálogo de Fontes")
    st.dataframe(
        sources_table[["name", "label", "type", "apply_mode", "enabled", "implemented", "fetchable", "url"]],
        use_container_width=True,
        hide_index=True,
    )

    implemented_sources = [
        row["name"] for row in sources_table.to_dict("records")
        if row["fetchable"] and row["name"] != "linkedin"
    ]
    default_sources = [
        row["name"] for row in sources_table.to_dict("records")
        if row["fetchable"] and row["enabled"] and row["name"] != "linkedin"
    ]

    with st.form("crawler_form"):
        st.write("### 🔎 Parâmetros da Coleta")
        selected_sources = st.multiselect(
            "Fontes:",
            options=implemented_sources,
            default=default_sources or implemented_sources,
        )
        keywords_value = st.text_input(
            "Palavras-chave (separadas por vírgula):",
            value=", ".join(source_registry.default_keywords(crawler_config)),
        )
        locations_value = st.text_input(
            "Localizações (separadas por vírgula):",
            value=", ".join(source_registry.default_locations(crawler_config)),
        )
        limit_value = st.number_input(
            "Limite de vagas por fonte:",
            min_value=1,
            max_value=200,
            value=int(os.getenv("CRAWLER_LIMIT_PER_SOURCE", "50")),
            step=10,
        )
        col_cv, col_dry, col_notify = st.columns(3)
        with col_cv:
            with_cv_value = st.checkbox("Gerar CV para vagas novas", value=False)
        with col_dry:
            dry_run_value = st.checkbox("Dry-run (não gravar)", value=True)
        with col_notify:
            notify_value = st.checkbox("Notificar no Telegram", value=True)

        run_crawler = st.form_submit_button("🚀 Executar Coleta")

    if run_crawler:
        if not selected_sources:
            st.warning("Selecione ao menos uma fonte.")
        else:
            keywords = [item.strip() for item in keywords_value.split(",") if item.strip()]
            locations = [item.strip() for item in locations_value.split(",") if item.strip()]
            with st.spinner("Coletando vagas..."):
                try:
                    st.session_state["crawler_summary"] = crawler.collect(
                        source_names=selected_sources,
                        keywords=keywords,
                        locations=locations,
                        limit=int(limit_value),
                        with_cv=with_cv_value,
                        dry_run=dry_run_value,
                        notify=notify_value and not dry_run_value,
                        ignore_schedule=True,
                        config=crawler_config,
                    )
                    st.success("Coleta concluída.")
                except Exception as exc:
                    st.error(f"Falha na coleta: {exc}")

    summary = st.session_state.get("crawler_summary")
    if summary:
        st.divider()
        st.write("### 📊 Resultado da Última Coleta")
        summary_rows = []
        for name, info in (summary.get("sources") or {}).items():
            summary_rows.append(
                {
                    "fonte": name,
                    "coletadas": info.get("fetched", 0),
                    "filtradas": info.get("matched", 0),
                    "novas": info.get("new", 0),
                    "já_conhecidas": info.get("skipped", 0),
                    "observação": info.get("error") or info.get("skipped_reason") or "",
                }
            )
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

        postings = summary.get("postings") or []
        if postings:
            st.write("### 🧾 Vagas Encontradas (dry-run)")
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "fonte": posting.fonte,
                            "titulo": posting.titulo,
                            "empresa": posting.empresa,
                            "localizacao": posting.localizacao,
                            "url": posting.url,
                            "score": crawler.fit_score(posting, summary.get("keywords")),
                        }
                        for posting in postings
                    ]
                ).sort_values("score", ascending=False),
                use_container_width=True,
                hide_index=True,
            )

    with st.expander("🗑️ Itens descartados na curadoria (Application.txt)"):
        discarded = pd.DataFrame(crawler_config.get("discarded") or [])
        if not discarded.empty:
            st.dataframe(discarded, use_container_width=True, hide_index=True)
