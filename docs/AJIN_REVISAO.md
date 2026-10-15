# AJIN — revisão aprovada no DEV em 15/10/2026

O visual foi aprovado nas prévias `ajin-tela-unica-xpti.html`, com o acréscimo
do botão de excluir nas configurações. As mudanças compõem a beta 2.2.3-beta.1.
A validação no DEV preservou o executável e o perfil CLIENT instalados.

## Interface

- Área clara, azul XPTI e ações principais amarelas. Cabeçalho do aplicativo
  preservado. Painel lateral azul uniforme com cantos arredondados.
- Uma barra com busca, status, Atualizar, Incidentes e Scanner. Sem CSV, filtro
  de porta PON ou título AJIN junto à busca. O painel lateral mostra Total de
  pontos, Ativados, Desativado, Online e Offline no mesmo padrão, com filtros.
  O filtro inicia em Ativados (somente online e offline); as opções são Ativados,
  Todos, Online, Offline e Desativados. Limpar filtros retorna a Ativados.
  Não há opção Desconhecido no seletor; um status não informado pelo coletor
  continua identificado corretamente em Todos, sem ser confundido com offline.
- Colunas: Ponto, Status, Endereço, UPTime, MAC/serial, Fabricante, Porta PON
  e Ações. Sem lápis, lixeira ou seta no botão Menu. Localização preservada.
- Menu abre uma única tela com identificação, coordenadas, status e UPTime.
  Sem categorias, câmeras vinculadas, histórico ou seção de monitoramento.
- Excluir ponto abre uma caixa flutuante central e exclusiva, sobre fundo
  escurecido. O formulário de configurações sai de cena durante a confirmação.
  Cancelar ou Esc retorna ao formulário preservando os campos ainda não salvos.
  A confirmação remove o cadastro
  compartilhado do monitoramento; não desativa nem reseta a ONU na OLT.
  Se o coletor recusar a exclusão, a janela permanece aberta e informa o erro.
  O botão final fica desabilitado por pelo menos três segundos. Cancelar e abrir
  novamente reinicia a espera. O foco inicial fica em Cancelar; o prazo nunca
  executa a exclusão automaticamente.
- UPTime fica vazio para pontos offline/desconhecidos. O tempo de indisponibilidade
  aparece na lista de incidentes. O coletor fornece tempo no estado, não uptime
  de hardware; o app não inventa uma segunda medida.

## Histórico de incidentes

Uma única lista apresenta início, ponto, incidente, status, recuperação e duração.
Ela utiliza `events_history` do coletor (atualmente limitado aos últimos 100 eventos)
e `active_problems` para identificar as ocorrências que continuam abertas.

Queda e recuperação do mesmo ponto e serial são reunidas em uma ocorrência.
Eventos duplicados não geram múltiplas quedas. Quando a queda já saiu do histórico,
a duração explícita da recuperação permite reconstruir o início. Se o coletor não
informar um início ou uma recuperação, o app não inventa uma data: entradas antigas
sem confirmação ficam indicadas como tal, separadas dos incidentes abertos.
O inventário atual permite exibir problemas ativos mais antigos que o histórico.

## Scanner

Consulta a API existente `/api/scan` do coletor, com tabela, busca, seleção em lote
e filtros de cadastro. A tela consulta ao entrar na AJIN, a cada 30 segundos enquanto
a aba está aberta, ao abrir o Scanner e ao clicar em Re-escanear. Esses comandos
consultam os arquivos da coleta existente; não iniciam outra varredura SNMP na OLT.

A homologação usa `/api/add_devices`. Antes de enviar, o aplicativo confere a
descoberta novamente, comparando porta, ID e serial, para evitar cadastrar uma ONU
que mudou ou já foi cadastrada por outro cliente. Uma resposta HTTP 200 com
`ok: false` é erro. Falha de consulta preserva a última lista e bloqueia homologação
até uma consulta bem-sucedida. Não há dispositivos de exemplo no aplicativo.

## Operação e persistência

O campo Observações fica abaixo das coordenadas e aceita até 4000 caracteres.
É salvo no coletor, no arquivo `logs_ONU/point_notes.json`, com escrita atômica.
Cada snapshot entrega as observações aos clientes que possuem esse campo.
O registro inclui o serial da ONU para não transferir anotações automaticamente
a outro dispositivo que venha a ocupar a mesma porta/ID. O endpoint
`/api/point_label` exige confirmação explícita de gravação das observações.
Os endpoints antigos continuam funcionando e edições de versões antigas não
apagam as observações, que ficam separadas do arquivo legado de identificação.

O contador do botão Scanner só é exibido quando há uma ou mais ONUs novas.

A opção Ativar ponto fica nas configurações, abaixo das coordenadas.
O campo legado `map_enabled` é compartilhado pelo coletor e persiste com as
observações, vinculada ao serial. Versões anteriores que editam somente as
observações preservam a preferência de ativação. Os pontos existentes ficam
habilitados por padrão, preservando a exibição anterior.

