# Plano de qualidade e refatoração do RemoteXPTI

**Revisão:** 16/10/2026. **Base:** `2.2.3-beta.1`, commit `c1a424fc34ba661d8aa82bc2f1dd35d70de3a63c`.

Substitui a avaliação da 2.1.9. As referências de linha correspondem ao commit acima. Esta etapa alterou documentação e produziu diagnósticos locais; não modificou código de produção, credenciais, serviços remotos ou a instalação CLIENT.

**Atualização de execução — 16/10/2026:** depois da revisão, o usuário autorizou corrigir R01–R04. As correções foram implementadas no código e disponibilizadas no DEV, com regressões e validação isolada de um EXE onefile. O CLIENT instalado permanece separado e nenhuma release foi publicada nesta etapa. Os achados abaixo registram o diagnóstico da base; o estado das correções está em [docs/CORRECOES_PERSISTENCIA_E_SYNC.md](docs/CORRECOES_PERSISTENCIA_E_SYNC.md). R05–R10 continuam no backlog.

## 1. Recomendação

A distribuição de R01–R04 e dos ajustes posteriores foi autorizada como
pré-release 2.2.4-beta.1. O escopo e os limites estão nas
[notas da beta](docs/RELEASE_2.2.4-beta.1.md); R05–R10 continuam no backlog.

**Manter a base e refatorar por etapas. Não recomendo reescrever do zero.**

O app tem separação CLIENT/DEV, distribuição com verificação de pacote, atualização por canal, integração de portas, vídeo e regras AJIN que precisariam ser reconstruídas e homologadas. A dívida técnica está concentrada em persistência, sincronização, inicialização global, contratos e coexistência das duas interfaces.

As primeiras entregas devem impedir perda de dados e sucesso falso. Reorganizar pastas ou diminuir linhas antes disso não resolve os principais riscos. Mudança de layout precisa de apresentação e aprovação visual prévias.

## 2. Escopo, medições e validação

Foram examinados os módulos Python da raiz, ferramentas, frontend, testes, SQL local, build, instalador e documentos operacionais. A análise aprofundou os caminhos modernos de armazenamento, nuvem, portas, eventos, mapa e encerramento; não representa execução de todos os recursos legados.

| Verificação executada | Resultado | Limite da evidência |
|---|---|---|
| `py -3.12 -m unittest discover -s tests` | **182 testes aprovados**, 8,949 s | Serviços/dispositivos simulados |
| `node --test desktop_ui/tests/ajin.test.cjs` | **14 testes aprovados** | Regras de dados AJIN; não toda a UI |
| `tsc -b`, em `desktop_ui` | **Aprovado** | Configuração atual sem `strict` |
| Oxlint, saída JSON | **21 avisos, zero erros** | Os avisos não fazem o comando falhar |
| Reproduções isoladas com AST e arquivos temporários | **5 comportamentos problemáticos confirmados** | Sem inicializar backend real ou alterar perfis |
| Registro da release anterior | 5 assets conferidos; canais e download validados | Evidência anterior, não nova instalação nesta revisão |

Scripts/relatórios: `.test-artifacts/quality-*-2026-10-16.*`, ignorados pelo Git. Evidência anterior de atualização: `.test-artifacts/published-2.2.3-beta.1-update-result.json`. Não foram acionados portões, abertas conexões RDP, consultadas policies efetivas do Supabase nem alterado o servidor AJIN. Não foi necessário recompilar o EXE para esta revisão de documentação.

