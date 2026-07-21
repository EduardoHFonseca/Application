# Log de Correções e Melhorias (Orquestrador OpenClaw - Twister)

Durante os testes de integração e acionamento, identifiquei e resolvi os seguintes gargalos no motor de candidatura e no módulo de inteligência artificial:

### 1. Inicialização e Autenticação (Banco e Ambiente)
- **Correção da Ordem de Importação (`app.py`, `playwright_bot.py`)**: O banco de dados PostgreSQL estava falhando ao inicializar porque o `database.py` estava sendo carregado *antes* do `.env` injetar as senhas, caindo na configuração default vazia. Corrigido para garantir que `load_dotenv` seja a primeira operação do escopo.

### 2. Geração e Formatação do Currículo PDF (`ai_brain.py`)
- **Sanitização de Fonte no FPDF**: O pacote `fpdf2` sofria pane com caracteres estendidos (como travessões longos `–` e aspas curvas originárias de Word). Criada a função `sanitize_text()` para limpar todo o input antes da geração do PDF, mantendo compatibilidade com a fonte `helvetica` base.
- **Estruturação Correta de Retorno do LLM (JSON vs String)**: A IA (`gpt-4o-mini`) estava quebrando a diretriz de output e devolvendo o campo `full_original_experience` como uma lista de dicionários JSON em vez de string pura. Modifiquei o código para iterar e formatar listas/dicionários no PDF caso o LLM volte a alucinar a estrutura, além de adicionar uma restrição explícita no System Prompt (`JAMAIS retorne listas de objetos JSON`).
- **Refinamento Semântico e Keyword Stuffing**: Alterado o System Prompt no `customize_cv_text` para ordenar o modelo a evitar repetições exaustivas (ex: "LGPD", "IA" aparecendo em todo bloco) e produzir um texto elegante, orgânico e fluido.
- **Correção da Base Cognitiva (Hook no Motor)**: O `playwright_bot` ainda usava a função velha `select_best_cv` que pegava o currículo "menos pior" (ex: `CV-EHF-Template PORT.pdf`). Refatorei a injeção para que a IA sempre consuma a nova super matriz `Competencias.MD` (`AIBrain.get_competencias_context()`) na hora de sintetizar a versão focada da vaga.

### 3. Automação Playwright e Gestão do LinkedIn
- **Robusteza do Botão Easy Apply**: O botão era frequentemente omitido por carregamentos assíncronos ou divs aninhadas (Testes A/B do LinkedIn).
  - Adicionado `page.wait_for_timeout(4000)` para dar fôlego ao render da página.
  - Implementado duplo fallback de clique: tenta localizadores mistos (`button.jobs-apply-button`, `button:has-text('Easy Apply')`, etc.) e, em caso de erro por sobreposição DOM, utiliza Injeção JavaScript agressiva forçando o clique nativo via `.click()`.
- **Limitação de Gaveta de Currículos (Limite de 5)**: O LinkedIn bloqueia uploads se o container de arquivos salvos encher. Inserida uma rotina destrutiva no método `upload_cv_if_requested` que, antes de tentar enviar o novo PDF gerado, varre e clica nas lixeiras (`Delete / Remove`) até esvaziar a lista antiga, limpando espaço.

### 4. Sistema de Notificação e Feedback (AgentMail)
- **E-mail Imediato de Geração**: O envio estava configurado apenas no final do Wizard. Caso o LinkedIn bloqueasse a candidatura, o PDF ia para o ralo. Criei `EmailService.send_cv_generated_email` e posicionei logo após a geração da IA. Assim, o usuário recebe a versão customizada no e-mail na mesma hora, podendo usar para candidatura manual se a automação falhar.
