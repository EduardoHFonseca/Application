# Solicitação de Refatoração: Migração do Motor Bot para Playwright

Devido a sucessivas falhas de inicialização do Chromium via Selenium/WebDriver-Manager no ambiente isolado (headless) da VM Linux, o modelo atual baseado no repositório `LinkedIn-Easy-Apply-Bot` demonstrou-se instável e de difícil manutenção.

Solicito ao agente codificador a reconstrução do "Motor Bot" (a camada responsável pela navegação no LinkedIn) utilizando **Playwright**.

## Requisitos para o Novo Motor (Playwright)

1.  **Tecnologia:** Utilizar o framework Playwright para Python (`playwright`).
2.  **Modo de Execução:** Deve suportar execução headless (`headless=True`) de forma nativa e estável no Linux.
3.  **Persistência de Sessão:** Implementar o salvamento do estado do navegador (cookies, localStorage) após o primeiro login bem-sucedido. Isso evitará que o LinkedIn exija CAPTCHAs a cada execução. (Pesquisar: `browser.new_context(storage_state="state.json")`).
4.  **Integração de Credenciais:** Ler o `username` e `password` do LinkedIn, além de outras preferências, diretamente do arquivo `.env` global, descartando o uso de `config.yaml`.
5.  **Fluxo Básico (MVP):**
    *   Fazer login na plataforma.
    *   Navegar até a página de busca de vagas com os filtros definidos (ex: cargo, localidade, Easy Apply).
    *   Extrair o título da vaga, o link e a descrição (Job Description).
    *   Pausar a automação e acionar o módulo `AIBrain` (já existente no `ai_brain.py`) repassando os dados extraídos.
    *   (A parte de preenchimento e upload do currículo pode ser implementada em uma segunda etapa, o foco agora é estabilizar a extração e integração com a IA).

## Próximos Passos (Agente Codificador)

*   Criar um novo arquivo (ex: `playwright_bot.py`) na raiz do projeto.
*   Implementar a lógica descrita acima.
*   Atualizar o `PLANO_DESENVOLVIMENTO.md` refletindo a mudança de tecnologia na camada de navegação.
