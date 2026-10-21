"""Monta a edição do dia nos três formatos de envio: texto do Telegram, email HTML (com versão
em texto puro) e a página para virar PDF. Segue a mesma estrutura do site: título, destaque,
"Em resumo", item principal com "Por que importa", demais itens, "Para levar para o time".

Uso direto, para conferir sem enviar:
  python3 scripts/edicao.py --saida /tmp/preview      grava telegram.txt, email.html, email.txt, edicao.pdf
"""
import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
EDICOES = RAIZ / "site" / "edicoes.json"
STATUS = RAIZ / "site" / "status.json"
SITE_URL = os.environ.get("SITE_URL", "https://tadashilima.github.io/radar-next-gen/")
TELEGRAM_URL = "https://t.me/radarnextgen"
CREDITO = "Curadoria de Lucas Tadashi"

TEMAS = {"ldm": "Large Data Models", "transacional": "FM de transações", "tabular": "FM tabular",
         "agentes": "LLMs e agentes", "producao": "Produção e risco", "brasil": "Brasil"}
FONTES = {"x": "X", "reddit": "Reddit", "arxiv": "arXiv", "hf": "Hugging Face", "github": "GitHub",
          "blog": "Blog", "noticia": "Notícia", "podcast": "Podcast", "evento": "Evento"}
SINAL = {"alto": "alto", "medio": "médio", "baixo": "baixo"}
RANK = {"alto": 0, "medio": 1, "baixo": 2}
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
         "outubro", "novembro", "dezembro"]
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]


def esc(s):
    return html.escape(str(s or ""), quote=True)


def data_longa(iso):
    """2026-10-21 -> quarta-feira, 21 de outubro de 2026"""
    import datetime as dt
    try:
        d = dt.date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or ""
    return f"{DIAS[d.weekday()]}, {d.day} de {MESES[d.month - 1]} de {d.year}"


def data_curta(iso):
    import datetime as dt
    try:
        d = dt.date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or ""
    return f"{d.day} de {MESES[d.month - 1][:3]} de {d.year}"


def rotulo(ed):
    return "Edição zero" if ed.get("id") == "edicao-zero" else data_longa(ed.get("data", "")).capitalize()


def minutos(ed):
    partes = [ed.get("titulo", ""), ed.get("destaque", ""), *ed.get("resumo", []), *ed.get("perguntas", [])]
    partes += [f"{i.get('titulo', '')} {i.get('porque', '')}" for i in ed.get("itens", [])]
    return max(1, round(len(" ".join(partes).split()) / 200))


def ordenar(ed):
    return sorted(ed.get("itens", []), key=lambda i: RANK.get(i.get("sinal"), 2))


def fonte_data(i):
    f = FONTES.get(i.get("fonte"), i.get("fonte") or "Fonte")
    return f"{f}, {data_curta(i['data'])}" if i.get("data") else f


def edicao_do_dia(status=None):
    """A edição que o status.json aponta; se não houver, a mais recente."""
    eds = json.loads(EDICOES.read_text(encoding="utf-8"))
    eds.sort(key=lambda e: e.get("data", ""), reverse=True)
    if not eds:
        return None
    if status:
        for e in eds:
            if e.get("data") == status.get("data") or e.get("id") == status.get("data"):
                return e
    return eds[0]


def url_edicao(ed):
    return SITE_URL if ed.get("id") == edicao_do_dia().get("id") else f"{SITE_URL}?edicao={ed.get('id', '')}"


# ---------- Telegram (parse_mode=HTML; limite de 4096 caracteres) ----------

