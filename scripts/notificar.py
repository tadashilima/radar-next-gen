"""Envia a edição do dia do Radar Next Gen por Telegram e email.

Lê site/status.json (gravado pela curadoria diária) e site/edicoes.json, monta a edição com
scripts/edicao.py (mesma estrutura do site) e usa estas variáveis de ambiente, pulando o canal
cujas variáveis estiverem vazias:
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
  GMAIL_USER, GMAIL_APP_PASSWORD, EMAIL_DESTINATARIOS (separados por vírgula ou quebra de linha)

Telegram: mensagem com a edição inteira e, em seguida, o PDF. Email: HTML com a edição inteira
(texto puro como alternativa) e o PDF anexado. Sem Chrome no ambiente, segue sem o PDF.
"""
import json
import mimetypes
import os
import smtplib
import sys
import tempfile
import urllib.parse
import urllib.request
import uuid
from email.message import EmailMessage
from pathlib import Path

import edicao as ed_mod

SITE_URL = ed_mod.SITE_URL
STATUS = ed_mod.STATUS


def api_telegram(metodo, campos, arquivo=None):
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    campos = {"chat_id": chat, **campos}
    url = f"https://api.telegram.org/bot{token}/{metodo}"
    if arquivo is None:
        dados, cabecalho = urllib.parse.urlencode(campos).encode(), {}
    else:  # multipart/form-data montado à mão, sem dependências
        limite = uuid.uuid4().hex
        partes = []
        for k, v in campos.items():
            partes.append(f"--{limite}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
        tipo = mimetypes.guess_type(arquivo.name)[0] or "application/octet-stream"
        partes.append(f"--{limite}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{arquivo.name}\"\r\n"
                      f"Content-Type: {tipo}\r\n\r\n".encode() + arquivo.read_bytes() + b"\r\n")
        partes.append(f"--{limite}--\r\n".encode())
        dados, cabecalho = b"".join(partes), {"Content-Type": f"multipart/form-data; boundary={limite}"}
    with urllib.request.urlopen(urllib.request.Request(url, dados, cabecalho), timeout=60) as r:
        return json.load(r).get("ok")


def telegram(texto, pdf=None):
    if not (os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")):
        print("Telegram: sem credenciais, pulando")
        return True
    try:
        ok = api_telegram("sendMessage", {"text": texto, "parse_mode": "HTML", "disable_web_page_preview": "true"})
        if ok and pdf:
            ok = api_telegram("sendDocument", {"caption": "Edição em PDF"}, arquivo=pdf) and ok
    except Exception as e:  # noqa: BLE001
        print(f"Telegram: falhou ({type(e).__name__})")
        return False
    print("Telegram: enviado" if ok else "Telegram: recusado")
    return bool(ok)


def email(assunto, texto, html=None, pdf=None):
    user, senha = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD")
    dest = [e.strip() for e in os.environ.get("EMAIL_DESTINATARIOS", "").replace("\n", ",").split(",") if e.strip()]
    if not (user and senha):
        print("Email: sem credenciais, pulando")
        return True
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = assunto, f"Radar Next Gen <{user}>", user
    if dest:
        msg["Bcc"] = ", ".join(dest)
    msg.set_content(texto)
    if html:
        msg.add_alternative(html, subtype="html")
    if pdf:
        msg.add_attachment(pdf.read_bytes(), maintype="application", subtype="pdf", filename=pdf.name)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
            s.login(user, senha)
            s.send_message(msg)
    except Exception as e:  # noqa: BLE001
        print(f"Email: falhou ({type(e).__name__})")
        return False
    print(f"Email: enviado para você + {len(dest)} em cópia oculta")
    return True


def montar(st):
    """Devolve (assunto, texto, html, texto_telegram, edicao)."""
    if not st.get("novidade"):
        dia = ed_mod.data_longa(st.get("data", ""))
        texto = f"Sem novidade relevante hoje.\n\nRadar completo: {SITE_URL}\n\n{ed_mod.CREDITO}.\n"
        return f"Radar Next Gen · {dia} · sem novidade relevante", texto, None, ed_mod.telegram_sem_novidade(st), None
    ed = ed_mod.edicao_do_dia(st)
    return ed_mod.assunto(ed), ed_mod.texto_plano(ed), ed_mod.html_edicao(ed), ed_mod.telegram(ed), ed


if __name__ == "__main__":
    st = json.loads(STATUS.read_text(encoding="utf-8"))
    assunto, texto, html, tg, ed = montar(st)
    if "--dry-run" in sys.argv:
        print(assunto, texto, tg, sep="\n---\n")
        sys.exit(0)
    pdf = None
    if ed is not None:
        pdf = ed_mod.gerar_pdf(ed, Path(tempfile.mkdtemp(prefix="radar-")) / ed_mod.nome_pdf(ed))
    ok = [telegram(tg, pdf), email(assunto, texto, html, pdf)]
    sys.exit(0 if all(ok) else 1)
