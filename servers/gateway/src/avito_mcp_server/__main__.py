"""Запуск `python -m avito_mcp_server` — gateway-композиция.

Собирает движок (7 тулз) + mount/create_proxy на scraper/db/notify.
"""

from avito_mcp_server.gateway import main

if __name__ == "__main__":
    main()
