# 🚪 Plano de Integração: Módulo de Portões e Acesso Tuya no RemoteXPTI

> **Projeto:** RemoteXPTI Desktop Moderno  
> **Diretório:** `c:\Users\XPTI\Documents\vscode\remoteXPTI`  
> **Data:** 05/10/2026  
> **Escopo:** Controle de Acesso Restrito ao Modo Desenvolvedor (DEV) & Menu de Configuração Dedicado

---

## 📌 1. Visão Geral e Justificativa

Em vez de criar um aplicativo isolado consumindo memória e rodando separadamente no Windows, integraremos o controle dos portões e portas Tuya diretamente no **RemoteXPTI**, que já é a central de operações utilizada diariamente na empresa.

### 🔒 Regra de Segurança Central (Exclusividade DEV):
* **Somente usuários autenticados como Desenvolvedor (`is_dev`) terão visibilidade e acesso aos portões.**
* Para operadores normais:
  * A aba/botão de portões **não aparece** na barra de navegação.
  * As rotas da API no backend retornam **`403 Forbidden`**.
  * Os atalhos de teclado (ex: **`F7`**) ficam **desativados**, impedindo acionamentos acidentais ou não autorizados.
* Para quem estiver autenticado como Dev (com senha e token de sessão ativa):
  * Acesso total à aba de portões, disparos manuais, atalhos de teclado e menu dedicado de configurações.

---

## 🛡️ 2. Arquitetura de Permissões & Segurança

O RemoteXPTI já possui um sistema nativo de autenticação DEV baseado em hash SHA-256 com Salt (`ConfigManager.is_dev_authenticated()`). Aproveitaremos exatamente essa infraestrutura:

```
                          ┌───────────────────────────┐
                          │   OPERADOR OU DEV NO APP  │
                          └─────────────┬─────────────┘
                                        │
                         Verifica Status DEV via API
                         GET /api/dev/status (is_dev)
                                        │
                   ┌────────────────────┴────────────────────┐
                   ▼                                         ▼
         [ is_dev == false ]                       [ is_dev == true ]
         (Operador Padrão)                         (Modo Desenvolvedor)
         ─────────────────                         ────────────────────
       • Aba "Portões" OCULTA                    • Aba "Portões" VISÍVEL
       • Menu de Portões BLOQUEADO               • Menu de Configuração ATIVO
       • Atalhos F7/F8 DESATIVADOS               • Atalhos F7/F8 HABILITADOS
       • APIs retornam HTTP 403                  • Disparo Liberado via API
```

---

## 🖥️ 3. Interface Visual no React (`desktop_ui`)

### 3.1 Nova Aba na Barra de Título (`TitleBar.tsx`)
Ao lado dos modos de exibição existentes (`Grade`, `Mapa`, `ONUs Ajin`), adicionaremos condicionalmente o botão de **Portões**:

```tsx
{/* Exibido estritamente se o usuário estiver autenticado como DEV */}
{isDev && (
  <button
    onClick={() => setCurrentTab('doors')}
    title="Controle de Portões e Acessos Tuya (Restrito DEV)"
    className={`h-full px-3.5 rounded flex items-center space-x-1.5 text-xs font-bold transition-all ${
      currentTab === 'doors'
        ? 'bg-amber-600 text-white shadow-sm'
        : 'text-amber-400/80 hover:text-amber-300 hover:bg-[#252836]'
    }`}
  >
    <DoorClosed className="w-3.5 h-3.5" />
    <span>Portões [DEV]</span>
  </button>
)}
```

---

