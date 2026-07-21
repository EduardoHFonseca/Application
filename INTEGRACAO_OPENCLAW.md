# Especificação de Integração: OpenClaw & Project Application

Este documento descreve as interfaces, contratos de dados, comandos de execução e fluxos operacionais para que o orquestrador **OpenClaw** gerencie, acione e monitore o agente de candidaturas automatizadas no LinkedIn (**Project Application**).

---

## 1. Visão Geral da Arquitetura

O **Project Application** opera como um agente autônomo local integrado com Inteligência Artificial (Azure OpenAI `gpt-4o-mini`), banco de dados relacional **PostgreSQL**, notificação ativa via **Telegram** (*Human-in-the-Loop*) e relatório por e-mail via **AgentMail**.

```
┌─────────────────────────────────────────────────────────────┐
│                       OPENCLAW                              │
│                    (Orquestrador)                           │
└──────────────┬───────────────────────────────┬──────────────┘
               │ (Disparo CLI / Schedule)      │ (Geração de Matriz)
               ▼                               ▼
 ┌───────────────────────────┐   ┌───────────────────────────┐
 │   playwright_bot.py       │   │    ai_brain.py            │
 │ (Motor de Navegação Web)  │   │ (Consolidador de CVs)     │
 └─────────────┬─────────────┘   └─────────────┬─────────────┘
               │                               │
               ├───────────────┬───────────────┴──────────────┐
               ▼               ▼                              ▼
 ┌──────────────────┐ ┌──────────────────┐  ┌──────────────────┐
 │  PostgreSQL      │ │  Telegram Bot    │  │   AgentMail      │
 │ (application_db) │ │ (Human Feedback) │  │  (Relatórios)    │
 └──────────────────┘ └──────────────────┘  └──────────────────┘
```

---

## 2. Comandos de Invocação pelo OpenClaw (CLI Interfaces)

O OpenClaw pode invocar o robô via terminal/bash utilizando três modos principais:

### 2.1 Modo Varredura Completa (Crawler Loop Padrão)
Executa uma busca em lote no LinkedIn com base nas preferências configuradas no `.env` (`LINKEDIN_POSITIONS` e `LINKEDIN_LOCATIONS`).
```bash
python playwright_bot.py
```

### 2.2 Modo Candidatura Sob Demanda (URL Específica)
Aplica para uma vaga específica informada pelo OpenClaw via URL ou ID numérico do LinkedIn:
```bash
python playwright_bot.py --url "https://www.linkedin.com/jobs/view/4123456789/"
```
*Aplicações sob demanda ignoram os filtros gerais e focam exclusivamente no ID extraído.*

### 2.3 Modo Agendador Contínuo (Loop com Delay de 4h)
Roda a busca periodicamente respeitando o intervalo de segurança (padrão: 4 horas) entre as execuções:
```bash
python playwright_bot.py --loop --interval 4
```

### 2.4 Regeneração da Matriz de Competências (`Competencias.MD`)
Quando o OpenClaw adicionar ou atualizar modelos de currículos na pasta `source/`, deve acionar o consolidador para atualizar a matriz unificada:
```bash
python -c "from ai_brain import AIBrain; AIBrain.generate_competencias_md()"
```

### 2.5 Inicialização da Interface Visual (Streamlit Dashboard)
Para subir o painel de gerenciamento executivo e acompanhamento visual:
```bash
streamlit run app.py
```

---

## 3. Estrutura do Banco de Dados (`application_db` - PostgreSQL)

O OpenClaw pode consultar diretamente a tabela no PostgreSQL para gerar relatórios e métricas de desempenho.

- **URL de Conexão:** `postgresql://efonseca:123456@localhost:5432/application_db`

### Tabela `vagas`
| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `id` | SERIAL PRIMARY KEY | Identificador interno |
| `linkedin_job_id` | VARCHAR(100) UNIQUE | ID único da vaga no LinkedIn |
| `url` | TEXT | Link direto da vaga |
| `titulo` | TEXT | Cargo da oportunidade |
| `empresa` | TEXT | Nome da empresa anunciante |
| `localizacao` | TEXT | Cidade/Região/Modelo (Ex: Remoto) |
| `descricao` | TEXT | Texto na íntegra da Job Description |
| `status` | VARCHAR(50) | Status: `'iniciado'`, `'cv_gerado'`, `'aplicado'`, `'falha'` |
| `pdf_custom_path` | TEXT | Caminho do PDF customizado gerado para a vaga |
| `criado_em` | TIMESTAMP | Data de descoberta da vaga |
| `atualizado_em` | TIMESTAMP | Data da última alteração de status |

### Tabela `perguntas_respostas`
| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `id` | SERIAL PRIMARY KEY | Identificador interno |
| `vaga_id` | INTEGER | FK referente à tabela `vagas(id)` |
| `pergunta` | TEXT | Pergunta formulada pelo formulário Easy Apply |
| `resposta` | TEXT | Resposta fornecida |
| `origem` | VARCHAR(50) | Origem da resposta: `'ia'`, `'telegram'`, `'padrao'` |
| `respondido_em` | TIMESTAMP | Data do preenchimento |

---

## 4. Fluxo Bidirecional Human-in-the-Loop (Telegram)

Quando a IA encontra uma pergunta não coberta pela matriz `Competencias.MD`:
1. O bot envia uma mensagem Markdown para o Telegram configurado (`TELEGRAM_CHAT_ID` / `TELEGRAM_BOT_TOKEN`).
2. Entra em modo de escuta ativa (polling local) aguardando até 5 minutos (`timeout_seconds=300`).
3. Ao receber a resposta humana, injeta no formulário do LinkedIn e grava o evento no PostgreSQL com `origem='telegram'`.

---

## 5. Notificação de Conclusão por E-mail (AgentMail)

Após cada candidatura enviada com sucesso, o sistema dispara um e-mail automático via **AgentMail API**:
- **Destinatário:** `fonseca.eduardo@terra.com.br`
- **Conteúdo:** Título da vaga, resumo do preenchimento de perguntas/respostas e **PDF do currículo customizado anexado**.