| Indicador atual | Resultado | Interpretação |
|---|---:|---|
| Python na raiz | 44 arquivos / 16.124 linhas | Inclui app, legado, instalador, build e utilitários |
| Python em `tools/` | 4 arquivos / 544 linhas | Exclui diagnósticos temporários |
| Python em `tests/` | 15 arquivos / 2.293 linhas | Descoberta controlada em `tests/` |
| Grafo moderno de imports locais | 27 módulos / 6.672 linhas | Imports estáticos, inclusive dentro de funções |
| Exclusivos do grafo de `main.py` | 10 módulos / 8.252 linhas | Inclui desinstalador e shim; não autoriza exclusão |
| Frontend `src/` | 25 arquivos TS/TSX/CSS / 4.958 linhas | 20 TS/TSX e 5 CSS; sem assets/dependências |
| `any` explícitos no TypeScript | 14 | AST; eram 27 na avaliação antiga |
| Chamadas diretas a `fetch` | 37 | 14 em `App.tsx` |
| Rotas locais | 48 HTTP + 1 WebSocket | Concentradas em `desktop_backend.py` |
| Capturas genéricas na raiz Python | 262 | `Exception`, `BaseException` ou sem tipo |
| Capturas apenas com `pass` na raiz | 133 | Exigem análise contextual; nem todas são defeitos |

Os escopos Python antigo/atual diferem. Linhas incluem strings, comentários e vazios; tamanho não é nota de qualidade. Expressões muito longas em poucas linhas também prejudicam manutenção.

| Área que concentra responsabilidades | Tamanho | Próxima separação útil |
|---|---:|---|
| `desktop_backend.py` | 1.193 linhas / 49 rotas | Composição, serviços, schemas e routers |
| `launch_modern_desktop.py` | `main()` com 286 linhas | Dono e encerramento dos recursos |
| `tuya_access_manager.py` | 782 linhas | Configuração, sessão, comandos e feedback |
| `MapView.tsx` | 1.075 linhas | Camadas e seleção, preservando desempenho |
| `App.tsx` | 560 linhas | API, eventos e dados por recurso |
| `SettingsModal.tsx` | 550 linhas | Canal/update, acesso DEV e sincronização |
| Quatro maiores módulos legados | 6.393 linhas | Paridade antes da retirada |

## 3. O que já foi resolvido ou melhorado

| Tema anterior | Estado atual | Pendência |
|---|---|---|
| Reconexão WS após desmontagem | Flag de atividade, cancelamento do timer e cleanup em `App.tsx:135` | Extrair hook testável e padronizar cancelamento das requisições |
| Texto externo nos tooltips | Servidor/ONU usam elementos com `textContent`; número do SVG também | Manter testes contra HTML externo |
| Recriação de markers AJIN | Cache preserva objetos; efeito de servidores separado; sem animações contínuas AJIN | Medir camada de servidores, que ainda usa `clearLayers()` |
| Ícones residuais da bandeja | Ocultação antes do stop e controle DEV direcionado | Encerramento dos demais workers |
| Edição concorrente de portas | Lock, comparação com original, temporário único e `fsync` | Caminho da instalação CLIENT nova ainda falha; R01 |
| Compartilhamento de portas/câmeras | Payload Fernet, chave local DPAPI e PATCH condicional por revisão | Ainda usa registro reservado em servidores; sessão Tuya tem outra política |
| Renovação Tuya | Validação, precedência temporal e PATCH condicional testados | Evoluir identidade e armazenamento mantendo compatibilidade |
| Falsos alertas RDP | Confirmação temporal, lock por servidor e bloqueio de scans sobrepostos | Preservar limites na refatoração |
| Update/pacote | Manifesto/hash/tamanho, pending persistente, helper, saúde e recuperação; frontend/payload conferidos | Pipeline e homologação completa de instalação/rollback |
| Estado inicial AJIN | Vazio, conectando e stale; sem resultados operacionais fictícios | Uniformizar contratos e falhas das outras áreas |

O perfil anterior do mapa registrou 59 markers preservados em cinco snapshots de uptime, sem inserções/remoções, contra 300 inserções e 300 remoções antes. Evidência: `.test-artifacts/ajin-marker-profile-after.json`. Não é garantia de FPS em qualquer computador.

## 4. Achados atuais

**P0:** risco de perda de dados ou acesso que deve ser resolvido/verificado antes de ampliar distribuição. **P1:** falha funcional/confiabilidade. **P2:** manutenção. Prioridade não significa que todos os clientes já foram afetados.

