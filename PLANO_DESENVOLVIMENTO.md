# Plano de Desenvolvimento: LinkedIn Easy Apply & OpenClaw

Este documento estabelece o plano, arquitetura e backlog de atividades para o projeto **Application** ("Store Agentic Applicator"), integrando a automação de candidaturas com inteligência artificial orquestrada via **OpenClaw** e com um fluxo bidirecional de feedback humano (*Human-in-the-Loop*).

---

## 1. Visão de Arquitetura e Orquestração

Para permitir a orquestração robusta sob demanda pelo OpenClaw e a flexibilidade de comunicação de ida e volta (interação humana em tempo real), a arquitetura adotará os seguintes módulos:

```
                  ┌──────────────────────┐
                  │       OpenClaw       │
                  │   (Orquestrador)     │
                  └──────────┬───────────┘
                             │ (Gatilho / API)
                             ▼
┌──────────────┐  FastAPI Web Service  ┌──────────────┐
│  Motor Bot   │◄─────────────────────►│  Cérebro IA  │
│ (Playwright) │                       │ (LLM / RAG)  │
└──────┬───────┘                       └──────┬───────┘
       │                                      │
       ▼ (Dúvidas no Easy Apply)              ▼ (CV Base)
┌──────────────┐                       ┌──────────────┐
│  Interface   │                       │    Pasta     │
│  Mensageria  │                       │   source/    │
│ (Telegram    │                       └──────────────┘
│    Direct)   │
└──────┬───────┘
       ▼
┌──────────────┐
│ Usuário Real │ (Respostas adicionais complexas)
└──────────────┘
```

### 1.0 Dependência Externa: Roteador de LLMs (`FreeLLM-router`)

O **Application** não chama provedores de LLM diretamente. Ele consome um gateway local — o projeto **`FreeLLM-router`** (`/root/workspace/FreeLLM-router`), um clone MIT do *freellmapi* que roda em Docker (`http://127.0.0.1:3001/v1`).

- **Contrato no `.env`:** `LLM_BASE_URL`, `LLM_API_KEY` (chave unificada) e `LLM_MODEL`.
- **Azure OpenAI** permanece suportado apenas como *fallback* opcional, quando `LLM_BASE_URL`/`LLM_API_KEY` não estão definidos.
- O roteador é **infraestrutura compartilhada e independente**: pode servir outros projetos, não pertence ao backlog do Application e é versionado em repositório próprio.

### 1.1 Fluxo Bidirecional (*Human-in-the-Loop*)
1. O **Motor de Navegação (Playwright)** acessa a vaga no LinkedIn, inicia o processo de "Easy Apply" e se depara com uma pergunta não mapeada pelo cérebro IA.
2. O **Motor** faz uma consulta ao Telegram Bot direto enviando a pergunta formatada em Markdown.
3. O processo de aplicação entra em modo de **Espera Ativa / Polling** (escutando atualizações do Telegram de forma totalmente local, sem necessidade de servidores expostos ou portas abertas).
4. Assim que o usuário responde no Telegram, o robô recebe a resposta, confirma o recebimento, preenche o campo correspondente e avança a candidatura.

---

## 2. Backlog de Atividades

### [A.1] Planejamento e Estruturação
- [x] Criar e alinhar o documento `PLANO_DESENVOLVIMENTO.md`
- [x] Definir a especificação de integração e centralizar configurações no `.env`

### [A.2] Módulo do Cérebro IA (Fase 2)
- [x] Implementar o matcher de currículos em `source/` (leitura e parsing de PDFs via `pypdf`)
- [x] Integrar chamada de LLM para analisar a Job Description e extrair palavras-chave e habilidades requeridas
- [x] Implementar a geração de PDF dinâmico/personalizado com base no currículo selecionado e customizado para a vaga via `fpdf2`
- [x] Implementar o motor de respostas padrão estruturado com LLM

