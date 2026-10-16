"""Contrato da API: URL vinculada, arquivo nativo, limites e expiração."""
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from app import criar_app
from erros import FalhaAplicacao
from operacoes import GerenciadorOperacoes
import temporarios


URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
FORMATOS = {"titulo": "Teste", "duracao": 1,
            "video": [{"format_id": "137", "altura": 1080, "ext": "mp4"}],
            "audio": [{"format_id": "251", "bitrate": 128, "ext": "webm"}]}
CONTEUDO = b"teste de transferencia" * 20000


def executor(tarefa, dados, temporario, limite, cancelamento):
    if tarefa == "formatos":
        return FORMATOS
    arquivo = temporario.pasta / "Midia com acento ç.mp4"
    arquivo.write_bytes(CONTEUDO)
    (temporario.pasta / "maior.part").write_bytes(b"x" * (len(CONTEUDO) + 1))
    return {"arquivo": arquivo.name, "tamanho": arquivo.stat().st_size}


class OperacoesTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.TemporaryDirectory(prefix="tubeyou_test_api_")
        self.addCleanup(self.base.cleanup)
        p = patch.object(temporarios, "PASTA_TEMPORARIOS", Path(self.base.name))
        p.start()
        self.addCleanup(p.stop)
        self.gerenciador = GerenciadorOperacoes(executor=executor)
        self.addCleanup(self.gerenciador.close)
        self.app = criar_app(self.gerenciador)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def esperar(self, identificador):
        prazo = time.monotonic() + 5
        while time.monotonic() < prazo:
            resposta = self.client.get(f"/api/operacoes/{identificador}")
            dados = resposta.get_json()
            if dados.get("estado") != "preparando":
                return dados
            time.sleep(0.01)
        self.fail("Operação não terminou no prazo de teste")

    def consulta(self):
        resposta = self.client.post("/api/formats", json={"url": URL})
        self.assertEqual(resposta.status_code, 202)
        return self.esperar(resposta.get_json()["id"])["resultado"]["consulta"]

    def preparar(self):
        resposta = self.client.post("/api/download", json={
            "url": URL, "tipo": "video", "format_id": "137", "consulta": self.consulta()})
        self.assertEqual(resposta.status_code, 202)
        return self.esperar(resposta.get_json()["id"])

    def test_transferencia_nativa_e_limpeza_apos_fechar(self):
        pronto = self.preparar()
        self.assertEqual(pronto["estado"], "pronto")
        resposta = self.client.get(pronto["resultado"]["arquivo_url"], buffered=False)
        try:
            self.assertEqual(resposta.status_code, 200)
            self.assertEqual(int(resposta.headers["Content-Length"]), len(CONTEUDO))
            self.assertIn("attachment", resposta.headers["Content-Disposition"])
            self.assertIn("filename*=UTF-8", resposta.headers["Content-Disposition"])
            self.assertEqual(resposta.get_data(), CONTEUDO)
        finally:
            resposta.close()
        self.assertEqual(list(Path(self.base.name).iterdir()), [])
        self.assertEqual(self.esperar(pronto["id"])["estado"], "concluido")

    def test_desconexao_sem_consumir_corpo_remove_temporarios(self):
        pronto = self.preparar()
        resposta = self.client.get(pronto["resultado"]["arquivo_url"], buffered=False)
        self.assertEqual(resposta.status_code, 200)
        resposta.close()
        self.assertEqual(list(Path(self.base.name).iterdir()), [])

    def test_url_diferente_mesmo_formato_e_recusada(self):
        resposta = self.client.post("/api/download", json={
            "url": "https://youtu.be/aqz-KE-bpKQ", "tipo": "video", "format_id": "137", "consulta": self.consulta()})
        self.assertEqual(resposta.status_code, 409)
        self.assertEqual(resposta.get_json()["codigo"], "CONSULTA_DIFERENTE")

    def test_tipo_e_formato_devem_pertencer_a_consulta(self):
        resposta = self.client.post("/api/download", json={
            "url": URL, "tipo": "video", "format_id": "251", "consulta": self.consulta()})
        self.assertEqual(resposta.status_code, 409)

    def test_consulta_alterada_e_invalida_sao_recusadas(self):
        for consulta in ["adulterada", [], None]:
            resposta = self.client.post("/api/download", json={
                "url": URL, "tipo": "video", "format_id": "137", "consulta": consulta})
            self.assertIn(resposta.status_code, (400, 409))

    def test_consulta_expirada_e_recusada(self):
        consulta = self.consulta()
        with patch("itsdangerous.timed.time.time", return_value=time.time() + 1000):
            resposta = self.client.post("/api/download", json={
                "url": URL, "tipo": "video", "format_id": "137", "consulta": consulta})
        self.assertEqual(resposta.status_code, 409)

    def test_arquivo_nao_retirado_expira_e_e_removido(self):
        pronto = self.preparar()
        with self.gerenciador.lock:
            self.gerenciador.obter(pronto["id"]).concluida_em -= 301
        self.gerenciador.limpar()
        self.assertEqual(list(Path(self.base.name).iterdir()), [])
        self.assertEqual(self.client.get(pronto["resultado"]["arquivo_url"]).status_code, 404)

    def test_expiracao_nao_remove_envio_ativo(self):
        pronto = self.preparar()
        resposta = self.client.get(pronto["resultado"]["arquivo_url"], buffered=False)
        try:
            self.gerenciador.obter(pronto["id"]).concluida_em -= 1000
            self.gerenciador.limpar()
            self.assertTrue(self.gerenciador.obter(pronto["id"]).temporario.pasta.exists())
        finally:
            resposta.close()
        self.assertEqual(list(Path(self.base.name).iterdir()), [])

    def test_cancelar_arquivo_pronto_limpa(self):
        pronto = self.preparar()
        self.assertEqual(self.client.delete(f'/api/operacoes/{pronto["id"]}').status_code, 202)
        self.assertEqual(list(Path(self.base.name).iterdir()), [])

    def test_download_nao_pode_ser_enviado_duas_vezes(self):
        pronto = self.preparar()
        resposta = self.client.get(pronto["resultado"]["arquivo_url"])
        resposta.close()
        self.assertEqual(self.client.get(pronto["resultado"]["arquivo_url"]).status_code, 409)

    def test_erro_de_envio_tambem_limpa(self):
        pronto = self.preparar()
        with patch("app.send_file", side_effect=OSError("erro privado de teste")):
            resposta = self.client.get(pronto["resultado"]["arquivo_url"])
        self.assertEqual(resposta.status_code, 500)
        self.assertNotIn("erro privado", str(resposta.get_json()))
        self.assertIn("referencia", resposta.get_json())
        self.assertEqual(list(Path(self.base.name).iterdir()), [])

    def test_json_urls_e_metodos_invalidos_retornam_json(self):
        for payload in [["valor"], None, {"url": "https://example.com"}, {"url": []}]:
            self.assertEqual(self.client.post("/api/formats", json=payload).status_code, 400)
        for rota in ["/api/nao-existe", "/api/formats"]:
            resposta = self.client.get(rota)
            self.assertTrue(resposta.is_json)
        self.assertEqual(self.client.post("/api/formats", data="x" * 17000).status_code, 413)

    def test_cache_e_cors(self):
        resposta = self.client.options("/api/operacoes/teste", headers={
            "Origin": "http://127.0.0.1:5500", "Access-Control-Request-Method": "DELETE"})
        self.assertEqual(resposta.headers["Access-Control-Allow-Origin"], "http://127.0.0.1:5500")
        self.assertEqual(resposta.headers["Cache-Control"], "no-store")
        self.assertEqual(self.client.get("/").get_json()["versao_api"], 2)

    def test_limite_de_concorrencia_e_cancelamento(self):
        def esperando(tarefa, dados, temporario, limite, cancelamento):
            (temporario.pasta / "parcial.part").write_bytes(b"parcial")
            cancelamento.wait(5)
            raise FalhaAplicacao("CANCELADO", "Operação cancelada.", 409)
        self.gerenciador.executor = esperando
        ids = [self.client.post("/api/formats", json={"url": URL}).get_json()["id"] for _ in range(2)]
        self.assertEqual(self.client.post("/api/formats", json={"url": URL}).status_code, 429)
        for identificador in ids:
            self.client.delete(f"/api/operacoes/{identificador}")
            self.assertEqual(self.esperar(identificador)["estado"], "cancelado")
        self.assertEqual(list(Path(self.base.name).iterdir()), [])

    def test_erro_no_worker_preserva_codigo_referencia_e_limpa(self):
        def falha(*args):
            raise FalhaAplicacao("TEMPO_ESGOTADO", "O tempo do servidor terminou.", 504)
        self.gerenciador.executor = falha
        identificador = self.client.post("/api/formats", json={"url": URL}).get_json()["id"]
        estado = self.esperar(identificador)
        self.assertEqual((estado["estado"], estado["codigo"], estado["status"]), ("erro", "TEMPO_ESGOTADO", 504))
        self.assertIn("referencia", estado)
        self.assertEqual(list(Path(self.base.name).iterdir()), [])
