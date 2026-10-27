import os
import json
import hashlib
import logging
import re
import unicodedata
from typing import Optional, Dict, Any, List, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

DEFAULT_DB_URL = os.getenv("DATABASE_URL", "postgresql://efonseca@localhost:5432/application_db")

def get_connection(db_url: str = None) -> psycopg2.extensions.connection:
    url = db_url or os.getenv("DATABASE_URL", DEFAULT_DB_URL)
    conn = psycopg2.connect(url)
    return conn

EXPECTED_TABLES = (
    "vagas",
    "perguntas_respostas",
    "curacao_qualificacoes",
    "curacao_experiencias",
    "curacao_formacao",
)

SOURCE_COLUMNS = ("fonte", "source_job_id", "apply_mode", "hash_dedupe")


def _normalize(value: str) -> str:
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(value))
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()


def _dedupe_hash(titulo: str, empresa: str = "", localizacao: str = "", url: str = "") -> str:
    company = _normalize(empresa) or _normalize(localizacao) or (url or "")
    return hashlib.sha256(f"{_normalize(titulo)}|{company}".encode("utf-8")).hexdigest()


def _existing_columns(cursor) -> set:
    cursor.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'vagas'
    """)
    return {row[0] for row in cursor.fetchall()}


def ensure_schema(db_url: str = None) -> bool:
    """Aplica as colunas do crawler multi-fonte se ainda não existirem.

    O usuário de serviço normalmente não tem DDL; nesse caso apenas registra o
    aviso e a migração deve ser aplicada pelo dbadmin
    (migrations/001_add_source_columns.sql).
    """
    conn = get_connection(db_url)
    cursor = conn.cursor()
    try:
        if not set(SOURCE_COLUMNS) - _existing_columns(cursor):
            return False
        cursor.execute("""
            ALTER TABLE vagas
                ADD COLUMN IF NOT EXISTS fonte VARCHAR(50) NOT NULL DEFAULT 'linkedin',
                ADD COLUMN IF NOT EXISTS source_job_id VARCHAR(255),
                ADD COLUMN IF NOT EXISTS apply_mode VARCHAR(20) NOT NULL DEFAULT 'assisted',
                ADD COLUMN IF NOT EXISTS hash_dedupe CHAR(64),
                ALTER COLUMN linkedin_job_id DROP NOT NULL
        """)
        cursor.execute("""
            UPDATE vagas SET source_job_id = linkedin_job_id
            WHERE source_job_id IS NULL AND linkedin_job_id IS NOT NULL
        """)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_vagas_fonte_source
            ON vagas (fonte, source_job_id)
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vagas_hash_dedupe ON vagas (hash_dedupe)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vagas_fonte ON vagas (fonte)")
        conn.commit()
        log.info("Schema multi-fonte aplicado com sucesso.")
        return True
    except psycopg2.errors.InsufficientPrivilege:
        conn.rollback()
        log.warning(
            "Sem permissão para alterar o schema. Rode migrations/001_add_source_columns.sql "
            "como dbadmin antes de usar o crawler multi-fonte."
        )
        return False
    finally:
        cursor.close()
        conn.close()

def tables_exist(cursor) -> bool:
    """True se todas as tabelas esperadas já existem no schema corrente."""
    cursor.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = current_schema()
          AND table_name = ANY(%s)
    """, (list(EXPECTED_TABLES),))
    return len(cursor.fetchall()) == len(EXPECTED_TABLES)

