# Persistência, sincronização de servidores e favoritos

Implementação local em 16/10/2026, a partir da 2.2.3-beta.1. Sem publicação ou alteração do CLIENT instalado. Layout preservado; falhas passam a aparecer nas mensagens dos formulários e no aviso de favorito.

## Comportamento entregue

1. **Portas/sessão:** destino canônico no perfil `%LOCALAPPDATA%\RemoteXPTI`; DEV usa seu perfil próprio. Arquivos legados ao lado do EXE ou no bundle são apenas origens de migração e permanecem intactos. Perfil existente tem precedência. Migração usa temporário completo e criação sem sobrescrever outro processo. O caminho pessoal antigo foi removido.
2. **Consulta de servidores:** páginas ordenadas por ID, com contagem exata e intervalos validados. Falha em qualquer página, contagem desconhecida/alterada, ID inválido/duplicado ou formato incompatível descartam toda a consulta. Registros reservados são filtrados depois de confirmar a completude. A consulta real de leitura ao Supabase confirmou compatibilidade com esse mecanismo, sem merge ou envio.
3. **Merge:** somente `CompleteServerSnapshot` permite remover corporativos ausentes. Listas comuns fazem apenas inclusão/atualização. Particulares são preservados. A revisão local é capturada antes da consulta; uma edição no intervalo faz o app rejeitar o resultado e permite tentar de novo. Antes de remover, o estado anterior é salvo em `servers.json.pre-sync.bak`; falha do backup impede a remoção.
4. **Gravação:** temporário único na mesma pasta, flush, fsync e replace; operações de servidores são serializadas por RLock. Erro preserva arquivo e memória anteriores e chega à API como falha, antes de iniciar envio à nuvem. Preferências também usam escrita atômica e restauram o último estado salvo. Leitores de servidores recebem cópias. Arquivo corrompido não é substituído por uma lista vazia.
5. **Favoritos:** alteração no registro persistido, independente das preferências da nuvem; confirmação só depois de gravar. Frontend usa o booleano confirmado pela API, bloqueia cliques concorrentes no mesmo servidor e informa falha sem mudar a estrela. Favoritos aparecem primeiro na grade em ordem alfabética de nomes (pt-BR, sem distinção de caixa/acentos, números em ordem natural). Os demais mantêm a ordem normal; ao desmarcar, o cartão volta a ela. Favorito é uma preferência local: o cadastro compartilhado não envia esse campo e o merge não importa favoritos de outros PCs.

**DEV sincronizado, com proteção dos cadastros corporativos:** o código-fonte recebe as consultas completas automaticamente, mesmo com o antigo switch de envio desligado. Não pode publicar ou excluir servidores na nuvem; o gerenciador bloqueia essas duas operações antes de abrir uma conexão. A API também recusa edição/exclusão de servidores corporativos no DEV. Cadastros de teste novos ficam com escopo local. Clientes EXE mantêm sua preferência de sincronização e comportamento atual. Portas/sessão Tuya têm fluxo separado e foram preservadas.

Conferência do recebimento em 16/10/2026: DEV e CLIENT com os mesmos **59 IDs de servidores**, todos os 56 anteriores e os favoritos DEV preservados. As proteções foram exercitadas com serviços falsos (nenhum DELETE real foi enviado): envio/exclusão bloqueados no gerenciador, edição/exclusão corporativa retornando 403 na API e cadastro novo com escopo local. A notificação após o merge atualiza a grade sem aguardar o próximo scan. Evidência: `.test-artifacts/dev-receive-live-result.json`. Ordenação alfabética conferida no navegador com dados simulados.

Não houve migração de `servers.json`/`.secret.key` para outra pasta nem troca da criptografia RDP; esses itens mantêm a compatibilidade atual e têm escopo próprio no plano. A proteção de snapshot confirma a contagem e as páginas da consulta REST; não transforma múltiplas requisições numa transação do banco. Mudanças de autorização ou de protocolo de exclusão continuam exigindo revisão própria.

## Validação

- **205 testes Python aprovados**: inclui falhas de add/edit/delete/favorite/merge, erro depois do backup, gravações concorrentes, rejeição de snapshot incompleto, conflito durante a consulta e respostas HTTP reais via ASGI com serviços falsos.
- **18 testes frontend aprovados**: regras AJIN e confirmação/erro/interrupção do pedido de favorito.
- **TypeScript e build Vite aprovados.** Lint: zero erros, 20 avisos remanescentes; não foram ocultados por desabilitações.
- **Interface em Edge headless com APIs simuladas:** erro de disco não muda favorito; cliques repetidos geram um pedido; estado confirmado sobrevive ao reload; erro ao criar servidor mantém formulário aberto e informa a falha.
- **EXE onefile de diagnóstico**, compilado com os módulos reais de caminhos/gravação: grava portas/sessão num perfil temporário, encerra e reabre usando outra extração. Dados preservados e extração anterior removida; sem rede/dispositivos. Isso não substitui a homologação do instalador completo antes de publicar.
- **DEV reiniciado pelo controle próprio**, com backend saudável e verificação nativa da AJIN. Processos CLIENT preservados. Não foram disparados portões nem abertas conexões RDP.

Evidências ignoradas pelo Git: `.test-artifacts/four-fixes-python-tests.log`, `four-fixes-frontend-tests.log`, `four-fixes-ui-result.json`, `four-fixes-frozen-result.json` e `four-fixes-cloud-result.json`.

## Operação e recuperação

Se a nuvem não confirmar a consulta completa, a lista anterior fica disponível e a sincronização informa falha. Se alguém editar durante a consulta, repetir a atualização. Se houver erro de disco, corrigir permissão/espaço e tentar salvar de novo; o formulário permanece disponível.

`servers.json.pre-sync.bak` guarda o estado anterior à última operação de merge que removeu servidores. É uma única cópia de recuperação, atualizada antes de cada nova remoção, no mesmo diretório dos dados. Não restaurar por cima de um app aberto nem publicar esse arquivo: contém os mesmos dados privados da lista original.

Distribuição autorizada pelo usuário em 16/10/2026 como pré-release
2.2.4-beta.1. A preparação exige o pacote completo e o verificador atualizado,
que confere `atomic_storage` e `server_snapshot`, interface, manifesto,
instalador e ZIP. Consulte [notas da beta](RELEASE_2.2.4-beta.1.md).
