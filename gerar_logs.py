"""
Gera 24 horas de logs FICTÍCIOS de uma API de criação de pedidos.

O cenário imita o que encontramos na análise real (sem nenhum dado real):
- A API é lenta: a duração segue uma curva com mediana ~6 s.
- Quem chama a API tem timeout de 10 s. Se a resposta demora mais que isso,
  o cliente tenta de novo ~10 s depois. Como o pedido já foi criado,
  a segunda tentativa recebe 409 "Order already exists".
- Uma pequena parte dos duplicados nasce na origem (clique duplo, < 1 s).
- Entre 03:00 e 03:40 há um incidente: o banco fica instável e parte das
  chamadas retorna 500.
- Cada requisição com 409 escreve a frase "already exists" em VÁRIAS linhas
  de log (a mesma armadilha de contagem que você encontrou na sexta).

Uso:  python gerar_logs.py
Saída: logs.jsonl (uma linha JSON por evento de log)
"""

import json
import math
import random
import uuid
from datetime import datetime, timedelta, timezone

random.seed(42)  # mesma semente = mesmos dados toda vez

INICIO = datetime(2026, 10, 25, 0, 0, tzinfo=timezone.utc)
TIMEOUT_CLIENTE_S = 10
INCIDENTE_INICIO = INICIO + timedelta(hours=3)
INCIDENTE_FIM = INICIO + timedelta(hours=3, minutes=40)

# Pedidos por hora (UTC): pouco de madrugada, pico no horário comercial do Brasil
TRAFEGO_POR_HORA = [
    220, 180, 120, 80, 60, 50, 50, 70, 120, 200, 300, 380,
    450, 520, 600, 560, 520, 480, 420, 380, 340, 300, 270, 240,
]


def novo_id():
    return str(uuid.uuid4())


def linha(ts, request_id, nivel, modulo, mensagem, **extra):
    return {
        "timestamp": ts.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "requestId": request_id,
        "nivel": nivel,
        "modulo": modulo,
        "mensagem": mensagem,
        **extra,
    }


def linha_report(ts, request_id, duracao_ms):
    """Equivalente à linha REPORT que a Lambda grava no fim de cada execução."""
    return linha(ts, request_id, "REPORT", "lambda",
                 f"REPORT RequestId: {request_id} Duration: {duracao_ms:.2f} ms",
                 duracao_ms=round(duracao_ms, 2))


def execucao_criacao(ts, order_id, em_incidente):
    """Uma chamada nova de criação de pedido. Retorna (linhas, duracao_s, status)."""
    rid = novo_id()
    linhas = [linha(ts, rid, "INFO", "handler", "Recebida requisição de criação",
                    orderId=order_id)]

    if em_incidente and random.random() < 0.35:
        duracao = random.uniform(2.0, 5.0)
        fim = ts + timedelta(seconds=duracao)
        linhas.append(linha(fim, rid, "ERROR", "repository/orders",
                            "MongoTimeoutError: tempo esgotado ao conectar no banco",
                            orderId=order_id, status=500))
        linhas.append(linha(fim, rid, "ERROR", "handler",
                            "Erro interno ao criar pedido", orderId=order_id, status=500))
        linhas.append(linha_report(fim, rid, duracao * 1000))
        return linhas, duracao, 500

    # Lognormal: mediana ~6 s, ~18% acima de 10 s
    duracao = random.lognormvariate(math.log(6.0), 0.56)
    fim = ts + timedelta(seconds=duracao)
    linhas.append(linha(fim, rid, "INFO", "handler", "Pedido criado com sucesso",
                        orderId=order_id, status=201))
    linhas.append(linha_report(fim, rid, duracao * 1000))
    return linhas, duracao, 201


def execucao_duplicada(ts, order_id):
    """Tentativa de criar um pedido que já existe: rápida e com várias linhas de log."""
    rid = novo_id()
    duracao = random.uniform(0.08, 0.15)
    fim = ts + timedelta(seconds=duracao)
    msg = "Order already exists in collection"
    linhas = [
        linha(ts, rid, "INFO", "handler", "Recebida requisição de criação", orderId=order_id),
        linha(fim, rid, "ERROR", "deduplicate/verifyOrderDuplicate", msg,
              orderId=order_id, status=409),
        linha(fim, rid, "INFO", "getMessageFromFile", f"Mensagem final: {msg}"),
        linha(fim, rid, "INFO", "AdapterError", f"Mensagem final: {msg}"),
        linha(fim, rid, "ERROR", "handler", f"Error: {msg}", orderId=order_id, status=409),
        linha_report(fim, rid, duracao * 1000),
    ]
    return linhas


def gerar():
    todas = []
    for hora, qtd in enumerate(TRAFEGO_POR_HORA):
        for _ in range(qtd):
            ts = INICIO + timedelta(hours=hora, seconds=random.uniform(0, 3600))
            order_id = f"PED-{random.randint(10_000_000, 99_999_999)}"
            em_incidente = INCIDENTE_INICIO <= ts < INCIDENTE_FIM

            linhas, duracao, status = execucao_criacao(ts, order_id, em_incidente)
            todas.extend(linhas)

            # Cliente desistiu (timeout) e tenta de novo; o pedido já existe -> 409
            if status == 201 and duracao > TIMEOUT_CLIENTE_S:
                retry_ts = ts + timedelta(seconds=TIMEOUT_CLIENTE_S + random.uniform(0.2, 0.8))
                todas.extend(execucao_duplicada(retry_ts, order_id))

            # Duplicidade na origem (clique duplo), em ~3% dos pedidos
            if status == 201 and random.random() < 0.03:
                dup_ts = ts + timedelta(seconds=random.uniform(0.1, 0.9))
                todas.extend(execucao_duplicada(dup_ts, order_id))

    todas.sort(key=lambda l: l["timestamp"])
    with open("logs.jsonl", "w", encoding="utf-8") as f:
        for l in todas:
            f.write(json.dumps(l, ensure_ascii=False) + "\n")
    print(f"Gerado logs.jsonl com {len(todas):,} linhas de log.")


if __name__ == "__main__":
    gerar()