### [A.3] Canal de Mensageria Bidirecional (Human-in-the-Loop)
- [x] Desenvolver o canal de comunicação ativo por Telegram (`telegram_bot.py`)
- [x] Implementar o mecanismo de pausa, espera e polling assíncrono síncrono local no robô

### [A.4] Reconstrução do Motor para Playwright (Fase 3 - CONCLUÍDO)
- [x] Criar `playwright_bot.py` para substituir o Selenium legatário e o `easyapplybot.py` instável
- [x] Implementar persistência de cookies e login via `state.json` para evitar CAPTCHAs
- [x] Injetar chamadas de IA e respostas automatizadas/humanas em tempo real
- [x] Integrar o disparo de e-mail ao final com o currículo customizado anexo e as respostas enviadas via `email_service.py`

### [A.5] Testes, Execução e Homologação
- [x] Criar suíte de testes unitários e de integração mockando chamadas de APIs e comportamento de objetos (`test_suite.py`)
- [x] Validar a integração final com a orquestração do OpenClaw

---

## 3. Backlog de Expansão (Mapeado a partir de `Application Proj.pptx`)

### [Fase 1] Persistência de Dados & Matriz de Competências
- [x] **[F1.1] Camada de Banco de Dados (PostgreSQL):**
  - Criada tabela `vagas` (id, linkedin_job_id, url, titulo, empresa, localizacao, descricao, status, pdf_custom_path, criado_em, atualizado_em) no banco local `application_db`.
  - Criada tabela `perguntas_respostas` (id, vaga_id, pergunta, resposta, origem, respondido_em).
  - Integrado ao `playwright_bot.py` com checagem de idempotência antes da aplicação.
- [x] **[F1.2] Consolidador do Arquivo de Competências (`Competencias.MD`):**
  - Implementado leitor unificado em `source/` suportando `.pdf`, `.doc` e `.docx`.
  - Módulo LLM gera e atualiza automaticamente o arquivo `Competencias.MD` consolidando todo o histórico profissional.
  - Refatorado `ai_brain.py` utilizando `Competencias.MD` como base primária.

### [Fase 2] Candidatura Sob Demanda por URL & Scheduler de Automação
- [x] **[F2.1] Submissão por URL Individual (Sob Demanda):**
  - Implementado suporte CLI (`python playwright_bot.py --url <URL_DA_VAGA>`) com extrator automático de Job IDs para aplicação direta sob demanda.
- [x] **[F2.2] Scheduler com Delay Inter-Execuções (4 Horas):**
  - Implementado modo loop (`python playwright_bot.py --loop`) respeitando o intervalo configurado em `CRAWLER_INTERVAL_HOURS` (padrão 4 horas).

### [Fase 3] Interface Web / Painel de Controle (Streamlit)
- [x] **[F3.1] Dashboard Visual e Gestão de Parâmetros (`app.py`):**
  - Implementado painel executivo em Streamlit com 4 abas completas:
    - **Aba 1 - Histórico & Audit Trail:** Tabela de candidaturas conectada ao PostgreSQL, filtros por status, inspeção detalhada de formulários e download dos PDFs customizados gerados.
    - **Aba 2 - Candidatura Sob Demanda:** Execução em tempo real de aplicação por URL de vaga do LinkedIn com streaming de logs em tela.
    - **Aba 3 - Filtros & Configurações:** Edição visual do arquivo `.env` para posições, localizações, pretensão salarial e credenciais.
    - **Aba 4 - Acervo & Matriz Competencias.MD:** Upload de novos currículos/cartas para `source/`, botão para re-sintetizar a matriz via LLM e visualizador em Markdown do `Competencias.MD`.

