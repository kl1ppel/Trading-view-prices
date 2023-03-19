import json
import random
import re
import requests
from websocket import create_connection

tradingViewSocket = 'wss://data.tradingview.com/socket.io/websocket'

def pesquisar(query, categoria):
    res = requests.get(f'https://symbol-search.tradingview.com/symbol_search/?text={query}&type={categoria}')
    if res.status_code == 200:
        res = res.json()
        if len(res) == 0:
            print('Nenhuma moeda encontrada.')
            return False    
        else:
            return res[0]
    else:
        print('Erro de rede.')

def gerar_sessao():
    tamanho_string = 12
    letras = string.ascii_lowercase
    string_aleatoria =  ''.join(random.choice(letras) for i in range(tamanho_string))
    return "qs_" + string_aleatoria

def adicionar_cabecalho(st):
    return "~m~" + str(len(st)) + "~m~" + st

def construir_mensagem(func, lista_parametros):
    return json.dumps({
        "m": func,
        "p": lista_parametros
        }, separators=(',', ':'))

def criar_mensagem(func, lista_parametros):
    return adicionar_cabecalho(construir_mensagem(func, lista_parametros))

def enviar_mensagem(ws, func, args):
    ws.send(criar_mensagem(func, args))

headers = json.dumps({
    'Origin': 'https://data.tradingview.com'
})

def main():
    moeda = input('Moeda: ') 
    categoria = input('Categoria: ') # Categorias: 'stock', 'futures', 'forex', 'cfd', 'crypto', 'index', 'economic'
    dados = pesquisar(moeda, categoria)

    if not dados:
        exit()
        
    nome_simbolo = dados['symbol']
    corretora = dados['exchange']
    id_simbolo = f'{corretora.upper()}:{nome_simbolo.upper()}'
        
    print(id_simbolo, end='\n\n')
    
    # criar túnel
    ws = create_connection(tradingViewSocket, headers=headers)
    sessao = gerar_sessao()

    enviar_mensagem(ws, "quote_create_session", [sessao])
    enviar_mensagem(ws, "quote_set_fields", [sessao, 'lp'])
    enviar_mensagem(ws, "quote_add_symbols", [sessao, id_simbolo])

    while True:
        try:
            resultado = ws.recv()
            if 'quote_completed' in resultado or 'session_id' in resultado:
                continue
            res = re.findall("^.*?({.*)$", resultado)
            if len(res) != 0:
                json_res = json.loads(res[0])
                if json_res['m'] == 'qsd':
                    simbolo = json_res['p'][1]['n']
                    preco = json_res['p'][1]['v']['lp']
                    print(f'{simbolo} -> {preco}')
            else:
                # pacote de ping
                ping_str = re.findall(".......(.*)", resultado)
                if len(ping_str) != 0:
                    ping_str = ping_str[0]
                    ws.send("~m~" + str(len(ping_str)) + "~m~" + ping_str)
        except Exception as e:
            continue

if __name__ == '__main__':
    main()

