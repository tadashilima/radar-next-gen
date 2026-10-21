# Radar Next Gen

Curadoria diária do estado da arte em foundation models para crédito e fraude. Por Lucas Tadashi Lima.

Site: https://tadashilima.github.io/radar-next-gen/

## Como funciona

1. Uma rotina do Claude Code roda todo dia às 8h (horário de Brasília) na nuvem e segue [CURADORIA.md](CURADORIA.md).
2. Ela grava duas coisas e faz o commit:
   - a edição do dia, em `site/edicoes.json`;
   - o resumo para notificação, em `site/status.json`.
3. O workflow `.github/workflows/publicar.yml` publica `site/` no GitHub Pages.
4. Se `status.json` mudou, o mesmo workflow roda `scripts/notificar.py`, que manda o resumo para o canal do Telegram e por email.

## Configuração (Settings → Secrets and variables → Actions)

| Nome | Tipo | O que é |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | secret | Token do bot criado no @BotFather |
| `TELEGRAM_CHAT_ID` | variable | `@nome_do_canal`, com o bot como administrador |
| `GMAIL_USER` | variable | Gmail que envia (o resumo também chega nele) |
| `GMAIL_APP_PASSWORD` | secret | Senha de app do Google (exige verificação em 2 etapas) |
| `EMAIL_DESTINATARIOS` | secret | Emails em cópia oculta, separados por vírgula |

Para testar o envio sem esperar o dia seguinte: Actions → "Publicar e notificar" → Run workflow, com "notificar" marcado.
