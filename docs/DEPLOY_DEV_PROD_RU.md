# Dev и production для ЕГР

Целевая схема:

- `develop` -> `https://test.tendex.by`;
- `main` -> `https://company.tenders.by`.

Dev использует контейнеры `egr_dev_api`, `egr_dev_frontend`, `egr_dev_db` и
`egr_dev_redis`. База dev хранится только в новом volume
`egr_dev_postgres_data`. Production volume `egr_egr_postgres_data` не
подключается к dev. Не запускайте `docker compose down -v`: эта команда удаляет
volumes.

Из-за ограничения сервера в 4 ГБ RAM dev не поднимает второй Elasticsearch и
фоновые Celery-задачи. Поиск в dev работает через SQL. Production Elasticsearch
и его индекс dev не использует.

## Обычный цикл изменения

На рабочем компьютере:

```bash
git switch develop
git pull --ff-only origin develop
# внести правки
python -m pytest -q
cd frontend
npm ci
npm run typecheck
npm test
npm run build
cd ..
git add <только нужные файлы>
git commit -m "описание изменения"
git push origin develop
```

Не используйте `git add .`: добавляйте только перечисленные файлы.

На сервере, только когда вы решили развернуть dev:

```bash
cd /home/user/egr-dev
git status --short --branch
./scripts/deploy-dev.sh
```

Проверка dev:

```bash
cd /home/user/egr-dev
docker compose --project-name egr-dev --env-file .env.dev \
  -f deploy/dev/docker-compose.yml ps
docker logs --tail 100 egr_dev_api
curl -fsS https://test.tendex.by/api/v1/health/ready
```

Перед переносом в production проверьте интерфейс, поиск, изменённые API и логи
на `test.tendex.by`.

## Перенос проверенного develop в main

Предпочтительный вариант — pull request `develop` -> `main` с успешно прошедшим
CI. Для fast-forward из локальной консоли:

```bash
git switch main
git pull --ff-only origin main
git merge --ff-only develop
git push origin main
```

После этого production разворачивается вручную:

```bash
cd /home/user/egr
git status --short --branch
./scripts/deploy-prod.sh
```

Скрипт принимает только чистую ветку `main`, выполняет `git pull --ff-only`,
миграции, пересборку API/frontend/workers и health-check production-домена.

## Первый запуск двух окружений

Этот раздел нужен один раз. Сначала должен быть успешно поднят dev-стек из
`develop`. Затем инфраструктурный коммит переносится в `main`.

На текущем сервере `docker-compose.yml` и
`nginx/conf.d/company.tenders.by.conf` появились раньше, чем стали tracked в
Git. Перед первым `git pull` сохраните их вне репозитория, иначе Git остановит
обновление из-за untracked-файлов:

```bash
backup_dir=/home/user/egr-config-backups/first-dev-prod
mkdir -p "$backup_dir/nginx"
cd /home/user/egr
mv docker-compose.yml "$backup_dir/docker-compose.yml"
mv nginx/conf.d/company.tenders.by.conf \
  "$backup_dir/nginx/company.tenders.by.conf"
git pull --ff-only origin main
```

Это не удаляет старые конфиги: они остаются в
`/home/user/egr-config-backups/first-dev-prod`. Docker volumes и работающая БД
этими командами не затрагиваются.

Дальше подключите ACME webroot, примените новый Nginx-конфиг и выпустите один
сертификат сразу на оба домена:

```bash
cd /home/user/egr
mkdir -p acme-webroot/.well-known/acme-challenge
./scripts/deploy-prod.sh
./scripts/issue-certificates.sh
```

В `crontab -e` пользователя `user` добавьте:

```cron
17 3 * * * /home/user/egr/scripts/renew-certificates.sh >> /home/user/egr-backups/cert-renew.log 2>&1
```

Финальная проверка без отключения TLS-валидации:

```bash
curl -fsSI https://test.tendex.by/
curl -fsS https://test.tendex.by/api/v1/health/ready
curl -fsSI https://company.tenders.by/
curl -fsS https://company.tenders.by/api/v1/health/ready
printf '' | openssl s_client -connect company.tenders.by:443 \
  -servername test.tendex.by 2>/dev/null | \
  openssl x509 -noout -dates -ext subjectAltName
```

В SAN сертификата должны одновременно присутствовать `company.tenders.by` и
`test.tendex.by`.

## Откат

Не редактируйте production-код вручную. Сделайте `git revert` проблемного
коммита в `develop`, снова проверьте dev, перенесите revert в `main` и повторите
production deploy. Старые конфиги первого перехода лежат в каталоге резервной
копии выше; volumes при откате не удаляются.
