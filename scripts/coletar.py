"""Coleta bruta para a curadoria diária do Radar Next Gen.

Roda no GitHub Actions (que tem internet livre) antes da rotina das 8h e grava
coleta/AAAA-MM-DD.json com o que saiu nos últimos dias em arXiv, Hugging Face,
GitHub, X (via fxtwitter) e Reddit. A rotina na nuvem só lê esse arquivo.
Usa apenas a biblioteca padrão.
"""
import datetime as dt
import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIAS = 3
UA = "radar-next-gen/1.0 (+https://tadashilima.github.io/radar-next-gen/)"

ARXIV = [
    'all:"tabular foundation model"',
    'all:"transaction" AND all:"foundation model"',
    'all:"event sequence" AND (all:bank OR all:financial)',
    'all:"credit scoring" AND (all:transformer OR all:LLM)',
    'all:fraud AND (all:"foundation model" OR all:LLM OR all:agent)',
    'all:"prior-data fitted"',
    'all:"money mule" OR all:"authorized push payment"',
]
HF_TERMOS = ["tabular", "transaction", "fraud", "credit", "event sequence", "financial", "banking", "payment"]
REPOS = ["PriorLabs/TabPFN", "soda-inria/tabicl", "limix-ldm-ai/LimiX", "autogluon/tabarena",
         "autogluon/autogluon", "pytorch-lifestream/pytorch-lifestream"]
X_PERFIS = ["FrankRHutter", "Prior_Labs", "noahholl", "LennartPurucker", "innixma", "dholzmueller",
            "GaelVaroquaux", "autogluon", "ChristophMolnar", "RohanRamanath", "nubank", "emilygsands",
            "sytaylor", "LinasBeliunas", "rasbt", "NeoSpaceAI"]
REDDIT = [("MachineLearning", 'TabPFN OR TabICL OR "tabular foundation model"'),
          ("MachineLearning", "transaction transformer fraud"),
          ("MachineLearning", '"foundation model" credit'),
          ("datascience", 'TabPFN OR "tabular foundation model"'),
          ("fintech", "foundation model fraud")]

agora = dt.datetime.now(dt.timezone.utc)
corte = agora - dt.timedelta(days=DIAS)
falhas = []


def get(url, headers=None, tentativas=2):
    h = {"User-Agent": UA, **(headers or {})}
    for i in range(tentativas):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
                return r.read()
        except Exception:  # noqa: BLE001
            if i + 1 == tentativas:
                raise
            time.sleep(4)


def recente(iso):
    try:
        d = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d >= corte
    except Exception:  # noqa: BLE001
        return True


def arxiv():
    ns = {"a": "http://www.w3.org/2005/Atom"}
    vistos, out = set(), []
    for q in ARXIV:
        url = ("http://export.arxiv.org/api/query?" + urllib.parse.urlencode(
            {"search_query": q, "sortBy": "submittedDate", "sortOrder": "descending", "max_results": 15}))
        try:
            raiz = ET.fromstring(get(url))
        except Exception as e:  # noqa: BLE001
            falhas.append(f"arXiv ({q}): {type(e).__name__}")
            continue
        for en in raiz.findall("a:entry", ns):
            link = en.findtext("a:id", "", ns).strip()
            pub = en.findtext("a:published", "", ns)
            if link in vistos or not recente(pub):
                continue
            vistos.add(link)
            out.append({"titulo": " ".join(en.findtext("a:title", "", ns).split()), "url": link,
                        "data": pub[:10], "query": q,
                        "resumo": " ".join(en.findtext("a:summary", "", ns).split())[:700]})
        time.sleep(3)  # arXiv pede intervalo entre chamadas
    return out