### R01 — P0: portas podem ser salvas na extração temporária de uma instalação nova

**Evidência:** `tuya_access_manager.py:105–131`. O DEV retorna o perfil correto. No CLIENT, sem configuração prévia em `%LOCALAPPDATA%`, o destino é `Path(__file__).parent / doors_config.json`, mesmo que o arquivo não exista. A sessão possui fallback semelhante e caminho absoluto antigo de desenvolvimento.

**Confirmado:** o método original, com perfil vazio e `__file__` numa pasta que representa o bundle onefile, escolheu essa pasta temporária. Instalação existente com arquivo no perfil não percorre esse fallback.

**Correção:** escrever sempre em caminho persistente. Caminhos antigos servem apenas à migração, sem sobrescrever destino válido, com backup e leitura verificada. Remover dependência do caminho pessoal. Tratar separadamente `get_data_dir()`, que mantém servidores/chave ao lado do EXE no CLIENT, preservando compatibilidade até migração própria.

**Aceite:** EXE com perfil vazio salva portas/sessão, encerra, perde a extração temporária, reabre e recupera os dados. DEV permanece separado; nenhuma escrita no bundle.

### R02 — P0: retorno parcial da nuvem pode remover servidores válidos

**Evidência:** `cloud_sync.py:125–148` consulta `select=*` sem paginação/comprovação de completude. `storage.py:296` em diante considera ausência como exclusão; o backend repassa a lista diretamente.

**Confirmado:** lista com corporativos A/B e particular L, recebendo somente A, perde B e preserva L. Isso é correto para snapshot completo, mas perigoso com truncamento/filtro. Não foi comprovado truncamento da resposta atual do Supabase.

**Correção:** paginação estável, validação de IDs/formato e estado explícito de completude. Diferenciar erro, parcial e vazio confirmado. Não remover por ausência antes de completar todas as páginas. Evoluir para exclusões explícitas/versionadas e proteger edições locais concorrentes; manter cópia recuperável antes de remover.

**Aceite:** falha na segunda página, lista inválida ou concorrência não apagam dados; exclusão real confirmada continua propagando; particulares permanecem locais.

### R03 — P1: erro ao salvar não impede sucesso na API

**Evidência:** `storage.py:139–151` captura falha de replace e retorna normalmente; memória já foi alterada. Rotas como `desktop_backend.py:505` respondem `created` e podem enviar à nuvem. `ConfigManager.save()` também oculta a falha do chamador. Um único nome `.tmp` é compartilhado sem lock geral.

**Confirmado:** `PermissionError` simulado conserva o arquivo anterior, deixa memória diferente do disco e não gera exceção ao chamador.

**Correção:** repository com lock, snapshot candidato, temporário único, replace e atualização de memória após persistência. Propagar erro à API. Aplicar padrão às preferências e retirar saves duplicados depois de definir o dono da transação.

**Aceite:** disco cheio/acesso negado/concorrência não geram sucesso falso ou divergência silenciosa. Formulário permanece aberto e nuvem não recebe edição local que falhou sem um estado explícito de recuperação.

### R04 — P1: favorito é alterado numa cópia e não persiste

**Evidência:** `storage.py:268–274` retorna cópia em `get_server()`. A rota `desktop_backend.py:547–552` muda `favorite` nessa cópia e salva a lista original. `App.tsx` muda a UI antes da confirmação, ignora `res.ok` e não reverte falha.

**Confirmado:** rota original com armazenamento temporário responde `favorite: true`, mas lista e JSON continuam sem a alteração. Recarregar perde o favorito.

**Correção/aceite:** método próprio altera e salva o registro sob lock; UI confirma o valor persistido ou reverte com erro. Favorito deve sobreviver ao reload/reinício e ser tratado como preferência local, preservada no merge corporativo.

### R05 — P0 para verificação: permissões e cofre corporativo ainda têm mecanismos legados

