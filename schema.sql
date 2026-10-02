-- DDL do projeto Application, extraído de database.py:init_db()
-- Executado pelo dbadmin: o usuário de serviço (svc_application) não tem CREATE no schema.
-- Tabelas owner dbadmin; svc_application recebe apenas SELECT/INSERT/UPDATE/DELETE.
\set ON_ERROR_STOP on

SET search_path TO application, public;

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

CREATE TABLE IF NOT EXISTS perguntas_respostas (
    id SERIAL PRIMARY KEY,
    vaga_id INTEGER NOT NULL REFERENCES vagas(id) ON DELETE CASCADE,
    pergunta TEXT NOT NULL,
    resposta TEXT NOT NULL,
    origem VARCHAR(50) NOT NULL DEFAULT 'ia',
    respondido_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS curacao_qualificacoes (
    id SERIAL PRIMARY KEY,
    texto_acervo TEXT NOT NULL,
    tags TEXT[] DEFAULT '{}',
    atualizado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

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

CREATE TABLE IF NOT EXISTS curacao_formacao (
    id SERIAL PRIMARY KEY,
    tipo VARCHAR(50) NOT NULL,
    instituicao VARCHAR(255) NOT NULL,
    titulo VARCHAR(255) NOT NULL,
    ano VARCHAR(50),
    relevancia_tags TEXT[] DEFAULT '{}',
    atualizado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA application TO svc_application;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA application TO svc_application;
