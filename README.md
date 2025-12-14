# KiraBot — Tickets + Verificação (Discord)

Um bot simples e “pronto pra uso” para Discord, com:
- Painel de tickets (botão + menu de categorias)
- Categorias/canais criados automaticamente (organizado)
- Controle por cargo de staff (atendimento)
- Logs de abertura/fechamento
- Transcrição automática ao fechar o ticket (arquivo .txt)
- Multi-servidor isolado (cada servidor tem suas configurações no SQLite)

## Requisitos
- Python 3.10+ (recomendado 3.11+)
- Permissões do bot no servidor:
  - Manage Channels
  - Manage Roles (para verificação)
  - Read/Send Messages

## Instalação
1) Instale as dependências:
```bash
pip install -r requirements.txt
```

2) Crie o arquivo `.env` (ou exporte a variável no sistema).  
Use o modelo:
- `.env.example`

3) Rode:
```bash
python bot.py
```

## Primeiro setup (no servidor)
Como **admin do servidor**, rode:

1) Definir cargo de staff (quem atende e enxerga tickets):
```text
r!setup_staff @SeuCargoStaff
```

2) Definir canal de logs (onde vão as transcrições e eventos):
```text
r!setup_logs #logs-tickets
```

3) (Opcional) Definir onde quer postar o painel:
```text
r!setup_panel #painel
```

4) Postar os painéis:
```text
r!post_ticket
r!post_verificar
```

## Como funciona
- Se as categorias de tickets não existirem, o bot cria:
  - 📩 Tickets - Suporte
  - 💰 Tickets - Financeiro
  - 🧩 Tickets - ModCreator
  - 🎭 Tickets - ModelCreator
- Ao abrir ticket, o bot cria um canal privado dentro da categoria correta.
- O dono do ticket e o staff conseguem fechar.
- Ao fechar, o bot gera uma transcrição `.txt` e envia no canal de logs.

## Ajuda rápida
```text
r!help_ticket
```

## Banco de dados (SQLite)
O bot cria o arquivo `tickets.db` automaticamente.  
Ele guarda:
- Config do servidor (logs, staff, painel)
- Tickets abertos
- Categorias criadas

## Segurança
- Nunca coloque o token no código.
- Regere o token se ele já foi exposto em algum lugar.
