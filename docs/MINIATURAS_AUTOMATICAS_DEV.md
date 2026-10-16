# Miniaturas automáticas — DEV e beta

O acesso RDP solicita a miniatura somente do servidor clicado, em uma thread
separada e após o Windows aceitar a abertura do RDP. Isso não comprova que o
login remoto foi concluído. Abrir a grade, pesquisar, receber status ou deixar
o app aberto não dispara coleta. Não há varredura periódica nem controles
manuais de miniatura.

A imagem é o papel de parede do perfil correspondente à conta cadastrada,
obtido pelo WinRM já existente no servidor. Não captura janelas nem a área de
trabalho em uso, não instala agente e não habilita serviços remotos. Usar RDP
não garante acesso ao WinRM: se ele não estiver disponível ou a conta não tiver
permissão, a imagem anterior é preservada. Este piloto não usa SMB.

O transporte usa NTLM com criptografia de mensagem, valida certificados HTTPS
e não utiliza proxy. Há somente uma autenticação, com o usuário exatamente
cadastrado. Não tenta variações de conta, não altera configurações remotas e
não executa tarefas persistentes.

- Imagens válidas são reutilizadas por 24 horas. Depois desse prazo, uma nova
  tentativa ocorre **no próximo acesso àquele servidor**.
- Falhas comuns aguardam 10 minutos antes de permitir outra tentativa por
  clique; falhas de autenticação aguardam 24 horas.
- Há no máximo duas coletas simultâneas; cliques repetidos no mesmo servidor
  não duplicam a coleta. Se os dois espaços estiverem ocupados, o acesso RDP
  continua normalmente e a miniatura aguarda um próximo clique.
- As miniaturas ficam limitadas a 640 × 360. A gravação usa arquivo temporário
  e substituição atômica. Uma resposta antiga não pode substituir a imagem de
  um servidor cuja conta ou endereço mudou durante a coleta.
- O cache fica no perfil da instalação, sem senhas ou nomes de usuário nos metadados.
  A chegada da imagem notifica a interface e muda a URL de cache.
- Na 2.2.4-beta.1, o piloto está habilitado no código fonte (DEV) e no EXE
  com canal beta autenticado. A permissão é conferida a cada acesso; sair do
  canal interrompe a publicação de coletas em andamento, sem apagar imagens.
  O canal público mantém o recurso desligado.

Validação inicial: leitura real dos papéis de parede de COPE e Balneário
Camboriú, testes isolados de transporte/cache/rota e teste do navegador com
APIs simuladas, incluindo recuperação de uma imagem que antes retornava 404.
