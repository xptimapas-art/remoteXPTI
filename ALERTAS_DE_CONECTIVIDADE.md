# Alertas de conectividade RDP

A partir de 2.1.11, um resultado isolado do teste TCP não abre nem encerra um
incidente. O teste verifica a porta RDP configurada; ele não mede perda de
pacotes nem prova que uma cidade inteira está sem rede. Por isso a interface
identifica os incidentes como **falhas RDP confirmadas**.

- **Abertura:** pelo menos 3 falhas consecutivas, cobrindo pelo menos 60 segundos.
- **Recuperação:** 2 respostas bem-sucedidas consecutivas, separadas por pelo
  menos 10 segundos. Na verificação periódica a recuperação costuma ser
  confirmada na rodada seguinte, cerca de 30 segundos depois.
- **Teste:** timeout de 3 segundos, substituindo os 1,3–1,5 segundos anteriores.
- **Oscilação:** um sucesso interrompe a sequência candidata de falhas;
  uma falha interrompe a sequência candidata de recuperação.
- **Duração:** depois da confirmação, conta desde a primeira falha da sequência.
- **Atualização manual:** usa o mesmo filtro. Cliques repetidos em menos de
  10 segundos não contam como novas confirmações.

Os servidores são testados em paralelo. Rodadas completas não se sobrepõem,
e testes manuais e periódicos do mesmo servidor são serializados. Se o destino
for editado enquanto o teste está em andamento, o resultado antigo é descartado.

Os tempos de confirmação usam relógio monotônico, para alterações do relógio
do Windows não abrirem incidentes indevidamente. Apenas incidentes confirmados
são persistidos, com gravação atômica. No reinício o horário de início é
preservado, e a recuperação exige as mesmas duas confirmações. A exclusão do
servidor também remove o estado e o histórico correspondente.

Essa regra aceita um atraso de pelo menos 60 segundos para anunciar uma falha
nova. Uma oscilação de 10–30 segundos que se recupera antes da confirmação não
entra na lista vermelha. A programação das rodadas, a fila de testes e os tempos
de resposta podem prolongar um pouco esse atraso.

O mesmo monitor é usado pelo desktop moderno e pela interface Python legada.
Os testes simulam oscilação, falha contínua, recuperação parcial, reinício,
alteração de relógio, cliques rápidos, rodadas concorrentes e troca do destino,
sem acessar servidores reais ou acionar dispositivos.
