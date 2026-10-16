const link = document.getElementById("linkyoutube");
const enviar = document.getElementById("botaoEnviar");
const mensagemErro = document.getElementById("mensagemErro");
const opcoes = document.getElementById("opcoes");
const botaoAudio = document.getElementById("botaoAudio");
const botaoVideo = document.getElementById("botaoVideo");
const opcoesFormato = document.getElementById("opcoesFormato");
const botaoVoltar = document.getElementById("botaoVoltar");

const enderecoPagina = window.location;
const frontendLocalSeparado = enderecoPagina &&
    ["localhost", "127.0.0.1"].includes(enderecoPagina.hostname) &&
    ["5500", "8000"].includes(enderecoPagina.port);
const API_BASE = window.TUBEYOU_API_BASE || (frontendLocalSeparado ?
    `${enderecoPagina.protocol}//${enderecoPagina.hostname}:5000` :
    enderecoPagina?.origin || "http://127.0.0.1:5000");
let operacaoAtual = null;
let consultaAtual = null;
let arquivoPronto = null;
let salvamentoAtual = null;
let geracao = 0;

function endpoint(caminho) {
    return new URL(caminho, API_BASE).href;
}

function linkdetect(valor) {
    try {
        const url = new URL(valor.trim());
        return ["http:", "https:"].includes(url.protocol) &&
            ["youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"].includes(url.hostname) &&
            !url.username && !url.password;
    } catch {
        return false;
    }
}

function definirOcupado(ocupado) {
    for (const elemento of [link, enviar, botaoAudio, botaoVideo, botaoVoltar]) {
        elemento.disabled = ocupado;
    }
}

function exibirMensagem(texto, erro = false) {
    opcoesFormato.replaceChildren();
    opcoesFormato.classList.add("visivel");
    const mensagem = document.createElement("span");
    mensagem.textContent = texto;
    mensagem.style.color = erro ? "#b00020" : "";
    mensagem.setAttribute("role", erro ? "alert" : "status");
    opcoesFormato.appendChild(mensagem);
    return mensagem;
}

function mensagemDoErro(erro) {
    if (erro.name === "TimeoutError" || erro.name === "AbortError") {
        return "O servidor demorou a responder. Verifique a conexão e tente novamente.";
    }
    if (erro instanceof TypeError) {
        return "Não foi possível conectar ao servidor do TubeYou. Confirme que o backend está aberto.";
    }
    return erro.message || "Não foi possível concluir a operação.";
}

async function jsonDaResposta(resposta) {
    let dados;
    try {
        dados = await resposta.json();
    } catch {
        throw new Error("O servidor devolveu uma resposta inesperada. Reinicie o backend e atualize a página.");
    }
    if (!resposta.ok) {
        throw new Error((dados.erro || "Falha na comunicação com o servidor.") +
            (dados.referencia ? ` Referência: ${dados.referencia}.` : ""));
    }
    return dados;
}

async function cancelarNoServidor(operacao) {
    if (!operacao.id) return;
    await fetch(endpoint(`/api/operacoes/${operacao.id}`), {
        method: "DELETE", keepalive: true, signal: AbortSignal.timeout(10000)
    });
}

function liberarArquivoPronto() {
    if (arquivoPronto) {
        void cancelarNoServidor(arquivoPronto).catch(console.error);
        arquivoPronto = null;
    }
}