**Evidência local:** `supabase_schema.sql:27–35` contém política `FOR ALL USING(true) WITH CHECK(true)` sem restrição de papel. `storage.py:26–82` mantém chave mestre embutida e retorna a entrada quando não decifra. A sessão Tuya é transportada em `notes` de registro reservado. O estado DEV persistido localmente não representa autorização validada no servidor.

**Limite:** o SQL do repositório não comprova quais políticas estão instaladas. DPAPI para as novas chaves de portas é melhoria real, mas não migrou o cofre RDP nem a sessão Tuya. A chave publishable no app é esperada; a política do servidor precisa limitar operações.

**Ação:** inspecionar grants/policies efetivos e dependências das versões distribuídas. Definir papéis, schema próprio de acessos/sessões e migração do cofre. Não mudar permissões às cegas nem apagar/substituir chaves antigas antes de validar leitura e restauração. Diferenciar falha de decifragem de texto legado reconhecido.

**Aceite:** matriz real de permissões verificada por papel, edição corporativa bloqueada a quem não tem autorização e migração compatível com clientes existentes. Implantação de identidade/schema exige escopo e revisão próprios.

### R06 — P1: validação de servidores é insuficiente

**Evidência:** schemas em `desktop_backend.py:299–325` repetem campos e aceitam nome/host vazios, porta fora de 1–65535 e GPS fora da faixa. A reprodução aceitou porta 70000, latitude 91 e longitude 181. `scope` não consta no contrato, embora armazenamento diferencie local/corporativo e presuma corporativo.

**Correção:** contratos compartilhados, validação de nome/host/porta/par GPS finito/escopo e autorização no backend. Separar retorno de credenciais do retorno de listagem. Não alterar padrão de compartilhamento sem apresentar seu comportamento.

**Aceite:** dado inválido é recusado antes de salvar/conectar; zero é coordenada válida; par parcial/infinito é rejeitado; contrato explicita local/corporativo.

### R07 — P1: backend inicializa estado no import e não encerra todos os workers

**Evidência:** gerenciadores globais a partir de `desktop_backend.py:39`; carregamento/diretórios no import. `logger.py:124` configura e redireciona stdout/stderr ao importar. Heartbeat em `desktop_backend.py:1118` e watcher do launcher usam `while True`; há threads daemon e `os._exit`. A correção da bandeja resolveu um caso, não todo o ciclo de vida.

**Correção:** fábrica `create_app(services)`, bootstrap explícito, lifespan, supervisor com stop_event e dono por recurso. Preservar locks existentes de probes/Tuya/updater e fechar contêiner AV na própria thread, como o stream já faz. Permitir saída controlada do Uvicorn.

**Aceite:** importar não acessa perfil nem inicia serviços; TestClient usa a aplicação real com fakes; repetição de startup/shutdown não acumula threads, ícones, sockets ou hotkeys.

### R08 — P1/P2: API frontend repetida e cobertura de interação incompleta

Há 37 `fetch`, 14 `any` e configuração sem `strict`. AJIN/portas já conferem muitos erros; favoritos, conexão RDP e atualização geral ainda ignoram status HTTP. O modal de servidor não cancela a busca de detalhes ao fechar/trocar servidor. Os 14 testes atuais do frontend cobrem regras AJIN, não esses fluxos.

**Correção:** cliente HTTP tipado com timeout, cancelamento e erro padronizado; hooks por recurso; strict progressivo. Promover cenários úteis dos scripts temporários de UI a testes mantidos, independentes do DEV aberto. Gerar tipos de OpenAPI depois de corrigir schemas.

**Aceite:** erro HTTP não parece sucesso; resposta antiga não preenche outro servidor; unmount cancela trabalho e mantém uma conexão WS por janela. Cobrir interrupção/retomada/troca de stream com fakes.

### R09 — P2: legado, template e código excessivamente compacto

Os dez módulos exclusivos do grafo legado somam 8.252 linhas, incluindo utilitários independentes. Os maiores: `app.py` (1.771), `ajin_view.py` (1.627), `web_map_manager.py` (1.619), `dialogs.py` (1.376). `App.css` (184 linhas) e assets de template não têm referência encontrada no frontend atual; README frontend ainda é Vite e README raiz mistura entradas modernas/antigas.

