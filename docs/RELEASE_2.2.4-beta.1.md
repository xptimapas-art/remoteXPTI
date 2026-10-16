# RemoteXPTI 2.2.4-beta.1

Pré-release para usuários autenticados no canal beta. A versão estável permanece
2.2.0; esta publicação não muda o canal público.

- Cadastro de servidores redesenhado no padrão XPTI, com grupos BEMTEVI,
  SEJURI e XPTI, busca, criação e gerenciamento de grupos. Grupos com
  servidores não podem ser excluídos.
- Cidade e estado permitem colocar o servidor aproximadamente no mapa;
  coordenadas manuais opcionais têm prioridade.
- Favoritos são salvos neste computador e aparecem primeiro, em ordem
  alfabética. Não são enviados como preferências de outros clientes.
- Gravação atômica, retorno de erros reais ao salvar e preservação dos
  servidores locais quando a consulta à nuvem falha ou está incompleta.
- Configurações de portas e sessão passam a usar o perfil persistente do
  Windows, inclusive em instalações novas do EXE onefile.
- O DEV recebe os cadastros corporativos e bloqueia envio, edição e exclusão
  desses cadastros; servidores de teste permanecem locais.
- Miniatura automática do papel de parede ao acessar um servidor, usando
  WinRM existente quando disponível, sem instalar agente e sem varrer todos
  os servidores. Falhas preservam a imagem anterior. Habilitada no DEV e no
  EXE com canal beta autenticado; sair do canal interrompe coletas pendentes.
- Monitoramento distingue erros locais inconclusivos de falhas do destino,
  preserva a confirmação de quedas reais e registra ciclos para diagnóstico.

## Limites desta beta

Cidade, UF e indicação de origem da localização ficam no cadastro local.
As coordenadas continuam usando as colunas compartilhadas já existentes.
Grupos vazios são locais; grupos vinculados acompanham os servidores na
sincronização. Não há migração de esquema do Supabase nesta versão.

A miniatura depende das permissões e do WinRM já configurado no servidor.
Não é transmissão da área de trabalho em tempo real.

Os pacotes são conferidos pelo verificador de release: integridade do
manifesto, versão embutida, correspondência da interface, EXE contido no
instalador e no ZIP portátil, dados iniciais vazios e runtime de vídeo.
