#!/usr/bin/env python3
"""
ОДНОРАЗОВЫЙ скрипт — запускаете на СВОЁМ компьютере, не на сервере бота.

Что делает: открывает ваш браузер, вы логинитесь в СВОЙ Google-аккаунт и
разрешаете доступ только к "Create, read, update, delete drafts and send
messages" (scope gmail.compose) — не к чтению всей почты. После этого скрипт
печатает refresh_token, который вы сами вставляете в переменные окружения
бота на хостинге (GOOGLE_REFRESH_TOKEN). Ни ваш пароль, ни логин никуда не
передаются и не сохраняются этим скриптом.

Перед запуском:
1. console.cloud.google.com -> создайте проект (или выберите существующий).
2. "APIs & Services" -> "Library" -> включите "Gmail API".
3. "APIs & Services" -> "OAuth consent screen" -> тип "External", добавьте
   себя в "Test users" (этого достаточно для личного использования, без
   прохождения верификации Google).
4. "APIs & Services" -> "Credentials" -> "Create Credentials" -> "OAuth client ID"
   -> тип приложения "Desktop app". Скачайте client_id и client_secret.
5. pip install google-auth-oauthlib
6. Запустите: python3 gmail_oauth_setup.py --client-id XXX --client-secret YYY

Результат скрипта (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN)
вставьте в настройки окружения вашего облачного хостинга — это сделайте сами,
агент не вводит секреты в чужие панели управления за вас.
"""
import argparse

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--client-secret", required=True)
    args = parser.parse_args()

    client_config = {
        "installed": {
            "client_id": args.client_id,
            "client_secret": args.client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)

    print("\n=== Готово. Вставьте это в переменные окружения бота на хостинге ===")
    print(f"GOOGLE_CLIENT_ID={args.client_id}")
    print(f"GOOGLE_CLIENT_SECRET={args.client_secret}")
    print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
    print("=======================================================================\n")
    print(
        "Совет: refresh token действует долго, но вы можете отозвать его в любой "
        "момент на https://myaccount.google.com/permissions"
    )


if __name__ == "__main__":
    main()
