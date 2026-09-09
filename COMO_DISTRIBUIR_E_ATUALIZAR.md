# 🚀 Guia: Como Distribuir para Clientes e Enviar Atualizações Automáticas (100% Executável .exe)

Este guia explica como instalar o **RemoteXPTI** nos computadores dos clientes usando um **único arquivo .exe** (sem arquivos `.bat`) e como enviar atualizações com 1 clique pelo **GitHub Releases**.

---

## 📦 1. Como Distribuir para os Clientes (Apenas 1 Arquivo .exe)

Você só precisa enviar um único arquivo para o cliente:
- **`dist\Setup_RemoteXPTI.exe`**

### O que o cliente faz:
1. O cliente dá **dois cliques** em `Setup_RemoteXPTI.exe`.
2. Um assistente gráfico elegante (no mesmo tema dark do AnyDesk) se abre.
3. O cliente clica em **"Instalar Agora"**.
4. O instalador:
   - Extrai e instala o programa na pasta de aplicativos (`AppData\Programs\RemoteXPTI`).
   - Importa automaticamente todos os **8 servidores** já pré-configurados.
   - Cria os atalhos com ícone na **Área de Trabalho** e no **Menu Iniciar**.
   - Abre o programa automaticamente ao clicar em "Concluir e Abrir".
5. **Zero arquivos .bat, zero prompt de comando, zero telas pretas!**

---

## 🔄 2. Como Enviar Atualizações Automáticas via GitHub

Quando você adicionar novos servidores ou lançar uma versão nova:

### Passo 1: Configure seu Repositório (apenas 1 vez)
1. Abra o RemoteXPTI.
2. Clique no botão **`🚀 Atualizações`** no topo.
3. Digite o seu repositório no GitHub (exemplo: `seu-usuario/remoteXPTI`) e clique em **Salvar**.

### Passo 2: Quando for lançar uma versão nova:
1. Abra o arquivo **`version.py`** e altere o número (ex: `CURRENT_VERSION = "1.1.0"`).
2. Execute no terminal:
   ```bash
   python build_all.py
   ```
   *(Ele vai compilar o novo `RemoteXPTI.exe` e o novo `Setup_RemoteXPTI.exe` automaticamente).*
3. Acesse o seu repositório no GitHub no navegador:
   - Vá em **Releases** > **Draft a new release**.
   - Em **Tag version**, digite: `v1.1.0`.
   - Em **Release title**, digite: `RemoteXPTI v1.1.0`.
   - Escreva as notas da versão (ex: *"Novos servidores adicionados"*).
   - Arraste o arquivo **`dist\RemoteXPTI.exe`** para a área de anexos da release.
   - Clique em **Publish release**.

### Passo 3: O que acontece nos computadores dos clientes:
- Quando o cliente abrir o programa (ou clicar em **`🚀 Atualizações`**):
  - O app avisa que há uma nova versão disponível (`v1.1.0`).
  - O cliente clica em **`⬇️ Baixar e Atualizar Agora`**.
  - O programa faz o download com barra de progresso, atualiza o executável e reabre sozinho na versão nova com 1 clique!