def telegram(ed):
    itens = ordenar(ed)
    lead, resto = (itens[0], itens[1:]) if itens else (None, [])
    t = [f"<b>Radar Next Gen</b> · {esc(rotulo(ed))}", "", f"<b>{esc(ed.get('titulo', ''))}</b>"]
    if ed.get("destaque"):
        t.append(esc(ed["destaque"]))
    if ed.get("resumo"):
        t += ["", "<b>Em resumo</b>"] + [f"{n}. {esc(r)}" for n, r in enumerate(ed["resumo"], 1)]
    if lead:
        t += ["", f"<b>{esc(TEMAS.get(lead.get('tema'), lead.get('tema', '')))} · sinal {SINAL.get(lead.get('sinal'), 'baixo')}</b>",
              f'<a href="{esc(lead.get("url"))}">{esc(lead.get("titulo"))}</a>']
        if lead.get("porque"):
            t.append(f"<b>Por que importa:</b> {esc(lead['porque'])}")
    if resto:
        t += ["", "<b>Também nesta edição</b>"]
        for i in resto:
            t.append(f'• <a href="{esc(i.get("url"))}">{esc(i.get("titulo"))}</a> ({esc(fonte_data(i))})')
    if ed.get("perguntas"):
        t += ["", "<b>Para levar para o time</b>"] + [f"{n}. {esc(p)}" for n, p in enumerate(ed["perguntas"], 1)]
    t += ["", f'<a href="{esc(url_edicao(ed))}">Ler a edição no site</a> · {esc(CREDITO)}']
    texto = "\n".join(t)
    if len(texto) > 4000:  # corta os itens secundários antes de estourar o limite do Telegram
        corte = texto.rfind("\n\n<b>Também nesta edição</b>")
        texto = texto[:corte] + f'\n\n<a href="{esc(url_edicao(ed))}">Ler a edição completa no site</a> · {esc(CREDITO)}'
    return texto


def telegram_sem_novidade(st):
    return "\n".join([f"<b>Radar Next Gen</b> · {esc(data_longa(st.get('data', '')))}", "",
                      "Sem novidade relevante hoje.", f'<a href="{esc(SITE_URL)}">Ver o radar</a>'])


# ---------- Email e PDF (HTML com estilo inline, tabelas simples) ----------

CSS_BASE = """
  body { margin: 0; padding: 0; background: #FAFAF8; color: #1B1B1A; -webkit-text-size-adjust: 100%; }
  .wrap { max-width: 640px; margin: 0 auto; padding: 24px 20px 40px; font-family: 'IBM Plex Sans', -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; font-size: 16px; line-height: 1.55; }
  .serif { font-family: 'Newsreader', 'Iowan Old Style', Georgia, 'Times New Roman', serif; }
  a { color: #1B1B1A; }
  .mast { padding-bottom: 12px; border-bottom: 2px solid #1B1B1A; }
  .mast a { font-size: 24px; font-weight: 600; text-decoration: none; }
  .dateline { font-size: 13px; color: #62635F; padding: 10px 0 24px; border-bottom: 1px solid #E3E3DE; }
  .dateline b { color: #0B6B4F; font-weight: 500; }
  h1 { font-size: 34px; line-height: 1.12; font-weight: 500; margin: 28px 0 14px; letter-spacing: -.005em; }
  .dek { font-size: 19px; line-height: 1.4; color: #62635F; margin: 0 0 28px; }
  .sec { font-size: 15px; font-weight: 600; margin: 32px 0 10px; padding-bottom: 8px; border-bottom: 1px solid #E3E3DE; }
  ol.glance { margin: 0; padding-left: 22px; }
  ol.glance li { margin: 0 0 8px; }
  .kicker { font-size: 12.5px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: #0B6B4F; margin: 32px 0 8px; }
  h2 { font-size: 26px; line-height: 1.2; font-weight: 500; margin: 0 0 12px; }
  h2 a, h3 a { text-decoration: none; }
  .why { margin: 0 0 8px; }
  .src { font-size: 13px; color: #62635F; margin: 0; }
  .src a { color: #62635F; }
  .item { padding: 18px 0; border-bottom: 1px solid #E3E3DE; }
  .item:last-child { border-bottom: 0; }
  h3 { font-size: 21px; line-height: 1.3; font-weight: 500; margin: 0 0 8px; }
  h3.baixo { font-size: 19px; font-weight: 400; }
  .item .why { font-size: 15.5px; }
  .asks { background: #F1F1EC; padding: 18px 20px; margin: 32px 0 0; }
  .asks .sec { margin-top: 0; border: 0; padding: 0 0 8px; }
  .asks ol { margin: 0; padding-left: 20px; font-size: 18px; line-height: 1.4; }
  .asks li { margin-bottom: 8px; }
  .cta { margin: 32px 0 0; }
  .cta a { display: inline-block; background: #1B1B1A; color: #FAFAF8; text-decoration: none; padding: 10px 16px; font-size: 14px; font-weight: 500; border-radius: 2px; }
  .foot { margin-top: 36px; padding-top: 16px; border-top: 2px solid #1B1B1A; font-size: 13.5px; color: #62635F; }
  .foot b { color: #1B1B1A; font-weight: 500; }
"""
CSS_PRINT = """
  @page { size: A4; margin: 18mm 16mm; }
  body { background: #FFFFFF; }
  .wrap { max-width: none; padding: 0; }
  .cta { display: none; }
  .asks { page-break-inside: avoid; }
  .sec, .kicker, h1, h2, h3 { page-break-after: avoid; }
  a { text-decoration: none; }
"""