def init_db(db_url: str = None):
    """Inicializa as tabelas do banco de dados PostgreSQL.

    O DDL é criado pelo papel administrador (schema.sql). O usuário de serviço
    não tem CREATE no schema, então aqui apenas criamos o que faltar.
    """
    conn = get_connection(db_url)
    cursor = conn.cursor()

    if tables_exist(cursor):
        cursor.close()
        conn.close()
        log.info("Tabelas já existem; DDL não é necessário.")
        ensure_schema(db_url)
        return

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vagas (
            id SERIAL PRIMARY KEY,
            fonte VARCHAR(50) NOT NULL DEFAULT 'linkedin',
            source_job_id VARCHAR(255),
            linkedin_job_id VARCHAR(100) UNIQUE,
            url TEXT NOT NULL,
            titulo TEXT,
            empresa TEXT,
            localizacao TEXT,
            descricao TEXT,
            status VARCHAR(50) NOT NULL DEFAULT 'iniciado',
            apply_mode VARCHAR(20) NOT NULL DEFAULT 'assisted',
            hash_dedupe CHAR(64),
            pdf_custom_path TEXT,
            criado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_vagas_fonte_source
        ON vagas (fonte, source_job_id)
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vagas_hash_dedupe ON vagas (hash_dedupe)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vagas_fonte ON vagas (fonte)")
    
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
    cursor.execute(
        """
        SELECT * FROM vagas
        WHERE linkedin_job_id = %s
           OR (fonte = 'linkedin' AND source_job_id = %s)
        ORDER BY id DESC LIMIT 1
        """,
        (str(linkedin_job_id), str(linkedin_job_id)),
    )
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return dict(row) if row else None

def get_job_by_source(fonte: str, source_job_id: str, db_url: str = None) -> Optional[Dict[str, Any]]:
    conn = get_connection(db_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute(
        "SELECT * FROM vagas WHERE fonte = %s AND source_job_id = %s ORDER BY id DESC LIMIT 1",
        (fonte, str(source_job_id)),
    )
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return dict(row) if row else None

def find_job_by_dedupe(hash_dedupe: str, db_url: str = None) -> Optional[Dict[str, Any]]:
    conn = get_connection(db_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM vagas WHERE hash_dedupe = %s ORDER BY id ASC LIMIT 1", (hash_dedupe,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return dict(row) if row else None

def is_job_applied(linkedin_job_id: str, db_url: str = None) -> bool:
    job = get_job_by_linkedin_id(linkedin_job_id, db_url)
    return job is not None and job.get("status") == "aplicado"

def is_job_applied_source(fonte: str, source_job_id: str, db_url: str = None) -> bool:
    job = get_job_by_source(fonte, source_job_id, db_url)
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
    fonte: str = "linkedin",
    source_job_id: Optional[str] = None,
    apply_mode: str = "assisted",
    hash_dedupe: Optional[str] = None,
    db_url: str = None
) -> int:
    fonte = (fonte or "linkedin").strip().lower()
    source_job_id = str(source_job_id or linkedin_job_id)
    linkedin_value = str(linkedin_job_id) if fonte == "linkedin" else None
    hash_dedupe = hash_dedupe or _dedupe_hash(titulo, empresa, localizacao, url)

    conn = get_connection(db_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute(
        "SELECT id FROM vagas WHERE fonte = %s AND source_job_id = %s",
        (fonte, source_job_id),
    )
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
                apply_mode = %s,
                hash_dedupe = COALESCE(%s, hash_dedupe),
                atualizado_em = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (url, titulo, empresa, localizacao, descricao, status, pdf_custom_path,
              apply_mode, hash_dedupe, job_id))
    else:
        cursor.execute("""
            INSERT INTO vagas
                (fonte, source_job_id, linkedin_job_id, url, titulo, empresa,
                 localizacao, descricao, status, apply_mode, hash_dedupe, pdf_custom_path)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (fonte, source_job_id, linkedin_value, url, titulo, empresa,
              localizacao, descricao, status, apply_mode, hash_dedupe, pdf_custom_path))
        job_id = cursor.fetchone()["id"]
        
    conn.commit()
    cursor.close()
    conn.close()
    return job_id

def save_posting(posting, status: str = "descoberto", db_url: str = None) -> Tuple[int, bool]:
    """Persiste uma vaga normalizada de qualquer fonte.

    Retorna (vaga_id, criada). Se já existir o mesmo anúncio em outra fonte
    (mesmo hash de título + empresa), reaproveita o registro e retorna
    criada=False.
    """
    data = posting.to_db()
    conn = get_connection(db_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute(
        """
        SELECT id FROM vagas
        WHERE hash_dedupe = %s AND NOT (fonte = %s AND source_job_id = %s)
        ORDER BY id ASC LIMIT 1
        """,
        (data["hash_dedupe"], data["fonte"], data["source_job_id"]),
    )
    duplicate = cursor.fetchone()
    if duplicate:
        cursor.close()
        conn.close()
        return duplicate["id"], False

    cursor.execute(
        """
        INSERT INTO vagas
            (fonte, source_job_id, linkedin_job_id, url, titulo, empresa,
             localizacao, descricao, status, apply_mode, hash_dedupe)
        VALUES (%s, %s, NULL, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (fonte, source_job_id) DO UPDATE SET
            url = EXCLUDED.url,
            titulo = COALESCE(NULLIF(EXCLUDED.titulo, ''), vagas.titulo),
            empresa = COALESCE(NULLIF(EXCLUDED.empresa, ''), vagas.empresa),
            localizacao = COALESCE(NULLIF(EXCLUDED.localizacao, ''), vagas.localizacao),
            descricao = COALESCE(NULLIF(EXCLUDED.descricao, ''), vagas.descricao),
            apply_mode = EXCLUDED.apply_mode,
            hash_dedupe = COALESCE(EXCLUDED.hash_dedupe, vagas.hash_dedupe),
            status = CASE
                WHEN vagas.status IN ('aplicado', 'cv_gerado') THEN vagas.status
                ELSE EXCLUDED.status
            END,
            atualizado_em = CURRENT_TIMESTAMP
        RETURNING id, (xmax = 0) AS inserted
        """,
        (
            data["fonte"], data["source_job_id"], data["url"], data["titulo"],
            data["empresa"], data["localizacao"], data["descricao"], status,
            data["apply_mode"], data["hash_dedupe"],
        ),
    )
    row = cursor.fetchone()
    conn.commit()
    cursor.close()
    conn.close()
    return row["id"], bool(row["inserted"])

def update_job_status(
    job_id: int,
    status: str,
    pdf_custom_path: Optional[str] = None,
    db_url: str = None,
) -> None:
    conn = get_connection(db_url)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE vagas
        SET status = %s,
            pdf_custom_path = COALESCE(NULLIF(%s, ''), pdf_custom_path),
            atualizado_em = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (status, pdf_custom_path or "", job_id),
    )
    conn.commit()
    cursor.close()
    conn.close()

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
