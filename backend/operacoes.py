"""Trabalhos pequenos em memória, com concorrência, prazo e expiração limitados."""
from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
import secrets
import sys
import threading
import time

from erros import FalhaAplicacao, classificar_erro
from processos import ProcessoIsolado
from temporarios import DownloadTemporario, limpar_temporarios_abandonados


logger = logging.getLogger(__name__)


def executar_isolado(tarefa, dados, temporario, limite, cancelamento):
    pasta = temporario.pasta
    (pasta / "entrada.json").write_text(json.dumps({"tarefa": tarefa, "dados": dados}), encoding="utf-8")
    try:
        with ProcessoIsolado([sys.executable, "-B", str(Path(__file__).with_name("worker.py")), str(pasta)]) as processo:
            retorno = processo.aguardar(limite, cancelamento)
        caminho = pasta / "resultado.json"
        if retorno != 0 or not caminho.is_file():
            raise RuntimeError("Worker terminou sem um resultado válido.")
        saida = json.loads(caminho.read_text(encoding="utf-8"))
        if not saida["ok"]:
            raise FalhaAplicacao(saida["codigo"], saida["erro"], saida["status"])
        return saida["resultado"]
    finally:
        # Diagnóstico preservado no servidor antes de excluir os temporários.
        for caminho in [pasta / "worker.log.1", pasta / "worker.log"]:
            if caminho.exists():
                with caminho.open("rb") as arquivo:
                    arquivo.seek(max(0, caminho.stat().st_size - 16384))
                    trecho = arquivo.read().decode("utf-8", errors="replace")
                if trecho:
                    logger.warning("Diagnóstico %s: %s", pasta.name, trecho)


@dataclass
class Operacao:
    id: str
    tarefa: str
    dados: dict
    limite: float
    temporario: DownloadTemporario
    estado: str = "preparando"
    resultado: dict | None = None
    erro: dict | None = None
    concluida_em: float = 0
    cancelamento: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None


class GerenciadorOperacoes:
    def __init__(self, executor=executar_isolado, max_ativas=2, validade_arquivo=300, validade_estado=60):
        self.executor = executor
        self.max_ativas = max_ativas
        self.validade_arquivo = validade_arquivo
        self.validade_estado = validade_estado
        self.operacoes = {}
        self.lock = threading.RLock()
        self.parar = threading.Event()
        self.manutencao = None

    def iniciar(self, tarefa, dados, limite):
        self.limpar()
        with self.lock:
            ativas = sum(o.estado == "preparando" for o in self.operacoes.values())
            if ativas >= self.max_ativas or len(self.operacoes) >= 20:
                raise FalhaAplicacao("SERVIDOR_OCUPADO", "O servidor está ocupado. Aguarde uma operação terminar.", 429)
            operacao = Operacao(secrets.token_urlsafe(24), tarefa, dados, limite, DownloadTemporario())
            self.operacoes[operacao.id] = operacao
            try:
                operacao.thread = threading.Thread(target=self._executar, args=(operacao,), daemon=True,
                                                    name=f"tubeyou-{operacao.id[:8]}")
                operacao.thread.start()
            except Exception:
                del self.operacoes[operacao.id]
                operacao.temporario.close()
                raise
            return operacao

    def _executar(self, operacao):
        logger.info("Operação %s iniciada: %s, pasta %s, limite %ss", operacao.id,
                    operacao.tarefa, operacao.temporario.pasta.name, operacao.limite)
        resultado = None
        falha = None
        try:
            resultado = self.executor(operacao.tarefa, operacao.dados, operacao.temporario,
                                      operacao.limite, operacao.cancelamento)
        except Exception as erro:
            falha = classificar_erro(erro)
            logger.exception("Operação %s falhou: %s", operacao.id, falha.codigo)
        finally:
            with self.lock:
                if operacao.cancelamento.is_set():
                    falha = FalhaAplicacao("CANCELADO", "Operação cancelada.", 409)
                # Só publique o estado final depois de liberar os recursos.
                if operacao.tarefa == "formatos" or falha is not None:
                    operacao.temporario.close()
                operacao.concluida_em = time.monotonic()
                if falha is not None:
                    operacao.erro = falha.publico()
                    operacao.estado = "cancelado" if falha.codigo == "CANCELADO" else "erro"
                else:
                    operacao.resultado = resultado
                    operacao.estado = "pronto"
                    logger.info("Operação %s pronta", operacao.id)

    def obter(self, identificador):
        with self.lock:
            operacao = self.operacoes.get(identificador)
            if operacao is None:
                raise FalhaAplicacao("OPERACAO_EXPIRADA", "A operação expirou. Consulte os formatos novamente.", 404)
            return operacao

    def cancelar(self, identificador):
        with self.lock:
            operacao = self.obter(identificador)
            if operacao.estado == "enviando":
                raise FalhaAplicacao("ENVIO_INICIADO", "Cancele a transferência pelo gerenciador de downloads do navegador.", 409)
            operacao.cancelamento.set()
            if operacao.estado == "pronto":
                operacao.estado = "cancelado"
                operacao.concluida_em = time.monotonic()
                operacao.temporario.close()

    def iniciar_envio(self, identificador):
        with self.lock:
            operacao = self.obter(identificador)
            if operacao.tarefa != "download" or operacao.estado != "pronto":
                raise FalhaAplicacao("ARQUIVO_NAO_DISPONIVEL", "O arquivo ainda não está pronto ou já foi enviado.", 409)
            if time.monotonic() - operacao.concluida_em >= self.validade_arquivo:
                operacao.estado = "expirado"
                operacao.temporario.close()
                raise FalhaAplicacao("ARQUIVO_EXPIRADO", "O arquivo expirou. Prepare o download novamente.", 410)
            operacao.estado = "enviando"
            return operacao

    def finalizar_envio(self, operacao):
        with self.lock:
            operacao.temporario.close()
            operacao.estado = "concluido"
            operacao.concluida_em = time.monotonic()

    def limpar(self):
        with self.lock:
            agora = time.monotonic()
            for identificador, operacao in list(self.operacoes.items()):
                if operacao.estado in ("preparando", "enviando"):
                    continue
                validade = self.validade_arquivo if operacao.tarefa == "download" and operacao.estado == "pronto" else self.validade_estado
                if agora - operacao.concluida_em >= validade:
                    operacao.temporario.close()
                    del self.operacoes[identificador]

    def iniciar_manutencao(self):
        if self.manutencao is not None:
            return
        def executar():
            while not self.parar.wait(1):
                try:
                    self.limpar()
                    limpar_temporarios_abandonados()
                except Exception:
                    logger.exception("Falha na manutenção dos temporários")
        self.manutencao = threading.Thread(target=executar, daemon=True, name="tubeyou-manutencao")
        self.manutencao.start()

    def close(self):
        self.parar.set()
        with self.lock:
            operacoes = list(self.operacoes.values())
            for operacao in operacoes:
                operacao.cancelamento.set()
        for operacao in operacoes:
            if operacao.thread is not None:
                operacao.thread.join(timeout=15)
            if operacao.thread is None or not operacao.thread.is_alive():
                operacao.temporario.close()
        if self.manutencao is not None:
            self.manutencao.join(timeout=2)
