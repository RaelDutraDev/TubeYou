"""Erros públicos previsíveis; os detalhes técnicos ficam no log do servidor."""
import logging
import subprocess

import yt_dlp


class FalhaAplicacao(Exception):
    def __init__(self, codigo, mensagem, status=422):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.status = status

    def publico(self):
        return {"codigo": self.codigo, "erro": self.mensagem, "status": self.status}


def classificar_erro(erro):
    if isinstance(erro, FalhaAplicacao):
        return erro
    if isinstance(erro, (TimeoutError, subprocess.TimeoutExpired)):
        return FalhaAplicacao("TEMPO_ESGOTADO", "O tempo limite foi atingido. Tente novamente ou escolha uma qualidade menor.", 504)
    if isinstance(erro, yt_dlp.utils.DownloadError):
        texto = str(erro).lower()
        grupos = [
            (("private video", "members-only", "sign in", "login", "age-restricted", "confirm your age", "not a bot"),
             "ACESSO_RESTRITO", "O YouTube restringiu o acesso a este vídeo ou pediu autenticação."),
            (("not available in your country", "geo restricted", "geo-restricted"),
             "RESTRICAO_REGIONAL", "Este vídeo não está disponível na região do servidor."),
            (("requested format", "no video formats", "format is not available"),
             "FORMATO_INDISPONIVEL", "Este formato não está mais disponível. Consulte os formatos novamente."),
            (("http error 429", "too many requests"),
             "LIMITE_YOUTUBE", "O YouTube limitou as consultas. Aguarde alguns minutos antes de tentar novamente."),
            (("http error 403", "forbidden"),
             "ACESSO_NEGADO", "O YouTube recusou a transferência. Consulte os formatos novamente; se persistir, verifique o yt-dlp."),
            (("timed out", "timeout", "connection", "unable to download", "name resolution"),
             "FALHA_CONEXAO", "Não foi possível conectar ao YouTube. Verifique a conexão e tente novamente."),
            (("unavailable", "removed", "does not exist"),
             "VIDEO_INDISPONIVEL", "Este vídeo está indisponível ou foi removido do YouTube."),
        ]
        for termos, codigo, mensagem in grupos:
            if any(termo in texto for termo in termos):
                return FalhaAplicacao(codigo, mensagem)
        return FalhaAplicacao("FALHA_YOUTUBE", "O yt-dlp não conseguiu processar este vídeo. Consulte o registro da operação no servidor.")
    if isinstance(erro, OSError) and erro.errno == 28:
        return FalhaAplicacao("SEM_ESPACO", "O servidor ficou sem espaço para preparar o arquivo.", 507)
    if isinstance(erro, subprocess.SubprocessError):
        return FalhaAplicacao("FALHA_PROCESSAMENTO", "Não foi possível combinar ou validar a mídia. Tente outro formato.", 500)
    return FalhaAplicacao("ERRO_INTERNO", "O servidor não conseguiu concluir a operação. Use a referência exibida para consultar o registro.", 500)


class LoggerYTDLP:
    def debug(self, mensagem):
        # O yt-dlp envia mensagens de informação também por debug().
        if mensagem.startswith("[debug]"):
            logging.getLogger("yt_dlp").debug(mensagem)

    def warning(self, mensagem):
        logging.getLogger("yt_dlp").warning(mensagem)

    def error(self, mensagem):
        logging.getLogger("yt_dlp").error(mensagem)
