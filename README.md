# ⚡ RemoteXPTI - Gerenciador RDP Ágil & Central NOC de Monitoramento

O **RemoteXPTI** é um aplicativo desktop moderno para gerenciamento de conexões de Área de Trabalho Remota (RDP) e supervisão de infraestrutura em tempo real, inspirado na ergonomia visual de ferramentas como AnyDesk e Digifort.

Ele elimina a necessidade de digitar endereços IP, portas, credenciais e senhas repetidamente: **basta um clique no card e ele abre a sua sessão RDP (`mstsc.exe`) já autenticada**. Além do gerenciamento RDP, o RemoteXPTI integra um **Painel NOC completo para supervisão óptica da OLT C-Data FD1108S (Ajin)** e um **Mapa Interativo** de geolocalização dos ativos.

---

## 🧭 Modos de Visualização (Seletor Triplo)

No topo da aplicação, o seletor integrado permite alternar instantaneamente entre três modos operacionais sem reiniciar serviços ou perder o estado da tela:

| Modo | Finalidade | Descrição |
| :--- | :--- | :--- |
| **🗂️ Grade** | Conexões RDP Ágeis | Visual clássico estilo AnyDesk com cards dos servidores cadastrados, status de rede em tempo real, grupos e ações rápidas. |
| **🗺️ Mapa** | Geolocalização de Ativos | Visualização geográfica interativa integrada via Leaflet e Edge WebView2 nativo para conferência espacial dos servidores e pontos. |
| **🌐 ONUs Ajin** | Central de Supervisão NOC | Painel de monitoramento contínuo das ONUs conectadas na OLT C-Data FD1108S, telemetria em tempo real, status de links, câmeras e scanner. |

---

## 🌐 Central NOC de ONUs Ajin

A aba **ONUs Ajin** transforma o RemoteXPTI em um centro de operações de rede (NOC) dedicado para a infraestrutura óptica do projeto Ajin, operando através de dois módulos de alta performance:

### 1. Painel NOC Operacional (`ajin_view.py`)
Desenvolvido com foco em velocidade e visibilidade para equipes de plantão técnico:
- **Cards de Métricas Consolidadas (Topo)**:
  - 🟢 **Em Operação (Online)**: Total de ONUs ativas com link óptico estabelecido.
  - 🔴 **Fora de Operação (Offline)**: Dispositivos com perda de sinal ou interrupção de energia.
  - 🔵 **Total Homologadas**: Quantidade total de ONUs cadastradas no parque.
  - 🟣 **Disponibilidade (%)**: Índice percentual de SLA e saúde geral da rede óptica.
- **Filtros Dinâmicos Instantâneos**:
  - **Filtro de Status**: Segmentado em `Todas`, `Online` e `Offline`.
  - **Filtro por Porta PON**: ComboBox para isolar portas específicas (`Slot1-PON1`, `Slot1-PON2`, `Slot2-PON1`, `Slot2-PON2`).
  - **Busca em Tempo Real (Debounce 90ms)**: Busca dinâmica por nome do ponto, rua/descrição, endereço MAC, ID da ONU ou IP de câmeras vinculadas.
- **Grade e Tabela Detalhada de Dispositivos**:
  - *Status Pill*: Identificação visual imediata (Online/Offline).
  - *Identificação do Ponto*: Nome legível (ex: `Ponto 10`) e descrição de localização (rua, cruzamento, referência).
  - *Porta & ID*: Identificação exata da porta PON e índice físico na OLT (ex: `Slot1-PON1 #7`).
  - *MAC & Fabricante*: Endereço físico e reconhecimento automático de vendor (C-Data, Cianet CTS, etc.).
  - *Câmeras Vinculadas*: Lista os IPs das câmeras CFTV conectadas às portas LAN da ONU.
  - *Tempo no Estado (Uptime / Downtime)*: Contador humanizado do tempo de atividade contínua ou indisponibilidade (ex: `Online há 27d 6h 18m`).
- **Modal de Edição Rápida (`EditLabelDialog`)**:
  - Permite alterar o nome do ponto e a rua em 1 clique direto pela tabela (ícone ✏️).
  - Atualização com persistência atômica tanto no cache local quanto na nuvem Supabase em background.
- **Modal do Scanner de Rede (`ScannerModal`)**:
  - Monitora o surgimento de novos MACs conectados na fibra óptica que ainda não foram homologados.
  - Botão com badge indicador de contagem (`🔍 Scanner (N)`).
  - Ação **+ Homologar** integrada para cadastrar, nomear e inserir novos dispositivos na operação em poucos segundos.

### 2. Motor de Telemetria Ultrarrápido (`ajin_manager.py`)
Módulo singleton desacoplado projetado para ter **impacto zero de CPU e latência mínima (< 5ms)**:
- **Arquitetura Multi-Tier com Fallback Automático**:
  1. **Nuvem (Supabase REST)**: Consulta universal via tabela `ajin_telemetry` usando chamadas REST leves com timeout seguro.
  2. **Fallback Offline Local**: Se a internet ou a nuvem estiver indisponível, consome automaticamente o snapshot consolidado em `logs_ONU/telemetry_current.json` ou compila os dados na hora a partir dos logs locais.
  3. **Cache de Disco Local**: Armazena o último estado conhecido em `%LOCALAPPDATA%\RemoteXPTI\ajin_cache\telemetry_cached.json`, garantindo abertura com **0ms de atraso** na inicialização da aplicação.
