# Checkup do TubeYou — 16/10/2026

## Prioridades altas preservadas

- O seletor mantém o vídeo escolhido nas alternativas de combinação com áudio.
- FFprobe confirma o tipo da mídia final antes da oferta de salvamento.
- O único ambiente do projeto permanece `backend/venv`.
- O arquivo final vem do hook de conclusão do yt-dlp, nunca do maior tamanho da pasta.
- O envio fecha o arquivo antes de limpar a pasta; erros e desconexões também limpam.
- A limpeza respeita bloqueios de trabalhos ativos e recupera resíduos abandonados.

## Prioridades médias corrigidas

1. **URL/formatos:** editar o link apaga a consulta anterior. Respostas atrasadas
   são descartadas. O backend verifica uma consulta assinada que vincula URL,
   tipo e formatos, evitando misturar resultados de vídeos diferentes.
2. **Memória do navegador:** a interface consulta a preparação por JSON e oferece
   um link de salvamento direto. O arquivo não passa por `blob()`/ObjectURL.
3. **Prazo no backend:** consulta limitada a 90 segundos e preparação/validação
   a 600 segundos. Cancelamento/prazo encerram o processo isolado e sua árvore,
   incluindo auxiliares de processamento. Há limite de concorrência e expiração
   dos arquivos preparados que ninguém retirou.
4. **Arquivo final:** mantida e testada a correção anterior. Um arquivo parcial maior
   que a mídia concluída não é escolhido.
5. **Erros:** avisos do yt-dlp deixam de ser suprimidos; causas conhecidas têm códigos
   e mensagens específicas. A referência exibida na tela permite localizar detalhes
   no terminal e em logs locais com rotação. Tracebacks não são devolvidos ao cliente.

## Validação desta etapa

- 37 testes Python e 4 testes JavaScript passaram na preparação e no projeto final.
- A verificação de dependências não encontrou pacotes quebrados.
- Após a suíte final: zero pastas antigas/de testes, zero trabalhos temporários e
  zero processos FFmpeg/FFprobe/Deno restantes. Os processos preexistentes dos
  servidores locais foram preservados.
- Mídia real gerada localmente, FFmpeg/FFprobe e seletor real do yt-dlp usados nos testes.
- Verificada a junção de vídeo e Opus sem M4A e a obtenção de áudio separado.
- Verificados URL alterada, resposta atrasada, consulta assinada/adulterada/expirada,
  expiração de arquivo, desconexão, erro de envio, cancelamento e concorrência.
- Processos reais usados para conferir prazo, cancelamento e encerramento de filho
  pelo Job Object no Windows; o protocolo do worker isolado também foi exercitado.
- Prévia em navegador, com dados locais: editar a URL removeu os formatos e o
  novo fluxo mostrou o botão Salvar arquivo. A prévia foi encerrada ao terminar.
- Nenhum novo download do YouTube foi feito nesta etapa. O teste com a URL do usuário
  fica para depois da atualização e reinício do backend.

## Ativação e próximos passos

O backend que já estava aberto mantém o código antigo na memória. Reinicie o
primeiro PowerShell e atualize a página com Ctrl+F5 para usar a API versão 2.
O comando do servidor estático, no segundo PowerShell, permanece o mesmo.

Depois: testar URLs reais com o usuário; preparar repositório, CI e hospedagem.
GitHub Pages pode publicar a interface, mas não executar o backend Python.
Os detalhes, limites e instruções de execução estão no README.

## Correção posterior: aviso incorreto de nenhum formato de vídeo

O link 96-3VUxfNKc retornava seis qualidades no backend, mas a aba executava o
JavaScript anterior à API assíncrona e interpretava a resposta inicial como lista
vazia. O comportamento foi reproduzido no navegador, incluindo o registro antigo
Usuário escolheu VIDEO e a ausência de consultas de acompanhamento da operação.

O index agora referencia o JavaScript com uma versão baseada no SHA-256 do conteúdo.
A interface também distingue resposta incompatível de uma lista válida sem vídeos.
Passaram oito testes JavaScript, incluindo consulta assíncrona e validade da versão
no HTML. A consulta real na página exibiu 144p, 240p, 360p, 480p, 720p e 1080p.
Nenhum download de mídia foi feito nesta correção. O backend versão 2 e os dois
servidores em execução foram mantidos; apenas a página foi recarregada.

## Download real e escolha do destino

Verificação com o vídeo público 96-3VUxfNKc, de aproximadamente 48 segundos:

- API completa: MP4 de 1920x1080, H.264 com AAC, 9.605.924 bytes, operação concluída.
- API completa: M4A de áudio AAC, 772.588 bytes, operação concluída.
- Fluxo pelo navegador: MP4 de 640x360, H.264 com AAC, 1.704.956 bytes.
  O navegador salvou esse arquivo em Downloads, conforme sua configuração atual.
- Todos os arquivos foram inspecionados com FFprobe. Os dois arquivos da API foram
  guardados como artefatos de validação fora da pasta do código; o arquivo do
  navegador foi preservado na pasta Downloads.
- A verificação de dependências não encontrou pacotes quebrados.

O botão Escolher local e salvar usa o seletor do navegador em uma ação do usuário,
após a preparação. O fluxo grava os bytes recebidos no arquivo escolhido, mostra
progresso e confirma sucesso apenas depois de conferir o tamanho e fechar a gravação.
Cancelar o seletor permite tentar novamente; cancelamento de transferência e dados
incompletos abortam a gravação. O navegador continua oferecendo o modo normal como
alternativa. A janela do sistema e a seleção final da pasta ficam sob controle do usuário.

Passaram 12 testes da interface no projeto final, incluindo escolha de destino,
transferência em partes, cancelamento e integridade. O backend já funcionava no
teste real e não precisou de alterações ou reinício nesta etapa.

## Preparação do teste público

O usuário escolheu hospedar temporariamente no próprio PC. Foram preparados um
servidor Waitress separado em loopback, a interface e API na mesma origem, scripts
de início/parada do Quick Tunnel e validação SHA-256 do executável oficial.
O modo público limita concorrência, duração, tamanho e solicitações. Arquivos
privados do projeto não são publicados pelo servidor. Foi adicionado um workflow
de testes no GitHub; Actions não é usado para hospedar o downloader.

Validação do teste público em 16/10/2026:

- 42 testes Python e 13 testes JavaScript passaram; dependências sem conflitos.
- Site e API responderam pelo HTTPS do Quick Tunnel.
- Downloads reais pelo HTTPS: MP4 360p com H.264/AAC (1.704.956 bytes) e M4A AAC
  (772.588 bytes), com tamanhos íntegros e operações concluídas.
- Os temporários dos downloads foram removidos após o envio.
- Início, detecção de sessão existente, parada e reinício foram conferidos.
  O comando de parada valida caminho, PID e instante de início antes de encerrar
  os processos da sessão. A comparação de datas atende tanto strings JSON quanto
  datas convertidas automaticamente pelo PowerShell.
- Os servidores locais das portas 5000/5500 continuaram respondendo após a parada.
- Executável do túnel, sessão, logs, ambiente Python e mídia não entram no Git.

O endereço temporário não é gravado no repositório, pois muda entre sessões.
