import os
import json
import logging
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from ai_brain import AIBrain
import database

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Os currículos longos somam ~28k tokens, acima do que os tiers gratuitos de LLM
# atendem com confiança. A estratégia é usar um CV mestre (o mais completo) por
# vez de concatenar todos, e normalizar o schema devolvido pelo modelo (que varia
# muito entre providers grátis) antes de persistir.
CV_MESTRE_PADRAO = "CV-EHF-PORT-23.doc"


def _normalizar_experiencia(exp: dict, ordem_fallback: int) -> dict:
    """
    Normaliza uma experiência para o schema esperado por database.save_curacao_experiencia.

    Os LLMs livres usam nomes de campo variados (periodo, descricao, atividades,
    responsabilidades...). Esta função aceita os sinônimos conhecidos e devolve
    sempre o formato canônico, sem nunca lançar exceção por campo ausente.
    """
    if not isinstance(exp, dict):
        return {}

    def primeiro(*chaves):
        for k in chaves:
            v = exp.get(k)
            if v:
                return v
        return ""

    inicio = primeiro("periodo_inicio", "inicio", "data_inicio", "start")
    fim = primeiro("periodo_fim", "fim", "data_fim", "end")
    if not inicio and not fim:
        periodo = primeiro("periodo", "periodo_trabalho", "datas", "date")
        if periodo:
            partes = [p.strip() for p in str(periodo).replace("–", "-").replace("—", "-").split("-")]
            if len(partes) >= 2:
                inicio, fim = partes[0], partes[1]
            elif partes:
                inicio = partes[0]

    bullets = primeiro("bullets_acervo", "bullets", "atividades", "realizacoes",
                       "responsabilidades", "descricao", "descricao_atividades")
    if isinstance(bullets, str):
        bullets = [b.strip() for b in bullets.split("\n") if b.strip()]
    elif not isinstance(bullets, list):
        bullets = []

    siglas = primeiro("siglas_projetos", "siglas", "projetos")
    if not isinstance(siglas, dict):
        siglas = {}

    tags = primeiro("tags_dominio", "tags", "segmento")
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    elif not isinstance(tags, list):
        tags = []

    return {
        "empresa": str(primeiro("empresa", "company", "organizacao") or "Empresa"),
        "cargo": str(primeiro("cargo", "role", "posicao", "titulo") or "Cargo"),
        "periodo_inicio": str(inicio),
        "periodo_fim": str(fim),
        "ordem": int(exp.get("ordem") or ordem_fallback),
        "contexto_escopo": str(primeiro("contexto_escopo", "contexto", "escopo") or ""),
        "bullets_acervo": bullets,
        "siglas_projetos": siglas,
        "tags_dominio": tags,
    }


def _normalizar_formacao(form) -> dict:
    """Normaliza uma formação/qualificação para o schema canônico."""
    if isinstance(form, str):
        return {"tipo": "curso", "instituicao": "", "titulo": form, "ano": "", "relevancia_tags": []}
    if not isinstance(form, dict):
        return {}

    def primeiro(*chaves):
        for k in chaves:
            v = form.get(k)
            if v:
                return v
        return ""

    tags = primeiro("relevancia_tags", "tags")
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    elif not isinstance(tags, list):
        tags = []

    return {
        "tipo": str(primeiro("tipo", "type") or "graduacao"),
        "instituicao": str(primeiro("instituicao", "institution", "escola", "local") or ""),
        "titulo": str(primeiro("titulo", "nome", "curso", "degree") or ""),
        "ano": str(primeiro("ano", "year", "data") or ""),
        "relevancia_tags": tags,
    }


def _extrair_via_llm(cv_texto: str, filename: str) -> dict:
    """
    Chama o LLM uma única vez para extrair qualificações, experiências e formação.

    O conteúdo de entrada já é de um único CV mestre (não concatenado), mantendo a
    requisição dentro do que os tiers gratuitos conseguem atender.
    """
    system_prompt = (
        "Você é um arquiteto de carreiras e recrutador executivo de TI e Gestão de Produtos. "
        "Extraia TODAS as experiências profissionais do currículo, sem omitir nenhuma empresa, "
        "ordenando da mais recente para a mais antiga (campo ordem: 1 = mais recente).\n\n"
        "Retorne OBRIGATORIAMENTE um JSON válido puro (sem markdown, sem texto fora do JSON) "
        "com EXATAMENTE estas três chaves:\n"
        "{\n"
        '  "qualificacoes": {"texto_acervo": "resumo executivo abrangente das competências", "tags": ["LIDERANCA_TI", "..."]},\n'
        '  "experiencias": [\n'
        "    {\n"
        '      "empresa": "string",\n'
        '      "cargo": "string",\n'
        '      "periodo_inicio": "string (ex: 2001)",\n'
        '      "periodo_fim": "string (ex: 2007 ou Atual)",\n'
        '      "ordem": 1,\n'
        '      "contexto_escopo": "string (tamanho de equipe, setor, faturamento)",\n'
        '      "bullets_acervo": ["realização/projeto/métrica 1", "..."],\n'
        '      "siglas_projetos": {"SPB": "Sistema de Pagamentos Brasileiro"},\n'
        '      "tags_dominio": ["Bancos", "Regulação"]\n'
        "    }\n"
        "  ],\n"
        '  "formacao": [\n'
        '    {"tipo": "graduacao|mba|certificacao|curso", "instituicao": "string", "titulo": "string", "ano": "string", "relevancia_tags": ["..."]}\n'
        "  ]\n"
        "}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"CONTEÚDO DO CURRÍCULO ({filename}):\n\n{cv_texto}"},
    ]

    res_json_str = AIBrain.call_llm(messages, response_format="json")
    return json.loads(res_json_str)


