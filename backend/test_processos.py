"""Testes reais de prazo, cancelamento e encerramento da árvore de processos."""
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from erros import FalhaAplicacao, classificar_erro
from processos import ProcessoIsolado
from operacoes import executar_isolado
import temporarios


class ProcessosTest(unittest.TestCase):
    def test_worker_real_devolve_erro_estruturado_sem_acesso_a_rede(self):
        with tempfile.TemporaryDirectory(prefix="tubeyou_test_worker_") as pasta:
            with patch.object(temporarios, "PASTA_TEMPORARIOS", Path(pasta)):
                trabalho = temporarios.DownloadTemporario()
                try:
                    with self.assertRaises(FalhaAplicacao) as contexto:
                        executar_isolado("inexistente", {}, trabalho, 90, threading.Event())
                    self.assertEqual(contexto.exception.codigo, "ERRO_INTERNO")
                finally:
                    trabalho.close()
                self.assertEqual(list(Path(pasta).iterdir()), [])

    def test_prazo_encerra_processo(self):
        with ProcessoIsolado([sys.executable, "-B", "-c", "import time; time.sleep(60)"]) as processo:
            with self.assertRaises(FalhaAplicacao) as contexto:
                processo.aguardar(0.2, threading.Event())
            self.assertEqual(contexto.exception.codigo, "TEMPO_ESGOTADO")
        self.assertIsNotNone(processo.processo.poll())

    def test_cancelamento_encerra_processo(self):
        evento = threading.Event()
        evento.set()
        with ProcessoIsolado([sys.executable, "-B", "-c", "import time; time.sleep(60)"]) as processo:
            with self.assertRaises(FalhaAplicacao) as contexto:
                processo.aguardar(10, evento)
            self.assertEqual(contexto.exception.codigo, "CANCELADO")
        self.assertIsNotNone(processo.processo.poll())

    @unittest.skipUnless(os.name == "nt", "Verificação de Job Object no Windows")
    def test_encerrar_grupo_mata_tambem_processo_filho(self):
        with tempfile.TemporaryDirectory(prefix="tubeyou_test_tree_") as pasta:
            caminho_pid = Path(pasta) / "pid.txt"
            codigo = (
                "import subprocess,sys,time; from pathlib import Path; "
                "p=subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(60)']); "
                f"Path({str(caminho_pid)!r}).write_text(str(p.pid)); time.sleep(60)"
            )
            with ProcessoIsolado([sys.executable, "-B", "-c", codigo]) as processo:
                prazo = time.monotonic() + 45
                while not caminho_pid.exists() and time.monotonic() < prazo:
                    time.sleep(0.05)
                self.assertTrue(caminho_pid.exists())
                filho = int(caminho_pid.read_text())
                api = ctypes.WinDLL("kernel32", use_last_error=True)
                api.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
                api.OpenProcess.restype = ctypes.c_void_p
                api.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
                api.CloseHandle.argtypes = [ctypes.c_void_p]
                handle = api.OpenProcess(0x00100000, False, filho)
                self.assertTrue(handle)
            try:
                self.assertEqual(api.WaitForSingleObject(handle, 5000), 0)
            finally:
                api.CloseHandle(handle)

    def test_mensagens_classificam_causas_sem_expor_detalhes(self):
        from yt_dlp.utils import DownloadError
        casos = [("Private video token=secreto", "ACESSO_RESTRITO"),
                 ("HTTP Error 403: Forbidden", "ACESSO_NEGADO"),
                 ("HTTP Error 429", "LIMITE_YOUTUBE"),
                 ("Video unavailable", "VIDEO_INDISPONIVEL"),
                 ("Requested format is not available", "FORMATO_INDISPONIVEL"),
                 ("Unable to download webpage: connection timed out", "FALHA_CONEXAO")]
        for mensagem, codigo in casos:
            with self.subTest(codigo=codigo):
                erro = classificar_erro(DownloadError(mensagem))
                self.assertEqual(erro.codigo, codigo)
                self.assertNotIn("secreto", erro.mensagem)
