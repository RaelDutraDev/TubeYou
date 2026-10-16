"""Temporários de download, com bloqueio entre processos e recuperação de resíduos."""

import logging
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time


logger = logging.getLogger(__name__)
PASTA_TEMPORARIOS = Path(tempfile.gettempdir()) / "tubeyou"
INTERVALO_LIMPEZA = 60


def _bloquear(arquivo):
    arquivo.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(arquivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _remover(pasta):
    # A limpeza fica restrita às pastas de trabalho criadas por este módulo.
    if (pasta.is_symlink() or pasta.is_junction()
            or pasta.resolve().parent != PASTA_TEMPORARIOS.resolve()
            or not pasta.name.startswith("job_")):
        raise ValueError("Pasta temporária fora do local permitido.")
    try:
        shutil.rmtree(pasta)
    except FileNotFoundError:
        pass
    except OSError:
        logger.exception("Não foi possível limpar %s; haverá nova tentativa.", pasta)


class DownloadTemporario:
    def __init__(self):
        PASTA_TEMPORARIOS.mkdir(parents=True, exist_ok=True)
        self.pasta = Path(tempfile.mkdtemp(prefix="job_", dir=PASTA_TEMPORARIOS))
        self._fechado = False
        self._bloqueio = None
        try:
            self._bloqueio = (self.pasta / ".lock").open("w+b")
            self._bloqueio.write(b"1")
            self._bloqueio.flush()
            _bloquear(self._bloqueio)
        except Exception:
            self.close()
            raise

    def close(self):
        if self._fechado:
            return
        self._fechado = True
        # No Windows o arquivo de bloqueio também precisa fechar antes do rmtree.
        if self._bloqueio is not None:
            self._bloqueio.close()
        _remover(self.pasta)


def limpar_temporarios_abandonados(idade_minima=INTERVALO_LIMPEZA):
    if not PASTA_TEMPORARIOS.exists():
        return
    for pasta in PASTA_TEMPORARIOS.glob("job_*"):
        if not pasta.is_dir() or pasta.is_symlink() or pasta.is_junction():
            continue
        try:
            if time.time() - pasta.stat().st_mtime < idade_minima:
                continue
            bloqueio = pasta / ".lock"
            if bloqueio.exists():
                # O bloqueio do sistema é liberado inclusive se o servidor cair.
                with bloqueio.open("r+b") as arquivo:
                    _bloquear(arquivo)
            _remover(pasta)
        except FileNotFoundError:
            continue
        except OSError:
            # Um download ativo (inclusive em outro processo) mantém o bloqueio.
            logger.debug("Temporário ativo ou indisponível: %s", pasta)


def iniciar_limpeza_periodica():
    parar = threading.Event()

    def executar():
        while not parar.is_set():
            try:
                limpar_temporarios_abandonados()
            except OSError:
                logger.exception("Falha ao verificar os temporários do TubeYou.")
            parar.wait(INTERVALO_LIMPEZA)

    threading.Thread(target=executar, name="tubeyou-limpeza", daemon=True).start()
    return parar
