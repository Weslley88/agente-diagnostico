# Agente de diagnóstico de falhas (AIOps)

Agente de IA que investiga alertas de uma API serverless como um SRE de plantão faria:
consulta os logs, valida as métricas, segue a evidência e entrega um diagnóstico
com causa provável, evidências e ação sugerida.

> Todos os dados deste projeto são **fictícios**, gerados por `gerar_logs.py`.

## O problema

Em uma API de criação de pedidos, cerca de 1 em cada 5 chamadas recebia `409 Order already exists`.
Investigar isso manualmente exige várias consultas e tem armadilhas, por exemplo:
cada requisição com 409 escreve a mesma frase em várias linhas de log, e contar
linhas em vez de requisições leva a uma conclusão errada.

O agente automatiza essa investigação e reduz o **MTTD** (tempo para detectar)
e o **MTTR** (tempo para recuperar).

## Como funciona

```
Alerta ──▶ Modelo de IA ──▶ pede uma ferramenta ──▶ Python executa ──▶ resultado volta
               ▲                                                          │
               └──────────────── decide o próximo passo ◀────────────────┘
                                         │
                                         ▼
                                  Diagnóstico final
```

| Ferramenta | Equivale a (CloudWatch Logs Insights) |
| --- | --- |
| `resumo_por_hora` | `stats` por `bin(1h)` com execuções, 409, 500 e p95 |
| `amostrar_erros` | `filter status = 409` com `limit` |
| `buscar_requisicao` | `filter @requestId = ...` |
| `buscar_pedido` | `filter orderId = ...` ordenado por tempo |
| `intervalos_entre_tentativas` | intervalo entre a criação original e a repetição |

## Como rodar

```bash
# 1. Ambiente virtual e dependências
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt

# 2. Chave da API: copie .env.example para .env e coloque sua chave
copy .env.example .env          # Windows  (Linux/Mac: cp .env.example .env)

# 3. Gerar os logs fictícios
python gerar_logs.py

# 4. Rodar o agente
python agente.py
python agente.py "Alerta: aumento de erros 500 na API de pedidos"
```

## Roteiro

- [x] **Fase 1:** agente local com logs fictícios
- [ ] **Fase 2:** robô fictício na AWS (Step Functions + Lambda) e ferramentas consultando o CloudWatch Logs Insights
- [ ] **Fase 3:** EventBridge dispara o agente na falha e o diagnóstico chega por e-mail (SNS)

## Autor

Weslley · Analista de automação com foco em AIOps, AWS e RPA