async function executarTarefa(caminho, dados, texto) {
    const operacao = { id: null, cancelada: false };
    operacaoAtual = operacao;
    definirOcupado(true);
    const mensagem = exibirMensagem(texto);
    const cancelar = document.createElement("button");
    cancelar.classList.add("botao_formato");
    cancelar.textContent = "Cancelar";
    cancelar.addEventListener("click", () => {
        operacao.cancelada = true;
        cancelar.disabled = true;
        mensagem.textContent = "Cancelando e removendo os temporários...";
        void cancelarNoServidor(operacao).catch(console.error);
    });
    opcoesFormato.appendChild(cancelar);
    try {
        let estado = await jsonDaResposta(await fetch(endpoint(caminho), {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify(dados), signal: AbortSignal.timeout(15000)
        }));
        if (!estado.id) {
            throw new Error("Reinicie o backend do TubeYou e atualize a página para usar a nova versão.");
        }
        operacao.id = estado.id;
        if (operacao.cancelada) await cancelarNoServidor(operacao);
        // O servidor aplica 90/600 segundos; esta margem cobre as respostas de rede.
        const prazo = Date.now() + (estado.limite_segundos + 30) * 1000;
        while (true) {
            if (estado.estado === "pronto") {
                if (operacao.cancelada) throw new Error("Operação cancelada.");
                if (!estado.resultado || typeof estado.resultado !== "object" || Array.isArray(estado.resultado)) {
                    throw new Error("O servidor devolveu um resultado incompatível. Atualize a página e tente novamente.");
                }
                return { id: operacao.id, ...estado.resultado };
            }
            if (["erro", "cancelado", "expirado"].includes(estado.estado)) {
                throw new Error((estado.erro || "A operação foi cancelada ou expirou.") +
                    (estado.referencia ? ` Referência: ${estado.referencia}.` : ""));
            }
            if (Date.now() >= prazo) {
                throw new Error("O tempo de espera terminou. O servidor recebeu o pedido de cancelamento.");
            }
            await new Promise(resolve => setTimeout(resolve, 750));
            estado = await jsonDaResposta(await fetch(endpoint(`/api/operacoes/${operacao.id}`), {
                cache: "no-store", signal: AbortSignal.timeout(10000)
            }));
        }
    } catch (erro) {
        await cancelarNoServidor(operacao).catch(console.error);
        throw erro;
    } finally {
        if (operacaoAtual === operacao) operacaoAtual = null;
        definirOcupado(false);
    }
}

function invalidarConsulta() {
    geracao += 1;
    consultaAtual = null;
    liberarArquivoPronto();
    opcoesFormato.replaceChildren();
    opcoesFormato.classList.remove("visivel");
}

link.addEventListener("input", () => {
    invalidarConsulta();
    enviar.classList.toggle("inativo", !linkdetect(link.value));
    mensagemErro.classList.remove("visivel");
});

enviar.addEventListener("click", () => {
    if (!linkdetect(link.value)) {
        mensagemErro.classList.add("visivel");
        return;
    }
    invalidarConsulta();
    mensagemErro.classList.remove("visivel");
    opcoes.classList.add("visivel");
    enviar.classList.add("saindo");
    botaoVoltar.classList.add("visivel");
});

async function buscarFormatos(tipo) {
    if (operacaoAtual || salvamentoAtual) return;
    invalidarConsulta();
    const versao = geracao;
    const url = link.value.trim();
    if (!linkdetect(url)) {
        exibirMensagem("Informe um link válido de um vídeo do YouTube.", true);
        return;
    }
    try {
        const dados = await executarTarefa("/api/formats", { url }, "Consultando os formatos...");
        if (geracao !== versao || link.value.trim() !== url) return;
        if (!Array.isArray(dados.video) || !Array.isArray(dados.audio) || typeof dados.consulta !== "string") {
            throw new Error("A resposta de formatos é incompatível com esta página. Atualize a página e consulte novamente.");
        }
        consultaAtual = { url, tipo, token: dados.consulta, geracao: versao };
        opcoesFormato.replaceChildren();
        if (!dados[tipo]?.length) {
            exibirMensagem(`Nenhum formato de ${tipo === "video" ? "vídeo" : "áudio"} encontrado.`, true);
            return;
        }
        const consulta = consultaAtual;
        for (const formato of dados[tipo]) {
            const botao = document.createElement("button");
            botao.classList.add("botao_formato");
            botao.textContent = tipo === "video" ? `${formato.altura}p • ${formato.ext}` :
                `${formato.bitrate} kbps • ${formato.ext}`;
            botao.addEventListener("click", () => baixar(formato.format_id, consulta));
            opcoesFormato.appendChild(botao);
        }
    } catch (erro) {
        console.error(erro);
        if (geracao === versao) exibirMensagem(mensagemDoErro(erro), true);
    }
}