### [Fase 4] Reformulação do Gerador de CVs (Arquitetura Fact-Based)
- [x] **[F4.1] Camada 1 - Base Mestra Fact-Based no PostgreSQL:**
  - Criadas tabelas `curacao_qualificacoes`, `curacao_experiencias` e `curacao_formacao` no `application_db`.
  - `seed_curacao.py`: usa um **único CV mestre** (`CV-EHF-PORT-23.doc`) em vez de concatenar todos os currículos (a concatenação ultrapassava a janela prática dos tiers gratuitos de LLM); normaliza o schema de resposta (os nomes de campo variam entre provedores) para experiências/formação; normaliza período/descrição em `periodo_inicio`/`periodo_fim`/`bullets_acervo`; e persiste qualificações, experiências e formação de forma incremental.
  - **Estado atual do banco:** 16 janelas cronológicas ordenadas (1992 → Atual), cobrindo Multiplus (1992-1994), Dual CAD (1994-1997), RHT System (1997-2001), InfoSERVER (2001), ADM do Brasil (2001-2007, com SPB/BACEN/SOX), New Age (2008-2009), Grupo Belfort (2009), TCS (2009-2010), Lo-Jack/Tracker (2010-2012), Microsoft (2012-2014), NAVA (2014-2015), InfoSERVER (2016-2017), Freelance (2017), Nova Agri/Toyota Tsusho (2018-2020), NAVA (2020-2022) e Freelance (2022-Atual); mais 6 formações/certificações.
- [x] **[F4.2] Painel de Curação no Streamlit & Copiloto IA (`app.py`):**
  - Implementada a aba "🧩 Curação da Base Mestra" com layout em 2 colunas e Copiloto de IA para detecção de siglas (LLM, VLM, RAG, PoC, SPB), sugestão de tags de domínio e botão de injeção direta no dicionário do bloco em 1 clique.
- [ ] **[F4.3] Sessão de Entrevista Executiva por Janela:**
  - Janela 1 (IBOPE Media 2024-Atual): Concluída e refinada.
  - **Escopo revisado:** a extração automática (`seed_curacao.py`) já populou as 16 janelas com `contexto_escopo`, `bullets_acervo`, `siglas_projetos` e `tags_dominio` a partir do CV mestre, porém de forma automatizada e possivelmente rasa. O objetivo do F4.3 passa a ser **enriquecer manualmente, janela por janela**, os dados que o LLM não consegue inferir (tamanho real de equipe, faturamento, métricas de impacto, significado de siglas), usando o **Copiloto IA** da aba "🧩 Curação da Base Mestra" para sugerir tags/siglas e injetar em 1 clique.
  - Pendentes: enriquecimento guiado das janelas 2 a 16.
- [x] **[F4.4] Camada 3 - Template PDF Padrão Harvard/Corporate Executivo:**
  - Novo template `harvard` (padrão via `CV_TEMPLATE` no `.env` ou parâmetro explícito em `AIBrain.generate_pdf`): single-column preto e branco, sem faixas/retângulos coloridos, tipografia densa (9.2pt), seções com *heading* textual e régua fina, empresa em negrito com período alinhado à direita, cargo em itálico e formação/certificações ao final — leitura em ordem correta por robôs ATS.
  - Parser estruturado (`_parse_experience_blocks`) que converte o histórico `EMPRESA | CARGO (DATA)` do LLM em blocos de experiência e de formação.
  - Template legado `corporate` preservado com comportamento idêntico ao anterior; selecionável na aba ⚙️ Filtros & Configurações do painel.

### [Fase 5] Suporte a Vagas Internas / Mensagens Diretas & Auto-Detecção de Idioma (26/07/2026)
- [x] **[F5.1] Modo Descritivo Direto em Tab 2 (`app.py`):**
  - Adicionada opção de entrada por Copy + Paste de descritivo completo para vagas internas, WhatsApp ou documentos.
  - Registro automático na tabela `vagas` do PostgreSQL com ID `manual_<timestamp>` e geração instantânea de PDF customizado.
- [x] **[F5.2] Auto-Detecção de Idioma & Otimização de Títulos (`ai_brain.py`):**
  - Implementada detecção automática do idioma da vaga (Inglês x Português) para geração integral do CV no mesmo idioma.
  - Adicionada regra estrita para títulos executivos curtos (máximo 3 a 5 palavras, sem slogans/frases) e quebra de linha dinâmica no PDF (`multi_cell`).
