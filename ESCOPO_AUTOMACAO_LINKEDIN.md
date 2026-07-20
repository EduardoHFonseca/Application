# Arquitetura de Automação: LinkedIn Easy Apply Dinâmico

Este documento descreve o escopo e a arquitetura do projeto de automação de candidaturas no LinkedIn, integrando navegação web com Inteligência Artificial para personalização de currículos.

## 1. Visão Geral
O objetivo não é apenas automatizar cliques, mas garantir a qualidade das candidaturas. Para evitar os bloqueios anti-bot do LinkedIn e reduzir o tempo de desenvolvimento, utilizaremos um motor open-source consolidado para a navegação, enquanto os Agentes (Cérebro) ficarão responsáveis por adaptar o material do candidato à vaga.

## 2. Divisão de Tarefas

### Fase 1: Motor de Navegação (Bot Open-Source)
- **Ferramenta sugerida:** Fork de `nicolomantini/LinkedIn-Easy-Apply-Bot` ou similar.
- **Responsabilidades:**
  - Login seguro e bypass básico de automação.
  - Busca de vagas baseada em palavras-chave e filtros (foco exclusivo em "Easy Apply").
  - Extração da Descrição da Vaga (Job Description) e das Questões Adicionais.
  - Pausar o fluxo de submissão e enviar os dados extraídos para o módulo de IA.

### Fase 2: O Cérebro (Agentes IA)
- **Entrada:** Descrição da vaga e perguntas adicionais extraídas pela Fase 1.
- **Responsabilidades:**
  - Analisar os currículos base localizados na pasta `source/` (ex: perfis de PO/PM, IT Manager, Consultor, em Inglês e Português).
  - Selecionar o melhor CV base para a vaga.
  - Gerar um currículo personalizado destacando as habilidades exigidas pela vaga.
  - Gerar o PDF final.
  - Formular as respostas para as perguntas adicionais do Easy Apply (pretensão salarial, anos de experiência em X, etc.).
- **Saída:** Arquivo PDF customizado e JSON com as respostas estruturadas.

### Fase 3: Submissão (Motor de Navegação)
- **Responsabilidades:**
  - Retomar o fluxo no LinkedIn.
  - Fazer o upload do PDF gerado.
  - Preencher os campos com as respostas geradas pela IA.
  - Concluir a candidatura ("Submit Application").
  - **Notificação e Backup por E-mail (NOVO):** Logo após a submissão bem-sucedida, enviar uma notificação por e-mail para **fonseca.eduardo@terra.com.br** (via AgentMail) com o arquivo do currículo customizado anexado, acrescido do título da vaga e a lista exata de perguntas e respostas preenchidas no formulário.

---

## 3. Integrações e Orquestração (OpenClaw)

### 3.1 Loop de Mensagens do Telegram (Human-in-the-Loop)
- Quando o Cérebro de IA deparar-se com uma pergunta para a qual não possui dados suficientes para responder de forma fidedigna, a execução entrará em estado de espera ativa (*pooling*).
- Uma notificação contendo os detalhes da vaga e a pergunta será enviada via **Telegram Bot**.
- **Nota de Credenciais:** Como o **OpenClaw** já possui a comunicação via Telegram plenamente configurada e ativa com o usuário, **o robô deve reutilizar essa credencial e canal de mensageria pré-existentes** no orquestrador para centralizar o fluxo de perguntas e respostas humanas.

### 3.2 Notificações por E-mail (AgentMail)
- A cada candidatura finalizada, o sistema dispara um e-mail utilizando o AgentMail direcionado a **fonseca.eduardo@terra.com.br** para consolidar as respostas enviadas e registrar uma cópia de backup do currículo gerado para controle pessoal.