- **Debounce Inteligente (4s)**: Evita requisições redundantes à rede em atualizações repetidas.
- **Padrão Observer / Listeners**: Notificação assíncrona orientada a eventos para que a interface gráfica (`ajin_view.py`) receba os novos dados sem travamento ou bloqueio do thread principal do Tkinter.

---

## ✨ Recursos de Gerenciamento RDP

- **Visual Moderno (Dark Mode)**: Layout em grade com cards elegantes, cantos arredondados e suporte a telas Hi-DPI.
- **Conexão Direta com Senha**: Injeta credenciais de forma segura através do Windows Credential Manager (`cmdkey`), conectando instantaneamente pelo cliente oficial da Microsoft (`mstsc.exe`).
- **Status Online/Offline em Tempo Real**: Checagem contínua de conectividade da porta RDP em segundo plano (🟢 Online / 🔴 Offline).
- **Duplo-clique para Conectar**: Dê dois cliques em qualquer card para iniciar a sessão imediatamente.
- **Criptografia Local**: Todas as senhas salvas são protegidas com chave de criptografia local (AES/Fernet), sem senhas em texto puro desprotegido.
- **Filtros e Organização**:
  - Busca rápida em tempo real por nome, IP ou grupo.
  - Filtro por categorias/grupos (ex: "Produção", "Filiais", "Clientes", "Presídio PRJ").
- **Ações Rápidas por Servidor**:
  - ⚡ Conectar
  - 📋 Copiar IP
  - ✏️ Editar configurações
  - 🗑️ Excluir
- **Opções Avançadas por Servidor**:
  - Suporte a portas não-padrão (ex: `192.168.1.100:33890`).
  - Abrir em Tela Cheia (`/f`).
  - Sessão de Administrador/Console (`/admin`).
  - Suporte a Múltiplos Monitores (`/multimon`).

---

## 🔌 Guia de Integração com Outros Projetos

O **RemoteXPTI** funciona de maneira interoperável com as demais soluções da infraestrutura XPTI. Para orientações detalhadas de comunicação entre sistemas, fluxos de rede e parâmetros de ambiente, consulte:

👉 [**Guia de Integração Técnico (INTEGRACAO.md)**](file:///c:/Users/XPTI/Documents/vscode/remoteXPTI/INTEGRACAO.md)

Principais projetos integrados:
- [**Monitoramento AJIN**](file:///c:/Users/XPTI/Documents/vscode/monitoramentoAJIN): Coleta contínua da OLT C-Data, telemetria consolidada em `telemetry_current.json`, sincronização Supabase e gestão do servidor Dell PowerEdge R740.
- [**Rede Presídio PRJ**](file:///c:/Users/XPTI/Documents/vscode/problema%20de%20rede%20presidio%20PRJ): Conexões remotas para diagnóstico de CFTV, VMS e monitoramento de loops de camada 2.
- [**Rede XPTI (MikroTik)**](file:///c:/Users/XPTI/Documents/vscode/rede%20XPTI): Regras de firewall, túneis ZeroTier e compatibilidade com tráfego de telefonia VoIP.

---

## 🏗️ Estrutura do Projeto

```text
remoteXPTI/
├── app.py                      # Janela principal, orquestração de abas e ciclo de vida
├── main.py                     # Ponto de entrada da aplicação e inicialização
├── ajin_manager.py             # Motor singleton de telemetria das ONUs com cache <5ms
├── ajin_view.py                # Interface gráfica do Painel NOC (métricas, filtros e tabela)
├── map_manager.py              # Controlador de mapas geográficos e camadas
├── web_map_manager.py          # Renderização web do mapa interativo via Edge WebView2
├── rdp_manager.py              # Execução e autenticação do mstsc.exe via cmdkey
├── storage.py                  # Persistência de servidores com criptografia AES/Fernet
├── config_manager.py           # Gestão de configurações locais e credenciais de nuvem
├── cloud_sync.py               # Sincronização em nuvem via Supabase
├── splash_screen.py            # Splash screen moderna sem flickering
├── build_exe.bat               # Script para compilação do executável .exe
├── INTEGRACAO.md               # Guia de integração técnica com o ecossistema XPTI
└── requirements.txt            # Dependências Python (customtkinter, cryptography, etc.)
```

---

## 🚀 Como Executar

### Pré-requisitos
- Windows 10 ou 11
- Python 3.10 ou superior

### Instalação e Execução
```bash
# 1. Instale as dependências
pip install -r requirements.txt

# 2. Inicie o aplicativo
python main.py
```

---

## 📦 Gerando o Executável (.exe)

Para usar o programa em computadores que não possuem o Python instalado:

1. Dê um duplo clique no arquivo **`build_exe.bat`** (ou execute via terminal).
2. Ao finalizar, o executável independente estará na pasta **`dist\RemoteXPTI.exe`**.

---

## 🔒 Como Funciona a Autenticação RDP

O Windows por padrão não permite passar senhas diretamente via linha de comando no `mstsc.exe`. 
O **RemoteXPTI** resolve isso de forma nativa e limpa:
1. Quando você clica em "Conectar", o aplicativo cadastra a credencial no cofre do Windows via:
   ```cmd
   cmdkey /generic:TERMSRV/<IP_DO_SERVIDOR> /user:<USUARIO> /pass:<SENHA>
   ```
2. Em seguida, inicia o cliente oficial:
   ```cmd
   mstsc /v:<IP_DO_SERVIDOR>
   ```
3. O cliente RDP detecta a chave `TERMSRV/` e realiza o login automático sem abrir caixas de diálogo solicitando senha.