def huggingface():
    out = {"papers": [], "modelos_prior_labs": []}
    try:
        for p in json.loads(get("https://huggingface.co/api/daily_papers?limit=100")):
            pp = p.get("paper", {})
            texto = (pp.get("title", "") + " " + pp.get("summary", "")).lower()
            if any(t in texto for t in HF_TERMOS):
                out["papers"].append({"titulo": pp.get("title"), "url": f"https://huggingface.co/papers/{pp.get('id')}",
                                      "data": (p.get("publishedAt") or "")[:10],
                                      "resumo": (pp.get("summary") or "")[:700]})
    except Exception as e:  # noqa: BLE001
        falhas.append(f"Hugging Face papers: {type(e).__name__}")
    try:
        for m in json.loads(get("https://huggingface.co/api/models?author=Prior-Labs&sort=lastModified&limit=10")):
            if recente(m.get("lastModified", "")):
                out["modelos_prior_labs"].append({"modelo": m.get("id"), "url": f"https://huggingface.co/{m.get('id')}",
                                                  "atualizado": (m.get("lastModified") or "")[:10]})
    except Exception as e:  # noqa: BLE001
        falhas.append(f"Hugging Face modelos: {type(e).__name__}")
    return out


def github():
    h = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        h["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    out = []
    for repo in REPOS:
        try:
            for r in json.loads(get(f"https://api.github.com/repos/{repo}/releases?per_page=3", h)):
                if recente(r.get("published_at") or ""):
                    out.append({"repo": repo, "release": r.get("name") or r.get("tag_name"), "url": r.get("html_url"),
                                "data": (r.get("published_at") or "")[:10], "notas": (r.get("body") or "")[:1200]})
        except Exception as e:  # noqa: BLE001
            falhas.append(f"GitHub {repo}: {type(e).__name__}")
    return out


def x():
    out, pendentes = [], []

    def um(user):
        d = json.loads(get(f"https://api.fxtwitter.com/2/profile/{user}/statuses?count=10", tentativas=1))
        for s in d.get("results") or d.get("statuses") or []:
            criado = s.get("created_timestamp")
            if criado and dt.datetime.fromtimestamp(criado, dt.timezone.utc) < corte:
                continue
            out.append({"perfil": user, "url": s.get("url"), "texto": (s.get("text") or "")[:600],
                        "data": dt.datetime.fromtimestamp(criado, dt.timezone.utc).date().isoformat() if criado else ""})

    for user in X_PERFIS:
        try:
            um(user)
        except Exception:  # noqa: BLE001
            pendentes.append(user)
        time.sleep(5)  # fxtwitter devolve 404 falso quando as chamadas são rápidas
    for user in pendentes:
        time.sleep(8)
        try:
            um(user)
        except Exception as e:  # noqa: BLE001
            falhas.append(f"X @{user}: {type(e).__name__}")
    return out


def reddit():
    out = []
    for sub, q in REDDIT:
        url = f"https://www.reddit.com/r/{sub}/search.json?" + urllib.parse.urlencode(
            {"q": q, "restrict_sr": 1, "sort": "new", "t": "week", "limit": 15})
        try:
            d = json.loads(get(url, tentativas=1))
            for c in d.get("data", {}).get("children", []):
                p = c.get("data", {})
                quando = dt.datetime.fromtimestamp(p.get("created_utc", 0), dt.timezone.utc)
                if quando >= corte:
                    out.append({"sub": sub, "titulo": p.get("title"), "url": "https://www.reddit.com" + p.get("permalink", ""),
                                "data": quando.date().isoformat(), "texto": (p.get("selftext") or "")[:500],
                                "score": p.get("score")})
        except Exception as e:  # noqa: BLE001
            falhas.append(f"Reddit r/{sub}: {type(e).__name__}")
        time.sleep(3)
    return out


if __name__ == "__main__":
    hoje = dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).date().isoformat()
    dados = {"gerado_em": agora.isoformat(timespec="seconds"), "janela_dias": DIAS,
             "arxiv": arxiv(), "huggingface": huggingface(), "github": github(), "x": x(), "reddit": reddit()}
    dados["falhas"] = falhas
    pasta = RAIZ / "coleta"
    pasta.mkdir(exist_ok=True)
    (pasta / f"{hoje}.json").write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    for velho in sorted(pasta.glob("*.json"))[:-14]:  # guarda só as últimas 2 semanas
        velho.unlink()
    print(f"coleta/{hoje}.json: arXiv {len(dados['arxiv'])}, HF {len(dados['huggingface']['papers'])}, "
          f"GitHub {len(dados['github'])}, X {len(dados['x'])}, Reddit {len(dados['reddit'])}, falhas {len(falhas)}")
    for f in falhas:
        print("  falha:", f)
