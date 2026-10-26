"""
Agente de diagnóstico de falhas (fase 1: local, com logs fictícios).

Como um agente funciona, em 4 passos que se repetem:
1. Mandamos para o modelo: o alerta + a lista de ferramentas disponíveis.
2. O modelo responde pedindo para usar uma ferramenta (ex.: resumo_por_hora).
3. NÓS executamos a ferramenta em Python e devolvemos o resultado.
4. O modelo lê o resultado e decide: usa outra ferramenta ou escreve o diagnóstico.

O modelo nunca acessa os logs diretamente. Ele só vê o que as ferramentas devolvem.

Uso:
    python agente.py
    python agente.py "Alerta: aumento de erros 500 na API de pedidos"
"""

import json
import sys

from anthropic import Anthropic
from dotenv import load_dotenv

from ferramentas import FERRAMENTAS, FUNCOES

load_dotenv()  # lê a ANTHROPIC_API_KEY do arquivo .env

MODELO = "claude-sonnet-5-5"
MAX_PASSOS = 12           # limite de segurança para o agente não rodar para sempre
MAX_CARACTERES_RESULTADO = 15_000

PROMPT_SISTEMA = """Você é um agente de diagnóstico SRE de plantão.
Você investiga alertas da Lambda de criação de pedidos usando as ferramentas disponíveis.

Regras de investigação:
- Comece pelo panorama (resumo por hora) antes de olhar casos individuais.
- VALIDE as métricas antes de concluir: confira se contagem de linhas de log
  é diferente de contagem de requisições únicas.
- Siga a evidência. Toda conclusão precisa citar números que você obteve das ferramentas.
- Diferencie lentidão, erros 4xx e erros 5xx; eles têm causas e ações diferentes.
- Horários dos logs estão em UTC; no relatório, informe também o horário de Brasília (UTC-3).
- Se a evidência não for suficiente, diga isso e indique o que falta investigar.

Ao terminar, responda em português, neste formato:

## Resumo
(2 frases)

## Impacto
(quantos, quanto, desde quando)

## Causa provável
(com o grau de confiança: alta, média ou baixa)

## Evidências
(lista com os números que sustentam a causa)

## Ação sugerida
(imediata e definitiva)

## Outros achados
(o que apareceu mas não é a causa principal)
"""

ALERTA_PADRAO = ("Alerta: alto volume de respostas 409 (Order already exists) "
                 "na Lambda mind-api-orders-create nas últimas 24 horas. Investigue.")


def executar_ferramenta(nome, argumentos):
    """Executa a função Python correspondente e devolve o resultado em texto."""
    try:
        resultado = FUNCOES[nome](**argumentos)
        texto = json.dumps(resultado, ensure_ascii=False)
    except Exception as erro:
        texto = f"Erro ao executar {nome}: {erro}"
    if len(texto) > MAX_CARACTERES_RESULTADO:
        texto = texto[:MAX_CARACTERES_RESULTADO] + " ... [resultado cortado]"
    return texto


def rodar_agente(alerta):
    cliente = Anthropic()
    mensagens = [{"role": "user", "content": alerta}]

    print(f"\n🚨 {alerta}\n")

    for passo in range(1, MAX_PASSOS + 1):
        resposta = cliente.messages.create(
            model=MODELO,
            max_tokens=4000,
            system=PROMPT_SISTEMA,
            tools=FERRAMENTAS,
            messages=mensagens,
        )

        # Guarda a resposta do modelo no histórico da conversa
        mensagens.append({"role": "assistant", "content": resposta.content})

        # O modelo terminou: imprime o diagnóstico
        if resposta.stop_reason != "tool_use":
            texto_final = "".join(b.text for b in resposta.content if b.type == "text")
            print("=" * 70)
            print(texto_final)
            return texto_final

        # O modelo pediu ferramentas: executa cada uma e devolve os resultados
        resultados = []
        for bloco in resposta.content:
            if bloco.type == "text" and bloco.text.strip():
                print(f"💭 {bloco.text.strip()}\n")
            if bloco.type == "tool_use":
                print(f"🔧 Passo {passo}: {bloco.name}({json.dumps(bloco.input, ensure_ascii=False)})")
                resultados.append({
                    "type": "tool_result",
                    "tool_use_id": bloco.id,
                    "content": executar_ferramenta(bloco.name, bloco.input),
                })
        mensagens.append({"role": "user", "content": resultados})

    print("⚠️ O agente atingiu o limite de passos sem concluir.")
    return None


if __name__ == "__main__":
    alerta = " ".join(sys.argv[1:]) or ALERTA_PADRAO
    rodar_agente(alerta)
