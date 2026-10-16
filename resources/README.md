# Referências municipais do Brasil

br_municipalities.json contém somente nome, UF, latitude e longitude dos
municípios, além da identificação da origem. O app consulta esse arquivo
localmente; não envia nomes de servidores, credenciais ou cidades a serviços
externos para resolver uma localização.

- Origem: https://github.com/kelvins/municipios-brasileiros
- Revisão: 503e2f70bbf1b4b7ec0b1f68b09086ccc38fe861
- Arquivo de origem: csv/municipios.csv
- Consulta: 16/10/2026
- Registros importados: 5.571
- Licença: MIT, reproduzida em municipalities-LICENSE.txt.
- Integridade do CSV original: SHA-256 armazenado no JSON.

As coordenadas são referências municipais aproximadas, não a posição física
de servidores. A correspondência exige município e UF; nenhuma coordenada é
inventada para nomes desconhecidos. Novos municípios ou correções exigem
atualização explícita da base e nova validação.
