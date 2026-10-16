from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from yt_dlp import YoutubeDL
from erros import FalhaAplicacao
import midia


VIDEO = {"format_id": "137", "ext": "mp4", "vcodec": "avc1", "acodec": "none"}
AUDIO = {"format_id": "251", "ext": "webm", "vcodec": "none", "acodec": "opus"}


class MidiaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.TemporaryDirectory(prefix="tubeyou_test_media_")
        cls.pasta = Path(cls.base.name)
        cls.video, cls.audio = cls.pasta / "video.mp4", cls.pasta / "audio.webm"
        cls.video_mudo = cls.pasta / "mudo.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=160x120:r=10",
                        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100", "-t", "0.5",
                        "-c:v", "mpeg4", "-c:a", "aac", "-y", str(cls.video)],
                       check=True, capture_output=True, timeout=30)
        for saida, opcoes in [(cls.audio, ["-vn", "-c:a", "libopus"]), (cls.video_mudo, ["-an", "-c:v", "copy"])]:
            subprocess.run(["ffmpeg", "-v", "error", "-i", str(cls.video), *opcoes, "-y", str(saida)],
                           check=True, capture_output=True, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.base.cleanup()

    def test_ffprobe_detecta_audio_e_video_corretamente(self):
        midia.verificar_midia(self.video, "video")
        midia.verificar_midia(self.audio, "audio")
        for arquivo, tipo in [(self.audio, "video"), (self.video, "audio"), (self.video_mudo, "video")]:
            with self.subTest(arquivo=arquivo.name, tipo=tipo):
                with self.assertRaises(FalhaAplicacao):
                    midia.verificar_midia(arquivo, tipo)

    def test_processamento_real_preserva_video_sem_m4a_e_audio_separado(self):
        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass
        servidor = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=self.base.name))
        thread = threading.Thread(target=servidor.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{servidor.server_port}"
            info = {"id": "teste", "title": "Mídia de teste", "extractor": "teste", "webpage_url": url,
                    "formats": [dict(VIDEO, url=url + "/mudo.mp4"), dict(AUDIO, url=url + "/audio.webm")]}
            class YDLLocal(YoutubeDL):
                def extract_info(self, url, download=True):
                    return self.process_ie_result(info, download=download)
            for tipo, formato in [("video", "137"), ("audio", "251")]:
                with tempfile.TemporaryDirectory(prefix="tubeyou_test_result_") as destino:
                    with patch.object(midia, "obter_info", return_value=info), patch.object(midia.yt_dlp, "YoutubeDL", YDLLocal):
                        resultado = midia.preparar_download({"url": url, "tipo": tipo, "format_id": formato}, Path(destino))
                    midia.verificar_midia(Path(destino) / resultado["arquivo"], tipo)
                    self.assertGreater(resultado["tamanho"], 0)
        finally:
            servidor.shutdown()
            servidor.server_close()
            thread.join(timeout=5)

    def test_arquivo_final_vem_do_hook_e_nao_do_tamanho(self):
        info = {"formats": [VIDEO, AUDIO]}
        with tempfile.TemporaryDirectory(prefix="tubeyou_test_result_") as destino:
            destino = Path(destino)
            (destino / "gigante.part").write_bytes(b"x" * 50000)
            def construir(opcoes):
                class YDL:
                    def __enter__(self): return self
                    def __exit__(self, *args): return False
                    def extract_info(self, *args, **kwargs):
                        saida = destino / "correto.mp4"
                        shutil.copyfile(MidiaTest.video, saida)
                        opcoes["post_hooks"][0](str(saida))
                return YDL()
            with patch.object(midia, "obter_info", return_value=info), patch.object(midia.yt_dlp, "YoutubeDL", side_effect=construir):
                resultado = midia.preparar_download({"url": "teste", "tipo": "video", "format_id": "137"}, destino)
            self.assertEqual(resultado["arquivo"], "correto.mp4")

    def test_playlist_e_live_sao_recusadas_antes_do_download(self):
        for info in [{"_type": "playlist", "entries": []}, {"id": "live", "is_live": True}]:
            with patch.object(midia.yt_dlp, "YoutubeDL") as ydl:
                ydl.return_value.__enter__.return_value.extract_info.return_value = info
                with self.assertRaises(FalhaAplicacao):
                    midia.obter_info("https://youtu.be/teste")

    def test_codec_audio_ausente_nao_quebra_listagem(self):
        with patch.object(midia, "obter_info", return_value={"formats": [
            dict(VIDEO, height=1080, acodec=None), dict(VIDEO, format_id="138", height=1080, fps=60)]}):
            formatos = midia.obter_formatos("teste")
        self.assertEqual(len(formatos["video"]), 1)