def seed_curacao(force_reseed=True, cv_mestre: str = CV_MESTRE_PADRAO):
    log.info("Iniciando ingestão e auto-clustering da base mestra (LLM)...")

    # TRUNCATE exige privilégio de owner; o usuário de serviço (svc_application)
    # tem apenas SELECT/INSERT/UPDATE/DELETE. Usa DELETE, equivalente aqui e que
    # respeita o contrato do schema.sql.
    if force_reseed:
        conn = database.get_connection()
        cursor = conn.cursor()
        for tabela in ("curacao_experiencias", "curacao_qualificacoes", "curacao_formacao"):
            cursor.execute(f"DELETE FROM {tabela};")
        conn.commit()
        cursor.close()
        conn.close()

    cvs = AIBrain.get_base_cvs()
    if not cvs:
        log.warning("Nenhum CV encontrado na pasta source/ para ingestão.")
        return

    cvs_por_nome = {c["filename"]: c["content"] for c in cvs}

    # Usa um único CV mestre (o mais completo) em vez de concatenar todos: a
    # concatenação ultrapassava a janela prática dos tiers gratuitos de LLM.
    if cv_mestre in cvs_por_nome and cvs_por_nome[cv_mestre].strip():
        conteudo = cvs_por_nome[cv_mestre]
        nome = cv_mestre
    else:
        nome, conteudo = max(cvs_por_nome.items(), key=lambda kv: len(kv[1] or ""))
        log.info("CV mestre '%s' ausente; usando '%s' (mais extenso).", cv_mestre, nome)

    log.info("CV mestre: %s (%d chars ~%d tokens)", nome, len(conteudo), len(conteudo) // 4)

    try:
        data = _extrair_via_llm(conteudo, nome)
    except Exception as e:
        log.error("Erro na extração via LLM: %s", e)
        return

    if not isinstance(data, dict):
        log.error("LLM não retornou um objeto JSON. Abortando.")
        return

    # 1. Qualificações
    qual = data.get("qualificacoes", {})
    if isinstance(qual, str):
        q_texto, q_tags = qual, ["LIDERANCA_TI", "PRODUCT_HEAD", "GOVERNANCA"]
    elif isinstance(qual, dict):
        q_texto = qual.get("texto_acervo") or qual.get("texto") or "Perfil Executivo de Tecnologia e Gestão de Produtos"
        q_tags = qual.get("tags") or ["LIDERANCA_TI", "PRODUCT_HEAD", "GOVERNANCA"]
    else:
        q_texto, q_tags = "Perfil Executivo de Tecnologia e Gestão de Produtos", ["LIDERANCA_TI", "PRODUCT_HEAD", "GOVERNANCA"]
    database.save_curacao_qualificacoes(q_texto, q_tags)
    log.info("Qualificações mestre salvas.")

    # 2. Experiências (normaliza schema variável e salva em ordem cronológica)
    exps_raw = data.get("experiencias", [])
    if isinstance(exps_raw, dict):
        exps_raw = list(exps_raw.values())
    exps = [_normalizar_experiencia(e, i + 1) for i, e in enumerate(exps_raw)]
    exps = [e for e in exps if e.get("empresa") and e.get("cargo")]
    exps.sort(key=lambda x: x.get("ordem", 99))
    for idx, exp in enumerate(exps):
        database.save_curacao_experiencia(
            exp_id=None,
            empresa=exp["empresa"],
            cargo=exp["cargo"],
            periodo_inicio=exp["periodo_inicio"],
            periodo_fim=exp["periodo_fim"],
            ordem=idx + 1,
            contexto_escopo=exp["contexto_escopo"],
            bullets_acervo=exp["bullets_acervo"],
            siglas_projetos=exp["siglas_projetos"],
            tags_dominio=exp["tags_dominio"],
        )
    log.info("%d experiências cronológicas salvas.", len(exps))

    # 3. Formação
    form_raw = data.get("formacao", [])
    if isinstance(form_raw, dict):
        form_raw = list(form_raw.values())
    forms = [_normalizar_formacao(f) for f in form_raw]
    forms = [f for f in forms if f.get("titulo")]
    for f in forms:
        database.save_curacao_formacao(
            form_id=None,
            tipo=f["tipo"],
            instituicao=f["instituicao"],
            titulo=f["titulo"],
            ano=f["ano"],
            relevancia_tags=f["relevancia_tags"],
        )
    log.info("%d formações/certificações salvas.", len(forms))


if __name__ == "__main__":
    seed_curacao(force_reseed=True)
