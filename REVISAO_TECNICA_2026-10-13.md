# Revisão técnica do RemoteXPTI

Data: 13/10/2026. Escopo: diagnóstico do auto update e revisão da arquitetura, distribuição, persistência e segurança do projeto local.

## Conclusão

O auto update consegue descobrir e baixar uma versão nova, mas tem bloqueios no reinício e na aplicação. Há também uma diferença essencial entre executar o código Python e executar o EXE instalado: baixar um EXE não atualiza o código Python que está em execução.

Recomendo manter Python + React + pywebview e reconstruir o subsistema de atualização e distribuição. Uma reescrita completa do produto teria custo e risco de regressão sem resolver, por si só, os problemas encontrados.

Esta revisão não alterou o código de produção. Foi gerado o build local da interface e este relatório. Nenhuma atualização foi aplicada, nenhum instalador foi executado e nenhuma configuração de nuvem foi modificada.

## Evidência nesta máquina

Os logs locais registram, em 13/10/2026:

- A aplicação em execução informava versão `2.1.7`.
- O GitHub retornou HTTP 403 por limite de requisições; o fallback Atom conseguiu continuar.
- Às 16:37, a versão `2.1.8` foi descoberta e baixada: **36.397.080 bytes**.
- O arquivo `.pending_update.exe` está no diretório do projeto, possui esse tamanho e começa com o cabeçalho `MZ`. Isso confirma a presença do download, mas não autentica o arquivo nem comprova a versão interna.
- Os logs anteriores do launcher mostram inicialização por `pythonw.exe` com `launch_modern_desktop.py`. `run_modern.bat` também inicia dessa forma. Não foi possível confirmar o processo atual por WMI, que retornou acesso negado.
- Logs históricos registram alterações de `version.py` pelo updater em modo de desenvolvimento. O código atual continua implementando esse comportamento.

Portanto, o 403 não explica sozinho a falha observada. O download aconteceu; os problemas seguintes são locais.

## Falhas do auto update

| Prioridade | Local | Problema e consequência |
|---|---|---|
| Alta | `desktop_backend.py:713` | O endpoint `/api/update/restart` usa `sys` sem importá-lo. Quando uma atualização está pronta, gera `NameError` antes de iniciar o reinício. Reproduzido isoladamente. |
| Alta | `updater.py:439` e `:458` | `import time` dentro de um ramo torna `time` variável local de toda a função. Se esse ramo não for executado, `time.sleep` gera `UnboundLocalError`. Reproduzido no caminho frozen em que a troca não é necessária. O caminho de desenvolvimento também pode alcançar o erro. |
| Alta | `updater.py:462` | Em modo Python, o updater altera `CURRENT_VERSION` e reinicia o mesmo script, sem instalar código novo. A interface pode anunciar uma versão que não corresponde ao código. |
| Alta | `updater.py:32` | O canal público aceita somente versões com patch zero, como `2.1.0`. Uma correção `2.1.8` é ignorada, mesmo que seja uma release estável no GitHub. Reproduzido: `is_public_version('2.1.8') == False`. |
| Alta | `updater.py:401` e `:446` | A troca renomeia o executável atual e depois move o novo, sem transação nem restauração automática. Uma falha entre as duas operações pode deixar o caminho principal sem EXE. O download tenta trocar o binário enquanto o app está aberto. |
| Alta | `updater.py:379` | A única validação de download é tamanho superior a 5 MB. Não há conferência de tamanho esperado, hash, assinatura ou identidade do produto. Arquivos inválidos podem passar. |
| Alta | `desktop_backend.py:769` | A instalação de versão aceita uma URL enviada pelo cliente, sem restringir à release oficial nem exigir autorização DEV no endpoint. A interface ocultar um botão não protege a API. |
| Média | `desktop_ui/src/App.tsx:278` | O botão de reinício não confere `res.ok` nem interpreta a resposta. Um HTTP 500 não rejeita automaticamente `fetch`, então o usuário não recebe uma explicação. |
| Média | `desktop_backend.py:715` | A checagem aceita a existência do EXE atual como evidência de que o download existe. Assim, pode prosseguir mesmo que o arquivo de atualização tenha sumido. |
| Média | `updater.py:97` e `:296` | O estado `is_checking` só é marcado dentro da thread. Chamadas simultâneas podem passar pelas guardas antes disso. A instalação de versão específica também compartilha os mesmos arquivos e estado sem exclusão mútua. |
| Média | seleção de releases | O canal beta usa o primeiro item retornado, sem ordenar por versão. O canal público combina redirecionamento, regra de patch e histórico. Assets são inferidos pelo nome em alguns caminhos, podendo produzir uma URL inexistente. |
| Média | estado e erros | O estado de atualização pronta só existe em memória. Ao fechar e abrir, o download não é recuperado como atualização pendente. Falhas de download ficam principalmente no log; mensagens e flags não são publicadas de modo consistente ao terminar. |

O parser atual também transforma partes de versões em dígitos e não implementa comparação correta de pré-lançamentos. Deve ser substituído por uma política de versão explícita.

