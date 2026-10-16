"""Consulta, seleção e preparação de mídia; executadas em um processo limitado."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import yt_dlp

from erros import FalhaAplicacao, LoggerYTDLP


def opcoes_base():
    return {"quiet": True, "noprogress": True, "no_warnings": False,
            "noplaylist": True, "socket_timeout": 15, "retries": 2,
            "fragment_retries": 2, "extractor_retries": 1,
            "cachedir": False, "logger": LoggerYTDLP()}


def obter_info(url):
    with yt_dlp.YoutubeDL(opcoes_base()) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info or info.get("_type") in ("playlist", "multi_video") or "entries" in info:
        raise FalhaAplicacao("LINK_NAO_E_VIDEO", "Use o link de um vídeo individual, em vez de um canal ou playlist.")
    if info.get("is_live"):
        raise FalhaAplicacao("TRANSMISSAO_AO_VIVO", "Aguarde o término da transmissão ao vivo para baixar o vídeo.")
    limite_duracao = int(os.getenv("TUBEYOU_MAX_DURATION", "0"))
    if limite_duracao and (info.get("duration") or 0) > limite_duracao:
        raise FalhaAplicacao("VIDEO_LONGO", f"Este teste público aceita vídeos de até {limite_duracao // 60} minutos.")
    return info


def obter_formatos(url):
    info = obter_info(url)
    videos, audios = {}, {}
    for formato in info.get("formats", []):
        identificador = formato.get("format_id")
        vcodec, acodec = formato.get("vcodec"), formato.get("acodec")
        altura, bitrate = formato.get("height"), formato.get("abr")
        if vcodec not in (None, "none") and altura and identificador:
            candidato = {"format_id": str(identificador), "altura": int(altura),
                         "ext": formato.get("ext"), "tem_audio": acodec not in (None, "none"),
                         "fps": formato.get("fps")}
            def score(item):
                return (item["tem_audio"], item["ext"] == "mp4", item["fps"] or 0)
            atual = videos.get(int(altura))
            if atual is None or score(candidato) > score(atual):
                videos[int(altura)] = candidato
        if acodec not in (None, "none") and vcodec == "none" and bitrate and identificador:
            bitrate = round(float(bitrate))
            audios.setdefault(bitrate, {"format_id": str(identificador), "bitrate": bitrate,
                                       "ext": formato.get("ext"), "acodec": acodec})
    return {"titulo": info.get("title", "Vídeo"), "duracao": info.get("duration"),
            "video": sorted(videos.values(), key=lambda f: f["altura"], reverse=True),
            "audio": sorted(audios.values(), key=lambda f: f["bitrate"], reverse=True)}


def selecionar_formato(selecionado, tipo, formatos):
    identificador = str(selecionado["format_id"])
    tem_video = selecionado.get("vcodec") not in (None, "none")
    tem_audio = selecionado.get("acodec") not in (None, "none")
    if tipo == "audio":
        if not tem_audio or tem_video:
            raise FalhaAplicacao("TIPO_INCOMPATIVEL", "Selecione um formato de áudio sem vídeo.")
        return identificador
    if not tem_video:
        raise FalhaAplicacao("TIPO_INCOMPATIVEL", "O formato selecionado não contém vídeo.")
    if tem_audio:
        return identificador
    if not any(f.get("vcodec") == "none" and f.get("acodec") not in (None, "none") for f in formatos):
        raise FalhaAplicacao("AUDIO_INDISPONIVEL", "Não há áudio disponível para combinar com este vídeo.")
    if shutil.which("ffmpeg") is None:
        raise FalhaAplicacao("FFMPEG_AUSENTE", "Instale o FFmpeg no servidor e confirme que ele está no PATH.")
    extensao = "webm" if selecionado.get("ext") == "webm" else "m4a"
    return f"{identificador}+bestaudio[ext={extensao}]/{identificador}+bestaudio"


def verificar_midia(arquivo, tipo):
    resultado = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(arquivo)],
        capture_output=True, text=True, timeout=30, check=True,
    )
    tipos = {stream["codec_type"] for stream in json.loads(resultado.stdout).get("streams", [])}
    if tipo == "video" and not {"video", "audio"}.issubset(tipos):
        raise FalhaAplicacao("MIDIA_INVALIDA", "O arquivo gerado não contém vídeo e áudio. Tente outro formato.")
    if tipo == "audio" and ("audio" not in tipos or "video" in tipos):
        raise FalhaAplicacao("MIDIA_INVALIDA", "O arquivo gerado não contém somente áudio. Tente outro formato.")


def preparar_download(dados, pasta):
    info = obter_info(dados["url"])
    formatos = info.get("formats", [])
    selecionado = next((f for f in formatos if str(f.get("format_id")) == dados["format_id"]), None)
    if selecionado is None:
        raise FalhaAplicacao("FORMATO_INDISPONIVEL", "Este formato não está mais disponível. Consulte novamente.")
    seletor = selecionar_formato(selecionado, dados["tipo"], formatos)
    if shutil.which("ffprobe") is None:
        raise FalhaAplicacao("FFPROBE_AUSENTE", "Instale o FFprobe junto do FFmpeg no servidor e confirme o PATH.")
    concluidos = []
    limite_bytes = int(os.getenv("TUBEYOU_MAX_BYTES", "0"))
    tamanhos = {}

    def verificar_tamanho(progresso):
        if not limite_bytes:
            return
        chave = progresso.get("filename") or str(progresso.get("info_dict", {}).get("format_id", "midia"))
        tamanhos[chave] = progresso.get("downloaded_bytes") or 0
        if sum(tamanhos.values()) > limite_bytes:
            raise FalhaAplicacao("ARQUIVO_GRANDE", "O arquivo excede o limite de 100 MiB deste teste público.")

    opcoes = dict(opcoes_base(), format=seletor,
                 outtmpl=str(pasta / "%(title).120B [%(id)s].%(ext)s"),
                 windowsfilenames=True, post_hooks=[concluidos.append], progress_hooks=[verificar_tamanho])
    with yt_dlp.YoutubeDL(opcoes) as ydl:
        ydl.extract_info(dados["url"], download=True)
    if len(concluidos) != 1:
        raise FalhaAplicacao("ARQUIVO_FINAL_INVALIDO", "O processamento não gerou um único arquivo final.", 500)
    arquivo = Path(concluidos[0]).resolve()
    if (arquivo.parent != pasta.resolve() or not arquivo.is_file() or arquivo.stat().st_size == 0
            or arquivo.suffix.lower() in (".part", ".ytdl", ".json")):
        raise FalhaAplicacao("ARQUIVO_FINAL_INVALIDO", "O arquivo final do download é inválido.", 500)
    verificar_midia(arquivo, dados["tipo"])
    if limite_bytes and arquivo.stat().st_size > limite_bytes:
        raise FalhaAplicacao("ARQUIVO_GRANDE", "O arquivo excede o limite de 100 MiB deste teste público.")
    return {"arquivo": arquivo.name, "tamanho": arquivo.stat().st_size}
