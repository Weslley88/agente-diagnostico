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

## Exemplo de diagnóstico

Saída real do agente investigando o alerta padrão. Ele fez 9 consultas e chegou ao diagnóstico sozinho:

```text
🚨 Alerta: alto volume de respostas 409 (Order already exists) na Lambda mind-api-orders-create nas últimas 24 horas. Investigue.

🔧 Passo 1: resumo_por_hora({})
🔧 Passo 1: intervalos_entre_tentativas({})
🔧 Passo 1: amostrar_erros({"status": 409, "limite": 3})
🔧 Passo 1: amostrar_erros({"status": 500, "limite": 3})
🔧 Passo 2: buscar_pedido({"order_id": "PED-36687537"})
🔧 Passo 2: buscar_pedido({"order_id": "PED-95132217"})
🔧 Passo 2: buscar_pedido({"order_id": "PED-95942441"})
🔧 Passo 3: buscar_requisicao({"request_id": "b7f53621-eb3e-4e72-ba79-bfa2a3cf4c7b"})
🔧 Passo 3: buscar_requisicao({"request_id": "4b81a155-52ae-47c4-8935-2c29d881b6c7"})
```

**Resumo do diagnóstico:**

- **Causa (confiança alta):** os 409 são retries do cliente sobre uma criação lenta. Em 87,5% dos casos, a repetição chegou entre 9,5 e 11,5 s depois de uma 1ª tentativa que demorou mais de 10 s, o que indica timeout de ~10 s em quem chama.
- **Impacto:** cerca de 17% das execuções (1.447 de 8.357) terminaram em 409, de forma constante nas 24 h; p95 entre 11 e 16 s.
- **Validação da métrica:** o agente percebeu que cada 409 gera 4 linhas de log e que contar linhas superestima o problema em 4 vezes.
- **Segunda causa:** 12,5% dos duplicados chegaram em menos de 2 s, indicando duplo envio na origem.
- **Outro achado:** rajada de 16 erros 500 (`MongoTimeoutError`) às 03:00 UTC, tratada como problema separado, com a pergunta se esses pedidos foram perdidos.
- **Ações sugeridas:** tratar a repetição como sucesso idempotente, ajustar o alerta para contar requisições únicas, investigar a lentidão da criação e usar chave de idempotência com índice único.

## Roteiro

- [x] **Fase 1:** agente local com logs fictícios
- [ ] **Fase 2:** robô fictício na AWS (Step Functions + Lambda) e ferramentas consultando o CloudWatch Logs Insights
- [ ] **Fase 3:** EventBridge dispara o agente na falha e o diagnóstico chega por e-mail (SNS)

## Autor

Weslley · Analista de automação com foco em AIOps, AWS e RPA
