import os
import json
import logging
from dotenv import load_dotenv

load_dotenv()

from ai_brain import AIBrain
import database

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

def seed_curacao():
    log.info("Iniciando processo de ingestão e auto-clustering inicial dos CVs...")
    
    # Check if database already has experiences
    exps = database.get_curacao_experiencias()
    if exps:
        log.info(f"O banco de dados já possui {len(exps)} experiências cadastradas. Pulando re-seed inicial.")
        return

    cvs = AIBrain.get_base_cvs()
    if not cvs:
        log.warning("Nenhum CV encontrado na pasta source/ para ingestão.")
        return

    cv_contents = "\n\n".join([f"=== ARQUIVO: {c['filename']} ===\n{c['content'][:4000]}" for c in cvs])

    system_prompt = (
        "Você é um arquiteto de carreiras e recrutador executivo especialista em TI e Gestão de Produtos.\n"
        "Sua tarefa é analisar os textos de currículos fornecidos e estruturar os dados do candidato em JSON com 3 seções principais:\n"
        "1. QUALIFICACOES: Um texto rico e abrangente com todas as competências executivas, metodológicas e tecnológicas + lista de tags.\n"
        "2. EXPERIENCIAS: Lista de todas as janelas cronológicas por empresa/cargo. Para cada experiência, forneça:\n"
        "   - empresa (string)\n"
        "   - cargo (string)\n"
        "   - periodo_inicio (string, ex: 2001)\n"
        "   - periodo_fim (string, ex: 2007 ou Atual)\n"
        "   - ordem (integer, 1 para a mais recente, 2 para anterior, etc.)\n"
        "   - contexto_escopo (string resumo do tamanho da equipe, faturamento ou setor)\n"
        "   - bullets_acervo (lista de strings com TODOS os realizações/projetos/métricas encontrados)\n"
        "   - siglas_projetos (objeto json mapeando siglas/sistemas para seu significado, ex: {'SPB': 'Sistema de Pagamentos Brasileiro, Operações Bancárias, BACEN'})\n"
        "   - tags_dominio (lista de tags do segmento, ex: ['Bancos', 'Regulação', 'ERP'])\n"
        "3. FORMACAO: Lista de diplomas, MBAs, certificações e cursos encontrados (tipo, instituicao, titulo, ano, relevancia_tags).\n\n"
        "Retorne OBRIGATORIAMENTE um JSON válido puro com as chaves 'qualificacoes', 'experiencias' e 'formacao'."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"CONTEÚDO DOS CURRÍCULOS ORIGINAIS:\n\n{cv_contents}"}
    ]

    try:
        log.info("Chamando LLM para extração estruturada dos blocos de carreira...")
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
        for idx, exp in enumerate(exps_data):
            database.save_curacao_experiencia(
                exp_id=None,
                empresa=exp.get("empresa", "Empresa"),
                cargo=exp.get("cargo", "Cargo"),
                periodo_inicio=str(exp.get("periodo_inicio", "")),
                periodo_fim=str(exp.get("periodo_fim", "")),
                ordem=exp.get("ordem", idx + 1),
                contexto_escopo=exp.get("contexto_escopo", ""),
                bullets_acervo=exp.get("bullets_acervo", []),
                siglas_projetos=exp.get("siglas_projetos", {}),
                tags_dominio=exp.get("tags_dominio", [])
            )
        log.info(f"{len(exps_data)} experiências cronológicas salvas com sucesso.")

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
    seed_curacao()