async function baixar(formatId, consulta) {
    if (operacaoAtual || salvamentoAtual) return;
    if (consultaAtual !== consulta || consulta.geracao !== geracao || link.value.trim() !== consulta.url) {
        invalidarConsulta();
        exibirMensagem("O link mudou. Consulte os formatos novamente.", true);
        return;
    }
    liberarArquivoPronto();
    try {
        const arquivo = await executarTarefa("/api/download", {
            url: consulta.url, consulta: consulta.token, tipo: consulta.tipo, format_id: formatId
        }, "Preparando o arquivo de vídeo ou áudio...");
        if (consulta.geracao !== geracao || link.value.trim() !== consulta.url) {
            await cancelarNoServidor(arquivo);
            return;
        }
        oferecerSalvamento(arquivo);
    } catch (erro) {
        console.error(erro);
        exibirMensagem(mensagemDoErro(erro), true);
    }
}

function oferecerSalvamento(arquivo) {
    arquivoPronto = arquivo;
    const podeEscolherLocal = typeof window.showSaveFilePicker === "function";
    const mensagem = exibirMensagem(podeEscolherLocal ?
        "Arquivo pronto. Escolha onde salvar:" : "Arquivo pronto. Clique para baixar:");
    const expiraEm = Date.now() + arquivo.validade_segundos * 1000;
    let validade;

    function agendarExpiracao() {
        clearTimeout(validade);
        if (arquivoPronto !== arquivo) return;
        validade = setTimeout(() => {
            if (arquivoPronto !== arquivo) return;
            liberarArquivoPronto();
            exibirMensagem("O arquivo preparado expirou. Selecione áudio ou vídeo para preparar novamente.", true);
        }, Math.max(0, expiraEm - Date.now()));
    }

    const salvarNoNavegador = document.createElement("a");
    salvarNoNavegador.href = endpoint(arquivo.arquivo_url);
    salvarNoNavegador.textContent = podeEscolherLocal ? "Usar download do navegador" : "Salvar arquivo";
    salvarNoNavegador.classList.add("botao_formato", "salvar_arquivo");
    salvarNoNavegador.download = arquivo.nome;
    salvarNoNavegador.addEventListener("click", evento => {
        if (arquivoPronto !== arquivo || salvamentoAtual) {
            evento.preventDefault();
            return;
        }
        arquivoPronto = null;
        clearTimeout(validade);
        mensagem.textContent = "Transferência entregue ao navegador. A pasta e a janela de salvamento seguem as configurações dele.";
        setTimeout(() => {
            salvarNoNavegador.remove();
            escolher?.remove();
            orientacao?.remove();
        }, 0);
    });

    let escolher = null;
    let orientacao = null;
    if (podeEscolherLocal) {
        escolher = document.createElement("button");
        escolher.textContent = "Escolher local e salvar";
        escolher.classList.add("botao_formato");
        escolher.addEventListener("click", async () => {
            if (arquivoPronto !== arquivo || salvamentoAtual) return;
            clearTimeout(validade);
            const controlador = new AbortController();
            salvamentoAtual = { controlador };
            definirOcupado(true);
            escolher.disabled = true;
            let gravador = null;
            let fechado = false;
            let transferenciaIniciada = false;
            const cancelar = document.createElement("button");
            cancelar.classList.add("botao_formato");
            cancelar.textContent = "Cancelar transferência";
            cancelar.addEventListener("click", () => {
                controlador.abort();
                cancelar.disabled = true;
                mensagem.textContent = "Cancelando o salvamento...";
            });
            try {
                // O seletor deve abrir no clique, antes de qualquer espera de rede.
                const destino = await window.showSaveFilePicker({
                    suggestedName: arquivo.nome, id: "tubeyou", startIn: "downloads"
                });
                controlador.signal.throwIfAborted();
                gravador = await destino.createWritable();
                controlador.signal.throwIfAborted();
                arquivoPronto = null;
                transferenciaIniciada = true;
                opcoesFormato.appendChild(cancelar);
                mensagem.textContent = "Salvando no local escolhido...";
                const resposta = await fetch(endpoint(arquivo.arquivo_url), { signal: controlador.signal });
                if (!resposta.ok) await jsonDaResposta(resposta);
                if (!resposta.body) throw new Error("O navegador não conseguiu iniciar a transferência. Prepare o arquivo novamente.");
                const leitor = resposta.body.getReader();
                let recebidos = 0;
                try {
                    while (true) {
                        const { done, value } = await leitor.read();
                        if (done) break;
                        controlador.signal.throwIfAborted();
                        await gravador.write(value);
                        recebidos += value.byteLength;
                        const progresso = Math.min(100, Math.floor(recebidos * 100 / arquivo.tamanho));
                        mensagem.textContent = `Salvando no local escolhido... ${progresso}%`;
                    }
                } finally {
                    leitor.releaseLock();
                }
                controlador.signal.throwIfAborted();
                if (recebidos !== arquivo.tamanho) {
                    throw new Error("A transferência ficou incompleta. Prepare o download novamente.");
                }
                await gravador.close();
                fechado = true;
                mensagem.textContent = `Arquivo salvo: ${destino.name || arquivo.nome}.`;
                escolher.remove();
                salvarNoNavegador.remove();
            } catch (erro) {
                if (erro.name === "AbortError") {
                    mensagem.textContent = transferenciaIniciada ?
                        "Transferência cancelada. Selecione áudio ou vídeo para preparar novamente." :
                        "Local não escolhido. Clique em salvar quando quiser tentar novamente.";
                } else {
                    console.error(erro);
                    mensagem.textContent = transferenciaIniciada ? mensagemDoErro(erro) :
                        "Não foi possível abrir ou gravar no local escolhido. Tente outro local ou use o download do navegador.";
                    mensagem.style.color = "#b00020";
                }
                if (transferenciaIniciada) {
                    escolher.remove();
                    salvarNoNavegador.remove();
                }
            } finally {
                controlador.abort();
                if (gravador && !fechado) await gravador.abort().catch(console.error);
                cancelar.remove();
                salvamentoAtual = null;
                definirOcupado(false);
                escolher.disabled = false;
                agendarExpiracao();
            }
        });
        opcoesFormato.appendChild(escolher);
    } else {
        orientacao = document.createElement("span");
        orientacao.textContent = "Para escolher a pasta, ative a opção de perguntar onde salvar os arquivos no seu navegador.";
        opcoesFormato.appendChild(orientacao);
    }
    opcoesFormato.appendChild(salvarNoNavegador);
    agendarExpiracao();
}

botaoVideo.addEventListener("click", () => buscarFormatos("video"));
botaoAudio.addEventListener("click", () => buscarFormatos("audio"));
botaoVoltar.addEventListener("click", () => {
    invalidarConsulta();
    opcoes.classList.remove("visivel");
    enviar.classList.remove("saindo");
    botaoVoltar.classList.remove("visivel");
    mensagemErro.classList.remove("visivel");
    link.value = "";
    enviar.classList.add("inativo");
});

window.addEventListener("pagehide", () => {
    salvamentoAtual?.controlador.abort();
    if (operacaoAtual) void cancelarNoServidor(operacaoAtual).catch(() => {});
    if (arquivoPronto) void cancelarNoServidor(arquivoPronto).catch(() => {});
});
