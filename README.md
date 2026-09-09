# ⚡ RemoteXPTI - Gerenciador RDP Ágil (Estilo AnyDesk)

O **RemoteXPTI** é um gerenciador de conexões de Área de Trabalho Remota (RDP) moderno, inspirado na interface intuitiva do AnyDesk (cartões de servidores, status de rede online/offline em tempo real, busca rápida e grupos). 

Ele resolve o problema de digitar IP, usuário e senha repetidamente: **basta um clique no card e ele abre a sua sessão RDP (`mstsc.exe`) já autenticado**.

---

## ✨ Recursos Principais

- **Visual Moderno (Dark Mode)**: Layout em grade com cards elegantes, cantos arredondados e suporte a monitores de alta resolução (Hi-DPI).
- **Conexão Direta com Senha**: Injeta credenciais de forma segura através do Windows Credential Manager (`cmdkey`), conectando instantaneamente pelo cliente oficial da Microsoft (`mstsc.exe`).
- **Status Online/Offline em Tempo Real**: Checagem de conectividade da porta RDP em segundo plano (🟢 Online / 🔴 Offline) sem travar a interface.
- **Duplo-clique para Conectar**: Dê dois cliques em qualquer card para iniciar a sessão imediatamente.
- **Criptografia Local**: Todas as senhas salvas são protegidas com chave de criptografia local (AES/Fernet), sem senhas em texto puro desprotegido.
- **Filtros e Organização**:
  - Busca rápida em tempo real por nome, IP ou grupo.
  - Filtro por categorias/grupos (ex: "Produção", "Filiais", "Clientes").
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