O mapa exige latitude/longitude numéricas, finitas e dentro dos limites.
Coordenadas zero são válidas. Desativar mantém o ponto na lista e no mapa:
status Desativado, sem UPTime ou contagem online/offline, e círculo amarelo
numerado no mapa. Isso não interrompe a coleta física da ONU. A atualização
compartilhada muda o marcador e o detalhe aberto na próxima telemetria.
O contador do mapa inclui todos os pontos com coordenadas, ativos e desativados.
Os pontos AJIN usam agrupamento por proximidade em uma camada própria, separada
dos servidores. Ao afastar, aparece um contador por grupo, com sombra discreta;
ao aproximar ou clicar, os grupos se abrem. O agrupamento termina no zoom 14:
na visão do bairro todos os pontos já aparecem separados. Grupos distantes usam
o mesmo contador circular, tamanhos e cores dos grupos de servidores, sem uma
etiqueta AJIN separada. Na camada AJIN, pulsos, filtros de sombra SVG e animação
dos grupos foram removidos para reduzir o custo de desenhar todos os pontos.
As imagens do mapa são atualizadas ao concluir cada nível de zoom.
O tooltip informa online, offline e
desativados somente entre os pontos daquele grupo. Marcadores individuais
mantêm o número do ponto e os desativados permanecem amarelos. O atalho da lista
aproxima até revelar o ponto solicitado, inclusive quando estava agrupado.

Os marcadores AJIN são preservados por porta/ID ou chave do cadastro geográfico.
Uma coleta com apenas UPTime diferente não recria os ícones, grupos ou servidores.
Ícone, tooltip e posição só mudam quando os respectivos campos mudam; inclusões
e remoções são aplicadas individualmente. O clique utiliza os dados mais recentes.
No teste com cinco coletas simuladas e 59 pontos visíveis, a versão anterior
removeu/adicionou 300 marcadores (incluindo o servidor próximo), enquanto a nova
preservou os 59 pontos e não adicionou/removeu nenhum marcador. Essa medida
verifica trabalho evitado; não representa uma garantia de FPS em cada computador.

- Pausar congela a exibição desta tela. O coletor e os outros clientes continuam
  funcionando. Retomar aplica o estado mais recente recebido.
- Atualizar aguarda os dados do painel/API e informa falha/timeout. A consulta
  normal ao painel continua a cada 10 segundos. Status desconhecido é separado
  de offline e coleta inválida, futura ou antiga é marcada como desatualizada.
- Nome/endereço só são confirmados após `ok: true`. Campos recém-confirmados são
  preservados até o snapshot do coletor alcançar a edição, por no máximo 30s.
  Uma exclusão confirmada também fica protegida contra reaparecer nesse intervalo.
- Endereços e coordenadas passaram a ser compartilhados no coletor com a importação
  de `dados AJIN/pontos_ajin_jurere.md`. O cadastro central tem prioridade sobre
  coordenadas locais antigas. Zero é válido e limpar os dois campos também é
  compartilhado. A gravação é atômica e os textos do mapa não são interpretados
  como HTML. Arquivos locais anteriores permanecem como compatibilidade para
  pontos sem localização central, sem sobrescrever uma localização compartilhada.

## Importação dos pontos

`tools/import_ajin_points.py` prepara um plano somente de leitura por padrão.
Cruza o número no nome do ponto com o arquivo, nunca o confunde com o ID da ONU,
e recusa duplicatas e coordenadas inválidas ou divergentes entre tabela e link.
A aplicação requer `--apply`, guarda o cadastro anterior e confere o serial
esperado no coletor antes de cada alteração. O Ponto 42 fica excluído da importação
por decisão do usuário. Pontos sem ONU cadastrada são exportados em
`inactive_points.json`, sempre com `map_enabled: false`. Esse arquivo fica no
`logs_ONU` do painel e é entregue em `/data` como `inactive_points`, separado das
ONUs: não altera a telemetria física ou gera incidentes offline.
Os cadastros entram na tabela principal como **Desativado** e no mapa como
círculos amarelos numerados. O resumo **Pontos desativados** filtra a mesma
tabela e usa o mesmo visual de Online e Offline. ONUs desativadas mantêm suas
configurações; cadastros sem ONU oferecem detalhes, sem inventar porta, serial,
fabricante ou UPTime. As chaves `catalog-N` existem somente na interface e
nunca são enviadas aos endpoints de operação da ONU. Se o mesmo número for posteriormente
cadastrado como ONU, não é duplicado na lista de pontos geográficos.
As coordenadas recebem a precisão
do link presente no próprio arquivo, sem geocodificação ou consulta externa.

## Validação

Testes isolados cobrem telemetria, cache, concorrência, confirmação das operações,
coordenadas, registro com descoberta alterada e reconstrução de incidentes.
O navegador verifica tamanhos de 940 a 1920px, configurações em tela única,
confirmação de exclusão, falhas de salvamento/exclusão/homologação, busca, seleção
em lote, pausa/retomada e atualização. Todas as mutações nesses testes são
interceptadas; a validação real usa apenas leitura do coletor e do Scanner.
