const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const test = require("node:test");
const crypto = require("node:crypto");

class Elemento {
    constructor(tag = "div") {
        this.tagName = tag;
        this.value = "";
        this.textContent = "";
        this.children = [];
        this.style = {};
        this.listeners = {};
        const classes = new Set();
        this.classList = {
            add: (...nomes) => nomes.forEach(n => classes.add(n)),
            remove: (...nomes) => nomes.forEach(n => classes.delete(n)),
            toggle: (nome, ativo) => ativo ? classes.add(nome) : classes.delete(nome),
            contains: nome => classes.has(nome)
        };
    }
    appendChild(filho) { this.children.push(filho); filho.parent = this; return filho; }
    replaceChildren(...filhos) { this.children = filhos; }
    addEventListener(nome, funcao) { (this.listeners[nome] ||= []).push(funcao); }
    setAttribute() {}
    remove() { if (this.parent) this.parent.children = this.parent.children.filter(f => f !== this); }
    async disparar(nome) {
        const evento = { defaultPrevented: false, preventDefault() { this.defaultPrevented = true; } };
        for (const funcao of this.listeners[nome] || []) await funcao(evento);
        return evento;
    }
}

function criar(fetchPersonalizado, seletor, localizacao) {
    const ids = Object.fromEntries(["linkyoutube", "botaoEnviar", "mensagemErro", "opcoes", "botaoAudio",
        "botaoVideo", "opcoesFormato", "botaoVoltar"].map(id => [id, new Elemento()]));
    const chamadas = [];
    const formatos = { id: "consulta1", estado: "pronto", limite_segundos: 90, resultado: {
        consulta: "token", video: [{ format_id: "137", altura: 1080, ext: "mp4" }], audio: []
    }};
    const pronto = { id: "download1", estado: "pronto", limite_segundos: 600, resultado: {
        nome: "video.mp4", tamanho: 100, arquivo_url: "/api/download/download1/arquivo", validade_segundos: 300
    }};
    const responder = dados => ({ ok: true, json: async () => dados });
    const contexto = vm.createContext({
        document: { getElementById: id => ids[id], createElement: tag => new Elemento(tag) },
        window: { addEventListener() {}, ...(seletor ? { showSaveFilePicker: seletor } : {}),
                  ...(localizacao ? { location: localizacao } : {}) },
        console: { error() {} }, URL, AbortSignal, AbortController,
        fetch: async (url, opcoes = {}) => {
            chamadas.push({ url, opcoes });
            if (fetchPersonalizado) return fetchPersonalizado(url, opcoes, responder, formatos, pronto);
            return responder(url.endsWith("/api/formats") ? formatos : pronto);
        },
        setTimeout: (funcao, tempo) => tempo >= 10000 ? { unref() {} } : setTimeout(funcao, 1),
        clearTimeout, Date
    });
    vm.runInContext(fs.readFileSync(__dirname + "/../script.js", "utf8"), contexto);
    ids.linkyoutube.value = "https://www.youtube.com/watch?v=jNQXAC9IVRw";
    return { ids, chamadas, contexto };
}

test("alterar a URL apaga formatos e impede usar o botão antigo", async () => {
    const { ids, chamadas } = criar();
    await ids.botaoVideo.disparar("click");
    const botaoAntigo = ids.opcoesFormato.children[0];
    ids.linkyoutube.value = "https://youtu.be/aqz-KE-bpKQ";
    await ids.linkyoutube.disparar("input");
    assert.equal(ids.opcoesFormato.children.length, 0);
    await botaoAntigo.disparar("click");
    assert.equal(chamadas.filter(c => c.url.endsWith("/api/download")).length, 0);
});

test("download usa URL consultada e oferece link nativo sem buscar o corpo da mídia", async () => {
    const { ids, chamadas } = criar();
    await ids.botaoVideo.disparar("click");
    await ids.opcoesFormato.children[0].disparar("click");
    const download = chamadas.find(c => c.url.endsWith("/api/download"));
    assert.equal(JSON.parse(download.opcoes.body).consulta, "token");
    assert.equal(JSON.parse(download.opcoes.body).url, ids.linkyoutube.value);
    const salvar = ids.opcoesFormato.children.find(e => e.tagName === "a");
    assert.equal(salvar.href, "http://127.0.0.1:5000/api/download/download1/arquivo");
    assert.equal(salvar.download, "video.mp4");
    await salvar.disparar("click");
    assert.equal(chamadas.length, 2);
});

