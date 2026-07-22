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
- [ ] **[F4.1] Camada 1 - Base Mestra de Carreira Granular (`master_career_base.json`):**
  - Estruturação do histórico completo por Empresa, Cargo, Período, Escopo/Equipe/Budget, Conquistas Quantificadas (Métricas STAR), Case Studies de Projetos e Tags de Perfil (`CTO`, `PRODUCT_HEAD`, `IT_MANAGER`, `CONSULTING`).
- [ ] **[F4.2] Camada 2 - Motor de Redação Executiva (STAR Tailored Engine):**
  - Job Profiler (Aderência de perfil, ATS Keywords, Idioma).
  - Resgate inteligente de fatos e conquistas relevantes sem alucinações.
- [ ] **[F4.3] Camada 3 - Template PDF Padrão Harvard/Corporate:**
  - Layout denso e otimizado para robôs de recrutamento (ATS).

---

## 4. Instruções de Execução em Servidor/VM Headless (SSH)

Para garantir 100% de estabilidade e imunidade contra erros gráficos (como `KeyError: 'DISPLAY'` ou `DevToolsActivePort`):
1. **Playwright Standalone:** O robô utiliza o Playwright Python, que instala e gerencia o Chromium de forma hermética, independente e fora do ecossistema Snap ou drivers globais do sistema.
2. **Execução Headless Real:** O navegador é iniciado no modo `headless=True` otimizado nativamente para servidores Linux.
3. **Persistência de Sessão:** O login inicial cria um arquivo `state.json`. Execuções posteriores reutilizam esse arquivo para evitar re-autenticação e desafios de segurança (CAPTCHA) do LinkedIn.

---

## 4. Próximos Passos Imediatos
1. Inserir os dados de API e credenciais do Telegram e do LinkedIn no arquivo local `.env` (Já preenchido pelo usuário).
2. Delegar ao OpenClaw a execução do motor via comando simples: `python playwright_bot.py`.
