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

## 3. Instruções de Execução em Servidor/VM Headless (SSH)

Para garantir 100% de estabilidade e imunidade contra erros gráficos (como `KeyError: 'DISPLAY'` ou `DevToolsActivePort`):
1. **Playwright Standalone:** O robô utiliza o Playwright Python, que instala e gerencia o Chromium de forma hermética, independente e fora do ecossistema Snap ou drivers globais do sistema.
2. **Execução Headless Real:** O navegador é iniciado no modo `headless=True` otimizado nativamente para servidores Linux.
3. **Persistência de Sessão:** O login inicial cria um arquivo `state.json`. Execuções posteriores reutilizam esse arquivo para evitar re-autenticação e desafios de segurança (CAPTCHA) do LinkedIn.

---

## 4. Próximos Passos Imediatos
1. Inserir os dados de API e credenciais do Telegram e do LinkedIn no arquivo local `.env` (Já preenchido pelo usuário).
2. Delegar ao OpenClaw a execução do motor via comando simples: `python playwright_bot.py`.
