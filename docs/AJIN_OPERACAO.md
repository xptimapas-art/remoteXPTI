# AJIN — recuperação da entrega de dados em 14/10/2026

O coletor SNMP permanece no AJINServer, `192.168.190.187`, executado pela
tarefa `ColetaONU` a cada minuto. Os snapshots continuam em `C:\temp`.
O socket de origem da coleta, a validação de integridade e o cadastro físico
da OLT não foram alterados.

O RemoteXPTI consome `/data` pela porta HTTP 3000. Antes da recuperação,
`192.168.12.10:3000` e `192.168.190.187:3000` recusavam conexões; a coleta
continuava funcionando, mas o painel que publicava a API estava ausente dos
caminhos verificados. O fluxo anterior tinha um painel separado puxando CSVs
via WinRM. A última telemetria salva pelo cliente era de 09/10/2026.

## Instalação recuperada

- API: `http://192.168.190.187:3000/data`.
- Tarefa: `RemoteXPTI_AJIN_Painel`, como SYSTEM, iniciada no boot, com
  reinício após falha e verificação a cada cinco minutos, sem instâncias duplicadas.
- Diretório: `C:\temp\RemoteXPTI-AJIN-Hub\20261014-154335`.
- Componentes: `dashboard.py` do projeto Monitoramento AJIN e
  `run_ajin_hub.py`, cuja fonte está em `tools/run_ajin_hub.py` neste projeto.
- Cadastros e nomes dos 39 dispositivos foram recuperados da última
  telemetria do cliente; o mapeamento de câmeras é lido do servidor.
- Metadados ficam no `logs_ONU` da instalação do painel. Os CSVs do coletor
  são lidos diretamente, sem cópia por WinRM nem outra coleta SNMP.
- Firewall: TCP 3000, rede local e `192.168.190.0/24`, autorizado pelo usuário.
- Erros do processamento ficam em `hub.log`; acessos em `logs_ONU/dash_access.log`.

O painel prepara um snapshot antes de abrir a porta e atualiza o resultado
em segundo plano a cada dez segundos. As requisições padrão recebem esse
resultado pronto. Reprocessar o histórico por requisição levava aproximadamente
5,6 segundos, acima dos quatro segundos de timeout do cliente; após o cache,
uma consulta local foi medida em aproximadamente 12 ms.

O histórico disponível no cache do cliente foi preservado. O rastreador de
estado começa na coleta observada na recuperação; o intervalo sem painel não
é presumido como continuidade de uptime.

## Verificação e operação

No servidor:

```powershell
Get-ScheduledTask -TaskName ColetaONU,RemoteXPTI_AJIN_Painel
Get-NetTCPConnection -LocalPort 3000 -State Listen
Invoke-RestMethod http://127.0.0.1:3000/data
```

Para iniciar o painel parado, sem iniciar outra coleta:

```powershell
Start-ScheduledTask -TaskName RemoteXPTI_AJIN_Painel
```

Para reiniciar somente o painel:

```powershell
Stop-ScheduledTask -TaskName RemoteXPTI_AJIN_Painel
Start-ScheduledTask -TaskName RemoteXPTI_AJIN_Painel
```

Na versão DEV, o servidor AJIN é o endereço principal, com o endereço LAN
antigo como alternativa. As ações usam o mesmo servidor que respondeu à
telemetria. A interface informa falhas de conexão e coleta atrasada, mantém
o último inventário disponível e usa somente contagens recebidas da API.
Esta alteração do executável ainda não foi publicada no GitHub.