### 3.2 Painel Principal de Portões (`DoorsView.tsx`)
Quando a aba estiver ativa, exibe uma grade com cards modernos para cada porta cadastrada:

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  🚪 CONTROLE DE ACESSO & PORTARIAS                       🔒 Sessão DEV Ativa    │
│  Gerenciamento de fechaduras e motores de portão integrados via Tuya Cloud       │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   ┌──────────────────────────┐  ┌──────────────────────────┐                     │
│   │ 🚪 Porta Operacional     │  │ 🚗 Portão Garagem XPTI   │                     │
│   │ Status: 🟢 Nuvem Online  │  │ Status: 🟢 Nuvem Online  │                     │
│   │ Atalho: [ F7 ]           │  │ Atalho: [ F8 ]           │                     │
│   │                          │  │                          │                     │
│   │ ┌──────────────────────┐ │  │ ┌──────────────────────┐ │                     │
│   │ │   🔓 ABRIR PORTA     │ │  │ │   🚗 ABRIR PORTÃO    │ │                     │
│   │ └──────────────────────┘ │  │ └──────────────────────┘ │                     │
│   │ Último uso: 14:38 (Micael│  │ Último uso: 12:10 (Painel│                     │
│   └──────────────────────────┘  └──────────────────────────┘                     │
│                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────┐   │
│   │ 📋 Histórico Recente de Acessos                                          │   │
│   │ • [14:38:12] Porta Operacional acionada via Atalho Global F7 (Sucesso)   │   │
│   │ • [13:10:04] Portão Garagem acionado via Painel DEV (Sucesso)            │   │
│   └──────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

### 3.3 Menu de Configurações Dedicado aos Portões (`DoorsSettingsModal.tsx`)
Acessível a partir da própria aba de portões ou dentro do modal principal de configurações:

1. **Lista de Dispositivos & Cenas:**
   * Adicionar nova porta/portão (Nome, ID da Cena Tuya ou Device ID).
   * Habilitar/Desabilitar cada porta individualmente.
2. **Mapeamento de Teclas de Atalho (Hotkeys):**
   * Gravador interativo de teclas: O usuário clica em *"Gravar Tecla"* e pressiona a tecla no teclado (ex: `F7`, `F8`, `F10`, `Ctrl+Alt+P`).
   * Opção para ativar/desativar atalhos globais.
3. **Comportamento e Feedback:**
   * Tocar bipe suave do Windows ao acionar.
   * Exibir notificação toast no canto da tela (*"Porta Operacional Aberta"*).
4. **Gerenciamento da Conta Tuya:**
   * Status da conexão OAuth (`BxLxxMC` - Tuya Smart).
   * Botão **"Escanear Novo QR Code"**: Se a sessão expirar, permite gerar o QR Code direto no modal para reautenticar sem abrir terminais.

---

## ⚙️ 4. Estrutura do Backend (`desktop_backend.py`)

### 4.1 Novo Módulo: `tuya_access_manager.py`
Ficará na raiz de `remoteXPTI/` gerenciando:
* Leitura e persistência de `doors_config.json`.
* Sessão da Tuya (`session.json`) reaproveitando a biblioteca `tuya_devices`.
* Disparo de cenas Tuya (`cloud_scene`) em threads assíncronas para não bloquear a interface.
* Gerenciamento do listener de atalho global (`pynput` / `keyboard`).

### 4.2 Endpoints REST Protegidos por DEV:

| Método | Endpoint | Proteção | Descrição |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/doors` | **Requer DEV** | Retorna a lista de portas configuradas, status e atalhos. |
| `POST` | `/api/doors/{door_id}/open` | **Requer DEV** | Dispara o comando de abertura da porta especificada. |
| `GET` | `/api/doors/config` | **Requer DEV** | Retorna os parâmetros de configuração e atalhos. |
| `POST` | `/api/doors/config` | **Requer DEV** | Salva novos atalhos, portas ou opções de som/notificação. |
| `POST` | `/api/doors/sync` | **Requer DEV** | Consulta a nuvem da Tuya para atualizar status dos dispositivos. |
| `POST` | `/api/doors/qr-login` | **Requer DEV** | Gera novo QR Code para reautenticação se necessário. |

#### Exemplo de Verificação de Segurança no Backend:
```python
@app.post("/api/doors/{door_id}/open")
async def open_door(door_id: str):
    if not config_mgr.is_dev_authenticated():
        raise HTTPException(
            status_code=403, 
            detail="Acesso negado: Somente usuários em Modo Desenvolvedor podem acionar portões."
        )
    success = access_manager.open_door(door_id)
    if not success:
        raise HTTPException(status_code=500, detail="Falha ao acionar porta na Nuvem Tuya.")
    return {"success": True, "message": "Comando enviado com sucesso!"}
```

---

## 🕒 5. Atalhos Globais e Bandeja do Sistema (Tray)

### 5.1 Listener Global com Verificação de Sessão
O listener de teclas de atalho (`hotkey_manager`) roda em uma thread em segundo plano gerenciada pelo `desktop_backend.py`.

Quando a tecla configurada (ex: `F7`) é pressionada:
1. O listener consulta `config_mgr.is_dev_authenticated()`.
2. Se `False`: Ignora a tecla completamente (nenhum comando é enviado).
3. Se `True`: Envia o disparo de abertura para a Tuya e exibe notificação toast no Windows.

### 5.2 Minimização para a Bandeja no RemoteXPTI
Para que o atalho `F7` funcione mesmo enquanto você está em outros programas:
* No arquivo `launch_modern_desktop.py`, adicionamos o hook de bandeja via `pystray`.
* Ao clicar no botão **"X"** da janela do RemoteXPTI, o aplicativo **não é finalizado**: ele oculta a janela e permanece ativo ao lado do relógio do Windows.
* Ao dar duplo clique no ícone da bandeja, a janela do RemoteXPTI volta para o primeiro plano instantaneamente.

---

## 📂 6. Estrutura de Arquivos Criados / Modificados

```text
remoteXPTI/
│
├── tuya_access_manager.py       # [NOVO] Lógica Tuya, disparo de cenas e listener de hotkeys
├── doors_config.json            # [NOVO] Configuração de portas, atalhos e preferências
│
├── desktop_backend.py           # [MODIFICADO] Rotas /api/doors/* protegidas por is_dev
├── config_manager.py            # [MODIFICADO] Suporte a preferências de portões do dev
├── launch_modern_desktop.py     # [MODIFICADO] Suporte a minimizar para bandeja do Windows
│
└── desktop_ui/src/
    ├── components/
    │   ├── DoorsView.tsx        # [NOVO] Tela principal com cards das portas e histórico
    │   ├── DoorsSettingsModal.tsx # [NOVO] Modal dedicado de configuração de portões e atalhos
    │   ├── TitleBar.tsx         # [MODIFICADO] Botão "Portões [DEV]" na barra superior
    │   └── SettingsModal.tsx    # [MODIFICADO] Link rápido para ajustes de portões
    └── App.tsx                  # [MODIFICADO] Roteamento da aba 'doors'
```

---

## 🚀 7. Cronograma de Implementação Passo a Passo

### Etapa 1: Backend & Segurança (Python)
1. Criar `tuya_access_manager.py` integrando as credenciais e lógica de cena (`cloud_scene`) já validadas (`Porta operacional` ID `o34EQAoAQQniX6Vk`).
2. Adicionar as rotas seguras `/api/doors/*` em `desktop_backend.py` exigindo `is_dev_authenticated()`.
3. Iniciar o listener de atalho `F7` acoplado à validação da sessão DEV.

### Etapa 2: Frontend React (`desktop_ui`)
1. Atualizar `TitleBar.tsx` para exibir o botão **"Portões [DEV]"** quando `isDev === true`.
2. Criar `DoorsView.tsx` com visual Tailwind Dark idêntico ao restante do RemoteXPTI.
3. Criar `DoorsSettingsModal.tsx` com seletor de atalhos e teste de disparo.
4. Conectar o estado do React no `App.tsx`.

### Etapa 3: Bandeja do Windows (System Tray)
1. Integrar `pystray` em `launch_modern_desktop.py` para permitir que o RemoteXPTI fique em segundo plano na bandeja ao fechar a janela.

### Etapa 4: Validação & Build
1. Testar o fluxo completo:
   * Sem login DEV: Verificar que a aba não aparece e `F7` não dispara.
   * Com login DEV: Pressionar `F7` e verificar a abertura da porta.
   * Clicar no botão da interface e validar o acionamento em tempo real.
2. Compilar versão atualizada via `Setup_RemoteXPTI.spec`.

---

## ✅ Conclusão

Com essa arquitetura:
1. **Nenhum aplicativo novo precisa ser instalado no Windows.**
2. **Apenas o usuário DEV tem acesso e controle.**
3. **A interface ganha um design corporativo profissional de alto nível.**
4. **O atalho F7 funciona com o RemoteXPTI minimizado na bandeja.**
