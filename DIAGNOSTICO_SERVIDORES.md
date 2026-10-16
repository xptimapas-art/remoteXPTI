# Guia de Diagnóstico Remoto de Servidores (CLI)

Este módulo permite auditar a saúde de qualquer um dos **56 servidores cadastrados** no `servers.json` (redes BEMTEVI, SEJURI, AJIN e XPTI) diretamente via linha de comando ou através do assistente de IA.

---

## 🚀 Como Usar a Ferramenta CLI

O script está localizado em `remoteXPTI/diagnostico_servidor.py`.

### 1. Diagnóstico Rápido de um Servidor
Audita instantaneamente memória RAM, tempo de atividade (Uptime), espaço de todos os discos e Top 10 processos consumidores de RAM:
```bash
python diagnostico_servidor.py --server "Lages"
# ou passando o IP direto:
python diagnostico_servidor.py --server 10.189.112.10
```

### 2. Diagnóstico Aprofundado (`--deep`)
Além dos dados básicos, audita o status de todos os **VSS Writers (Volume Shadow Copy)** e busca eventos de **OutOfMemory**, falhas de backup ou estouro de memória nas últimas 24 horas:
```bash
python diagnostico_servidor.py --server "Lages" --deep
```

### 3. Listar Servidores Disponíveis no Catálogo
```bash
python diagnostico_servidor.py --list
```

---

## 🧠 Como Funciona a Comunicação Remota

1. **Descriptografia Automática:** O script lê o arquivo `servers.json` e descriptografa as credenciais usando o cofre seguro local (`.secret.key` / Fernet).
2. **Protocolo WinRM / WS-Man (Porta 5985):** Conecta via HTTP NTLM utilizando o módulo `pywinrm`. Isso dispensa a necessidade de ingressar o computador de gerenciamento no domínio do cliente (`bemtevi.net`) e ignora as restrições normais de `TrustedHosts`.
3. **Execução sem Instalação de Agentes:** Não é necessário instalar nenhum agente adicional nos servidores; a coleta é feita nativamente via APIs do Windows (`Win32_OperatingSystem`, `Win32_LogicalDisk`, `Get-Process`, `vssadmin` e `Get-WinEvent`).

---

## 📋 Registro de Incidente: Caso Servidor de Lages (05/10/2026)

* **Host:** `10.189.112.10` (Nome de rede: `VMU-LGS`)
* **Sintoma:** Servidor travou com consumo cravado em 64 GB de RAM (99% de uso) sem motivo aparente.
* **Diagnóstico Coletado:**
  1. Às 07:46 - 08:23, o **Veeam Agent** (`Veeam.EndPoint.Service.exe`) tentou executar a rotina de backup criando snapshots via **VSS**.
  2. O disco de gravações do Digifort (`F:`, volume RAID de ~82 Terabytes) e o disco `E:` estavam com **0% de espaço livre**.
  3. Sem espaço em disco para a área de sombra do VSS, o subsistema de I/O e o Veeam retiveram os blocos diferenciais na memória RAM.
  4. O Veeam entrou em estouro de pilha (*Stack Overflow 0xc00000fd*) e travou com `System.OutOfMemoryException`.
  5. A memória Commit do Windows foi 100% drenada até travar a máquina.
* **Ação Corretiva Inicial (05/10):** 
  - Reinicialização do servidor (memória reduziu para 4.7 GB).

---

## 🚨 Reincidência Crítica Identificada (06/10/2026 - 08:45)

* **Sintoma:** O servidor reiniciou por volta das 02:00 da madrugada (Uptime de 6h 41m), mas a memória RAM escalou novamente até **60.80 GB de 63.63 GB (95.6% em uso)** e o host **congelou/caiu às 08:46 AM**.
* **Mapeamento Exato da Memória Coletado:**
  * **Processos em Modo Usuário:** Apenas **~6.01 GB** (Digifort `Server64` com 3.3 GB, `avp` com 186 MB, `sqlservr` com 160 MB).
  * **Vazamento no Kernel do Windows:**
    * **Paged Pool:** **68.16 GB (69.795 MB)** *(Normal: 300 MB a 1 GB)*.
    * **Non-Paged Pool:** **15.12 GB (15.483 MB)** *(Normal: 200 MB a 800 MB)*.
    * **Memória Commit:** **91.63 GB** de um limite de **102.47 GB**.
* **Causa Raiz Definitiva do Vazamento:**
  1. O volume de gravação do Digifort (`F:`, 82 TB) e o volume `E:` (15 GB) continuam com **0% de espaço livre (0 bytes livres)**.
  2. Os minifilters de proteção e backup do Kaspersky (`KLIF.KES-12-12` e `klbackupflt.KES-12-12`, com 14 instâncias ativas no filesystem) e o subsistema NTFS tentam interceptar e alocar descritores de gravação para as câmeras que continuam chegando sem parar.
  3. Sem espaço nos blocos de disco, as operações de I/O e descritores de arquivos são empilhados no **Paged Pool** da memória RAM a uma taxa de **~300 a 500 MB por minuto**.
  4. Ao atingir o limite de Commit da máquina (~100 GB), o kernel do Windows esgota a tabela de memória paginada e entra em colapso (*Kernel Pool Exhaustion*), travando a rede e congelando o sistema operacional.
* **Ações Definitivas Mandatórias:**
  1. **Liberar Espaço Imediato no Disco F: / E:** Ajustar a cota de auto-limpeza do Digifort para manter no mínimo **5% a 10% de espaço livre** no volume `F:` (cerca de 4 a 8 TB livres como margem de manobra do NTFS).
  2. **Exclusão no Kaspersky (KES):** Adicionar o diretório de gravações e os discos `E:` e `F:` nas **Exclusões de Verificação de Arquivos em Tempo Real** do Kaspersky Endpoint Security para que o minifilter `KLIF` não intercepte os blocos contínuos de gravação de vídeo.
  3. **Desativar Backup do Veeam para o Volume F:** Manter o backup do Veeam Agent restrito apenas ao volume `C:` (Sistema Operacional) e banco SQL, nunca incluindo os volumes de 82 TB de CFTV.

---

## ✅ Resolução Definitiva Aplicada (06/10/2026 - 10:05)

1. **Expurgo Automático Configurado:** Margem de espaço livre do Digifort configurada para **10%** (garantindo ~8.2 TB de margem no volume de 82 TB).
2. **Migração das 20 Câmeras do Micro SD (E:) para o Storage (F:):** Identificado que 20 câmeras (`LPR` e `-Copy`) estavam gravando no cartão MicroSD `E:` (Dell IDSDM de 15 GB). Todas as 20 câmeras foram migradas com sucesso para o disco principal `F:`. Gravações no disco `E:` cessaram completamente às 10:03:51 e foram confirmadas 100% ativas no disco `F:`.
3. **Limpeza da Unidade Fantasma G:** A letra `G:` (partição residual de 189 MB) foi desvinculada para não poluir o sistema.
4. **Rotulação dos Volumes:**
   - `C:`: Sistema Operacional (1.1 TB)
   - `E:`: `apenas micro SD` (15 GB)
   - `F:`: `gravacoes do digifort` (82 TB, 26.5 TB livres)
5. **Estabilização da Memória RAM:** Consumo estabilizado em **~5.7 GB de 63.6 GB (9% em uso, 58 GB livres)**, eliminando o vazamento de memória no Kernel Pool.

