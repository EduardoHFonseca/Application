import os
import json
import logging
from typing import Optional, Dict, Any, List
import psycopg2
from psycopg2.extras import RealDictCursor

log = logging.getLogger(__name__)

DEFAULT_DB_URL = os.getenv("DATABASE_URL", "postgresql://efonseca@localhost:5432/application_db")

def get_connection(db_url: str = None) -> psycopg2.extensions.connection:
    url = db_url or os.getenv("DATABASE_URL", DEFAULT_DB_URL)
    conn = psycopg2.connect(url)
    return conn

def init_db(db_url: str = None):
    """Inicializa as tabelas do banco de dados PostgreSQL."""
    conn = get_connection(db_url)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vagas (
            id SERIAL PRIMARY KEY,
            linkedin_job_id VARCHAR(100) UNIQUE NOT NULL,
            url TEXT NOT NULL,
            titulo TEXT,
            empresa TEXT,
            localizacao TEXT,
            descricao TEXT,
            status VARCHAR(50) NOT NULL DEFAULT 'iniciado',
            pdf_custom_path TEXT,
            criado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS perguntas_respostas (
            id SERIAL PRIMARY KEY,
            vaga_id INTEGER NOT NULL REFERENCES vagas(id) ON DELETE CASCADE,
            pergunta TEXT NOT NULL,
            resposta TEXT NOT NULL,
            origem VARCHAR(50) NOT NULL DEFAULT 'ia',
            respondido_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS curacao_qualificacoes (
            id SERIAL PRIMARY KEY,
            texto_acervo TEXT NOT NULL,
            tags TEXT[] DEFAULT '{}',
            atualizado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS curacao_experiencias (
            id SERIAL PRIMARY KEY,
            empresa VARCHAR(255) NOT NULL,
            cargo VARCHAR(255) NOT NULL,
            periodo_inicio VARCHAR(50) NOT NULL,
            periodo_fim VARCHAR(50) NOT NULL,
            ordem INTEGER DEFAULT 0,
            contexto_escopo TEXT,
            bullets_acervo JSONB DEFAULT '[]'::jsonb,
            siglas_projetos JSONB DEFAULT '{}'::jsonb,
            tags_dominio TEXT[] DEFAULT '{}',
            atualizado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS curacao_formacao (
            id SERIAL PRIMARY KEY,
            tipo VARCHAR(50) NOT NULL,
            instituicao VARCHAR(255) NOT NULL,
            titulo VARCHAR(255) NOT NULL,
            ano VARCHAR(50),
            relevancia_tags TEXT[] DEFAULT '{}',
            atualizado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    conn.commit()
    cursor.close()
    conn.close()
    log.info("Banco de dados PostgreSQL inicializado com sucesso!")

def get_job_by_linkedin_id(linkedin_job_id: str, db_url: str = None) -> Optional[Dict[str, Any]]:
    conn = get_connection(db_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM vagas WHERE linkedin_job_id = %s", (str(linkedin_job_id),))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return dict(row) if row else None

def is_job_applied(linkedin_job_id: str, db_url: str = None) -> bool:
    job = get_job_by_linkedin_id(linkedin_job_id, db_url)
    return job is not None and job.get("status") == "aplicado"

def save_or_update_job(
    linkedin_job_id: str,
    url: str,
    titulo: str = "",
    empresa: str = "",
    localizacao: str = "",
    descricao: str = "",
    status: str = "iniciado",
    pdf_custom_path: str = "",
    db_url: str = None
) -> int:
    conn = get_connection(db_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("SELECT id FROM vagas WHERE linkedin_job_id = %s", (str(linkedin_job_id),))
    row = cursor.fetchone()
    
    if row:
        job_id = row["id"]
        cursor.execute("""
            UPDATE vagas 
            SET url = COALESCE(NULLIF(%s, ''), url),
                titulo = COALESCE(NULLIF(%s, ''), titulo),
                empresa = COALESCE(NULLIF(%s, ''), empresa),
                localizacao = COALESCE(NULLIF(%s, ''), localizacao),
                descricao = COALESCE(NULLIF(%s, ''), descricao),
                status = %s,
                pdf_custom_path = COALESCE(NULLIF(%s, ''), pdf_custom_path),
                atualizado_em = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (url, titulo, empresa, localizacao, descricao, status, pdf_custom_path, job_id))
    else:
        cursor.execute("""
            INSERT INTO vagas (linkedin_job_id, url, titulo, empresa, localizacao, descricao, status, pdf_custom_path)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (str(linkedin_job_id), url, titulo, empresa, localizacao, descricao, status, pdf_custom_path))
        job_id = cursor.fetchone()["id"]
        
    conn.commit()
    cursor.close()
    conn.close()
    return job_id

def save_qa(vaga_id: int, pergunta: str, resposta: str, origem: str = "ia", db_url: str = None):
    conn = get_connection(db_url)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO perguntas_respostas (vaga_id, pergunta, resposta, origem)
        VALUES (%s, %s, %s, %s)
    """, (vaga_id, pergunta, resposta, origem))
    conn.commit()
    cursor.close()
    conn.close()

def get_all_jobs(db_url: str = None) -> List[Dict[str, Any]]:
    conn = get_connection(db_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM vagas ORDER BY id DESC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [dict(r) for r in rows]

def get_qa_for_job(vaga_id: int, db_url: str = None) -> List[Dict[str, Any]]:
    conn = get_connection(db_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM perguntas_respostas WHERE vaga_id = %s ORDER BY id ASC", (vaga_id,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [dict(r) for r in rows]

# --- CURACAO DATABASE HELPERS ---

def get_curacao_qualificacoes(db_url: str = None) -> Dict[str, Any]:
    conn = get_connection(db_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM curacao_qualificacoes ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return dict(row) if row else {"id": None, "texto_acervo": "", "tags": []}

def save_curacao_qualificacoes(texto: str, tags: List[str] = None, db_url: str = None) -> int:
    conn = get_connection(db_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    tags_val = tags or []
    cursor.execute("SELECT id FROM curacao_qualificacoes ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    if row:
        qid = row["id"]
        cursor.execute("""
            UPDATE curacao_qualificacoes
            SET texto_acervo = %s, tags = %s, atualizado_em = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (texto, tags_val, qid))
    else:
        cursor.execute("""
            INSERT INTO curacao_qualificacoes (texto_acervo, tags)
            VALUES (%s, %s) RETURNING id
        """, (texto, tags_val))
        qid = cursor.fetchone()["id"]
    conn.commit()
    cursor.close()
    conn.close()
    return qid

def get_curacao_experiencias(db_url: str = None) -> List[Dict[str, Any]]:
    conn = get_connection(db_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM curacao_experiencias ORDER BY ordem ASC, id ASC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [dict(r) for r in rows]

def save_curacao_experiencia(
    exp_id: Optional[int],
    empresa: str,
    cargo: str,
    periodo_inicio: str,
    periodo_fim: str,
    ordem: int = 0,
    contexto_escopo: str = "",
    bullets_acervo: List[str] = None,
    siglas_projetos: Dict[str, str] = None,
    tags_dominio: List[str] = None,
    db_url: str = None
) -> int:
    conn = get_connection(db_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    bullets_json = json.dumps(bullets_acervo or [])
    siglas_json = json.dumps(siglas_projetos or {})
    tags_arr = tags_dominio or []
    
    if exp_id:
        cursor.execute("""
            UPDATE curacao_experiencias
            SET empresa = %s, cargo = %s, periodo_inicio = %s, periodo_fim = %s,
                ordem = %s, contexto_escopo = %s, bullets_acervo = %s,
                siglas_projetos = %s, tags_dominio = %s, atualizado_em = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (empresa, cargo, periodo_inicio, periodo_fim, ordem, contexto_escopo, bullets_json, siglas_json, tags_arr, exp_id))
        res_id = exp_id
    else:
        cursor.execute("""
            INSERT INTO curacao_experiencias (empresa, cargo, periodo_inicio, periodo_fim, ordem, contexto_escopo, bullets_acervo, siglas_projetos, tags_dominio)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (empresa, cargo, periodo_inicio, periodo_fim, ordem, contexto_escopo, bullets_json, siglas_json, tags_arr))
        res_id = cursor.fetchone()["id"]
        
    conn.commit()
    cursor.close()
    conn.close()
    return res_id

def delete_curacao_experiencia(exp_id: int, db_url: str = None):
    conn = get_connection(db_url)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM curacao_experiencias WHERE id = %s", (exp_id,))
    conn.commit()
    cursor.close()
    conn.close()

def get_curacao_formacao(db_url: str = None) -> List[Dict[str, Any]]:
    conn = get_connection(db_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM curacao_formacao ORDER BY id ASC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [dict(r) for r in rows]

def save_curacao_formacao(
    form_id: Optional[int],
    tipo: str,
    instituicao: str,
    titulo: str,
    ano: str,
    relevancia_tags: List[str] = None,
    db_url: str = None
) -> int:
    conn = get_connection(db_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    tags_arr = relevancia_tags or []
    
    if form_id:
        cursor.execute("""
            UPDATE curacao_formacao
            SET tipo = %s, instituicao = %s, titulo = %s, ano = %s,
                relevancia_tags = %s, atualizado_em = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (tipo, instituicao, titulo, ano, tags_arr, form_id))
        res_id = form_id
    else:
        cursor.execute("""
            INSERT INTO curacao_formacao (tipo, instituicao, titulo, ano, relevancia_tags)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (tipo, instituicao, titulo, ano, tags_arr))
        res_id = cursor.fetchone()["id"]
        
    conn.commit()
    cursor.close()
    conn.close()
    return res_id

def delete_curacao_formacao(form_id: int, db_url: str = None):
    conn = get_connection(db_url)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM curacao_formacao WHERE id = %s", (form_id,))
    conn.commit()
    cursor.close()
    conn.close()

# Inicializa o banco de dados PostgreSQL ao importar
try:
    init_db()
except Exception as e:
    log.warning(f"Não foi possível inicializar o PostgreSQL automaticamente: {e}")
