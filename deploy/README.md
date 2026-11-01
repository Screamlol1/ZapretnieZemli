# Постоянный сервер для закрытого тестирования

Подготовленная схема: один Linux VPS → Caddy с HTTPS → Python на `127.0.0.1:8789`.
Node.js выполняет проверки листов и боевые правила. SQLite, карты и резервные копии
живут в `/var/lib/ravenhex`, отдельно от кода в `/opt/ravenhex`.
Начальная оценка для одной группы: 2 vCPU, 2 ГБ RAM, 20 ГБ SSD; это не результат
нагрузочного теста. Сохраняется ограничение 50 кампаний для закрытого тестирования.
Запускайте только один экземпляр сервера с этой базой.

## Перед установкой

Нужны VPS с systemd, Python 3.11+, поддерживаемая Node.js 22+ и Caddy.
Установите Node.js из [официальных дистрибутивов](https://nodejs.org/en/download),
Caddy — по [официальной инструкции](https://caddyserver.com/docs/install).
Проверьте `python3 --version`, `node --version`, `caddy version`.
Node должен быть доступен службе по `/usr/local/bin/node` или `/usr/bin/node`.

Подготовленные исходники с этими конфигурациями есть в локальном архиве
`outputs/Игровой-стол-ЗЗ.zip`. Архив распаковывается непосредственно в `/opt/ravenhex`.
Исходники также можно взять из ветки `codex/multiplayer-table-v0` репозитория
[Screamlol1/ZapretnieZemli](https://github.com/Screamlol1/ZapretnieZemli/tree/codex/multiplayer-table-v0).
В репозитории `server.py` лежит в корне; в рабочей папке разработчика — в `game/`.
В `/opt/ravenhex/server.py` должен оказаться именно файл сервера.
Перед первым запуском перенесите данные по следующему разделу.

## Перенос текущих аккаунтов и кампаний

На исходном компьютере создайте проверяемую копию:

```powershell
python game/backup.py --database game/.runtime/test.sqlite --reference-root game/local-assets --output game/.runtime/migration
```

Скрипт использует SQLite Backup API, проверяет целостность и пишет `COMPLETE.json`
с SHA-256 всех файлов. Копируются база, загруженные PNG, фон карты и слой местности.
Книги, журналы процессов и файлы с открытыми паролями не копируются.
База всё равно содержит приватные данные: передавайте снимок только через SSH/SFTP,
не прикладывайте к GitHub и не помещайте в публичный каталог сайта.

Для окончательного переключения остановите старый игровой сервер, создайте **новый**
снимок и перенесите его: иначе действия, сделанные после предварительной копии,
останутся только на старом компьютере. Пока идёт перенос, оба сервера не должны
принимать независимые изменения одной кампании.

Проверьте контрольные суммы на новом сервере, находясь в каталоге снимка:

```sh
python3 - <<'PY'
import hashlib, json
from pathlib import Path
root = Path('.').resolve()
manifest = json.loads((root / 'COMPLETE.json').read_text())
assert manifest['version'] == 1
for name, digest in manifest['sha256'].items():
    path = (root / name).resolve()
    assert path.is_relative_to(root)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, name
print('Snapshot verified')
PY
```

После проверки скопируйте `campaigns.sqlite`, `map-images/` (если есть) и
`local-assets/` (если есть) в `/var/lib/ravenhex/`. Не кладите снимок целиком
в директорию исходников. Старую базу сохраните до проверки новой установки.
Существующий администратор переносится вместе с аккаунтами; создавать его заново
не требуется. На новом домене пользователи входят своими прежними логинами и паролями.

## Установка службы

Команды для **нового выделенного** VPS после загрузки исходников:

```sh
sudo useradd --system --user-group --home-dir /var/lib/ravenhex --shell /usr/sbin/nologin ravenhex
sudo install -d -o ravenhex -g ravenhex -m 700 /var/lib/ravenhex
sudo install -d -o ravenhex -g ravenhex -m 700 /var/lib/ravenhex/backups
```

Загрузите проверенный снимок в созданный каталог, затем:

```sh
sudo chown -R ravenhex:ravenhex /var/lib/ravenhex
sudo chmod 700 /var/lib/ravenhex
sudo install -m 644 /opt/ravenhex/deploy/ravenhex.service /etc/systemd/system/
sudo install -m 644 /opt/ravenhex/deploy/ravenhex-backup.service /etc/systemd/system/
sudo install -m 644 /opt/ravenhex/deploy/ravenhex-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ravenhex
curl --fail http://127.0.0.1:8789/api/health
sudo systemctl start ravenhex-backup
sudo systemctl enable --now ravenhex-backup.timer
```

Код должен принадлежать администратору сервера и быть доступен `ravenhex` для чтения.
Служба может писать только в каталог данных. Она перезапускается после сбоя
и запускается после перезагрузки VPS.

## Домен и HTTPS

Кандидат: `ravenhex.ru` («Вороний гекс»); запасной — `voronhex.ru`.
Проверка реестра TCI 20 октября 2026: записей для обоих доменов не найдено.
Это не резервирование: окончательная доступность и цена проверяются у регистратора.

После регистрации установите DNS-запись A корневого домена на публичный IPv4 VPS.
AAAA добавляйте только при настроенном IPv6. В `deploy/Caddyfile` замените
`example.org` на купленный домен.

```sh
sudo install -m 644 /opt/ravenhex/deploy/Caddyfile /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy [автоматически получает HTTPS-сертификат](https://caddyserver.com/docs/automatic-https).
Разрешите входящие TCP 80 и 443 в панели VPS/фаерволе; сохраните доступ SSH.
Порт 8789 не открывайте: сервер слушает loopback.
Caddy сохраняет Host для проверки Origin и **перезаписывает** заголовок IP,
который сервер использует для ограничений запросов.
Этот конфиг рассчитан на прямое подключение к Caddy; при добавлении CDN потребуется
отдельно настроить доверенные прокси, иначе все посетители CDN разделят один лимит.

## Проверка, обновление и восстановление

Проверьте на HTTPS: вход существующих Мастера и игрока, личные листы, кампанию,
фон карты, сохранение действия, выход и повторный вход. Затем перезапустите службу
и убедитесь, что последние изменения сохранились. Проверьте доступ с другого устройства.

Перед обновлением выполните `sudo systemctl start ravenhex-backup`, дождитесь
успешного завершения, остановите `ravenhex`, замените код, запустите службу.
`journalctl -u ravenhex -n 100` показывает диагностику; журналы не публикуйте целиком.

Ежедневные копии находятся в `/var/lib/ravenhex/backups`. Копируйте их также
**вне этого VPS**: локальная копия не переживёт потерю диска. Автоматическое удаление
снимков пока не включено; контролируйте объём и храните хотя бы 14 последних копий.
Отдельно проверьте восстановление на временной базе.

Восстановление: остановить службу и таймер, сохранить текущую базу и карты отдельной
копией, проверить `COMPLETE.json` выбранного снимка, заменить базу и каталоги карт,
восстановить владельца `ravenhex`, запустить службу и таймер, повторить проверку входа
и кампании. Не заменяйте файл SQLite при работающем сервере.

Эти файлы готовят размещение; сами по себе они не арендуют VPS, не регистрируют
домен и не подтверждают успешный внешний запуск. Linux/systemd/Caddy должны быть
проверены на выбранном сервере.