### Execução Python versus EXE

Para desenvolvimento, a atualização automática do binário deve ficar desabilitada. A interface deve explicar que o app está sendo executado a partir do código e mostrar a versão desse código, sem escrever `version.py`.

Para uso diário e distribuição, o atalho deve apontar para o EXE instalado. Alterar os arquivos no repositório não modifica um processo Python já iniciado, e baixar um EXE não modifica os módulos desse processo.

Clientes que já possuem um updater quebrado provavelmente precisarão de uma instalação de recuperação uma vez. Só depois poderão receber as próximas versões pelo mecanismo corrigido. Essa recuperação deve usar um instalador corrigido, pois o atual tem os riscos descritos abaixo.

## Fluxo de atualização recomendado

1. Consultar um manifesto de atualização por canal, com versão, arquitetura, URL do pacote, tamanho e SHA-256. Assinar o manifesto ou verificar uma assinatura confiável do pacote; hash sozinho não autentica o publicador.
2. Baixar para uma pasta de staging em `%LOCALAPPDATA%\RemoteXPTI\updates`, preservando o app instalado.
3. Validar o pacote e persistir o estado. Só então mostrar “pronto para instalar”.
4. Ao usuário solicitar reinício, iniciar um helper independente, com parâmetros estruturados e log próprio.
5. Encerrar o app; o helper aguarda o processo e a liberação dos arquivos, com prazo e tentativas limitadas.
6. Instalar mantendo uma versão anterior recuperável; iniciar a nova versão e exigir confirmação de inicialização saudável.
7. Em falha, restaurar a versão anterior e registrar uma mensagem compreensível.

Estados sugeridos: `idle`, `checking`, `downloading`, `ready`, `applying`, `failed`. A UI deve receber o estado final e os erros, além de progresso de download.

