from pathlib import Path
from urllib.parse import urlparse
import shutil
import tempfile

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

import yt_dlp


app = Flask(__name__)

CORS(app)


def eh_link_youtube(url):

    try:

        endereco = urlparse(url)

        host = (endereco.hostname or "").lower()

        return (
            endereco.scheme in ("http", "https")
            and host in (
                "youtube.com",
                "www.youtube.com",
                "m.youtube.com",
                "youtu.be"
            )
        )

    except Exception:

        return False


def obter_info(url):

    opcoes = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True
    }

    with yt_dlp.YoutubeDL(opcoes) as ydl:

        return ydl.extract_info(
            url,
            download=False
        )


def obter_formatos(url):

    info = obter_info(url)

    formatos_video = {}
    formatos_audio = {}

    for formato in info.get("formats", []):

        format_id = formato.get("format_id")

        vcodec = formato.get("vcodec")
        acodec = formato.get("acodec")

        altura = formato.get("height")
        extensao = formato.get("ext")

        bitrate = formato.get("abr")
        fps = formato.get("fps")


        if (
            vcodec
            and vcodec != "none"
            and altura
        ):

            candidato = {
                "format_id": format_id,
                "altura": int(altura),
                "ext": extensao,
                "tem_audio": (
                    acodec
                    and acodec != "none"
                ),
                "fps": fps
            }

            atual = formatos_video.get(int(altura))

            if atual is None:

                formatos_video[int(altura)] = candidato

            else:

                candidato_score = (
                    int(candidato["tem_audio"]),
                    int(candidato["ext"] == "mp4"),
                    candidato["fps"] or 0
                )

                atual_score = (
                    int(atual["tem_audio"]),
                    int(atual["ext"] == "mp4"),
                    atual["fps"] or 0
                )

                if candidato_score > atual_score:

                    formatos_video[int(altura)] = candidato


        if (
            acodec
            and acodec != "none"
            and vcodec == "none"
            and bitrate
        ):

            bitrate = round(float(bitrate))

            candidato = {
                "format_id": format_id,
                "bitrate": bitrate,
                "ext": extensao,
                "acodec": acodec
            }

            atual = formatos_audio.get(bitrate)

            if atual is None:

                formatos_audio[bitrate] = candidato


    return {
        "titulo": info.get("title", "Vídeo"),

        "duracao": info.get("duration"),

        "video": sorted(
            formatos_video.values(),
            key=lambda x: x["altura"],
            reverse=True
        ),

        "audio": sorted(
            formatos_audio.values(),
            key=lambda x: x["bitrate"],
            reverse=True
        )
    }


@app.get("/")
def inicio():

    return {
        "status": "TubeYou backend funcionando!"
    }


@app.post("/api/formats")
def formats():

    dados = request.get_json(silent=True) or {}

    url = str(
        dados.get("url", "")
    ).strip()


    if not url:

        return jsonify({
            "erro": "URL não informada."
        }), 400


    if not eh_link_youtube(url):

        return jsonify({
            "erro": "URL inválida."
        }), 400


    try:

        return jsonify(
            obter_formatos(url)
        )

    except yt_dlp.utils.DownloadError as erro:

        print("Erro yt-dlp:", erro)

        return jsonify({
            "erro": "Não foi possível obter os formatos."
        }), 422


    except Exception as erro:

        print("Erro interno:", erro)

        return jsonify({
            "erro": "Erro interno do servidor."
        }), 500


@app.post("/api/download")
def download():

    dados = request.get_json(silent=True) or {}

    url = str(
        dados.get("url", "")
    ).strip()

    format_id = str(
        dados.get("format_id", "")
    ).strip()

    tipo = str(
        dados.get("tipo", "")
    ).strip()


    if not eh_link_youtube(url):

        return jsonify({
            "erro": "URL inválida."
        }), 400


    if not format_id:

        return jsonify({
            "erro": "Formato não informado."
        }), 400


    if tipo not in ("video", "audio"):

        return jsonify({
            "erro": "Tipo de download inválido."
        }), 400


    pasta_temp = Path(
        tempfile.mkdtemp(
            prefix="tubeyou_"
        )
    )


    try:

        info = obter_info(url)

        formatos = info.get(
            "formats",
            []
        )


        selecionado = next(
            (
                formato
                for formato in formatos
                if str(formato.get("format_id")) == format_id
            ),
            None
        )


        if selecionado is None:

            shutil.rmtree(
                pasta_temp,
                ignore_errors=True
            )

            return jsonify({
                "erro": "Formato não encontrado."
            }), 400


        if tipo == "video":

            tem_audio = (
                selecionado.get("acodec")
                and selecionado.get("acodec") != "none"
            )


            if tem_audio:

                format_selector = format_id

            else:

                format_selector = (
                    f"{format_id}+bestaudio[ext=m4a]/bestaudio"
                )


        else:

            format_selector = format_id


        opcoes = {

            "quiet": True,

            "no_warnings": True,

            "noplaylist": True,

            "format": format_selector,

            "outtmpl": str(
                pasta_temp /
                "%(title).200B [%(id)s].%(ext)s"
            ),

            "windowsfilenames": True
        }


        with yt_dlp.YoutubeDL(opcoes) as ydl:

            ydl.download([url])


        arquivos = [
            arquivo
            for arquivo in pasta_temp.iterdir()
            if arquivo.is_file()
        ]


        if not arquivos:

            raise RuntimeError(
                "Nenhum arquivo foi gerado."
            )


        arquivo_final = max(
            arquivos,
            key=lambda arquivo:
            arquivo.stat().st_size
        )


        resposta = send_file(
            arquivo_final,
            as_attachment=True,
            download_name=arquivo_final.name
        )


        @resposta.call_on_close
        def limpar():

            shutil.rmtree(
                pasta_temp,
                ignore_errors=True
            )


        return resposta


    except yt_dlp.utils.DownloadError as erro:

        print("Erro yt-dlp:", erro)

        shutil.rmtree(
            pasta_temp,
            ignore_errors=True
        )

        return jsonify({
            "erro": "O download não pôde ser realizado."
        }), 422


    except Exception as erro:

        print("Erro interno:", erro)

        shutil.rmtree(
            pasta_temp,
            ignore_errors=True
        )

        return jsonify({
            "erro": "Erro interno durante o download."
        }), 500


if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )