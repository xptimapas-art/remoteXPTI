# Correções do auto update — 2.1.9

## Comportamento aplicado

- O updater não troca o EXE durante o download. Usa staging separado em `%LOCALAPPDATA%\RemoteXPTI\updates`, identificado por instalação.
- Cada release exige `update-manifest.json`, com versão, protocolo, nome do EXE, tamanho e SHA-256. O download e a cópia instalada são conferidos.
- A origem de download é fixa no repositório oficial. O endpoint de seleção histórica exige sessão DEV e ignora URLs externas.
- O estado de download pronto é recuperado ao abrir novamente o app.
- Um helper PowerShell independente espera o app encerrar, mantém `RemoteXPTI.previous.exe`, instala e inicia a versão nova com ambiente independente do PyInstaller.
- A interface nova confirma a inicialização ao backend, que grava um recibo com versão real e token da tentativa. Se o processo falhar, informar uma versão diferente ou não confirmar em 90 segundos, o helper tenta restaurar o backup e abrir a versão anterior.
- Falhas do helper ficam em `result.json` no staging. Ao restaurar a versão anterior, a mensagem aparece no status do updater. O backup é mantido após sucesso, até a próxima atualização.
- O canal público usa releases estáveis, inclusive correções como `2.1.9`. Beta inclui prereleases. Na indisponibilidade da API, Atom é usado com `/latest` para confirmar o canal público.
- Em desenvolvimento, rodando `.py`, o auto update fica desabilitado e nunca altera `version.py`.
- A interface verifica os erros HTTP, exibe a mensagem nas configurações e bloqueia cliques repetidos durante instalação.

## Instalador e distribuição

O instalador exige uma pasta absoluta dedicada chamada `RemoteXPTI`. Encerra somente processos cujo executável corresponde à instalação escolhida. Preserva os demais arquivos da pasta e não sobrescreve listas de servidores ou chaves existentes. Instala o EXE por arquivo temporário e mantém backup quando já há uma instalação.

Os pacotes novos contêm apenas um template vazio de servidores. Não incluem `servers.json` de produção, `.secret.key`, `doors_config.json` ou `session.json`. Credenciais existentes continuam sendo usadas pela instalação correspondente. Instalar em uma pasta diferente não migra automaticamente dados de outra pasta ou do repositório de desenvolvimento.

`build_all.py` agora encaminha para o build moderno: instala dependências do frontend pelo lockfile, compila React, roda os testes, gera o EXE, o instalador e o manifesto. Assinatura é opcional via `REMOTEXPTI_SIGN=1`, usando certificado existente; falhas de validação impedem o build assinado. Não são criados certificados automaticamente.

Também foram removidas senhas padrão de dispositivos do código e o valor de senha do servidor de exemplo. A API local passou a rejeitar hosts e origens externas, incluindo WebSocket. Essa proteção limita comandos vindos de websites; não é uma barreira contra programas com acesso à mesma conta Windows.

## Recuperação de instalações antigas

As versões antigas podem não conseguir instalar a primeira correção. Use o novo `Setup_RemoteXPTI.exe` uma vez, apontando para a pasta da instalação que deseja atualizar. Depois abra o atalho do EXE instalado. O lançador de desenvolvimento continua executando código Python e, portanto, não recebe updates de EXE.

Uma release antiga sem manifesto ou sem confirmação de inicialização não é compatível com este protocolo. O novo updater recusa o manifesto ausente ou recupera o backup quando não recebe a confirmação. Instalações legadas devem usar o instalador, evitando baixar um EXE e apenas mudar o número da versão.

## Validação

Os 18 testes automatizados passaram. O build TypeScript/Vite passou. A dependência transitiva `source-map-js` foi atualizada para `1.2.2` no lockfile; a auditoria npm passou a informar zero vulnerabilidades. Essa versão corrige o problema de negação de serviço descrito no [aviso de segurança](https://github.com/advisories/GHSA-68fv-2mgg-jv7q).

Testes incluem versões estáveis/prerelease, assets exatos, concorrência, origem de download, manifesto inválido, arquivo incompleto/corrompido, persistência, arquivo ausente no reinício, confirmação de versão real, proteção de pasta e processos do instalador e rejeição de origem externa.

O teste de integração do helper compila executáveis de fixture e verifica a cópia e o rollback no Windows, em pasta temporária. Não aciona serviços corporativos. Uma atualização entre duas releases reais publicadas ainda precisa ser homologada em uma máquina isolada, com WebView2 e antivírus representativos dos clientes.

O build verifica Tcl antes de empacotar, para evitar um instalador sem Tkinter. Nesta máquina, Tcl era acessível fora do sandbox e não dentro dele; os pacotes finais foram recompilados no ambiente em que o runtime é acessível.

A conferência final dos pacotes `2.1.9` passou: versão embutida e SHA-256 do EXE, conteúdo da interface, helper e módulos do updater, bibliotecas Tcl/Tk do instalador, correspondência do payload e do ZIP portátil, e ausência dos arquivos locais de credenciais nos pacotes. Os artefatos finais estão em `dist/`.

## Pendências de segurança da revisão

Os novos pacotes não carregam arquivos de credenciais locais. Os arquivos locais `session.json` e `doors_config.json` foram retirados do versionamento, preservando as cópias locais. O histórico continua precisando de revisão e rotação das credenciais expostas; não foi reescrito.

A migração do cofre legado para DPAPI e a troca da autenticação DEV precisam preservar os dados existentes e estabelecer uma nova política de provisionamento. Não foi removida a chave mestre legada nesta correção, para não invalidar credenciais salvas.

As políticas reais do Supabase não foram alteradas. Antes de disponibilizar amplamente, revisar RLS/grants e autorização de escrita. A validação SHA-256 usa um manifesto obtido via HTTPS do repositório oficial; não é uma assinatura criptográfica independente do publicador. O build local sem `REMOTEXPTI_SIGN=1` gera binários sem Authenticode.
