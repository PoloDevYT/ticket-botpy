# KiraBot — Tickets, Verificação e Painel Web

Este repositório reúne o bot de tickets para Discord e um painel HTML para visualizar dados e ajustar configurações. Tudo está em português e pronto para uso rápido.

## Funcionalidades principais
- **Painel de tickets no Discord**: botão de abertura e menu de categorias.
- **Categorias automáticas**: cria e organiza os canais necessários.
- **Controle de staff**: apenas quem tem o cargo autorizado enxerga e atende.
- **Logs e transcrições**: fechamento gera arquivo `.txt` e envia no canal de logs.
- **Painel web (HTML)**: login via Discord OAuth2, lista servidores onde você é admin, exibe estatísticas e permite editar IDs de log e cargo staff diretamente no banco.

## Requisitos
- Python 3.10+ (recomendado 3.11+)
- Bibliotecas do `requirements.txt`
- Permissões do bot no servidor:
  - Manage Channels
  - Manage Roles (para verificação)
  - Read/Send Messages

## Configuração do bot
1. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
2. Crie o `.env` usando `.env.example` como base e defina pelo menos `DISCORD_TOKEN`.
3. Inicie o bot:
   ```bash
   python bot.py
   ```

### Primeiro setup no servidor
Como administrador do servidor, execute os comandos no Discord:
1. Definir cargo de staff (quem atende e enxerga tickets):
   ```text
   r!setup_staff @SeuCargoStaff
   ```
2. Definir canal de logs (onde vão transcrições e eventos):
   ```text
   r!setup_logs #logs-tickets
   ```
3. (Opcional) Definir canal para publicar o painel de tickets:
   ```text
   r!setup_panel #painel
   ```
4. Postar os painéis:
   ```text
   r!post_ticket
   r!post_verificar
   ```

## Painel web HTML
O painel web consome o mesmo `tickets.db` que o bot e usa OAuth2 do Discord.

1. Configure no `.env`:
   - `DISCORD_CLIENT_ID`
   - `DISCORD_CLIENT_SECRET`
   - `DISCORD_REDIRECT_URI` (opcional, padrão `http://localhost:5000/callback`)
   - `DISCORD_TOKEN` (para detectar em quais servidores o bot já está)
2. Inicie o painel:
   ```bash
   python dashboard.py
   ```
3. Acesse `http://localhost:5000`, faça login com Discord e selecione o servidor onde você é administrador.
4. No painel do servidor você pode:
   - Ver contagem de tickets por categoria.
   - Listar tickets em aberto (dados vindos do `tickets.db`).
   - Atualizar IDs do canal de logs e do cargo de staff.

## Banco de dados
O arquivo `tickets.db` é criado automaticamente. Ele armazena:
- Configurações do servidor (painel, logs, staff)
- Tickets em aberto
- Categorias já criadas

## Boas práticas de segurança
- Nunca coloque o token do bot em código ou capturas de tela.
- Regere o token se ele for exposto.
