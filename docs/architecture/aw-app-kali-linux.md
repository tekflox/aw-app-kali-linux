---
repo: architecture
path: docs/architecture/aw-app-kali-linux.md
source: generated
edited: false
checksum: sha256:18b41bf5589a4ca056b9f9c2551aad033d47a8e8306f9e10fa82f03fda3f3ff0
---
# Kali Linux

- **repo**: aw-app-kali-linux
- **layer**: app-container
- **technologies**: docker
- **health** (derived): planned

A full Kali Linux desktop in your browser. KDE Plasma with Kali's security toolset, opened as a workspace window — no VNC client, no local install. Everything you change sticks: your home directory, settings and any package you apt-get survive restarts and app updates, and this workspace's repos are mounted read-only so you can open them from a real desktop.

## Connections
_none_

## MCP tools
_none exposed_

## Requirements
### O desktop inteiro persiste em app data, então recriação de container não zera a máquina
- Given a imagem é a stock lscr.io/linuxserver/kali-linux, que guarda perfil KDE, estado do Firefox/Burp, ~/Desktop e as mudanças de apt/dpkg tudo sob /config
- When o volume é declarado (repos/aw-app-kali-linux/aw-app.json, runtime.volumes, $AW_APP_DATA montado em /config)
- Then todo apt-get, configuração e arquivo do desktop sobrevive a update do app e redeploy do workspace — sem o bind, cada recriação devolve um Kali recém-instalado, e o custo aparece exatamente quando é mais caro: depois de alguém ter passado uma tarde preparando o ambiente. ATENÇÃO: não há teste nenhum neste repo verificando isso — tests/ contém só um validate_manifest.py que o pytest nem coleta (nome fora do padrão test_*.py) e que virou vestigial desde que o release passou a validar pelo schema central do aw-marketplace
- intended_status: `not_implemented` · derived health: `not_implemented`
- tests: _none linked_

### Os repos do workspace entram read-only, e o hook de init mora em app data
- Given o monolito montava o workspace inteiro read-write (.:/home/abc/agentic-workspace:cached), de modo que uma sessão GUI podia rabiscar a árvore viva
- When os dois volumes restantes são declarados (repos/aw-app-kali-linux/aw-app.json, runtime.volumes: $AW_WORKSPACE_REPOS em /config/repos modo ro, e $AW_APP_DATA/custom-cont-init.d em /custom-cont-init.d)
- Then os checkouts são legíveis pelo Dolphin, editor ou shell mas não graváveis, e o hook de init do linuxserver — todo script executável ali roda como root antes da sessão KDE — aponta para app data, não para o pacote do app. O diretório de pacote é imutável e o runtime só faz bind de $AW_APP_DATA e $AW_WORKSPACE_*, então apontar o hook para app data é o que mantém a imagem upstream stock extensível sem forká-la num build próprio. ATENÇÃO: sem teste, mesmo motivo do requirement anterior
- intended_status: `not_implemented` · derived health: `not_implemented`
- tests: _none linked_
