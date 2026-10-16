"""Limites de execução reais, incluindo FFmpeg/Deno criados pelo worker."""
import ctypes
import os
import signal
import subprocess
import time

from erros import FalhaAplicacao


class GrupoWindows:
    """O Windows encerra os filhos mesmo se o servidor fechar inesperadamente."""
    def __init__(self, processo):
        from ctypes import wintypes

        class LimitesBasicos(ctypes.Structure):
            _fields_ = [("tempo_processo", ctypes.c_longlong), ("tempo_job", ctypes.c_longlong),
                        ("flags", wintypes.DWORD), ("memoria_min", ctypes.c_size_t),
                        ("memoria_max", ctypes.c_size_t), ("processos", wintypes.DWORD),
                        ("afinidade", ctypes.c_size_t), ("prioridade", wintypes.DWORD),
                        ("agendamento", wintypes.DWORD)]

        class ContadoresIO(ctypes.Structure):
            _fields_ = [(nome, ctypes.c_ulonglong) for nome in
                        ("leituras", "escritas", "outros", "bytes_lidos", "bytes_escritos", "outros_bytes")]

        class LimitesEstendidos(ctypes.Structure):
            _fields_ = [("basicos", LimitesBasicos), ("io", ContadoresIO),
                        ("memoria_processo", ctypes.c_size_t), ("memoria_job", ctypes.c_size_t),
                        ("pico_processo", ctypes.c_size_t), ("pico_job", ctypes.c_size_t)]

        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.api.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            limites = LimitesEstendidos()
            limites.basicos.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limites), ctypes.sizeof(limites)):
                raise ctypes.WinError(ctypes.get_last_error())
            if not self.api.AssignProcessToJobObject(self.handle, wintypes.HANDLE(int(processo._handle))):
                raise ctypes.WinError(ctypes.get_last_error())
        except Exception:
            self.close()
            raise

    def encerrar(self):
        if self.handle:
            self.api.TerminateJobObject(self.handle, 1)

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


class ProcessoIsolado:
    def __init__(self, argumentos):
        self.grupo_windows = None
        opcoes = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                  "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            opcoes["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            opcoes["start_new_session"] = True
        self.processo = subprocess.Popen(argumentos, **opcoes)
        try:
            if os.name == "nt":
                self.grupo_windows = GrupoWindows(self.processo)
        except Exception:
            self.processo.kill()
            self.processo.wait(timeout=10)
            raise

    def aguardar(self, limite, cancelamento):
        prazo = time.monotonic() + limite
        while self.processo.poll() is None:
            if cancelamento.wait(min(0.1, max(0, prazo - time.monotonic()))):
                raise FalhaAplicacao("CANCELADO", "Operação cancelada.", 409)
            if time.monotonic() >= prazo:
                raise FalhaAplicacao("TEMPO_ESGOTADO", "O tempo limite do servidor foi atingido. Escolha uma qualidade menor ou tente novamente.", 504)
        return self.processo.returncode

    def close(self):
        if self.grupo_windows is not None:
            self.grupo_windows.encerrar()
            self.grupo_windows.close()
            self.grupo_windows = None
        elif os.name != "nt":
            try:
                os.killpg(self.processo.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif self.processo.poll() is None:
            self.processo.kill()
        self.processo.wait(timeout=10)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
