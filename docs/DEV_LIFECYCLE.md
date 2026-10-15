# Ciclo de atualização do DEV

O CLIENT instalado e o DEV de cada checkout têm mutex, perfil e processo distintos.
Dois processos `RemoteXPTI.exe` em relação pai/filho podem pertencer à mesma execução
do pacote PyInstaller. Não encerrar o CLIENT durante a manutenção do DEV.

Ícones antigos na bandeja não significam, por si só, processos em execução.
Encerrar com `Stop-Process`/`TerminateProcess` impede a limpeza da bandeja. Além
disso, `pystray.stop()` apenas envia uma mensagem ao loop da bandeja: sair com
`os._exit()` imediatamente pode acontecer antes da remoção do ícone. O launcher
agora define `visible=False` antes de parar a bandeja e encerrar o processo.

Depois de compilar uma alteração da interface, usar o Python do projeto:

```powershell
py -3.12 tools/control_dev.py reload --pid <PID_DO_DEV>
```

Isso recarrega a interface na mesma janela, preservando processo, backend, ícone e
hotkeys. Para mudanças Python que exigem uma nova execução:

```powershell
py -3.12 tools/control_dev.py stop --pid <PID_DO_DEV>
```

Aguardar a saída do processo antes de iniciar outro DEV. Não usar encerramento
forçado como rotina. O comando é limitado ao PID, executável Python, título DEV
e mensagens deste checkout. O CLIENT não registra os comandos de controle DEV.
Esses comandos não são endpoints HTTP nem ações expostas ao JavaScript da página.

Ícones residuais de processos encerrados anteriormente ainda podem permanecer no
cache do Explorer e desaparecer quando o mouse passa sobre eles. A correção evita
criar novos resíduos; não exige reiniciar o Explorer ou interromper outros apps.