test("resposta antiga não repõe formatos depois de a URL mudar", async () => {
    let liberar;
    const { ids } = criar((url, opcoes, responder, formatos) =>
        new Promise(resolve => { liberar = () => resolve(responder(formatos)); }));
    const consulta = ids.botaoVideo.disparar("click");
    ids.linkyoutube.value = "https://youtu.be/aqz-KE-bpKQ";
    await ids.linkyoutube.disparar("input");
    liberar();
    await consulta;
    assert.equal(ids.opcoesFormato.children.length, 0);
});

test("erros do backend exibem causa e referência", async () => {
    const { ids } = criar((url, opcoes, responder) => responder({
        id: "id", estado: "erro", limite_segundos: 90,
        erro: "O vídeo está privado.", referencia: "abcd1234"
    }));
    await ids.botaoVideo.disparar("click");
    assert.match(ids.opcoesFormato.children[0].textContent, /privado.*abcd1234/);
    assert.equal(ids.linkyoutube.disabled, false);
});

test("consulta aguarda a operação assíncrona e apresenta os formatos reais da resposta", async () => {
    let consultas = 0;
    const { ids, chamadas } = criar((url, opcoes, responder, formatos) => {
        if (opcoes.method === "POST") {
            return responder({ id: "consulta1", estado: "preparando", limite_segundos: 90 });
        }
        consultas += 1;
        return responder(consultas === 1 ?
            { id: "consulta1", estado: "preparando", limite_segundos: 90 } : formatos);
    });
    await ids.botaoVideo.disparar("click");
    assert.equal(consultas, 2);
    assert.equal(ids.opcoesFormato.children[0].textContent, "1080p • mp4");
    assert.equal(chamadas.filter(c => c.url.endsWith("/api/operacoes/consulta1")).length, 2);
    assert.equal(ids.linkyoutube.disabled, false);
});

test("resultado incompatível não é apresentado como ausência de formatos", async () => {
    for (const resultado of [undefined, {}, { consulta: "token", audio: [] }]) {
        const { ids } = criar((url, opcoes, responder) => responder({
            id: "consulta1", estado: "pronto", limite_segundos: 90, resultado
        }));
        await ids.botaoVideo.disparar("click");
        const mensagem = ids.opcoesFormato.children[0].textContent;
        assert.match(mensagem, /incompatível/);
        assert.doesNotMatch(mensagem, /Nenhum formato/);
    }
});

test("lista válida sem vídeos continua informando ausência de formatos", async () => {
    const { ids } = criar((url, opcoes, responder) => responder({
        id: "consulta1", estado: "pronto", limite_segundos: 90,
        resultado: { consulta: "token", audio: [], video: [] }
    }));
    await ids.botaoVideo.disparar("click");
    assert.equal(ids.opcoesFormato.children[0].textContent, "Nenhum formato de vídeo encontrado.");
});

test("HTML usa uma versão do JavaScript correspondente ao conteúdo atual", () => {
    const script = fs.readFileSync(__dirname + "/../script.js");
    const versao = crypto.createHash("sha256").update(script).digest("hex").slice(0, 12);
    const html = fs.readFileSync(__dirname + "/../index.html", "utf8");
    assert.ok(html.includes(`src="script.js?v=${versao}"`),
        "Ao alterar script.js, atualize sua versão no index.html para invalidar o cache antigo.");
});

function prepararSeletor() {
    const gravacao = { blocos: [], fechamentos: 0, abortos: 0, selecoes: [] };
    const gravador = {
        write: async bloco => gravacao.blocos.push(Buffer.from(bloco)),
        close: async () => { gravacao.fechamentos += 1; },
        abort: async () => { gravacao.abortos += 1; }
    };
    const seletor = async opcoes => {
        gravacao.selecoes.push(opcoes);
        return { name: "destino.mp4", createWritable: async () => gravador };
    };
    return { gravacao, seletor };
}

function respostaMidia(tamanho) {
    let emitido = false;
    return { ok: true, body: { getReader: () => ({
        read: async () => {
            if (emitido) return { done: true };
            emitido = true;
            return { done: false, value: new Uint8Array(tamanho).fill(7) };
        },
        releaseLock() {}
    }) }};
}

