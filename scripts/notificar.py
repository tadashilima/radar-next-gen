"""Envia o resumo diário do Radar Next Gen por Telegram e email.

Lê site/status.json (gravado pela curadoria diária) e usa estas variáveis de ambiente,
pulando o canal cujas variáveis estiverem vazias:
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
  GMAIL_USER, GMAIL_APP_PASSWORD, EMAIL_DESTINATARIOS (separados por vírgula ou quebra de linha)
"""
import html
import json
import os
import smtplib
import sys
import urllib.parse
import urllib.request
from email.message import EmailMessage
from pathlib import Path

SITE_URL = os.environ.get("SITE_URL", "https://tadashilima.github.io/radar-next-gen/")
STATUS = Path(__file__).resolve().parent.parent / "site" / "status.json"


def data_br(iso):
    a, m, d = iso.split("-")
    return f"{d}/{m}"


def montar(st):
    dia = data_br(st["data"])
    if st.get("novidade"):
        p = st.get("principal") or {}
        assunto = f"Radar Next Gen · {dia} · {st.get('titulo', 'novidades')}"
        linhas = [st.get("destaque", "")]
        if p.get("url"):
            linhas += ["", f"Mais importante: {p.get('titulo', '')}", p["url"]]
        linhas += ["", f"{st.get('itens_novos', 0)} itens novos na edição de hoje: {SITE_URL}"]
        tg = [f"<b>Radar Next Gen · {dia}</b>", "", f"<b>{html.escape(st.get('titulo', ''))}</b>",
              html.escape(st.get("destaque", ""))]
        if p.get("url"):
            tg += ["", f'Mais importante: <a href="{html.escape(p["url"])}">{html.escape(p.get("titulo", ""))}</a>']
        tg += ["", f'{st.get("itens_novos", 0)} itens novos · <a href="{SITE_URL}">ver edição</a>']
    else:
        assunto = f"Radar Next Gen · {dia} · sem novidade relevante"
        linhas = ["Sem novidade relevante hoje.", "", f"Radar completo: {SITE_URL}"]
        tg = [f"<b>Radar Next Gen · {dia}</b>", "", "Sem novidade relevante hoje.",
              f'<a href="{SITE_URL}">Ver o radar</a>']
    corpo = "\n".join(linhas) + "\n\nCuradoria de Lucas Tadashi Lima.\n"
    return assunto, corpo, "\n".join(tg)


def telegram(texto):
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        print("Telegram: sem credenciais, pulando")
        return True
    dados = urllib.parse.urlencode({"chat_id": chat, "text": texto, "parse_mode": "HTML",
                                    "disable_web_page_preview": "true"}).encode()
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", dados, timeout=30) as r:
            ok = json.load(r).get("ok")
    except Exception as e:  # noqa: BLE001
        print(f"Telegram: falhou ({type(e).__name__})")
        return False
    print("Telegram: enviado" if ok else "Telegram: recusado")
    return bool(ok)


def email(assunto, corpo):
    user, senha = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD")
    dest = [e.strip() for e in os.environ.get("EMAIL_DESTINATARIOS", "").replace("\n", ",").split(",") if e.strip()]
    if not (user and senha):
        print("Email: sem credenciais, pulando")
        return True
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = assunto, f"Radar Next Gen <{user}>", user
    if dest:
        msg["Bcc"] = ", ".join(dest)
    msg.set_content(corpo)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
            s.login(user, senha)
            s.send_message(msg)
    except Exception as e:  # noqa: BLE001
        print(f"Email: falhou ({type(e).__name__})")
        return False
    print(f"Email: enviado para você + {len(dest)} em cópia oculta")
    return True


if __name__ == "__main__":
    st = json.loads(STATUS.read_text(encoding="utf-8"))
    assunto, corpo, tg = montar(st)
    if "--dry-run" in sys.argv:
        print(assunto, corpo, tg, sep="\n---\n")
        sys.exit(0)
    ok = [telegram(tg), email(assunto, corpo)]
    sys.exit(0 if all(ok) else 1)
