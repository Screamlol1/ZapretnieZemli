# Компоненты Windows-версии

Установщик включает следующие компоненты. Они сохраняют собственные лицензии и
принадлежат соответствующим авторам. Версии и SHA-256 закреплены в
`runtime-lock.json`; подготовка сборки не скачивает автоматически новые версии.

| Компонент | Версия | Лицензия и расположение в установленной игре |
| --- | --- | --- |
| Python, Windows x64 embeddable | 3.14.10 | Python Software Foundation License и уведомления компонентов: `resources/runtime/python/LICENSE.txt` |
| Node.js, Windows x64 | 24.22.2 LTS | MIT и лицензии встроенных компонентов: `resources/runtime/node/LICENSE` |
| cloudflared, Windows amd64 | 2026.10.7 | Apache License 2.0: `resources/runtime/cloudflared/LICENSE` |
| Electron | Версия в `package.json` | MIT и уведомления Chromium/Node.js: `LICENSE.electron.txt`, `LICENSES.chromium.html` рядом с исполняемым файлом приложения |

Официальные источники архивов и контрольных сумм:

- [Python 3.14.10, Windows embeddable package (64-bit)](https://www.python.org/downloads/release/python-31410/) — SHA-256 опубликован в таблице загрузок.
- [Node.js 24.22.2](https://nodejs.org/dist/v24.22.2/) — [SHASUMS256.txt](https://nodejs.org/dist/v24.22.2/SHASUMS256.txt).
- [cloudflared 2026.10.7](https://github.com/cloudflare/cloudflared/releases/tag/2026.10.7) — SHA-256 из поля `digest` официального [GitHub Release API](https://api.github.com/repos/cloudflare/cloudflared/releases/tags/2026.10.7); [лицензия этой версии](https://github.com/cloudflare/cloudflared/blob/2026.10.7/LICENSE).

Скрипт `scripts/prepare-runtime.cjs` проверяет SHA-256 каждого скачанного файла,
в том числе повторно используемого кэша. Ключ `--no-download` запрещает сетевые
загрузки и собирает ресурсы только из уже проверенного локального кэша.
Python и Node.js входят в установщик: отдельно устанавливать их игрокам не нужно.
cloudflared используется только при явном запуске временной ссылки для совместной
игры. Постоянный общий сервер работает без такого туннеля.

Архивы исходников указанных компонентов доступны по официальным ссылкам выше.
Книги правил, личные аккаунты, сохранения и данные кампаний в эти runtime-ресурсы
не входят.
