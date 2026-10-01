const link = document.getElementById("linkyoutube");

const enviar = document.getElementById("botaoEnviar");

const mensagemErro =
    document.getElementById("mensagemErro");

const opcoes =
    document.getElementById("opcoes");

const botaoAudio =
    document.getElementById("botaoAudio");

const botaoVideo =
    document.getElementById("botaoVideo");

const opcoesFormato =
    document.getElementById("opcoesFormato");

const botaoVoltar =
    document.getElementById("botaoVoltar");


const API_FORMATS =
    "http://127.0.0.1:5000/api/formats";

const API_DOWNLOAD =
    "http://127.0.0.1:5000/api/download";


function linkdetect(url) {

    try {

        const endereco =
            new URL(url);

        const host =
            endereco.hostname.toLowerCase();

        return (
            host === "youtube.com" ||
            host === "www.youtube.com" ||
            host === "m.youtube.com" ||
            host === "youtu.be"
        );

    } catch {

        return false;
    }
}


link.addEventListener("input", function() {

    if (linkdetect(link.value)) {

        enviar.classList.remove("inativo");

        mensagemErro.classList.remove(
            "visivel"
        );

    } else {

        enviar.classList.add("inativo");

    }

});


enviar.addEventListener(
    "click",
    function() {

        if (!linkdetect(link.value)) {

            mensagemErro.classList.add(
                "visivel"
            );

            return;
        }


        mensagemErro.classList.remove(
            "visivel"
        );


        opcoes.classList.add(
            "visivel"
        );


        enviar.classList.add(
            "saindo"
        );


        botaoVoltar.classList.add(
            "visivel"
        );


        opcoesFormato.innerHTML = "";

        opcoesFormato.classList.remove(
            "visivel"
        );

    }
);


async function buscarFormatos(tipo) {

    opcoesFormato.innerHTML = "";


    const carregando =
        document.createElement("span");

    carregando.textContent =
        "Consultando formatos...";


    opcoesFormato.appendChild(
        carregando
    );


    opcoesFormato.classList.add(
        "visivel"
    );


    try {

        const resposta =
            await fetch(
                API_FORMATS,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({
                        url: link.value
                    })
                }
            );


        const dados =
            await resposta.json();


        if (!resposta.ok) {

            throw new Error(
                dados.erro ||
                "Erro ao consultar vídeo."
            );

        }


        opcoesFormato.innerHTML = "";


        if (tipo === "video") {

            if (
                !dados.video ||
                dados.video.length === 0
            ) {

                mostrarErroFormatos(
                    "Nenhum formato de vídeo encontrado."
                );

                return;
            }


            dados.video.forEach(
                function(formato) {

                    const botao =
                        document.createElement(
                            "button"
                        );


                    botao.classList.add(
                        "botao_formato"
                    );


                    botao.textContent =
                        `${formato.altura}p • ${formato.ext}`;


                    botao.addEventListener(
                        "click",
                        function() {

                            baixar(
                                formato.format_id,
                                "video"
                            );

                        }
                    );


                    opcoesFormato.appendChild(
                        botao
                    );

                }
            );

        }


        if (tipo === "audio") {

            if (
                !dados.audio ||
                dados.audio.length === 0
            ) {

                mostrarErroFormatos(
                    "Nenhum formato de áudio encontrado."
                );

                return;
            }


            dados.audio.forEach(
                function(formato) {

                    const botao =
                        document.createElement(
                            "button"
                        );


                    botao.classList.add(
                        "botao_formato"
                    );


                    botao.textContent =
                        `${formato.bitrate} kbps • ${formato.ext}`;


                    botao.addEventListener(
                        "click",
                        function() {

                            baixar(
                                formato.format_id,
                                "audio"
                            );

                        }
                    );


                    opcoesFormato.appendChild(
                        botao
                    );

                }
            );

        }


    } catch (erro) {

        console.error(erro);

        mostrarErroFormatos(
            erro.message
        );

    }

}


async function baixar(formatId, tipo) {

    opcoesFormato.innerHTML = "";

    const mensagem = document.createElement("span");

    mensagem.textContent = "Baixando...";

    opcoesFormato.appendChild(mensagem);

    opcoesFormato.classList.add("visivel");

    try {

        const resposta = await fetch(
            API_DOWNLOAD,
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    url: link.value,
                    format_id: formatId,
                    tipo: tipo
                })
            }
        );


        if (!resposta.ok) {

            let erro;

            try {
                erro = await resposta.json();
            } catch {
                erro = {
                    erro: "Falha no download."
                };
            }

            throw new Error(
                erro.erro || "Falha no download."
            );
        }


        const arquivo = await resposta.blob();

        const urlArquivo =
            URL.createObjectURL(arquivo);


        const linkDownload =
            document.createElement("a");


        linkDownload.href =
            urlArquivo;

        linkDownload.download =
            "TubeYou-download";


        document.body.appendChild(
            linkDownload
        );


        linkDownload.click();


        linkDownload.remove();


        setTimeout(function() {

            URL.revokeObjectURL(
                urlArquivo
            );

        }, 5000);


        mensagem.textContent =
            "Download iniciado!";

    } catch (erro) {

        console.error(
            "Erro no download:",
            erro
        );

        mensagem.textContent =
            erro.message;

        mensagem.style.color =
            "red";
    }
}


function mostrarErroFormatos(mensagem) {

    opcoesFormato.innerHTML = "";


    const erro =
        document.createElement("span");


    erro.textContent =
        mensagem;


    erro.style.color =
        "red";


    opcoesFormato.appendChild(
        erro
    );

}


botaoVideo.addEventListener(
    "click",
    function() {

        console.log(
            "Usuário escolheu VIDEO"
        );

        buscarFormatos(
            "video"
        );

    }
);


botaoAudio.addEventListener(
    "click",
    function() {

        console.log(
            "Usuário escolheu AUDIO"
        );

        buscarFormatos(
            "audio"
        );

    }
);


botaoVoltar.addEventListener(
    "click",
    function() {

        opcoes.classList.remove(
            "visivel"
        );


        opcoesFormato.classList.remove(
            "visivel"
        );


        opcoesFormato.innerHTML =
            "";


        enviar.classList.remove(
            "saindo"
        );


        botaoVoltar.classList.remove(
            "visivel"
        );


        mensagemErro.classList.remove(
            "visivel"
        );


        link.value = "";


        enviar.classList.add(
            "inativo"
        );

    }
);