def html_edicao(ed, para_pdf=False):
    itens = ordenar(ed)
    lead, resto = (itens[0], itens[1:]) if itens else (None, [])
    link = url_edicao(ed)
    p = []
    p.append(f"<!doctype html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
             f"<title>{esc(ed.get('titulo', 'Radar Next Gen'))}</title>"
             "<link rel=\"stylesheet\" href=\"https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&family=IBM+Plex+Sans:wght@400;500;600&display=swap\">"
             f"<style>{CSS_BASE}{CSS_PRINT if para_pdf else ''}</style></head><body><div class=\"wrap\">")
    p.append(f'<div class="mast serif"><a href="{esc(SITE_URL)}">Radar Next Gen</a></div>')
    p.append(f"<div class=\"dateline\">{esc(rotulo(ed))}{'' if ed.get('id') == 'edicao-zero' else ''} &nbsp;&nbsp; "
             f"{len(itens)} {'item' if len(itens) == 1 else 'itens'}, leitura de {minutos(ed)} min</div>")
    p.append(f'<h1 class="serif">{esc(ed.get("titulo", ""))}</h1>')
    if ed.get("destaque"):
        p.append(f'<p class="dek serif">{esc(ed["destaque"])}</p>')
    if ed.get("resumo"):
        p.append('<div class="sec">Em resumo</div><ol class="glance">' + "".join(f"<li>{esc(r)}</li>" for r in ed["resumo"]) + "</ol>")
    if lead:
        p.append(f'<div class="kicker">{esc(TEMAS.get(lead.get("tema"), lead.get("tema", "")))} · sinal {SINAL.get(lead.get("sinal"), "baixo")}</div>')
        p.append(f'<h2 class="serif"><a href="{esc(lead.get("url"))}">{esc(lead.get("titulo"))}</a></h2>')
        if lead.get("porque"):
            p.append(f'<p class="why"><b>Por que importa:</b> {esc(lead["porque"])}</p>')
        p.append(f'<p class="src">{esc(fonte_data(lead))}. <a href="{esc(lead.get("url"))}">Ler na fonte</a></p>')
    if resto:
        p.append('<div class="sec">Também nesta edição</div>')
        for i in resto:
            sinal = i.get("sinal") if i.get("sinal") in RANK else "baixo"
            p.append(f'<div class="item"><h3 class="serif {sinal}"><a href="{esc(i.get("url"))}">{esc(i.get("titulo"))}</a></h3>')
            if i.get("porque"):
                p.append(f'<p class="why"><b>Por que importa:</b> {esc(i["porque"])}</p>')
            p.append(f'<p class="src">{esc(fonte_data(i))} · {esc(TEMAS.get(i.get("tema"), i.get("tema", "")))}</p></div>')
    if ed.get("perguntas"):
        p.append('<div class="asks"><div class="sec">Para levar para o time</div><ol class="serif">' + "".join(f"<li>{esc(q)}</li>" for q in ed["perguntas"]) + "</ol></div>")
    p.append(f'<p class="cta"><a href="{esc(link)}">Ler no site</a></p>')
    p.append(f'<div class="foot"><b>{esc(CREDITO)}</b><br>Fontes públicas. Números como divulgados pelas empresas.'
             f'<br><a href="{esc(TELEGRAM_URL)}">Canal no Telegram</a> · <a href="{esc(SITE_URL)}">{esc(SITE_URL)}</a></div>')
    p.append("</div></body></html>")
    return "".join(p)


def texto_plano(ed):
    itens = ordenar(ed)
    lead, resto = (itens[0], itens[1:]) if itens else (None, [])
    t = [f"RADAR NEXT GEN · {rotulo(ed)}", "", ed.get("titulo", ""), ed.get("destaque", "")]
    if ed.get("resumo"):
        t += ["", "EM RESUMO"] + [f"{n}. {r}" for n, r in enumerate(ed["resumo"], 1)]
    if lead:
        t += ["", f"{TEMAS.get(lead.get('tema'), '')} · sinal {SINAL.get(lead.get('sinal'), 'baixo')}", lead.get("titulo", ""),
              f"Por que importa: {lead.get('porque', '')}", lead.get("url", "")]
    if resto:
        t += ["", "TAMBÉM NESTA EDIÇÃO"]
        for i in resto:
            t += [f"- {i.get('titulo', '')} ({fonte_data(i)})", f"  {i.get('url', '')}"]
    if ed.get("perguntas"):
        t += ["", "PARA LEVAR PARA O TIME"] + [f"{n}. {q}" for n, q in enumerate(ed["perguntas"], 1)]
    t += ["", f"Ler no site: {url_edicao(ed)}", "", f"{CREDITO}. Fontes públicas, números como divulgados pelas empresas."]
    return "\n".join(t) + "\n"


def assunto(ed):
    return f"Radar Next Gen · {ed.get('titulo', rotulo(ed))}"


def gerar_pdf(ed, destino):
    """Imprime a edição em PDF com o Chrome headless. Devolve o caminho ou None se não houver Chrome."""
    chrome = next((c for c in [os.environ.get("CHROME_BIN"), "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                               "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"] if c and shutil.which(c)), None)
    if not chrome:
        print("PDF: Chrome não encontrado, pulando")
        return None
    destino = Path(destino)
    with tempfile.TemporaryDirectory() as tmp:
        pagina = Path(tmp) / "edicao.html"
        pagina.write_text(html_edicao(ed, para_pdf=True), encoding="utf-8")
        cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", f"--user-data-dir={tmp}/perfil",
               "--virtual-time-budget=6000", "--no-pdf-header-footer", f"--print-to-pdf={destino}", pagina.as_uri()]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            print(f"PDF: falhou ({type(e).__name__})")
            return None
    return destino if destino.exists() else None


def nome_pdf(ed):
    return f"radar-next-gen-{ed.get('id', ed.get('data', 'edicao'))}.pdf"


if __name__ == "__main__":
    saida = Path(sys.argv[sys.argv.index("--saida") + 1]) if "--saida" in sys.argv else Path(tempfile.mkdtemp(prefix="radar-"))
    saida.mkdir(parents=True, exist_ok=True)
    st = json.loads(STATUS.read_text(encoding="utf-8")) if STATUS.exists() else None
    ed = edicao_do_dia(st)
    (saida / "telegram.txt").write_text(telegram(ed), encoding="utf-8")
    (saida / "email.html").write_text(html_edicao(ed), encoding="utf-8")
    (saida / "email.txt").write_text(texto_plano(ed), encoding="utf-8")
    pdf = gerar_pdf(ed, saida / nome_pdf(ed))
    print(f"Prévia em {saida}" + (f" (PDF: {pdf.name})" if pdf else ""))
