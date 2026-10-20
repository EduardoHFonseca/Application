# Application — Store Agentic Applicator

Automação de candidaturas LinkedIn Easy Apply com cérebro IA (Azure OpenAI), persistência PostgreSQL e painel Streamlit. Detalhes de arquitetura e backlog em [`PLANO_DESENVOLVIMENTO.md`](PLANO_DESENVOLVIMENTO.md).

## Pré-requisitos

- Python 3.12+
- PostgreSQL 14+ rodando local (banco `application_db`, schema `application`)

## Setup

```bash
# 1. Ambiente virtual + dependências
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Navegador headless do Playwright (hermético, fora do Snap/global)
.venv/bin/playwright install --with-deps chromium

# 3. Variáveis de ambiente
cp .env.example .env   # e preencher as chaves

# 4. Schema do banco (o usuário de serviço não tem permissão de DDL)
psql -U dbadmin -d application_db -f schema.sql
```

## Execução

```bash
# Painel de controle (Streamlit)
.venv/bin/streamlit run app.py --server.headless true

# Candidatura sob demanda por URL
.venv/bin/python playwright_bot.py --url "https://www.linkedin.com/jobs/view/<ID>/"

# Modo loop (respeita CRAWLER_INTERVAL_HOURS)
.venv/bin/python playwright_bot.py --loop

# Testes
.venv/bin/python -m unittest test_suite -v
```

O login inicial no LinkedIn cria o `state.json` na raiz (gitignored); execuções seguintes reutilizam a sessão.

## Configuração

| Chave | Descrição |
| --- | --- |
| `DATABASE_URL` | Conexão PostgreSQL do serviço |
| `CV_TEMPLATE` | `harvard` (ATS, padrão) ou `corporate` (legado) |
| `AZURE_OPENAI_*` | Cérebro IA |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Human-in-the-Loop |
| `LINKEDIN_*` | Credenciais e preferências do crawler |

Também é possível editar tudo pela aba **⚙️ Filtros & Configurações** do painel, que grava o `.env`.

## Estrutura

```
app.py            Painel Streamlit (histórico, sob demanda, curação, acervo)
ai_brain.py       Cérebro IA: análise de vaga, síntese de CV e geração de PDF
playwright_bot.py Motor de candidatura (Playwright headless)
database.py       Persistência PostgreSQL
schema.sql        DDL do banco (aplicar como dbadmin)
telegram_bot.py   Canal humano via Telegram
email_service.py  Notificação por e-mail
source/           Acervo de currículos e cartas base
custom_cvs/       PDFs customizados gerados por vaga
bot-core/         Legado Selenium (não utilizado)
```
