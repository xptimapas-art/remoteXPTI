# Portas e portões — pré-release 2.1.12-beta.1

Canal de distribuição: pré-release para beta testers autenticados no modo DEV e com o canal Beta Tester selecionado. A versão estável permanece na 2.1.11. Esta interface ainda está em avaliação e poderá receber ajustes antes da versão final. Os pacotes precisam ser gerados pelo build completo, incluindo as bibliotecas de vídeo; os executáveis anteriores à integração não devem ser reutilizados.

Os quatro acessos do cliente foram copiados para o perfil DEV, com backup. Por solicitação do usuário, os acionamentos por botão estão habilitados e a sessão Tuya foi copiada para o perfil DEV. A câmera do facial está vinculada ao próprio equipamento, com as credenciais já existentes. O executável e a configuração do cliente foram preservados. A sincronização de nuvem do DEV permanece desligada.

A opção de atalhos globais é independente dos acionamentos por botão. No DEV, `hotkeys_enabled: false` evita registrar as mesmas ações globais enquanto o cliente também está aberto. Os atalhos por acesso continuam salvos e podem ser editados normalmente. O operador pode habilitar os atalhos globais em Configurações.

## Interface e configuração

A tela usa cartões compactos, botão amarelo de acionamento e a arte XPTI extraída em vetor do PDF da fachada. O logo e a faixa vermelha são SVGs com recortes próprios, preservando a geometria original. A engrenagem abre a configuração daquele acesso em uma única janela flutuante. Preferências gerais e login Tuya ficam em Configurações; o histórico abre sob demanda.

Salvar um acesso preserva os demais, credenciais e campos legados. Formulários desatualizados recebem um aviso, e falhas de gravação não são apresentadas como sucesso. A escrita é atômica.

## Imagem da câmera

Em Configurar acesso > Câmera, escolha Sem câmera, Câmera do próprio equipamento ou Outra câmera Hikvision. Para câmera própria será usada a conexão do controlador; na externa, endereço, porta, protocolo, canal e credenciais são independentes.

O cartão e a janela ampliada reproduzem o **stream secundário H.264 continuamente**, sem áudio. O backend lê RTSP por TCP com PyAV e reempacota o vídeo em MP4 fragmentado na memória, sem recodificar os frames. A interface reproduz o vídeo com Media Source Extensions. Endereço autenticado e senha da origem RTSP não são enviados ao player nem passados em linha de comando de processos externos.

O player mantém uma janela curta de reprodução, descarta atraso acumulado e reconecta após falhas. Consultas são encerradas ao sair da página, ocultar o documento ou trocar o cartão pela visualização ampliada. Cada visualização ativa mantém uma conexão RTSP; o backend limita as conexões simultâneas e usa uma fila limitada em memória. Não grava vídeos em disco. O endpoint de JPEG permanece para compatibilidade, mas a tela não faz polling de fotos.

O campo **Porta RTSP** é independente da porta HTTP. Canal 1 usa o stream 102, canal 2 usa 202. Nenhuma configuração foi alterada nos equipamentos.

| Acesso no DEV | Equipamento | Porta RTSP | Stream | Vídeo observado |
| --- | --- | --- | --- | --- |
| Facial Hikvision 1 | DS-K1T671MF-L | 554 | 102 | 1280×720, aproximadamente 25 FPS |
| Portão interno XPTI | DS-2CD7A26G0-IZS | 554 | 102 | 640×480, aproximadamente 20 FPS |
| Portão Garagem XPTI (principal, vínculo confirmado pelo usuário) | DS-2CD6924G0-IHS | 13699 | 102 | 1280×720, aproximadamente 15 FPS |

As duas câmeras foram vinculadas somente ao DEV. Credenciais ficam no perfil local, fora do repositório. A porta 13699 foi descoberta pela leitura de `/ISAPI/Security/adminAccesses` da câmera principal; as portas padrão 554 e 8554 não estavam disponíveis nela.

Referências: [substream RTSP — Hikvision](https://supportusa.hikvision.com/support/solutions/articles/17000129022-do-you-have-an-example-showing-the-format-for-getting-a-rtsp-stream-from-a-camera-), [PyAV](https://pyav.org/docs/stable/cookbook/basics.html) e [MP4 fragmentado — FFmpeg](https://ffmpeg.org/ffmpeg-formats.html#Fragmentation).

## Gravar atalho

Clique no botão do campo Atalho, pressione a tecla ou combinação e solte. O valor aparece no campo; clique em Salvar para persistir. Ctrl, Alt e Shift são reconhecidos. Esc cancela a captura.

O gravador nativo instala um hook somente durante essa ação explícita, bloqueia a tecla selecionada antes dos listeners globais e encerra a captura ao soltá-la. Fecha ou cancela se perder o foco, se o formulário sair ou após 30 segundos. Não registra sequências digitadas nem logs de teclas. O resultado só é salvo quando o operador confirma o formulário.

Referência técnica: [LowLevelKeyboardProc — Microsoft](https://learn.microsoft.com/en-us/windows/win32/winmsg/lowlevelkeyboardproc).

## Verificação

- 79 testes automatizados: atualização/rollback, perfis separados, conectividade, preservação de configurações, APIs autenticadas, cache de frames, streaming autenticado, encerramento de conexões, limites de memória e captura de teclas.
- TypeScript/Vite e lint sem erros; avisos de hooks e componentes existentes continuam documentados para a refatoração.
- Interface ligada ao serviço real do DEV: quatro botões habilitados, os três vídeos secundários carregados nos cartões e na visualização ampliada, reprodução contínua e arte SVG legível.
- Gravação de atalho validada na interface com respostas simuladas; instalação e remoção do hook real do Windows verificadas com callback estritamente passivo, sem capturar ou bloquear teclas. A captura da tecla física fica para o teste do operador.
- Na janela de medição de quatro segundos, o navegador decodificou 101 frames do facial, 80 da interna e 62 da principal; nenhuma requisição de foto foi feita.
- Nenhum comando de abertura foi enviado nos testes. Dados temporários, imagens de câmera e credenciais de perfil não são artefatos de distribuição.
