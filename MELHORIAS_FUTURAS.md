# 🚀 RemoteXPTI - Roteiro de Melhorias e Novas Funcionalidades

> **Status Atual**: Versão **v1.6.0** (Canal Público Oficial) estável e consolidada com novos ícones em alta definição, otimização de CPU, atualização automática sob demanda, sincronização em nuvem Supabase e executáveis assinados digitalmente.

Este documento consolida as ideias, arquiteturas e especificações técnicas de melhorias para as próximas versões do **RemoteXPTI**, organizadas por impacto, viabilidade e prioridade.

---

## 📋 Índice
1. [Prioridade 1: Segurança, Confiabilidade e Proteção de Dados](#1-segurança-confiabilidade-e-proteção-de-dados)
2. [Prioridade 2: Monitoramento RDP e Diagnóstico de Rede](#2-monitoramento-rdp-e-diagnóstico-de-rede)
3. [Prioridade 3: Produtividade e Ferramentas Administrativas](#3-produtividade-e-ferramentas-administrativas)
4. [Prioridade 4: Acabamento Visual e Integração com Windows 10/11](#4-acabamento-visual-e-integração-com-windows-1011)
5. [Prioridade 5: Recursos Avançados e Longo Prazo](#5-recursos-avançados-e-longo-prazo)

---

## 1. Segurança, Confiabilidade e Proteção de Dados

### 1.1 Backup Automático e Rotativo Local (`servers.json`)
* **Objetivo**: Proteger os dados contra exclusões acidentais na nuvem, conflitos ou corrupção de arquivos em máquinas de clientes.
* **Funcionamento Técnico**:
  - Toda vez que o método `storage.save()` for acionado ou antes de uma sincronização em nuvem que realize alterações, uma cópia do arquivo atual é salva em:
    `%LOCALAPPDATA%\RemoteXPTI\backups\servers_YYYYMMDD_HHMMSS.json`.
  - Mecanismo rotativo automático: mantém os **últimos 10 snapshots**, deletando cópias mais antigas automaticamente.
  - Na Área do Desenvolvedor (`⚙️ Configurações` -> `🔐 Área do Desenvolvedor`), adicionar o botão **`Restaurar Backup Local`**, listando os snapshots disponíveis para restauração imediata em 1 clique.
* **Benefício**: Tolerância a falhas de nível corporativo e recuperação de desastre instantânea.

### 1.2 Indicador Visual Discreto de Nuvem no Header (☁️)
* **Objetivo**: Fornecer feedback visual ao operador de que a aplicação está conectada e atualizada com o banco central.
* **Funcionamento Técnico**:
  - No cabeçalho principal (ao lado dos botões de busca e filtro), inserir um widget sutil de status:
    - 🟢 **`☁️ Conectado`** (Verde suave): Nuvem operacional e sincronizada com sucesso.
    - 🔄 **`☁️ Sincronizando...`** (Azul com rotação sutil): Consulta ou envio em andamento em segundo plano.
    - 🟡 **`☁️ Offline`** (Laranja): Falha temporária de internet ou banco inacessível (sistema segue operando localmente).
  - **Tooltip ao passar o mouse**: Exibe a data/hora da última sincronização bem-sucedida (ex: *"Última sincronização: 10:45:12 - 56 servidores corporativos ativos"*).
* **Benefício**: Elimina qualquer incerteza se o aplicativo está com os dados mais recentes.

---

## 2. Monitoramento RDP e Diagnóstico de Rede

### 2.1 Medição de Latência em Milissegundos (Ping RTT no Card e no Mapa)
* **Objetivo**: Diagnosticar a qualidade da conexão antes de abrir a sessão RDP.
* **Funcionamento Técnico**:
  - O módulo `status_checker.py` atualmente realiza abertura de socket TCP para determinar se a porta (3389) está aberta.
  - Pode-se registrar o tempo decorrido no handshake TCP (`start_time = time.perf_counter()`), calculando o RTT (*Round-Trip Time*) em milissegundos:
    $$\text{Latência (ms)} = (\text{end\_time} - \text{start\_time}) \times 1000$$
  - Classificação visual nos cards e no popup do mapa Leaflet:
    - 🟢 **Ótima**: `< 40 ms` (Conexão instantânea)
    - 🟡 **Moderada**: `40 ms a 120 ms` (Uso normal, leve atraso visual)
    - 🔴 **Lenta / Instável**: `> 120 ms` (Possível perda de pacotes ou internet congestionada)
* **Benefício**: O técnico identifica lentidão na rede do cliente antes mesmo de se conectar.

### 2.2 Histórico e Filtro de Conexões Recentes ("Último Acesso")
* **Objetivo**: Facilitar o acesso rápido aos servidores mais utilizados pelo usuário.
* **Funcionamento Técnico**:
  - No momento em que o operador clica no card para conectar via RDP (`connect_to_server`), o campo `last_connected` é preenchido com a data/hora atual no ISO 8601.
  - No menu de filtro de grupos ou como botão rápido no topo, adicionar a opção **`🕒 Recentes`**, ordenando os servidores pela data de uso decrescente.
  - Exibir no rodapé do card: *"Último acesso: Hoje às 14:20"* ou *"Último acesso: Há 3 dias"*.
* **Benefício**: Agiliza a rotina diária de operadores que gerenciam dezenas de servidores.

---

## 3. Produtividade e Ferramentas Administrativas

### 3.1 Importação e Exportação em Massa (Excel / CSV)
* **Objetivo**: Permitir que administradores cadastrem ou atualizem dezenas de clientes corporativos de forma ágil através de planilhas.
* **Funcionamento Técnico**:
  - Botão na Área do Desenvolvedor: **`📥 Importar Planilha (XLSX / CSV)`** e **`📤 Exportar Servidores`**.
  - O modelo da planilha contém colunas padronizadas:
    `Nome`, `Host/IP`, `Porta`, `Usuário`, `Senha`, `Grupo`, `Latitude`, `Longitude`, `Modo Admin`, `Tela Cheia`.
  - Validação inteligente: verifica IPs duplicados e campos obrigatórios antes de persistir e enviar ao Supabase.
* **Benefício**: Reduz o tempo de onboarding de novos servidores de horas para segundos.

### 3.2 Atalhos Globais de Teclado
* **Objetivo**: Navegação rápida sem necessidade de mouse para operadores experientes.
* **Mapeamento Sugerido**:
  - `Ctrl + F`: Foca imediatamente no campo de busca de servidores.
  - `Esc`: Limpa a busca e desmarca filtros de grupo.
  - `F5`: Dispara atualização manual forçada (`_on_manual_refresh`), checando status e sincronizando a nuvem.
  - `Ctrl + N`: Abre o modal de adição de servidor (se usuário tiver permissão).
* **Benefício**: Fluidez e agilidade operacional.

---

## 4. Acabamento Visual e Integração com Windows 10/11

### 4.1 Barra de Título Nativa Imersiva Dark (`DWMWA_USE_IMMERSIVE_DARK_MODE`)
* **Objetivo**: Eliminar a barra de título clara/cinza padrão do Tkinter, integrando perfeitamente o aplicativo ao tema escuro do Windows.
* **Funcionamento Técnico**:
  - Chamada à API `dwmapi.dll` do Windows via `ctypes`:
    ```python
    import ctypes
    DWMWA_USE_IMMERSIVE_DARK_MODE = 20
    hwnd = self.winfo_id()
    value = ctypes.c_int(1)
    ctypes.windll.dwmapi.DwmSetWindowAttribute(
        hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value)
    )
    ```
  - Torna a barra de título nativa escura (`#181922`) com botões de fechar e minimizar perfeitamente integrados ao design moderno do app.
* **Benefício**: Aparência visual executiva, indistinguível de ferramentas modernas da Microsoft, AnyDesk e VS Code.

### 4.2 Notificações Nativas do Windows (Toasts)
* **Objetivo**: Alertar o operador sobre eventos críticos em segundo plano.
* **Funcionamento Técnico**:
  - Utilizar a API nativa do Windows Toast (`win11toast` ou PowerShell nativo sem dependências externas pesadas).
  - Cenários de disparo:
    - Alerta de Incidente: Servidor corporativo crítico monitorado caiu e ficou offline.
    - Novo Servidor Corporativo: Notificação discreta quando a empresa publicar um novo servidor na nuvem.
  - Opção no menu de configurações para desativar notificações sonoras.
* **Benefício**: Proatividade no suporte técnico sem precisar manter a janela principal aberta em primeiro plano.

---

## 5. Recursos Avançados e Longo Prazo

### 5.1 Cache Local Offline de Map Tiles (Leaflet)
* **Objetivo**: Permitir o funcionamento completo do Mapa de Acessos mesmo em redes totalmente isoladas, clientes sem acesso à internet externa ou notebooks em trânsito.
* **Funcionamento Técnico**:
  - O servidor web local embutido (`web_map_manager.py`) intercepta requisições de quadrantes (*tiles*) e armazena em `%LOCALAPPDATA%\RemoteXPTI\map_cache\`.
  - Se houver conexão, baixa e salva no cache; se offline, serve os tiles locais.
* **Benefício**: Disponibilidade 100% contínua do mapa em qualquer cenário.

### 5.2 Miniaturas Dinâmicas Pós-Desconexão (Live Thumbnail Capture)
* **Objetivo**: Exibir nos cards uma miniatura visual real da última tela do servidor acessado.
* **Funcionamento Técnico**:
  - O módulo `PreviewManager.capture_rdp_window` já possui o código base de captura de janela do `mstsc.exe`.
  - Pode-se aprimorar para capturar um frame de tela logo antes de fechar a sessão RDP, gerando a miniatura real e salvando na pasta de miniaturas.
* **Benefício**: Facilidade visual para identificar rapidamente o ambiente de trabalho de cada cliente.

---

## 📌 Tabela de Priorização e Estimativas

| Recurso | Categoria | Impacto | Complexidade | Prioridade Recomendada |
| :--- | :--- | :--- | :--- | :--- |
| **Backup Automático Local** | Confiabilidade | Alto | Baixa (~1h) | 🟢 Alta |
| **Indicador Visual de Nuvem (☁️)** | Usabilidade | Médio | Baixa (~40min) | 🟢 Alta |
| **Barra de Título Imersiva Dark** | Visual | Alto | Muito Baixa (~20min) | 🟢 Alta |
| **Medição de Latência RTT (ms)** | Diagnóstico | Alto | Média (~2h) | 🟡 Média |
| **Atalhos de Teclado Globais** | Ergonomia | Médio | Baixa (~30min) | 🟡 Média |
| **Importação/Exportação Excel** | Gestão | Alto | Média (~2h) | 🟡 Média |
| **Notificações Toasts Windows** | Proatividade | Médio | Média (~1.5h) | ⚪ Futura |
| **Cache Offline de Map Tiles** | Conectividade | Médio | Alta (~3h) | ⚪ Futura |
