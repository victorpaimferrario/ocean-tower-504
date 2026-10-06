#!/usr/bin/env python3
"""Baixa IPCA e CDI do Banco Central (SGS) e grava indices.json.

E a fonte do indicador "Meu dinheiro, mes a mes" do painel: sem ele, o calculo
trata o mes faltante como se nao tivesse rendido nada.

Chamado por DOIS workflows de proposito — ver o comentario em
.github/workflows/keepalive-supabase.yml sobre o atraso dos crons.

Saida: 0 gravou ou nada mudou · 1 falhou (e nesse caso NAO escreve nada).
"""
import json, urllib.request, datetime, time, os, sys

SERIES = {"ipca": 433, "cdi": 4391}   # 433 = IPCA % a.m. · 4391 = CDI acumulado no mes
DESTINO = "indices.json"


def sgs(cod, tentativas=4):
    """A API do BCB cai com frequencia. Sem retry, uma falha de rede custava o
    mes inteiro: em 01/10/2026 o robo falhou e o painel ficou cinco dias
    exibindo setembro com o parcial de 0,72%."""
    url = ("https://api.bcb.gov.br/dados/serie/bcdata.sgs.%d/dados"
           "?formato=json&dataInicial=01/06/2026" % cod)
    erro = None
    for t in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ocean504-bot"})
            with urllib.request.urlopen(req, timeout=45) as r:
                dados = json.load(r)
            out = {}
            for it in dados:
                dd, mm, yy = it["data"].split("/")
                out["%s-%s" % (yy, mm)] = float(str(it["valor"]).replace(",", "."))
            if not out:
                raise ValueError("serie %d voltou vazia" % cod)
            return out
        except Exception as e:
            erro = e
            espera = 5 * (2 ** t)                      # 5s, 10s, 20s, 40s
            print("serie %d, tentativa %d/%d falhou (%s)" % (cod, t + 1, tentativas, e),
                  flush=True)
            if t < tentativas - 1:
                time.sleep(espera)
    raise RuntimeError("serie %d falhou em %d tentativas: %s" % (cod, tentativas, erro))


def main():
    antigo = {}
    if os.path.exists(DESTINO):
        try:
            antigo = json.load(open(DESTINO, encoding="utf-8"))
        except Exception as e:
            print("indices.json atual ilegivel (%s) — sera reescrito" % e)

    novo = {}
    for nome, cod in SERIES.items():
        novo[nome] = sgs(cod)

    # NUNCA substituir o arquivo bom por um pior: se o BCB devolver menos meses
    # do que ja temos, o problema e do lado deles.
    for nome, serie in novo.items():
        velho = (antigo.get(nome) or {})
        if len(serie) < len(velho):
            print("::error::%s voltou com %d meses, menos que os %d ja gravados "
                  "— abortando sem escrever" % (nome, len(serie), len(velho)))
            return 1

    res = {
        "atualizado_em": datetime.datetime.now(datetime.timezone.utc)
                                 .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fonte": "Banco Central (SGS): IPCA=433, CDI acumulado no mes=4391 (% a.m.)",
    }
    res.update(novo)

    igual = all((antigo.get(k) or {}) == v for k, v in novo.items())
    with open(DESTINO, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)

    for nome, serie in novo.items():
        ult = sorted(serie)[-1]
        print("%s: %d meses, ultimo %s = %s" % (nome, len(serie), ult, serie[ult]))
    print("series inalteradas" if igual else "SERIES ATUALIZADAS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
