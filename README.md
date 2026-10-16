# TubeYou

Site para consultar formatos de um vídeo do YouTube e baixar vídeo com áudio ou
somente áudio. A interface usa HTML/CSS/JavaScript; o servidor local usa Flask,
yt-dlp e FFmpeg. Não há conversão automática de áudio para MP3.

## Teste público gratuito com seu PC ligado

O GitHub guarda o código e executa os testes; o backend roda no seu computador.
Um Cloudflare Quick Tunnel fornece um endereço temporário HTTPS, sem conta ou
domínio. Este modo é para demonstração e testes com um grupo pequeno.

Depois de preparar o ambiente e instalar `backend/requirements.txt`, execute na raiz:

```powershell
.\iniciar-publico.ps1
```

O comando baixa o `cloudflared` portátil do repositório oficial, verifica o SHA-256,
inicia o servidor Waitress em `127.0.0.1:5510` e abre o túnel. Ele mostra um link
`https://...trycloudflare.com` que pode ser compartilhado. Não é preciso mudar os
servidores locais das portas 5000/5500. O site público usa a API no mesmo endereço,
sem apontar para o localhost de quem visita.

Para encerrar imediatamente o acesso público:

```powershell
.\parar-publico.ps1
```

Mantenha o PC ligado, conectado à internet e sem suspender enquanto o teste estiver
disponível. Fechar o PowerShell que lançou o teste não encerra os processos ocultos;
use o comando de parada acima. O link muda em uma nova sessão. Os arquivos de sessão,
logs e executáveis ficam em `.runtime/` e `.tools/`, ignorados pelo Git.

O modo público atende uma preparação por vez, limita vídeos a 10 minutos, downloads
a 100 MiB e preparações/consultas a 12 solicitações por minuto no total. A preparação
tem prazo de 5 minutos; arquivos prontos expiram em 3 minutos. Ele expõe somente a
interface e a API, sem servir os diretórios de código, ambiente Python ou logs.
O custo de internet/energia é do computador que hospeda; visitantes não pagam ao site.

Quick Tunnels não têm garantia de disponibilidade e não substituem hospedagem de
produção. [Documentação oficial](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).

## Preparação no Windows

Instale Python 3.14, FFmpeg com FFprobe e Deno. Os três executáveis externos devem
estar no PATH. Na pasta raiz do TubeYou, abra o PowerShell:

```powershell
py -3.14 -m venv backend\venv
.\backend\venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\backend\venv\Scripts\python.exe -m pip check
ffmpeg -version
ffprobe -version
deno --version
```

O ambiente padrão é somente `backend\venv`; não crie um segundo `.venv`.
Se ele já existe e funciona, não é preciso recriá-lo. Para atualizações das
dependências, instale novamente o requirements usando o Python desse ambiente.

## Iniciar

Abra dois PowerShell na raiz do TubeYou. No primeiro:

```powershell
.\backend\venv\Scripts\python.exe backend\app.py
```

No segundo:

```powershell
.\backend\venv\Scripts\python.exe -m http.server 5500 --bind 127.0.0.1
```

Abra http://127.0.0.1:5500. Não abra `index.html` diretamente como arquivo.
Para encerrar, use Ctrl+C em cada terminal. Depois de atualizar o código, reinicie
o backend e atualize a página com Ctrl+F5; a API atual é a versão 2.

## Usar

1. Cole o link de um vídeo individual e clique em ENVIAR.
2. Selecione VÍDEO ou ÁUDIO e depois a qualidade/formato.
3. Aguarde a preparação. É possível cancelar durante essa etapa.
4. Quando aparecer **Escolher local e salvar**, clique, escolha a pasta/nome e
   confirme. A transferência grava o arquivo em partes no destino escolhido e a
   tela confirma o salvamento somente ao terminar.

O seletor de local precisa de suporte do navegador e abre em um clique do usuário,
depois da preparação. Se ele não estiver disponível, aparece **Salvar arquivo**;
também existe a alternativa **Usar download do navegador**. Nesse modo, a pasta e
a janela de salvamento dependem da configuração do navegador. Para perguntar a
pasta em cada download, habilite essa preferência no navegador. O site não altera
as preferências do navegador nem escolhe uma pasta no computador sem sua ação.

Nenhum dos modos carrega o vídeo inteiro em um blob na memória. O salvamento com
seletor mostra progresso, permite cancelar e confere o total de bytes antes de
confirmar a conclusão. Fechar o seletor sem escolher local não consome o arquivo
preparado; é possível tentar novamente dentro do prazo de validade.

Alterar o link invalida os formatos antigos. A consulta assinada pelo servidor
também vincula URL, tipo e formatos permitidos, com validade de 15 minutos.

## Limites e limpeza

- Consulta: até 90 segundos. Preparação e validação do download: até 600 segundos.
  São prazos do servidor, incluindo as etapas de yt-dlp, Deno, FFmpeg e FFprobe.
