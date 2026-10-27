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

## Crawler multi-fonte

Além do LinkedIn, o crawler descobre vagas em **Remotive**, **We Work Remotely** e **Working Nomads** (APIs/RSS públicas). O catálogo de fontes fica em [`config/sources.yaml`](config/sources.yaml), incluindo a curadoria de `Application.txt` e o motivo de cada item descartado.

```bash
# Listar fontes, status e modo de candidatura
.venv/bin/python crawler.py --list-sources

# Simular coleta (não grava nada no banco)
.venv/bin/python crawler.py --source remotive --source wwr --source workingnomads --dry-run

# Coletar e gravar (respeita o intervalo mínimo por fonte)
.venv/bin/python crawler.py --all

# Coletar e já gerar CV personalizado para as vagas novas
.venv/bin/python crawler.py --all --with-cv

# O CLI do motor LinkedIn também delega para o crawler
.venv/bin/python playwright_bot.py --source remotive
```

Modos de candidatura: `auto` (somente LinkedIn), `assisted` (descoberta + CV + aviso) e `link_only` (marketplaces, envio manual). O crawler respeita `robots.txt`, intervalos por fonte e não tenta burlar CAPTCHA/Cloudflare.

### Migração do banco (multi-fonte)

```bash
psql -U dbadmin -d application_db -f migrations/001_add_source_columns.sql
```

Adiciona `fonte`, `source_job_id`, `apply_mode` e `hash_dedupe` à tabela `vagas`, com índice único `(fonte, source_job_id)`.

## Configuração

| Chave | Descrição |
| --- | --- |
| `DATABASE_URL` | Conexão PostgreSQL do serviço |
| `CV_TEMPLATE` | `harvard` (ATS, padrão) ou `corporate` (legado) |
| `AZURE_OPENAI_*` | Cérebro IA |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Human-in-the-Loop |
| `LINKEDIN_*` | Credenciais e preferências do crawler |
| `CRAWLER_SOURCES` | Fontes habilitadas (ex.: `remotive,wwr,workingnomads`) |
| `SEARCH_KEYWORDS` / `SEARCH_LOCATIONS` | Filtros padrão do crawler multi-fonte |
| `CRAWLER_LIMIT_PER_SOURCE` | Limite de vagas por fonte (padrão 50) |

Também é possível editar tudo pela aba **⚙️ Filtros & Configurações** do painel, que grava o `.env`.

## Estrutura

```
app.py            Painel Streamlit (histórico, sob demanda, curação, acervo, fontes)
ai_brain.py       Cérebro IA: análise de vaga, síntese de CV e geração de PDF
playwright_bot.py Motor de candidatura LinkedIn (Playwright headless)
crawler.py        Orquestrador multi-fonte (descoberta → dedupe → CV → aviso)
sources/          Adaptadores por site (Remotive, WWR, Working Nomads, LinkedIn)
config/           Catálogo de fontes e curadoria (sources.yaml)
migrations/       DDL incremental aplicado pelo dbadmin
database.py       Persistência PostgreSQL
schema.sql        DDL do banco (aplicar como dbadmin)
telegram_bot.py   Canal humano via Telegram
email_service.py  Notificação por e-mail
source/           Acervo de currículos e cartas base
custom_cvs/       PDFs customizados gerados por vaga
bot-core/         Legado Selenium (não utilizado)
```
