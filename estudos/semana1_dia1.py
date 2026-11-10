import json

# Lê as 5 primeiras linhas do arquivo de logs
linhas = []
with open("logs.jsonl", encoding="utf-8") as arquivo:
    for numero, texto in enumerate(arquivo):
        if numero == 5:
            break
        linhas.append(json.loads(texto))

primeira = linhas[0]

print("Tipo de variável linhas:", type(linhas))
print("Quantas linhas li:", len(linhas))
print("Tipo da primeira linha:", type(primeira))
print("Chaves da primeira linha:", list(primeira.keys()))
print("Mensagem:", primeira["mensagem"])
print("Pedido:", primeira["orderId"])

for linha in linhas:
    print(linha["timestamp"], "|", linha["mensagem"], "|", linha.get("status", "-"))
