import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from erros import FalhaAplicacao
from operacoes import GerenciadorOperacoes
from publico import criar_app_publica
import midia
import temporarios


class PublicacaoTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.TemporaryDirectory(prefix="tubeyou_test_publico_")
        self.addCleanup(self.base.cleanup)
        p = patch.object(temporarios, "PASTA_TEMPORARIOS", Path(self.base.name))
        p.start()
        self.addCleanup(p.stop)
        self.gerenciador = GerenciadorOperacoes(executor=lambda *args: {})
        self.addCleanup(self.gerenciador.close)
        self.app = criar_app_publica(self.gerenciador)
        self.client = self.app.test_client()

    def test_site_e_api_na_mesma_origem(self):
        resposta = self.client.get("/")
        try:
            self.assertIn(b"<title>TubeYou</title>", resposta.data)
        finally:
            resposta.close()
        self.assertEqual(self.client.get("/api/health").get_json()["versao_api"], 2)
        for recurso in ("/script.js", "/style.css"):
            resposta = self.client.get(recurso)
            self.assertEqual(resposta.status_code, 200)
            self.assertTrue(resposta.data)
            resposta.close()

    def test_arquivos_privados_nao_sao_servidos(self):
        for caminho in ("/.git/config", "/backend/app.py", "/backend/logs/tubeyou.log",
                        "/.runtime/session.json", "/README.md", "/.tools/cloudflared.exe"):
            self.assertEqual(self.client.get(caminho).status_code, 404)

    def test_limite_global_de_preparacoes(self):
        for _ in range(12):
            self.assertEqual(self.client.post("/api/formats", json={"url": "invalida"}).status_code, 400)
        self.assertEqual(self.client.post("/api/formats", json={"url": "invalida"}).status_code, 429)
        # A consulta de estado não consome o limite de preparações.
        self.assertEqual(self.client.get("/api/health").status_code, 200)

    def test_duracao_publica_limitada(self):
        with patch.dict(os.environ, {"TUBEYOU_MAX_DURATION": "600"}), patch.object(midia.yt_dlp, "YoutubeDL") as ydl:
            ydl.return_value.__enter__.return_value.extract_info.return_value = {"duration": 601}
            with self.assertRaises(FalhaAplicacao) as contexto:
                midia.obter_info("teste")
        self.assertEqual(contexto.exception.codigo, "VIDEO_LONGO")

    def test_tamanho_soma_video_e_audio_e_interrompe_antes_de_finalizar(self):
        video = {"format_id": "137", "vcodec": "avc1", "acodec": "none", "ext": "mp4"}
        audio = {"format_id": "140", "vcodec": "none", "acodec": "aac", "ext": "m4a"}
        def construir(opcoes):
            class YDL:
                def __enter__(self): return self
                def __exit__(self, *_): return False
                def extract_info(self, *_args, **_kwargs):
                    hook = opcoes["progress_hooks"][0]
                    hook({"filename": "video", "downloaded_bytes": 80})
                    hook({"filename": "audio", "downloaded_bytes": 30})
            return YDL()
        with patch.dict(os.environ, {"TUBEYOU_MAX_BYTES": "100"}), patch.object(midia, "obter_info", return_value={"formats": [video, audio]}), patch.object(midia.yt_dlp, "YoutubeDL", side_effect=construir):
            with self.assertRaises(FalhaAplicacao) as contexto:
                midia.preparar_download({"url": "teste", "tipo": "video", "format_id": "137"}, Path(self.base.name))
        self.assertEqual(contexto.exception.codigo, "ARQUIVO_GRANDE")