- Cada operação usa um processo separado. Prazo/cancelamento encerram sua árvore
  de processos. No Windows, Job Objects também protegem contra queda do servidor.
  Em sistemas POSIX, o encerramento normal usa grupos de processos; uma hospedagem
  Linux deverá também garantir o encerramento de todo o serviço/container ao cair.
- Até duas preparações/consultas simultâneas e no máximo 20 registros em memória.
  Atingir o limite retorna uma mensagem de servidor ocupado.
- Arquivos preparados e não retirados expiram em cinco minutos. Estados de
  operações concluídas/erros expiram após um minuto.
- A transferência é de uso único: fechar/concluir o envio remove o trabalho.
  Para repetir uma transferência interrompida, prepare o arquivo novamente.
- Os temporários ficam em `%TEMP%\tubeyou\job_*`. Uma manutenção periódica remove
  operações expiradas e resíduos abandonados; bloqueios protegem trabalhos ativos.
  Um download já entregue ao navegador deve ser cancelado pelo próprio navegador.
- Os prazos de 90/600 segundos são de consulta/preparação; o tempo da transferência
  final depende da conexão do navegador. Não há retomada por intervalos (Range).
- Atualizar/fechar a página solicita cancelamento da preparação em andamento.
  Se esse aviso não chegar ao servidor, o prazo continua valendo e o arquivo
  preparado expira automaticamente.

Transmissões ainda ao vivo, canais e playlists não são aceitos como downloads de
vídeo individual. A disponibilidade depende também das condições de acesso do
YouTube; as versões de yt-dlp/EJS podem precisar de atualização conjunta.

## Erros e diagnóstico

A tela informa causas como vídeo indisponível/privado, formato removido, conexão,
recusa/limite do YouTube, dependência ausente, cancelamento e prazo atingido.
Erros de operações têm uma referência curta para localizar o registro técnico.

Ao iniciar por `backend/app.py`, os detalhes e avisos aparecem no terminal e em
`backend/logs/tubeyou.log`, com rotação: um arquivo de até 1 MiB e dois históricos.
Os logs são locais e ignorados pelo Git; não são enviados ao navegador.

## Estrutura

- `backend/app.py`: API, validação da consulta e entrega do arquivo.
- `backend/midia.py`: extração de formatos, combinação e validação da mídia.
- `backend/operacoes.py`: operações, concorrência, expiração e limpeza.
- `backend/processos.py`: limites/cancelamento da árvore de processos.
- `backend/worker.py`: execução isolada de cada consulta/preparação.
- `backend/erros.py`: mensagens públicas e classificação das falhas.
- `backend/temporarios.py`: pastas e bloqueios dos temporários.
- `script.js`: estado da interface, consulta, cancelamento e salvamento nativo.

## Testes

```powershell
.\backend\venv\Scripts\python.exe -B -m unittest discover -s backend -p "test_*.py" -v
node --test tests\frontend.test.cjs
.\backend\venv\Scripts\python.exe -m pip check
```

O teste da interface usa Node.js 20 ou superior, sem pacotes npm. Os testes automatizados não
acessam o YouTube: usam mídia curta gerada por FFmpeg, FFprobe, o seletor real do
yt-dlp, um servidor de mídia local e processos reais para conferir encerramento.
Os testes específicos de Job Objects são executados no Windows.

## GitHub e hospedagem contínua

O GitHub pode guardar o código e executar testes/publicação por Actions. GitHub
Pages hospeda arquivos estáticos e não executa Python; o processamento dos downloads
precisa de um backend separado. Actions têm execuções limitadas e não substituem um
servidor permanente de downloads para visitantes.

O teste público deste projeto já serve a interface e API no mesmo endereço. Para
uma futura hospedagem com a interface separada, configure `window.TUBEYOU_API_BASE` com a URL HTTPS
do backend, antes de carregar `script.js`, e configure `TUBEYOU_ALLOWED_ORIGINS`
no servidor com a origem exata da interface. Localmente, a interface usa
`http://127.0.0.1:5000` e as portas 5500/8000 são permitidas por padrão.

O gerenciador atual guarda operações em memória. Uma publicação inicial deverá
usar um único processo de servidor com suporte a threads e iniciar/encerrar sua
manutenção. Múltiplos processos/instâncias exigirão um registro compartilhado de
operações e arquivos. O servidor público incluído já usa um único processo Waitress
com threads e manutenção. Não publique a página apontando para o localhost do visitante.

Fontes: [GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site)
e [limites de Actions](https://docs.github.com/en/actions/reference/limits).

## Cache da interface durante manutenção

O index.html referencia script.js com uma versão igual aos primeiros 12 caracteres
do SHA-256 do arquivo. Ao alterar o JavaScript, atualize também essa versão no HTML.
O teste da interface verifica a correspondência para evitar páginas antigas usando
contratos incompatíveis com o backend. Depois da alteração, recarregue a página.
