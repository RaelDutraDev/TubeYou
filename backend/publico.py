"""Servidor único para o teste público, sem expor o diretório do projeto."""
import logging
import os
import threading
import time

from waitress import create_server

from app import criar_app
from erros import FalhaAplicacao
from operacoes import GerenciadorOperacoes


def criar_app_publica(gerenciador=None):
    gerenciador = gerenciador or GerenciadorOperacoes(max_ativas=1, validade_arquivo=180)
    app = criar_app(gerenciador)
    app.config["SERVIR_SITE"] = True
    app.config["LIMITE_DOWNLOAD"] = 300
    # Todos os visitantes compartilham um limite simples no teste público.
    # Não confiamos em cabeçalhos de IP fornecidos por visitantes.
    consultas = []
    trava = threading.Lock()

    @app.before_request
    def limitar_preparacoes():
        from flask import request
        if request.method != "POST" or request.path not in ("/api/formats", "/api/download"):
            return
        with trava:
            agora = time.monotonic()
            consultas[:] = [instante for instante in consultas if agora - instante < 60]
            if len(consultas) >= 12:
                raise FalhaAplicacao("LIMITE_TESTE_PUBLICO", "O teste público recebeu muitas solicitações. Aguarde um minuto.", 429)
            consultas.append(agora)
    return app


def main():
    os.environ.setdefault("TUBEYOU_MAX_DURATION", "600")
    os.environ.setdefault("TUBEYOU_MAX_BYTES", str(100 * 1024 * 1024))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = criar_app_publica()
    gerenciador = app.extensions["operacoes"]
    gerenciador.iniciar_manutencao()
    servidor = create_server(app, host="127.0.0.1", port=int(os.getenv("TUBEYOU_PORT", "5510")),
                             threads=6, connection_limit=100, channel_timeout=120,
                             max_request_body_size=16384, expose_tracebacks=False)
    try:
        servidor.run()
    finally:
        servidor.close()
        gerenciador.close()


if __name__ == "__main__":
    main()
