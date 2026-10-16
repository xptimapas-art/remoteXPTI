# Cadastro de servidores no DEV

Implementado o desenho aprovado: cabeçalho “Adicionar servidor”, grafite com
detalhes vermelhos, grupo com lista própria e busca, gerenciamento de grupos,
cidade/estado, coordenadas opcionais, observações e opções RDP.

O DEV continua recebendo os servidores corporativos e bloqueando alterações
ou exclusões desses cadastros. Servidores novos no DEV são locais. Nenhuma
publicação ou instalação CLIENT faz parte desta entrega.

## Grupos

BEMTEVI, SEJURI e XPTI são os padrões do cadastro sem registro de grupos.
Grupos existentes, como AJIN, são preservados. O registro é local, no mesmo
arquivo servers.json, e aceita grupos vazios. Excluir um padrão vazio não o
recria no próximo carregamento.

Renomear atualiza o nome e os vínculos dos servidores numa única gravação
atômica. O backend recusa excluir qualquer grupo com servidores, mesmo se a
contagem da tela ficou desatualizada. No DEV, grupos vinculados a servidores
corporativos também não podem ser renomeados. Grupos locais podem ser
criados, renomeados e excluídos quando vazios, com confirmação.

## Localização

Cidade e UF são independentes do nome do servidor. A base local de municípios
inclui 5.571 referências, com origem e licença em resources/README.md.
Localização aproximada fica identificada no tooltip e no detalhe do mapa.
Sem localização, novos cadastros ficam somente na grade; não recebem posição
inferida pelo nome em um reinício posterior.

Coordenadas válidas têm prioridade, aceitam zero e podem ser adicionadas pelo
editor existente depois. Uma alteração real das coordenadas substitui a
posição aproximada. Salvar outros campos sem alterar o par aproximado não
transforma a referência municipal em posição exata. Cidade/UF desconhecidas
ou um par incompleto são recusados antes de gravar.

Os campos novos de cidade, UF e origem estão no arquivo local; os clientes
antigos continuam recebendo as colunas de latitude/longitude já existentes.
Não foi alterado o esquema do Supabase. Para distribuir os metadados novos
entre instalações, revisar a migração de esquema e o envio desses campos
antes de uma publicação; grupos vazios não são compartilhados nesta entrega.

## Verificação

259 testes Python e 25 testes frontend aprovados; TypeScript e build Vite
aprovados. Os componentes novos passaram no lint sem avisos. O empacotador
inclui a base de municípios e a licença; o verificador exige ambos.

O teste integrado no DEV criou, renomeou e excluiu grupos temporários,
cadastrou um servidor local com cidade/UF e depois substituiu a posição
aproximada por coordenadas manuais. A exclusão de grupo ocupado retornou
409. Os dados dos 59 servidores corporativos permaneceram iguais e todos
os registros temporários foram removidos, sem abrir conexões RDP.

A conferência final com APIs simuladas verificou a identificação de
localização aproximada no mapa, o cabeçalho aprovado, ausência de estouro
horizontal em 320 px e acesso ao botão Salvar em janela de 700 px de altura.
As capturas desktop e compacta foram inspecionadas. O comando de recarga
da interface foi enviado à instância DEV identificada, preservando o CLIENT.