- [x] **[F5.3] Parser Defensivo de Destaques de Experiência:**
  - Implementado `format_experience_content` para converter listas/dicionários JSON do LLM em marcadores (*bullets*) limpos sem exibições de sintaxe de código no PDF.

### [Fase 6] Crawler Multi-Fonte (27/10/2026)
- [x] **[F6.1] Curadoria da lista `Application.txt`:**
  - 25 entradas avaliadas com teste HTTP real; itens mortos, pagos, duplicados e fora de escopo descartados com justificativa.
  - Catálogo versionado em `config/sources.yaml` com `apply_mode` (`auto` | `assisted` | `link_only`), intervalo mínimo por fonte e notas de ToS.
- [x] **[F6.2] Framework de fontes + 3 fontes API/RSS:**
  - `sources/base.py` com `JobPosting` normalizado, URL canônica, hash de dedupe e filtros de cargo/localização; `sources/registry.py` como catálogo.
  - Adaptadores `remotive.py` (API), `rss.py` (We Work Remotely) e `workingnomads.py` (endpoint JSON público).
  - `crawler.py`: descoberta → normalização → filtro → dedupe → persistência → CV opcional → resumo no Telegram.
  - CLI `--source/--all/--dry-run/--with-cv/--list-sources`; `playwright_bot.py` delega fontes não-LinkedIn.
  - Migração `migrations/001_add_source_columns.sql` (`fonte`, `source_job_id`, `apply_mode`, `hash_dedupe`) com backfill dos registros existentes.
  - Aba "🌐 Fontes & Crawler" no painel e filtro por fonte no histórico.
  - `test_sources.py`: 19 casos com fixtures locais, sem chamadas de rede.
- [ ] **[F6.3] Boards HTML (Fase 2):** Jobspresso, JustRemote, DailyRemote, Pangian e ARC em modo assistido.
- [ ] **[F6.4] Wellfound e marketplaces (Fase 3):** sessão manual para Wellfound; link + rascunho de proposta via IA para Upwork/Fiverr/Freelancer/ServiceScape.
- [ ] **[F6.5] Boards brasileiros (Fase 4):** Gupy, Vagas.com.br e Programathor.

---

## 4. Instruções de Execução em Servidor/VM Headless (SSH)

Para garantir 100% de estabilidade e imunidade contra erros gráficos (como `KeyError: 'DISPLAY'` ou `DevToolsActivePort`):
1. **Playwright Standalone:** O robô utiliza o Playwright Python, que instala e gerencia o Chromium de forma hermética, independente e fora do ecossistema Snap ou drivers globais do sistema.
2. **Execução Headless Real:** O navegador é iniciado no modo `headless=True` otimizado nativamente para servidores Linux.
3. **Persistência de Sessão:** O login inicial cria um arquivo `state.json`. Execuções posteriores reutilizam esse arquivo para evitar re-autenticação e desafios de segurança (CAPTCHA) do LinkedIn.

---

## 5. Próximos Passos Imediatos
1. **[F6.3]** Implementar os parsers HTML dos boards remotos (Jobspresso, JustRemote, DailyRemote, Pangian, ARC).
2. **[F6.4]** Wellfound com sessão manual e marketplaces em modo link-only com rascunho de proposta.
3. **[F6.5]** Boards brasileiros (Gupy, Vagas.com.br, Programathor).
4. **[F4.3]** Enriquecer as janelas 2 a 16 da Base Mestra via sessão de entrevista guiada + Copiloto IA.
5. Preencher as credenciais ausentes no `.env` local: `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` e `LINKEDIN_USERNAME`/`LINKEDIN_PASSWORD` — necessários para HITL e disparo real de candidaturas.
6. Garantir que o roteador de LLMs (`FreeLLM-router`) esteja de pé antes de rodar o motor: `docker compose up -d` em `/root/workspace/FreeLLM-router`.
7. Delegar ao OpenClaw a execução do motor via comando simples: `python crawler.py --all` ou `python playwright_bot.py`.