Alguns componentes novos também têm JSX/CSS e lógica concentrados em linhas muito longas. Melhorar legibilidade e separar responsabilidades sem multiplicar componentes triviais.

**Correção/aceite:** inventário de paridade, formatação por área e remoção comprovada de template. Só retirar UI antiga após conferir lacunas como preview RDP. Preservar instalador CustomTkinter, desinstalador e shim enquanto necessários. Build e visual de referência permanecem equivalentes. Dados AJIN, PDF de fachada, `resumo.md` e arquivos pessoais ficam fora da limpeza automática.

### R10 — P2: release e diagnóstico ainda dependem do ambiente do operador

Build e `tools/verify_release.py` já conferem integridade, frontend, payload, exclusão de arquivos locais e runtime de vídeo. Publicação e parte da homologação usam scripts ignorados em `.test-artifacts`. Não foi encontrado workflow em `.github`. `test_facial_door.py` na raiz depende da configuração da máquina; não deve entrar na suíte isolada por acidente.

**Correção:** versionar ferramentas de release sem credenciais, build de commit identificado e registro de source/frontend/assets. CI Windows com testes isolados, typecheck, lint e pacote; diagnóstico real separado e explícito. Registrar falhas de workers com `threading.excepthook` no bootstrap. Corrigir `CloudSyncManager.test_connection()`, que retorna sucesso para alguns HTTP de erro sem comprovar acesso à tabela.

**Aceite:** processo reproduzível por outra máquina autorizada; logs sem segredos; homologação completa de upgrade/rollback frozen em ambiente isolado, além da descoberta/download já validados. Publicação segue aprovação específica.

## 5. Estrutura recomendada

| Camada | Responsabilidade | Primeiro passo |
|---|---|---|
| Bootstrap Windows | Compor janela, bandeja, hotkeys e serviços | Extrair ciclo de vida do launcher |
| API local | Validar, autorizar e traduzir erros | Fábrica FastAPI e routers por recurso |
| Serviços | Regras de servidores, acessos, sync e AJIN | Extrair das rotas mantendo contratos |
| Persistência | Caminhos, locks, backups e migrações | ServerRepository e SettingsRepository |
| Integrações | RDP, Tuya, Hikvision, Supabase e AJIN | Adaptadores substituíveis por fakes |
| Frontend | UI, hooks e cliente HTTP | Tipar servidores/eventos e separar camadas do mapa |

```text
src/remotexpti/
  bootstrap.py
  api/           # fábrica, routers e schemas
  services/      # regras e supervisor
  persistence/   # repositories, cofre, caminhos e migrações
  integrations/  # RDP, Tuya, Hikvision, Supabase e AJIN
  updates/       # catálogo, download, estado e instalação
  platform/      # janela, bandeja e hotkeys Windows
desktop_ui/src/
  api/           # cliente e contratos
  hooks/         # eventos e dados
  features/      # servidores, mapa, AJIN, acessos e configurações
tests/           # unitários, API, integração simulada e pacote
tools/           # build, release e diagnósticos explícitos
```

Não começar movendo tudo para `src/`: estabelecer fronteiras e testes antes. JSON com lock, escrita atômica e migração basta para o primeiro ciclo. Considerar SQLite se transações/histórico justificarem; não trocar stack nem adicionar infraestrutura só para organizar arquivos.

## 6. Execução por entregas

Faixas de dias úteis para implementação/validação por alguém familiarizado com o projeto; não são prazo contratado. Não incluem espera por autorização, acesso ou homologação externa.

