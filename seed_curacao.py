import os
import json
import logging
from dotenv import load_dotenv

load_dotenv()

from ai_brain import AIBrain
import database

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

def seed_curacao(force_reseed=True):
    log.info("Iniciando processo de ingestão e auto-clustering completo dos CVs...")
    
    conn = database.get_connection()
    cursor = conn.cursor()
    if force_reseed:
        cursor.execute("TRUNCATE TABLE curacao_experiencias RESTART IDENTITY;")
        cursor.execute("TRUNCATE TABLE curacao_qualificacoes RESTART IDENTITY;")
        cursor.execute("TRUNCATE TABLE curacao_formacao RESTART IDENTITY;")
        conn.commit()
    cursor.close()
    conn.close()

    cvs = AIBrain.get_base_cvs()
    if not cvs:
        log.warning("Nenhum CV encontrado na pasta source/ para ingestão.")
        return

    # Utiliza o conteúdo completo dos arquivos sem truncamento agressivo
    combined_texts = []
    for c in cvs:
        # Pega arquivos relevantes e limpos
        if c['filename'].endswith('.pdf') or 'PORT-23' in c['filename'] or 'PORT-11G' in c['filename']:
            combined_texts.append(f"=== ARQUIVO: {c['filename']} ===\n{c['content']}")

    cv_contents = "\n\n".join(combined_texts)

    system_prompt = (
        "Você é um arquiteto de carreiras e recrutador executivo de TI e Gestão de Produtos.\n"
        "Sua tarefa é extrair TODAS AS EXPERIÊNCIAS PROFISSIONAIS do candidato contidas nos currículos, sem omitir nenhuma empresa.\n\n"
        "A LINHA DO TEMPO DEVE SER ORDENADA STRICTAMENTE DA MAIS RECENTE PARA A MAIS ANTIGA (ORDEM 1, 2, 3...):\n"
        "1. Kantar IBOPE Media (2024 - Atual)\n"
        "2. Consultor de Tecnologia / Freelance (2022 - 2024)\n"
        "3. NAVA Technology for Business (2020 - 2022)\n"
        "4. Nova Agri / Toyota Tsusho (2017 - 2020)\n"
        "5. InfoSERVER Informática LTDA (2016 - 2017)\n"
        "6. Grupo Unicom / FlexVision (2014 - 2016) -> ATENÇÃO: Inclua os projetos de Dashboards para Bancos, Atlassian Jira, Catálogo de Serviços e Gerenciamento de Delivery!\n"
        "7. Microsoft Informática LTDA (2012 - 2014)\n"
        "8. Lo-JACK / Tracker do Brasil (2010 - 2012)\n"
        "9. TCS – TATA Consultancy Services (2009 - 2010)\n"
        "10. Grupo Belfort (2009)\n"
        "11. New Age Software S/A (2008 - 2009)\n"
        "12. ADM do Brasil LTDA (2001 - 2007) -> ATENÇÃO: Inclua os projetos SPB, Sistema de Pagamentos Brasileiro, Operações Bancárias e BACEN!\n"
        "13. InfoSERVER Informática S/A (2001)\n"
        "14. RHT - System Informática (1997 - 2001)\n\n"
        "Para cada uma das 14 experiências, forneça:\n"
        "   - empresa (string)\n"
        "   - cargo (string)\n"
        "   - periodo_inicio (string, ex: 2001)\n"
        "   - periodo_fim (string, ex: 2007 ou Atual)\n"
        "   - ordem (integer, 1 para a mais recente, 2 para anterior, etc.)\n"
        "   - contexto_escopo (string resumo do tamanho da equipe, faturamento ou setor)\n"
        "   - bullets_acervo (lista de strings com TODOS os realizações/projetos/métricas encontrados)\n"
        "   - siglas_projetos (objeto json mapeando siglas/sistemas para seu significado, ex: {'SPB': 'Sistema de Pagamentos Brasileiro, Operações Bancárias, BACEN'})\n"
        "   - tags_dominio (lista de tags do segmento, ex: ['Bancos', 'Regulação', 'BACEN', 'ERP'])\n\n"
        "Também extraia:\n"
        "QUALIFICACOES: Um texto rico e abrangente com todas as competências executivas + lista de tags.\n"
        "FORMACAO: Lista de diplomas, MBAs, certificações e cursos encontrados.\n\n"
        "Retorne OBRIGATORIAMENTE um JSON válido puro com as chaves 'qualificacoes', 'experiencias' e 'formacao'."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"CONTEÚDO DOS CURRÍCULOS ORIGINAIS:\n\n{cv_contents[:40000]}"}
    ]

    try:
        log.info("Chamando LLM para extração da linha do tempo completa (13 posições)...")
        res_json_str = AIBrain.call_llm(messages, response_format="json")
        data = json.loads(res_json_str)

        # 1. Salva Qualificações
        qual = data.get("qualificacoes", {})
        if isinstance(qual, str):
            q_texto = qual
            q_tags = ["LIDERANCA_TI", "PRODUCT_HEAD", "GOVERNANCA"]
        elif isinstance(qual, dict):
            q_texto = qual.get("texto_acervo", "Perfil Executivo de Tecnologia e Gestão de Produtos")
            q_tags = qual.get("tags", ["LIDERANCA_TI", "PRODUCT_HEAD", "GOVERNANCA"])
        else:
            q_texto = "Perfil Executivo de Tecnologia e Gestão de Produtos"
            q_tags = ["LIDERANCA_TI", "PRODUCT_HEAD", "GOVERNANCA"]

        database.save_curacao_qualificacoes(q_texto, q_tags)
        log.info("Qualificações mestre salvas com sucesso.")

        # 2. Salva Experiências
        exps_data = data.get("experiencias", [])
        # Ordena obrigatoriamente pela chave ordem / datas
        exps_data.sort(key=lambda x: x.get("ordem", 99))
        
        for idx, exp in enumerate(exps_data):
            database.save_curacao_experiencia(
                exp_id=None,
                empresa=exp.get("empresa", "Empresa"),
                cargo=exp.get("cargo", "Cargo"),
                periodo_inicio=str(exp.get("periodo_inicio", "")),
                periodo_fim=str(exp.get("periodo_fim", "")),
                ordem=idx + 1,
                contexto_escopo=exp.get("contexto_escopo", ""),
                bullets_acervo=exp.get("bullets_acervo", []),
                siglas_projetos=exp.get("siglas_projetos", {}),
                tags_dominio=exp.get("tags_dominio", [])
            )
        log.info(f"{len(exps_data)} experiências cronológicas ordenadas salvas com sucesso.")

        # 3. Salva Formações
        form_data = data.get("formacao", [])
        for f in form_data:
            database.save_curacao_formacao(
                form_id=None,
                tipo=f.get("tipo", "graduacao"),
                instituicao=f.get("instituicao", ""),
                titulo=f.get("titulo", ""),
                ano=str(f.get("ano", "")),
                relevancia_tags=f.get("relevancia_tags", [])
            )
        log.info(f"{len(form_data)} formações e certificações salvas com sucesso.")

    except Exception as e:
        log.error(f"Erro ao executar seed da curação: {e}")

if __name__ == "__main__":
    seed_curacao(force_reseed=True)
