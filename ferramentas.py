"""
Ferramentas que o agente pode usar para investigar os logs.

Cada função aqui faz o papel de uma consulta do CloudWatch Logs Insights.
Na fase 2, trocamos o arquivo local por consultas reais na sua conta AWS,
sem mudar o agente.

Cada ferramenta tem duas partes:
1. A função Python que faz o trabalho.
2. A "descrição" (em FERRAMENTAS) que diz ao modelo o que ela faz e quais
   parâmetros aceita. É assim que o modelo decide qual usar.
"""

import json
from collections import defaultdict
from datetime import datetime

ARQUIVO_LOGS = "logs.jsonl"
_cache = None


def _carregar():
    global _cache
    if _cache is None:
        with open(ARQUIVO_LOGS, encoding="utf-8") as f:
            _cache = [json.loads(l) for l in f]
    return _cache


def _percentil(valores, p):
    if not valores:
        return None
    v = sorted(valores)
    k = (len(v) - 1) * p / 100
    i = int(k)
    j = min(i + 1, len(v) - 1)
    return v[i] + (v[j] - v[i]) * (k - i)


# ---------------------------------------------------------------- ferramentas

def resumo_por_hora():
    """Por hora: execuções, requisições únicas com 409 e 500, % e p95 da duração."""
    por_hora = defaultdict(lambda: {"execucoes": 0, "duracoes": [],
                                    "req_409": set(), "req_500": set(),
                                    "linhas_already_exists": 0})
    for l in _carregar():
        h = por_hora[l["timestamp"][:13] + ":00Z"]
        if l["nivel"] == "REPORT":
            h["execucoes"] += 1
            h["duracoes"].append(l["duracao_ms"])
        if l.get("status") == 409:
            h["req_409"].add(l["requestId"])
        if l.get("status") == 500:
            h["req_500"].add(l["requestId"])
        if "already exists" in l["mensagem"]:
            h["linhas_already_exists"] += 1

    resultado = []
    for hora in sorted(por_hora):
        h = por_hora[hora]
        ex = h["execucoes"] or 1
        resultado.append({
            "hora_utc": hora,
            "execucoes": h["execucoes"],
            "req_409": len(h["req_409"]),
            "pct_409": round(len(h["req_409"]) * 100 / ex, 1),
            "req_500": len(h["req_500"]),
            "pct_500": round(len(h["req_500"]) * 100 / ex, 1),
            "p95_ms": round(_percentil(h["duracoes"], 95) or 0),
            "linhas_com_already_exists": h["linhas_already_exists"],
        })
    return resultado


def amostrar_erros(status, limite=5):
    """Algumas requisições com o status pedido (409 ou 500), com todas as suas linhas."""
    ids = []
    for l in _carregar():
        if l.get("status") == status and l["requestId"] not in ids:
            ids.append(l["requestId"])
        if len(ids) >= limite:
            break
    return {rid: buscar_requisicao(rid) for rid in ids}


def buscar_requisicao(request_id):
    """Todas as linhas de log de uma requisição (equivale a filtrar por @requestId)."""
    return [l for l in _carregar() if l["requestId"] == request_id]


def buscar_pedido(order_id):
    """Todas as tentativas de criar um pedido, em ordem, com o intervalo entre elas."""
    tentativas = {}
    for l in _carregar():
        if l.get("orderId") != order_id:
            continue
        t = tentativas.setdefault(l["requestId"], {"requestId": l["requestId"],
                                                  "inicio": l["timestamp"],
                                                  "status": None})
        if l.get("status"):
            t["status"] = l["status"]
    for t in tentativas.values():
        dur = [x["duracao_ms"] for x in buscar_requisicao(t["requestId"]) if x["nivel"] == "REPORT"]
        t["duracao_ms"] = dur[0] if dur else None
    return sorted(tentativas.values(), key=lambda t: t["inicio"])


def intervalos_entre_tentativas(limite=200):
    """
    Para pedidos que receberam 409: quanto tempo depois da 1ª tentativa veio a repetição,
    e quanto a 1ª tentativa demorou. É a prova para separar 'retry por timeout'
    de 'duplicidade na origem'.
    """
    pedidos_409 = []
    for l in _carregar():
        if l.get("status") == 409 and l.get("orderId") and l["orderId"] not in pedidos_409:
            pedidos_409.append(l["orderId"])
        if len(pedidos_409) >= limite:
            break

    faixas = defaultdict(int)
    for oid in pedidos_409:
        t = buscar_pedido(oid)
        if len(t) < 2:
            continue
        t0 = datetime.fromisoformat(t[0]["inicio"].replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(t[1]["inicio"].replace("Z", "+00:00"))
        intervalo = (t1 - t0).total_seconds()
        dur1 = (t[0]["duracao_ms"] or 0) / 1000
        if intervalo < 2:
            faixa = "repeticao em menos de 2 s"
        elif 9.5 <= intervalo <= 11.5:
            faixa = "repeticao entre 9,5 e 11,5 s"
        else:
            faixa = "repeticao em outro intervalo"
        faixas[faixa] += 1
        faixas[faixa + " | 1a tentativa demorou > 10 s"] += 1 if dur1 > 10 else 0

    return {"pedidos_analisados": len(pedidos_409), "distribuicao": dict(faixas)}


# ------------------------------------------------- descrição para o modelo

FERRAMENTAS = [
    {
        "name": "resumo_por_hora",
        "description": ("Resumo das últimas 24 h por hora (UTC): execuções, requisições únicas "
                        "com 409 e 500, porcentagens, p95 da duração em ms e quantas LINHAS de "
                        "log contêm 'already exists' (útil para validar a contagem)."),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "amostrar_erros",
        "description": "Retorna algumas requisições com o status pedido, com todas as linhas de log de cada uma.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "integer", "enum": [409, 500]},
                "limite": {"type": "integer", "default": 5},
            },
            "required": ["status"],
        },
    },
    {
        "name": "buscar_requisicao",
        "description": "Todas as linhas de log de um requestId.",
        "input_schema": {
            "type": "object",
            "properties": {"request_id": {"type": "string"}},
            "required": ["request_id"],
        },
    },
    {
        "name": "buscar_pedido",
        "description": "Todas as tentativas de criação de um orderId, em ordem, com status e duração.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    },
    {
        "name": "intervalos_entre_tentativas",
        "description": ("Para pedidos que receberam 409, distribui o intervalo entre a 1ª tentativa "
                        "e a repetição, e conta quantas 1ªs tentativas demoraram mais de 10 s."),
        "input_schema": {
            "type": "object",
            "properties": {"limite": {"type": "integer", "default": 200}},
        },
    },
]

FUNCOES = {
    "resumo_por_hora": resumo_por_hora,
    "amostrar_erros": amostrar_erros,
    "buscar_requisicao": buscar_requisicao,
    "buscar_pedido": buscar_pedido,
    "intervalos_entre_tentativas": intervalos_entre_tentativas,
}
