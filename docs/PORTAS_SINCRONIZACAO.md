# Portas e câmeras compartilhadas entre PCs da empresa

O cadastro de portas tem sincronização própria, independente da lista de
servidores RDP. Assim, alterações no DEV podem chegar aos PCs da empresa sem
habilitar a publicação dos dados de teste dos servidores.

O compartilhamento inclui cenas Tuya, a porta facial e suas câmeras vinculadas.
As configurações de câmera/facial são cifradas antes do envio ao Supabase.
A senha DEV validada deriva a chave de leitura; essa chave fica protegida pelo
DPAPI do Windows, vinculada ao usuário local, e é removida ao sair do modo DEV.
Não é usada a chave pública do Supabase como chave de criptografia.

## Ativação

Nos PCs que já estavam autenticados antes desta implementação, abrir
**Portas e portões → Configurações → Portas e câmeras da empresa** e confirmar
a senha DEV uma vez em **Habilitar sincronização**. Novos logins DEV já
preparam a chave protegida. A senha é informada apenas no app.

O primeiro PC publica seu cadastro completo. Os demais recebem o cadastro
compartilhado e mantêm seus atalhos, habilitação dos acionamentos, sons e
notificações locais. A sincronização automática ocorre no ciclo de um minuto;
o botão **Atualizar Tuya** também consulta as configurações compartilhadas.

As alterações são enviadas antes de serem confirmadas como salvas. Se outro
PC tiver alterado o cadastro, o formulário acusa conflito e pede atualização,
sem substituir o cadastro remoto por uma cópia antiga. A exclusão de um
acesso compartilhado também se propaga; acessos privados não gerenciados
pela nuvem são preservados.

Clientes antigos continuam lendo as cenas Tuya do mesmo registro reservado.
Receber câmeras e porta facial protegidas exige a versão com este novo fluxo
e a ativação da chave no PC. A versão publicada 2.2.0 não contém esse fluxo.
O compartilhamento das configurações não cria conectividade: o PC também
precisa de acesso de rede aos IPs e às portas dos equipamentos.

## Verificação

Os testes usam dados fictícios para conferir criptografia, chave do Windows,
credenciais atualizadas, preservação de atalhos, exclusão de acessos,
compatibilidade com cenas Tuya antigas e rejeição de alterações desatualizadas.
Não executar aberturas físicas como parte da verificação de sincronização.
