#!/usr/bin/env python3
"""
tradingview_client.py

Cliente para consumir ticks de preço em tempo real via WebSocket
do TradingView. Usa Lógica de sessão, assinatura de símbolos,
parsing de mensagens e auto-reconnect com backoff.
"""

import argparse
import json
import logging
import random
import string
import sys
import time
from typing import Any, Dict, Optional

import requests
from websocket import WebSocketApp, WebSocketConnectionClosedException

# --- Configuração de logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

# --- Constantes ---
SEARCH_URL = "https://symbol-search.tradingview.com/symbol_search/"
WS_URL = "wss://data.tradingview.com/socket.io/websocket"

PING_INTERVAL = 20  # segundos
BACKOFF_MAX = 300   # limite de backoff exponencial


class TradingViewClient:
    """Cliente WebSocket para streaming de dados do TradingView."""

    def __init__(self, symbol: str, category: str):
        """
        :param symbol: texto de pesquisa do símbolo (ex: 'BTCUSD').
        :param category: 'stock', 'forex', 'crypto', etc.
        """
        self.symbol = symbol
        self.category = category
        self.session_id = self._generate_session_id()
        self.ws: Optional[WebSocketApp] = None

    @staticmethod
    def _generate_session_id(length: int = 12) -> str:
        chars = string.ascii_lowercase
        return "qs_" + "".join(random.choice(chars) for _ in range(length))

    def _search_symbol(self) -> Dict[str, Any]:
        """Faz search na API REST para obter o símbolo completo."""
        params = {"text": self.symbol, "type": self.category}
        resp = requests.get(SEARCH_URL, params=params, timeout=5)
        resp.raise_for_status()
        results = resp.json()
        if not results:
            raise ValueError("Nenhum símbolo encontrado para "
                             f"'{self.symbol}' em '{self.category}'")
        return results[0]

    @staticmethod
    def _wrap_message(func: str, params: list) -> str:
        """Empacota JSON com header ~m~<len>~m~JSON."""
        payload = json.dumps({"m": func, "p": params}, separators=(",", ":"))
        return f"~m~{len(payload)}~m~{payload}"

    def on_message(self, ws, raw_msg: str):
        """Callback para cada mensagem recebida."""
        # descarta mensagens de handhake/ping padrão
        if raw_msg.startswith("~h~") or raw_msg.strip() == "":
            return

        # extrai JSON depois do segundo "~m~"
        parts = raw_msg.split("~m~")
        if len(parts) < 3:
            return
        try:
            data = json.loads(parts[2])
        except json.JSONDecodeError:
            logger.debug("Falha ao decodificar JSON: %s", parts[2])
            return

        # evento de preço
        if data.get("m") == "qsd":
            # data['p'] = [session, {"n": symbol, "v": {"lp": last_price}}]
            symbol = data["p"][1]["n"]
            price = data["p"][1]["v"]["lp"]
            logger.info(f"{symbol} -> {price}")

    def on_error(self, ws, error):
        logger.error("WebSocket error: %s", error)

    def on_close(self, ws, close_status_code, close_msg):
        logger.warning("WebSocket closed (%s): %s", close_status_code, close_msg)

    def on_open(self, ws):
        """Callback de abertura: registra sessão e símbolos."""
        logger.info("WebSocket aberto, session_id=%s", self.session_id)
        send = lambda f, p: ws.send(self._wrap_message(f, p))

        send("quote_create_session", [self.session_id])
        send("quote_set_fields", [self.session_id, "lp"])
        # símbolo no formato EXCHANGE:SYMBOL
        meta = self._search_symbol()
        full_sym = f"{meta['exchange'].upper()}:{meta['symbol'].upper()}"
        send("quote_add_symbols", [self.session_id, full_sym])

    def run(self):
        """Inicia o loop de conexão com auto-reconnect."""
        backoff = 1
        while True:
            try:
                self.ws = WebSocketApp(
                    WS_URL,
                    on_open=self.on_open,
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close,
                    header={"Origin": "https://data.tradingview.com"},
                    ping_interval=PING_INTERVAL,
                    ping_timeout=10
                )
                self.ws.run_forever()
            except WebSocketConnectionClosedException:
                logger.warning("Conexão fechada, reconectando em %s s...", backoff)
            except Exception as e:
                logger.exception("Erro inesperado, reconectando em %s s...", backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX)


def parse_args():
    p = argparse.ArgumentParser(
        description="Consome preço em tempo real do TradingView via WebSocket"
    )
    p.add_argument("symbol", help="Texto de busca do símbolo (ex: BTCUSD)")
    p.add_argument(
        "-c", "--category", default="crypto",
        choices=["stock", "forex", "crypto", "futures", "cfd", "index", "economic"]
    )
    return p.parse_args()


def main():
    args = parse_args()
    client = TradingViewClient(args.symbol, args.category)
    try:
        client.run()
    except KeyboardInterrupt:
        logger.info("Encerrando por keyboard interrupt")
        sys.exit(0)


if __name__ == "__main__":
    main()
