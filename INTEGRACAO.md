# 🔌 Guia de Integração - RemoteXPTI

Este documento descreve como o **RemoteXPTI** se integra tecnicamente com os demais projetos e infraestruturas do ecossistema da XPTI.

---

## 🗺️ Mapa de Integrações

```
                     ┌───────────────────────────────────┐
                     │            RemoteXPTI             │
                     └─┬───────────────────────────────┬─┘
                       │                               │
        (Acesso RDP    │                               │ (Acesso RDP
         Administrativo)│                               │  Operacional)
                       ▼                               ▼
       ┌───────────────────────────────┐   ┌───────────────────────────────┐
       │      Monitoramento AJIN       │   │       Rede Presídio PRJ       │
       │   Dell R740 (192.168.190.187) │   │     Servidores (10.40.90.x)   │
       └───────────────────────────────┘   └───────────────────────────────┘
                       ▲
                       │ (Ambiente de Rede & Conectividade VPN)
       ┌───────────────┴───────────────┐
       │           Rede XPTI           │
       │   MikroTik (192.168.11.0/24)  │
       └───────────────────────────────┘
```

---

## 1. Integração com [Monitoramento AJIN](file:///c:/Users/XPTI/Documents/vscode/monitoramentoAJIN)

### Objetivo
Permitir que operadores e técnicos acessem diretamente o servidor central Dell PowerEdge R740 (`AJINSERVER`) via RDP com credenciais injetadas e visualizem o Dashboard NOC na porta `3000`.

### Como Configurar no RemoteXPTI

No arquivo `servers.json` (ou pela interface do RemoteXPTI clicando em **Adicionar Servidor**):

```json
{
  "id": "ajin-server-prod",
  "name": "Servidor AJIN (Dell R740)",
  "ip": "192.168.190.187",
  "port": 3389,
  "user": "Administrator",
  "group": "Produção AJIN",
  "fullscreen": true,
  "multimon": false,
  "description": "Windows Server 2022 - Host do Coletor SNMP da OLT e Dashboard Web :3000"
}
```

### Abrindo o Dashboard Web do AJIN a partir do RemoteXPTI
Se desejar abrir o painel web do monitoramento diretamente pelo RemoteXPTI sem precisar logar via RDP:
* **URL:** `http://192.168.190.187:3000` (requer ZeroTier ativo na máquina local).
* **Verificação de Saúde (Health Check via Python):**
  ```python
  import socket

  def check_ajin_status():
      sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
      sock.settimeout(2)
      result = sock.connect_ex(('192.168.190.187', 3000))
      sock.close()
      return "Online" if result == 0 else "Offline"
  ```

### Telemetria Direta das ONUs (Aba 'ONUs Ajin' no RemoteXPTI)
Além do acesso RDP e Web ao servidor, o RemoteXPTI consome a telemetria em tempo real das ONUs da OLT C-Data FD1108S:
* **Módulo `ajin_manager.py`**: Conecta via Supabase REST (`ajin_telemetry`) com fallback local lendo `logs_ONU/telemetry_current.json` e cache em disco em `%LOCALAPPDATA%\RemoteXPTI\ajin_cache\telemetry_cached.json` (<5ms de latência).
* **Painel `ajin_view.py`**: Apresenta dashboard completo com métricas de disponibilidade global, filtros por porta PON e status, busca rápida, identificação de câmeras IP conectadas e scanner de novos dispositivos.


---

## 2. Integração com [Rede Presídio PRJ](file:///c:/Users/XPTI/Documents/vscode/problema%20de%20rede%20presidio%20PRJ)

### Objetivo
Gerenciar conexões remotas para servidores locais de CFTV/VMS e estações de auditoria do presídio.

### Como Configurar no RemoteXPTI

```json
{
  "id": "presidio-workstation-diag",
  "name": "Workstation Diagnóstico Presídio",
  "ip": "10.40.90.152",
  "port": 3389,
  "user": "admin",
  "group": "Presídio PRJ",
  "fullscreen": false,
  "description": "Host local de execução do diagnostico_cabeada.py e monitoramento de loops L2"
}
```

> [!NOTE]
> Para alcançar a faixa `10.40.88.0/22`, a máquina de origem deve estar conectada fisicamente à rede ou via VPN institucional autorizada.

---

## 3. Integração com [Rede XPTI (MikroTik)](file:///c:/Users/XPTI/Documents/vscode/rede%20XPTI)

### Requisitos de Rede Local
O RemoteXPTI opera a partir da rede local corporativa (`192.168.11.0/24`):
1. **Portas de Saída:**
   * `3389/TCP` (RDP Padrão)
   * `443/TCP` (Sincronização com Supabase Cloud e checagem de releases no GitHub)
2. **Compatibilidade com VoIP:**
   * As chamadas RDP abertas pelo RemoteXPTI não colidem com as regras de firewall do MikroTik ajustadas para os telefones Intelbras TIP 125i (portas UDP 10000–20000).