| Entrega | Ordem | Esforço | Resultado verificável |
|---|---:|---:|---|
| A. Caminhos de portas/sessão e migração | 1 | 1–2 dias | Perfil vazio e reinício onefile preservam dados; DEV isolado |
| B. Repository e propagação de erro ao salvar | 2 | 2–3 dias | Erros/concorrência preservam último estado válido; UI informa falha |
| C. Sync completo, exclusões e conflitos | 3 | 2–4 dias | Paginação parcial/falha/concorrência não perdem registros |
| D. Favoritos e contratos de servidores | 4 | 1–2 dias | Favorito persiste e entrada inválida é recusada |
| E. Verificar políticas e desenhar migração de acesso | Análise inicial independente | 1–2 dias | Matriz real e proposta compatível com clientes |
| F. Fábrica FastAPI, supervisor e logs | Após B/C | 3–5 dias | App testável sem perfil real e shutdown verificável |
| G. Cliente HTTP, hooks, tipos e lint por área | Após D; por recurso | 2–4 dias | Política de erro única, strict progressivo e testes de fluxo |
| H. Legibilidade, template, docs e paridade | Gradual | 2–3 dias | Limpeza demonstrada por referências e build |
| I. Ferramentas de release e CI Windows | Após primeiro ciclo | 2–4 dias | Build rastreável e homologação frozen isolada |

**Primeiro ciclo: A → B → C → D**, com E como inspeção independente. Faixa preliminar A–D: **6–11 dias úteis**. Recalibrar depois desse ciclo. Soma sequencial de A–I: **16–29 dias úteis**, antes de paralelismo e esperas.

A implementação da nova identidade/RLS/cofre e a retirada completa da UI antiga precisam de escopo próprio após análise; não estão incluídas nessas faixas. Não juntar migração de cofre, remoção de UI e troca do protocolo de sync na mesma entrega.

## 7. Validação, migração e rollback

Cada correção começa com cenário que reproduz o problema. Preservar os 182 testes Python e 14 de regras AJIN; quantidade não substitui cobertura dos riscos.

- **Dados:** JSON inválido, erro de chave, escrita interrompida, concorrência e restauração, usando fixtures e arquivos temporários.
- **Nuvem:** páginas parciais, vazio confirmado, conflito, exclusão e falha entre etapas. Verificação de permissões reais separada, sem comandos destrutivos.
- **Desktop:** ciclos de início/fim, multi-monitor, minimizar/maximizar/restaurar, bandeja e hotkeys simuladas. Encerrar DEV pelo controle próprio; preservar CLIENT.
- **UI:** favorito, erros HTTP, troca de servidor durante fetch, cleanup WS e stream. Prévia aprovada antes de redesenho.
- **Mapa:** comparar CPU/RAM, listeners e markers no mesmo cenário; só ampliar otimização após medir. Preservar agrupamento AJIN aprovado.
- **EXE:** perfil vazio, migração de versão antiga, frontend/payload, upgrade e recuperação em pasta com espaços e arquivo bloqueado; conferir canais estável/beta.

Migração exige backup, formato versionado e restauração verificada. Reverter código não deve apagar dados já migrados. Definir retenção dos backups para não criar outra pilha permanente.

Manter a regra de versão do usuário: estável termina em `.0` e incrementa o número do meio; último número reservado a beta/pré-release. Esta revisão não altera a base **2.2.3-beta.1** nem a estável **2.2.0**. Publicação futura requer autorização específica.

## 8. Critérios permanentes de qualidade

1. Nenhuma escrita mutável dentro do bundle temporário; caminho canônico e migração explícita.
2. Nenhum sucesso de edição sem persistência confirmada; sincronização tem estado separado do salvamento local.
3. Nenhuma remoção em massa por resposta cuja completude não foi comprovada.
4. Um responsável por thread, timer, stream, socket, hotkey e ícone; cleanup testável.
5. Contratos tipados/validados e nenhum novo `any` público sem justificativa.
6. Falhas acionáveis observáveis, sem novos `except: pass` indiscriminados e sem segredos nos logs.
7. Limpeza por referências/paridade, nunca só pela idade ou tamanho do arquivo.
8. Layout aprovado preservado; refatoração funcional não redesenha telas sem prévia.
9. Testes e ferramentas independentes das credenciais e do DEV aberto do operador.
10. Pacote/publicação verificáveis, CLIENT preservado e aprovação antes de publicar.
