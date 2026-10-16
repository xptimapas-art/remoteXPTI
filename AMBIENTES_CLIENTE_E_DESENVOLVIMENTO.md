# Cliente e desenvolvimento separados

O atalho **RemoteXPTI** abre o executável oficial instalado em
`%LOCALAPPDATA%\Programs\RemoteXPTI\RemoteXPTI.exe`. Essa instalação recebe
atualizações das releases públicas do GitHub. Alterar ou compilar o projeto
não substitui o executável instalado.

O atalho **RemoteXPTI DEV** ou `run_development.bat` abre o código Python.
A janela e a bandeja têm a identificação DEV. As duas versões podem funcionar
simultaneamente, com identificadores de instância diferentes.

| Dados | Cliente instalado | Desenvolvimento |
|---|---|---|
| Configurações, logs, sessão e caches de telemetria/mapas | `%LOCALAPPDATA%\RemoteXPTI` | `%LOCALAPPDATA%\RemoteXPTI-Dev\<id-do-projeto>` |
| Servidores e chave de criptografia | Pasta do executável instalado | Perfil de desenvolvimento |
| Miniaturas e cache SQLite | Pasta do executável instalado | Perfil de desenvolvimento |
| Atualização automática | Habilitada | Desabilitada |
| Sincronização de servidores | Preferência do cliente | Recebimento automático; publicação e exclusão corporativa bloqueadas |
| Portas e atalhos de dispositivos | Configuração do cliente | Sem sessão e desligados por padrão |

O identificador do perfil de desenvolvimento é derivado da pasta do projeto.
Mudar a pasta do projeto cria outro perfil. Para consultar o caminho atual:

```powershell
python -c "from runtime_paths import get_profile_dir; print(get_profile_dir())"
```

Desde 16/10/2026, o DEV recebe automaticamente os servidores da empresa no
startup e nas consultas periódicas. A leitura usa `server_pull_enabled`, separada
da preferência legada `cloud_sync_enabled`; essa preferência não habilita envio
de servidores quando o programa roda pelo código-fonte. O bloqueio de envio e
exclusão também existe diretamente no gerenciador de nuvem.

No DEV, os cadastros corporativos podem ser consultados e favoritados; editar ou
excluir esses cadastros pela API é bloqueado antes da alteração local. Novos
servidores de teste recebem escopo local e continuam apenas no perfil DEV.
Favoritos são pessoais de cada instalação, aparecem primeiro em ordem alfabética
e não são enviados nem importados pela sincronização de servidores.

A sincronização de portas e sessão Tuya mantém seu fluxo próprio, já autorizado;
o modo de recebimento de servidores não altera esse compartilhamento.

`run_modern.bat` é mantido como um alias do desenvolvimento. Para abrir o
cliente a partir do projeto, use `run_client.bat`. `launch_task.ps1` configura
a tarefa de inicialização para abrir o executável instalado.

Na separação local feita em 14/10/2026, a instalação foi atualizada para o
binário publicado 2.1.10, validado pelo SHA-256 do manifesto. Os 56 servidores
da cópia mais recente e sua chave foram levados para a instalação cliente,
com as configurações pessoais preservadas. A cópia DEV recebeu uma cópia
independente dos servidores; a sessão de dispositivos não foi compartilhada.

A instalação anterior, os perfis, os dados originais e os atalhos/tarefas
alterados foram preservados em `%LOCALAPPDATA%\RemoteXPTI-Backups\separation-<data>`.
Esses backups contêm dados pessoais e credenciais; não devem ir para o GitHub.

Publicar uma release nova é uma ação separada. Para testar o auto update
como cliente, use o atalho normal e o botão de atualização dele.
