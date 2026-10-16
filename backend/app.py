from pathlib import Path
import atexit
import logging
from logging.handlers import RotatingFileHandler
import os
import secrets
from urllib.parse import urlparse

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.wsgi import ClosingIterator

from erros import FalhaAplicacao
from operacoes import GerenciadorOperacoes


def eh_link_youtube(url):
    try:
        endereco = urlparse(url)
        return (endereco.scheme in ("http", "https")
                and endereco.hostname in ("youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be")
                and not endereco.username and not endereco.password)
    except ValueError:
        return False


def criar_app(gerenciador=None):
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=16384, LIMITE_FORMATOS=90, LIMITE_DOWNLOAD=600)
    gerenciador = gerenciador or GerenciadorOperacoes()
    app.extensions["operacoes"] = gerenciador
    assinador = URLSafeTimedSerializer(secrets.token_hex(32), salt="tubeyou-consulta-v2")
    app.extensions["assinador"] = assinador
    origens = [o.strip() for o in os.getenv("TUBEYOU_ALLOWED_ORIGINS",
        "http://127.0.0.1:5500,http://localhost:5500,http://127.0.0.1:8000,http://localhost:8000").split(",") if o.strip()]
    CORS(app, resources={r"/api/*": {"origins": origens}}, expose_headers=["Content-Disposition"])

    def dados_json():
        if request.content_length is not None and request.content_length > app.config["MAX_CONTENT_LENGTH"]:
            raise RequestEntityTooLarge()
        dados = request.get_json(silent=True)
        if not isinstance(dados, dict):
            raise FalhaAplicacao("JSON_INVALIDO", "Envie um objeto JSON válido.", 400)
        return dados

    def validar_url(dados):
        url = dados.get("url", "")
        if not isinstance(url, str) or len(url) > 2048 or not eh_link_youtube(url.strip()):
            raise FalhaAplicacao("URL_INVALIDA", "Informe um link válido de um vídeo do YouTube.", 400)
        return url.strip()

    def apresentar(operacao):
        resultado = {"id": operacao.id, "estado": operacao.estado,
                     "limite_segundos": operacao.limite, "referencia": operacao.id[:8],
                     "status_url": f"/api/operacoes/{operacao.id}"}
        if operacao.erro:
            resultado.update(operacao.erro)
        if operacao.estado == "pronto":
            if operacao.tarefa == "formatos":
                formatos = dict(operacao.resultado)
                formatos["consulta"] = assinador.dumps({
                    "url": operacao.dados["url"],
                    "video": [f["format_id"] for f in formatos["video"]],
                    "audio": [f["format_id"] for f in formatos["audio"]],
                })
                resultado["resultado"] = formatos
            else:
                resultado["resultado"] = {
                    "nome": operacao.resultado["arquivo"], "tamanho": operacao.resultado["tamanho"],
                    "arquivo_url": f"/api/download/{operacao.id}/arquivo", "validade_segundos": gerenciador.validade_arquivo,
                }
        return resultado

    @app.after_request
    def sem_cache(resposta):
        if request.path.startswith("/api/"):
            resposta.headers["Cache-Control"] = "no-store"
            resposta.headers["X-Content-Type-Options"] = "nosniff"
        return resposta

    @app.errorhandler(FalhaAplicacao)
    def erro_publico(erro):
        return jsonify(erro.publico()), erro.status

    @app.errorhandler(Exception)
    def erro_inesperado(erro):
        if isinstance(erro, HTTPException):
            mensagens = {404: "Endereço não encontrado.", 405: "Método não permitido.",
                         413: "A requisição excede o tamanho permitido."}
            return jsonify({"erro": mensagens.get(erro.code, "A requisição não pôde ser processada."),
                            "codigo": f"HTTP_{erro.code}"}), erro.code
        referencia = secrets.token_hex(4)
        app.logger.exception("Erro de API, referência %s", referencia)
        return jsonify({"erro": "O servidor encontrou um erro. Consulte o registro usando a referência.",
                        "codigo": "ERRO_INTERNO", "referencia": referencia}), 500

    @app.get("/")
    def inicio():
        if app.config.get("SERVIR_SITE"):
            return send_file(Path(__file__).resolve().parent.parent / "index.html", max_age=0)
        return {"status": "TubeYou backend funcionando!", "versao_api": 2}

    @app.get("/api/health")
    def health():
        return {"status": "ok", "versao_api": 2}

    @app.get("/script.js")
    @app.get("/style.css")
    def recurso_site():
        if not app.config.get("SERVIR_SITE"):
            raise FalhaAplicacao("NAO_ENCONTRADO", "Endereço não encontrado.", 404)
        resposta = send_file(Path(__file__).resolve().parent.parent / request.path.lstrip("/"), max_age=0)
        resposta.headers["Cache-Control"] = "no-cache"
        return resposta

    @app.post("/api/formats")
    def formatos():
        url = validar_url(dados_json())
        operacao = gerenciador.iniciar("formatos", {"url": url}, app.config["LIMITE_FORMATOS"])
        with gerenciador.lock:
            return jsonify(apresentar(operacao)), 202

    @app.post("/api/download")
    def preparar():
        dados = dados_json()
        url = validar_url(dados)
        tipo, formato = dados.get("tipo"), dados.get("format_id")
        if tipo not in ("audio", "video") or not isinstance(formato, str) or not formato:
            raise FalhaAplicacao("FORMATO_INVALIDO", "Selecione um formato de vídeo ou áudio válido.", 400)
        token = dados.get("consulta", "")
        if not isinstance(token, str) or len(token) > 12000:
            raise FalhaAplicacao("CONSULTA_INVALIDA", "Consulte os formatos novamente.", 400)
        try:
            consulta = assinador.loads(token, max_age=900)
        except (BadSignature, SignatureExpired, TypeError):
            raise FalhaAplicacao("CONSULTA_EXPIRADA", "A consulta expirou ou é inválida. Consulte os formatos novamente.", 409)
        if consulta["url"] != url or formato not in consulta[tipo]:
            raise FalhaAplicacao("CONSULTA_DIFERENTE", "A URL ou o formato mudou. Consulte os formatos novamente.", 409)
        operacao = gerenciador.iniciar("download", {"url": url, "tipo": tipo, "format_id": formato},
                                      app.config["LIMITE_DOWNLOAD"])
        with gerenciador.lock:
            return jsonify(apresentar(operacao)), 202

    @app.get("/api/operacoes/<identificador>")
    def consultar(identificador):
        gerenciador.limpar()
        with gerenciador.lock:
            return jsonify(apresentar(gerenciador.obter(identificador)))

    @app.delete("/api/operacoes/<identificador>")
    def cancelar(identificador):
        gerenciador.cancelar(identificador)
        return jsonify({"estado": "cancelamento_solicitado"}), 202

    @app.get("/api/download/<identificador>/arquivo")
    def arquivo(identificador):
        operacao = gerenciador.iniciar_envio(identificador)
        try:
            caminho = (operacao.temporario.pasta / operacao.resultado["arquivo"]).resolve()
            if caminho.parent != operacao.temporario.pasta.resolve() or not caminho.is_file():
                raise FalhaAplicacao("ARQUIVO_AUSENTE", "O arquivo não está mais disponível. Prepare o download novamente.", 410)
            resposta = send_file(caminho, as_attachment=True, download_name=caminho.name, conditional=False)
            resposta.response = ClosingIterator(resposta.response, lambda: gerenciador.finalizar_envio(operacao))
            return resposta
        except Exception:
            gerenciador.finalizar_envio(operacao)
            raise

    return app


app = criar_app()


if __name__ == "__main__":
    logs = Path(__file__).with_name("logs")
    logs.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), RotatingFileHandler(logs / "tubeyou.log", maxBytes=1048576,
                                                             backupCount=2, encoding="utf-8")])
    gerenciador = app.extensions["operacoes"]
    gerenciador.iniciar_manutencao()
    atexit.register(gerenciador.close)
    try:
        app.run(host="127.0.0.1", port=5000, debug=False)
    finally:
        gerenciador.close()
