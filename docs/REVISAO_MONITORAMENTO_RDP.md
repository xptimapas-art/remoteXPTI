# Revisão de monitoramento RDP — 16/10/2026

Relato: 49 servidores ficaram offline e recuperaram juntos no CLIENT e no
DEV. Na revisão, o inventário tinha 59 servidores: 49 em duas faixas de rede
remotas e 10 em outras faixas. O DEV consultado depois do episódio tinha uma
falha persistente em Bombinhas. A rota consultada para um destino remoto
usava o gateway do Wi-Fi; a presença do ZeroTier não comprova seu envolvimento.
Não havia eventos de desconexão no intervalo consultado dos logs de perfil
de rede/WLAN do Windows.

O padrão é compatível com indisponibilidade de um caminho compartilhado, mas
**não foi possível confirmar a causa do episódio**. O monitor anterior não
guardava os resultados brutos dos ciclos e preservava somente incidentes
ainda abertos. Resposta TCP/RDP também não comprova o estado completo do
servidor: falhas podem estar na rota, firewall, serviço RDP ou equipamento.

## Problemas encontrados e ajustes no DEV

- Erros de rede local e falta de recursos do computador eram apresentados
  como porta fechada/filtrada. Agora esses erros e falhas de resolução DNS são
  medições inconclusivas: não adicionam votos de queda ou recuperação e
  preservam o último estado confirmado. O motivo e a data do último teste
  válido ficam disponíveis na API.
- Uma sequência pendente podia atravessar uma pausa prolongada. Intervalos
  acima de 90 segundos agora exigem uma sequência nova de confirmação,
  preservando incidentes que já estavam confirmados.
- Sockets do teste antigo não eram fechados em todos os caminhos de exceção.
  O teste usa fechamento garantido, suporta IPv4/IPv6 e diferencia timeout,
  conexão recusada, destino inacessível e erro local.
- Uma exceção inesperada num teste não interrompe o processamento dos outros
  servidores: o resultado daquele teste é registrado como inconclusivo.
- Resultados de alvos editados ou removidos durante o teste são descartados.

Os limiares permanecem em pelo menos três falhas válidas por 60 segundos e
duas respostas válidas separadas por pelo menos 10 segundos para recuperação.
O ciclo automático continua a cada 30 segundos. A detecção de falha coletiva
é diagnóstica: uma queda persistente de 49 servidores continua sendo
confirmada, sem ocultação por porcentagem.

## Evidência para uma próxima ocorrência

Os últimos 120 ciclos ficam no arquivo logs/rdp_status_scans.json do perfil
local, com gravação atômica. Cada ciclo contém horário, duração, contagens,
IDs que caíram/recuperaram, resultados e motivos dos testes. Não contém
senhas ou nomes de usuário. A ausência de disco disponível para essa evidência
não altera os estados dos servidores.

Metade ou mais dos testes falhando, com pelo menos cinco falhas, marca o ciclo
como falha coletiva. A agregação de endereços por prefixo serve para investigar
o padrão; não demonstra que existe uma única rota. Erros inconclusivos são
contados separadamente. O log normal registra transições, falhas coletivas e
seu fim. A API local GET /api/monitoring/status fornece o último ciclo.

Nenhum teste adicional de rede foi criado para esse diagnóstico. Não houve
mudança no roteador, firewall, VPN, ZeroTier ou servidores remotos, nem
instalação/publicação de uma versão CLIENT.

## Validação

Testes com sockets e relógios simulados: erro local/DNS/recursos, timeout,
recusa, IPv6, sequência após pausa, recuperação, histórico limitado, erro de
disco e falha coletiva de **49 servidores com 10 respondendo**, seguida de
recuperação dos 49. A falha coletiva continua aparecendo corretamente.

Os testes e dados simulados não reproduzem a causa do episódio real. O
diagnóstico novo permite correlacionar uma nova ocorrência sem inferir a
causa apenas pela quantidade de servidores.

Regressão: 245 testes Python aprovados, incluindo os 33 de conectividade e
diagnóstico; TypeScript e build Vite aprovados. Os novos módulos também são
exigidos pelo verificador do pacote para uma distribuição futura.

No DEV reiniciado, dois ciclos automáticos normais registraram 59 testes,
58 respostas, um timeout em Bombinhas e zero resultados inconclusivos; cerca
de três segundos por ciclo. A API e o histórico em disco conferiram. Os
18 testes frontend também passaram. Evidência local ignorada pelo Git:
.test-artifacts/rdp-monitor-live-result.json.
