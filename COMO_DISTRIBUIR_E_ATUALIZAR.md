# Distribuição e atualização do RemoteXPTI moderno

## Preparar o ambiente

Windows 10/11, Python 3.12 e Node/npm. Use um ambiente Python dedicado:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-build.txt
```

## Gerar os pacotes

Atualize `CURRENT_VERSION` em `version.py` e execute:

```powershell
python build_all.py
```

O comando instala o frontend pelo lockfile, compila a interface, executa testes e gera:

- `dist/RemoteXPTI.exe`
- `dist/update-manifest.json`
- `dist/Setup_RemoteXPTI.exe` e `dist/Setup_RemoteXPTI.zip`
- `dist/RemoteXPTI_Portatil.zip`

A distribuição contém configuração inicial vazia. Não envie arquivos de servidores, chaves ou sessões de produção como assets públicos.

Para exigir assinatura com um certificado de assinatura de código existente e confiável:

```powershell
$env:REMOTEXPTI_SIGN = '1'
python build_all.py
```

Sem essa variável, o build informa que os binários estão sem assinatura. Certificados autoassinados não estabelecem confiança automaticamente nas máquinas dos clientes.

## Publicar a release

1. Use uma tag que corresponda exatamente à versão compilada, por exemplo `v2.1.9`.
2. Para o canal público, publique como release estável. Para beta, use uma versão como `2.1.10b1` e marque prerelease.
3. Anexe juntos `RemoteXPTI.exe` e `update-manifest.json`, preservando esses nomes. O manifesto deve ser do mesmo build e gerado depois da assinatura.
4. Anexe o instalador/ZIP para instalação inicial e recuperação.
5. Homologue a atualização numa instalação isolada antes de distribuir aos clientes.

O updater consulta o repositório fixo definido em `version.py`. O canal público recebe também releases de correção, sem a antiga restrição de patch zero. O EXE fica intacto durante o download; após validação, o usuário solicita o reinício e um helper instala a nova versão. Se a versão nova não confirmar inicialização, tenta restaurar o backup.

## Atualizar versões com updater quebrado

Execute o novo instalador uma vez, escolhendo a pasta dedicada `RemoteXPTI` da instalação anterior. Ele preserva seus arquivos de dados e chaves nessa pasta. Passe a usar o atalho do EXE instalado.

Rodar `launch_modern_desktop.py`, `run_modern.bat` ou `python main.py` executa o código de desenvolvimento; esse modo não instala updates de EXE nem altera o número da versão.

Veja `CORRECOES_AUTO_UPDATE.md` para comportamento, validação e limitações.