test("seletor escolhe o destino antes da transferência e salva todos os bytes", async () => {
    const { gravacao, seletor } = prepararSeletor();
    const { ids, chamadas } = criar((url, opcoes, responder, formatos, pronto) => {
        if (url.endsWith("/arquivo")) {
            assert.equal(gravacao.selecoes.length, 1);
            return respostaMidia(100);
        }
        return responder(url.endsWith("/api/formats") ? formatos : pronto);
    }, seletor);
    await ids.botaoVideo.disparar("click");
    await ids.opcoesFormato.children[0].disparar("click");
    const salvar = ids.opcoesFormato.children.find(e => e.textContent === "Escolher local e salvar");
    assert.ok(salvar);
    assert.equal(chamadas.length, 2);
    await salvar.disparar("click");
    assert.equal(gravacao.selecoes[0].suggestedName, "video.mp4");
    assert.deepEqual(Buffer.concat(gravacao.blocos), Buffer.alloc(100, 7));
    assert.equal(gravacao.fechamentos, 1);
    assert.equal(gravacao.abortos, 0);
    assert.match(ids.opcoesFormato.children[0].textContent, /Arquivo salvo: destino.mp4/);
    assert.equal(ids.linkyoutube.disabled, false);
});

test("cancelar o seletor não transfere o arquivo e permite escolher novamente", async () => {
    const { ids, chamadas } = criar(null, async () => {
        const erro = new Error("cancelado");
        erro.name = "AbortError";
        throw erro;
    });
    await ids.botaoVideo.disparar("click");
    await ids.opcoesFormato.children[0].disparar("click");
    const salvar = ids.opcoesFormato.children.find(e => e.textContent === "Escolher local e salvar");
    await salvar.disparar("click");
    assert.equal(chamadas.length, 2);
    assert.match(ids.opcoesFormato.children[0].textContent, /Local não escolhido/);
    assert.equal(salvar.disabled, false);
    assert.ok(ids.opcoesFormato.children.includes(salvar));
});

test("transferência incompleta aborta a gravação em vez de confirmar um arquivo corrompido", async () => {
    const { gravacao, seletor } = prepararSeletor();
    const { ids } = criar((url, opcoes, responder, formatos, pronto) => {
        if (url.endsWith("/arquivo")) return respostaMidia(20);
        return responder(url.endsWith("/api/formats") ? formatos : pronto);
    }, seletor);
    await ids.botaoVideo.disparar("click");
    await ids.opcoesFormato.children[0].disparar("click");
    await ids.opcoesFormato.children.find(e => e.textContent === "Escolher local e salvar").disparar("click");
    assert.equal(gravacao.fechamentos, 0);
    assert.equal(gravacao.abortos, 1);
    assert.match(ids.opcoesFormato.children[0].textContent, /incompleta/);
});

test("cancelar uma transferência ativa aborta a gravação e libera a interface", async () => {
    const { gravacao, seletor } = prepararSeletor();
    let comecou;
    const inicio = new Promise(resolve => { comecou = resolve; });
    const { ids } = criar((url, opcoes, responder, formatos, pronto) => {
        if (url.endsWith("/arquivo")) return new Promise((resolve, reject) => {
            opcoes.signal.addEventListener("abort", () => {
                const erro = new Error("cancelado");
                erro.name = "AbortError";
                reject(erro);
            });
            comecou();
        });
        return responder(url.endsWith("/api/formats") ? formatos : pronto);
    }, seletor);
    await ids.botaoVideo.disparar("click");
    await ids.opcoesFormato.children[0].disparar("click");
    const transferencia = ids.opcoesFormato.children.find(e => e.textContent === "Escolher local e salvar").disparar("click");
    await inicio;
    await ids.opcoesFormato.children.find(e => e.textContent === "Cancelar transferência").disparar("click");
    await transferencia;
    assert.equal(gravacao.abortos, 1);
    assert.equal(gravacao.fechamentos, 0);
    assert.match(ids.opcoesFormato.children[0].textContent, /Transferência cancelada/);
    assert.equal(ids.linkyoutube.disabled, false);
});

test("site público usa seu próprio HTTPS para a API, sem localhost do visitante", async () => {
    const { ids, chamadas } = criar(null, null, {
        hostname: "teste.trycloudflare.com", port: "", protocol: "https:", origin: "https://teste.trycloudflare.com"
    });
    await ids.botaoVideo.disparar("click");
    assert.equal(chamadas[0].url, "https://teste.trycloudflare.com/api/formats");
});