O reinício de um executável PyInstaller precisa de ambiente independente. A documentação oficial recomenda `PYINSTALLER_RESET_ENVIRONMENT=1` para processos que sobrevivem ao aplicativo anterior: [PyInstaller — reinício](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#restarting-the-application). O updater atual não prepara esse ambiente.

Usar `prerelease`/canal explícito para separar versões estáveis e beta, permitindo correções `2.1.8`, `2.1.9` etc. O GitHub disponibiliza `prerelease`, assets, tamanho e digest na API: [GitHub Releases](https://docs.github.com/en/rest/releases/releases). O fallback não deve inventar dados de integridade que não recebeu.

## Distribuição e instalador

**Corrigir antes de distribuir novamente:**

- `installer_gui.py:210`: encerra todos os processos `python.exe` e `pythonw.exe`, além de RemoteXPTI. Pode matar tarefas de outros aplicativos. Identificar exclusivamente o processo desta instalação e solicitar encerramento controlado.
- `installer_gui.py:208` e `:241`: aceita o diretório digitado e remove seus conteúdos, exceto quatro nomes. Uma pasta errada pode perder arquivos alheios ao app. Usar diretório dedicado validado e remover somente arquivos pertencentes a um manifesto da instalação.
- `build_v2.py` empacota `desktop_ui/dist`, mas não executa nem exige um build novo da interface. Pode distribuir interface antiga com backend novo.
- `build_all.py` ainda compila `main.py`, correspondente à UI antiga. A documentação de distribuição indica esse script. Isso permite publicar a aplicação antiga sob uma versão nova.
- Os scripts incluem `servers.json`, `.secret.key` e, na V2, `doors_config.json`. Pacotes públicos não devem levar dados e credenciais de produção. Usar templates sem segredos e provisionamento separado.
- A assinatura usa certificado autoassinado e imprime sucesso sem conferir retorno/status. Isso não comprova assinatura válida ou confiança em máquinas de clientes. Falha de assinatura deve bloquear uma release quando assinatura for exigida.
- `requirements.txt` não declara dependências centrais da V2, como pywebview, FastAPI, Uvicorn e pystray. Separar dependências de execução, build e integrações opcionais, com versões reproduzíveis.
- `run_modern.bat` e `launch_task.ps1` têm caminhos específicos desta máquina. O segundo também encerra `pythonw` por nome. Substituir por caminhos relativos ou pelo atalho da instalação.

Recomendo um único comando de release: instalar dependências reproduzíveis, compilar React, verificar versão/tag, executar testes, empacotar, validar assinatura, gerar manifesto e preparar os assets. A publicação deve usar o mesmo conjunto de arquivos verificados.

## Segurança e dados

Há problemas concretos que merecem prioridade equivalente ao updater:

- `config_manager.py` contém a senha DEV em comentário, além do hash. O token de sessão é derivado de valores locais conhecidos, e o estado DEV é persistido em JSON. Isso não deve autorizar operações de nuvem ou distribuição.
- `storage.py` tem uma chave mestre embutida, fallback sem criptografia quando a biblioteca está ausente e fallback que retorna o texto recebido quando a descriptografia falha. Corrigir para falhar explicitamente e migrar segredos locais para DPAPI/Windows Credential Manager. Não trocar chaves sem uma migração que preserve as credenciais existentes.
- `session.json` e `doors_config.json` são rastreados pelo Git. A interface também contém senha de dispositivo como valor padrão. Remover os valores do código, revisar o histórico e rotacionar credenciais efetivamente expostas; apagar só a versão atual não remove o histórico.
- `supabase_schema.sql` cria políticas com `USING (true)` e `WITH CHECK (true)` para todas as operações de servidores. Se aplicadas com os grants correspondentes, deixam leitura/escrita sem restrição por usuário. Não foi auditada a configuração real do banco. Uma chave publishable no cliente é normal; a proteção precisa vir de autenticação, grants e RLS: [Supabase — RLS](https://supabase.com/docs/guides/database/postgres/row-level-security).
- O backend local usa CORS amplo e não possui autenticação geral das operações. Vincular ao loopback ajuda, mas não substitui autorização. Usar token por instância e validação de origem para operações sensíveis, incluindo instalação e abertura de portas.

## Estrutura recomendada

Migrar gradualmente para um pacote, mantendo a interface existente:

```text
src/remotexpti/
  bootstrap.py          # janela, bandeja e ciclo de vida
  api/                  # routers: servidores, portas, telemetria, updates
  services/             # operações e coordenação de tarefas
  integrations/         # RDP, Tuya, Hikvision, Supabase, Ajin
  persistence/          # dados, migrações e cofre do Windows
  updates/              # manifesto, download, validação e estado
desktop_ui/src/
  api/                  # cliente HTTP tipado e tratamento de erros
  hooks/                # WebSocket, estado e carregamento
  features/             # servidores, portas, mapa, configurações
tools/                  # build e validação de release
tests/                  # updater, persistência e autorização
docs/
```

Separar binários, dados do usuário e staging de atualização. Inicializar serviços no ciclo de vida da aplicação, em vez de criar gerenciadores e threads como efeito de importação. O backend de cerca de mil linhas concentra APIs, tarefas periódicas, integração e estado global; routers e serviços reduzirão o risco das próximas mudanças.

O storage já usa substituição atômica para salvar JSON, o que é positivo. Ainda precisa de sincronização entre as threads e de uma política clara para conciliar alterações locais e nuvem. SQLite pode ser adotado quando crescerem consultas, histórico e concorrência; não é pré-requisito para corrigir o updater.

Consolidar o código legado CustomTkinter e a V2 após confirmar quais recursos precisam ser preservados. Manter duas aplicações principais e dois builds favorece divergências. A documentação atual também precisa refletir a V2.

Migrar para outro shell desktop só passa a fazer sentido com um objetivo adicional, como multiplataforma ou unificação da equipe em outra linguagem. Primeiro estabilizar distribuição, atualização e segredos com a base existente.

## Validação realizada e limites

- Análise de sintaxe dos 29 arquivos Python da raiz: passou. Isso não detecta nomes ausentes em execução.
- Reprodução isolada do endpoint de reinício: `NameError: name 'sys' is not defined`.
- Reprodução isolada do reinício frozen com dependências simuladas: `UnboundLocalError` para `time`. Nenhum processo real foi iniciado ou encerrado.
- Verificação da regra pública: `2.1.8` é rejeitada.
- `npm.cmd --prefix desktop_ui run build`: passou; aviso de bundle JavaScript superior a 500 kB.
- `npm.cmd --prefix desktop_ui run lint`: terminou com avisos de hooks, estado em efeitos e pureza de renderização.
- Revisão estática e logs dos caminhos principais de launcher, backend, UI, updater, builds, instalador, storage, configuração, RDP e nuvem. Não constitui validação funcional de todas as integrações nem teste de todos os comportamentos do produto.
- Não foi aplicado update real, acionada porta, aberta sessão RDP ou acessado/modificado o banco corporativo. A lista atual de releases não pôde ser confirmada pelo navegador de pesquisa; a evidência da `2.1.8` vem dos logs e do arquivo local.

## Ordem de execução sugerida

1. Corrigir os bloqueios reproduzidos, o feedback HTTP e a atualização falsa em modo Python; preparar uma recuperação para instalações existentes.
2. Corrigir as operações destrutivas do instalador e retirar credenciais dos pacotes.
3. Implementar updater com helper, integridade, persistência e rollback; testar o EXE real em ambiente isolado, incluindo pasta com espaços e arquivos bloqueados.
4. Unificar build/publicação e política de canais; atualizar o guia de distribuição.
5. Revisar autorização local, credenciais e RLS real; migrar dados preservando compatibilidade.
6. Refatorar backend e frontend por função, com testes nos fluxos de maior risco.

Critério de aceite do updater: instalar uma versão A, descobrir B no canal correto, baixar e validar, reiniciar, confirmar que o código de B está em execução, preservar dados e recuperar A quando B falhar. Conferir somente o texto da versão na tela não é suficiente.
