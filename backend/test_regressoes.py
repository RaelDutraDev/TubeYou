import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from yt_dlp import YoutubeDL
from erros import FalhaAplicacao
import midia as aplicativo
import temporarios

VIDEO = {"format_id": "137", "ext": "mp4", "vcodec": "avc1", "acodec": "none"}
AUDIO = {"format_id": "251", "ext": "webm", "vcodec": "none", "acodec": "opus"}
M4A = {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "aac"}
COMPLETO = {"format_id": "18", "ext": "mp4", "vcodec": "avc1", "acodec": "aac"}

class FormatosTest(unittest.TestCase):
    def escolher(self, formatos):
        seletor = aplicativo.selecionar_formato(VIDEO, "video", formatos)
        with YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            formatos = [dict(f, url="https://example.invalid/media") for f in formatos]
            return list(ydl.build_format_selector(seletor)({
                "formats": formatos, "has_merged_format": False,
                "incomplete_formats": False,
            }))[0]

    def test_video_sem_m4a_preserva_video_e_combina_opus(self):
        escolhido = self.escolher([VIDEO, AUDIO])
        self.assertEqual([f["format_id"] for f in escolhido["requested_formats"]],
                         ["137", "251"])

    def test_video_prefere_m4a_quando_disponivel(self):
        escolhido = self.escolher([VIDEO, M4A, AUDIO])
        self.assertEqual([f["format_id"] for f in escolhido["requested_formats"]],
                         ["137", "140"])

    def test_formato_completo_preserva_escolha(self):
        self.assertEqual(aplicativo.selecionar_formato(COMPLETO, "video", []), "18")

    def test_audio_permanece_audio(self):
        self.assertEqual(aplicativo.selecionar_formato(AUDIO, "audio", []), "251")

    def test_tipos_incompativeis_sao_recusados(self):
        for formato, tipo in [(AUDIO, "video"), (VIDEO, "audio"), (COMPLETO, "audio")]:
            with self.subTest(tipo=tipo, formato=formato["format_id"]):
                with self.assertRaises(FalhaAplicacao):
                    aplicativo.selecionar_formato(formato, tipo, [VIDEO, AUDIO])

    def test_video_sem_audio_disponivel_falha(self):
        with self.assertRaises(FalhaAplicacao):
            aplicativo.selecionar_formato(VIDEO, "video", [VIDEO])

    def test_juncao_sem_ffmpeg_falha(self):
        with patch.object(aplicativo.shutil, "which", return_value=None):
            with self.assertRaises(FalhaAplicacao):
                aplicativo.selecionar_formato(VIDEO, "video", [VIDEO, AUDIO])


class LimpezaTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.TemporaryDirectory(prefix="tubeyou_test_cleanup_")
        self.addCleanup(self.base.cleanup)
        p = patch.object(temporarios, "PASTA_TEMPORARIOS", Path(self.base.name))
        p.start()
        self.addCleanup(p.stop)

    def test_download_ativo_nao_e_removido(self):
        download = temporarios.DownloadTemporario()
        try:
            temporarios.limpar_temporarios_abandonados(idade_minima=0)
            self.assertTrue(download.pasta.is_dir())
        finally:
            download.close()
        self.assertFalse(download.pasta.exists())

    def test_restos_de_processo_encerrado_sao_removidos(self):
        codigo = (
            "import os; from pathlib import Path; import temporarios; "
            f"temporarios.PASTA_TEMPORARIOS = Path({self.base.name!r}); "
            "d = temporarios.DownloadTemporario(); "
            "(d.pasta / 'incompleto.part').write_bytes(b'teste'); os._exit(0)"
        )
        subprocess.run([sys.executable, "-B", "-c", codigo],
                       cwd=Path(temporarios.__file__).parent, check=True, timeout=90)
        self.assertTrue(list(Path(self.base.name).iterdir()))
        temporarios.limpar_temporarios_abandonados(idade_minima=0)
        self.assertEqual(list(Path(self.base.name).iterdir()), [])

    def test_residuo_sem_lock_e_arquivo_alheio(self):
        pasta = Path(self.base.name) / "job_orfao"
        pasta.mkdir()
        (pasta / "video.part").write_bytes(b"teste")
        alheio = Path(self.base.name) / "outro_app"
        alheio.mkdir()
        temporarios.limpar_temporarios_abandonados(idade_minima=0)
        self.assertFalse(pasta.exists())
        self.assertTrue(alheio.exists())

    def test_falha_de_remocao_e_recuperada_na_proxima_limpeza(self):
        download = temporarios.DownloadTemporario()
        with patch.object(temporarios.shutil, "rmtree", side_effect=PermissionError("teste")):
            download.close()
        self.assertTrue(download.pasta.exists())
        temporarios.limpar_temporarios_abandonados(idade_minima=0)
        self.assertFalse(download.pasta.exists())

    def test_limpeza_periodica_para_sem_prender_processo(self):
        with patch.object(temporarios, "INTERVALO_LIMPEZA", 0.01):
            evento = temporarios.iniciar_limpeza_periodica()
            evento.set()
