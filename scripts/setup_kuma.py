"""
Configure Uptime Kuma monitors and status page for AgentGuard services.

Prerequisites:
  1. Uptime Kuma running at http://localhost:3001
  2. Admin account created via browser (first-time setup)
  3. pip install uptime-kuma-api

Usage:
  python -m scripts.setup_kuma --username admin --password <your-password>
  python -m scripts.setup_kuma --username admin --password <pw> --reset
"""

import argparse
from uptime_kuma_api import UptimeKumaApi, MonitorType

KUMA_URL = "http://localhost:3001"

# Public services (accessible from host)
MONITORS = [
    # Core AI stack
    dict(type=MonitorType.HTTP, name="LiteLLM Proxy", url="http://localhost:4000/health/liveliness", interval=30, maxretries=3),
    dict(type=MonitorType.HTTP, name="RAG API", url="http://localhost:8001/health", interval=30, maxretries=3),
    dict(type=MonitorType.HTTP, name="Ollama", url="http://localhost:11434/api/version", interval=60, maxretries=3),

    # Observability & UI
    dict(type=MonitorType.HTTP, name="Langfuse", url="http://localhost:3200/api/public/health", interval=30, maxretries=3),
    dict(type=MonitorType.HTTP, name="Open WebUI", url="http://localhost:3100/health", interval=30, maxretries=3),
    dict(type=MonitorType.HTTP, name="OpenObserve", url="http://localhost:5080/healthz", interval=60, maxretries=3),
    dict(type=MonitorType.HTTP, name="Grafana", url="http://localhost:3300/api/health", interval=60, maxretries=3),
    dict(type=MonitorType.HTTP, name="Jaeger", url="http://localhost:16686/", interval=60, maxretries=3),
    dict(type=MonitorType.HTTP, name="Traefik Dashboard", url="http://localhost:8090/api/overview", interval=60, maxretries=3),
    dict(type=MonitorType.HTTP, name="Portainer", url="https://localhost:9443/api/system/status", interval=60, maxretries=3, ignoreTls=True),
    dict(type=MonitorType.HTTP, name="Dockge", url="http://localhost:5001/", interval=60, maxretries=3),

    # Vector store
    dict(type=MonitorType.HTTP, name="Qdrant", url="http://localhost:6333/healthz", interval=30, maxretries=3),

    # Internal TCP checks (127.0.0.1 bound)
    dict(type=MonitorType.PORT, name="PostgreSQL", hostname="127.0.0.1", port=5500, interval=60, maxretries=3),
    dict(type=MonitorType.PORT, name="Redis", hostname="127.0.0.1", port=6300, interval=60, maxretries=3),
    dict(type=MonitorType.PORT, name="ClickHouse HTTP", hostname="127.0.0.1", port=8123, interval=60, maxretries=3),
    dict(type=MonitorType.PORT, name="MinIO API", hostname="127.0.0.1", port=9299, interval=60, maxretries=3),
    dict(type=MonitorType.PORT, name="Prometheus", hostname="127.0.0.1", port=9090, interval=60, maxretries=3),
    dict(type=MonitorType.PORT, name="Loki", hostname="127.0.0.1", port=3101, interval=60, maxretries=3),
    dict(type=MonitorType.PORT, name="OTEL Collector gRPC", hostname="127.0.0.1", port=4317, interval=60, maxretries=3),
]

STATUS_PAGE_SLUG = "status"
STATUS_PAGE_TITLE = "AgentGuard Status"


def connect(username: str, password: str) -> UptimeKumaApi:
    api = UptimeKumaApi(KUMA_URL)
    api.login(username, password)
    print(f"Connected to {KUMA_URL}")
    return api


def delete_all_monitors(api: UptimeKumaApi) -> None:
    monitors = api.get_monitors()
    for m in monitors:
        api.delete_monitor(m["id"])
        print(f"  Deleted monitor: {m['name']}")


def setup_monitors(api: UptimeKumaApi) -> dict[str, int]:
    existing: dict[str, int] = {m["name"]: int(m["id"]) for m in api.get_monitors()}
    id_map: dict[str, int] = {}

    for cfg in MONITORS:
        name = cfg["name"]
        if name in existing:
            print(f"  Skip (exists): {name}")
            id_map[name] = existing[name]
            continue
        result = api.add_monitor(**cfg)
        mid = int(result["monitorID"])
        id_map[name] = mid
        print(f"  Added: {name} (id={mid})")

    return id_map


def setup_status_page(api: UptimeKumaApi, id_map: dict[str, int]) -> None:
    pages = api.get_status_pages()
    existing_slugs = [p["slug"] for p in pages]

    if STATUS_PAGE_SLUG not in existing_slugs:
        api.add_status_page(STATUS_PAGE_TITLE, STATUS_PAGE_SLUG)
        print(f"  Created status page: {STATUS_PAGE_SLUG}")
    else:
        print(f"  Status page exists: {STATUS_PAGE_SLUG}")

    # Group monitors into categories
    public_names = [
        "LiteLLM Proxy", "RAG API", "Ollama",
        "Langfuse", "Open WebUI", "OpenObserve",
        "Grafana", "Jaeger", "Traefik Dashboard", "Portainer", "Dockge",
        "Qdrant",
    ]
    infra_names = [
        "PostgreSQL", "Redis", "ClickHouse HTTP",
        "MinIO API", "Prometheus", "Loki", "OTEL Collector gRPC",
    ]

    def make_group(title: str, names: list[str]) -> dict:
        return {
            "type": "group",
            "name": title,
            "children": [
                {"id": id_map[n]} for n in names if n in id_map
            ],
        }

    public_monitors_list = [make_group("AI Stack & UIs", public_names)]
    infra_list = [make_group("Infrastructure", infra_names)]

    api.save_status_page(
        slug=STATUS_PAGE_SLUG,
        title=STATUS_PAGE_TITLE,
        publicGroupList=public_monitors_list + infra_list,
        theme="dark",
        published=True,
        showTags=False,
        domainNameList=[],
        description="Live status of all AgentGuard services",
    )
    print(f"  Saved status page → http://localhost:3001/status/{STATUS_PAGE_SLUG}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Configure Uptime Kuma for AgentGuard")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", required=True)
    parser.add_argument("--reset", action="store_true", help="Delete all monitors first")
    args = parser.parse_args()

    api = connect(args.username, args.password)
    try:
        if args.reset:
            print("Resetting all monitors...")
            delete_all_monitors(api)

        print("Setting up monitors...")
        id_map = setup_monitors(api)

        print("Setting up status page...")
        setup_status_page(api, id_map)

        print(f"\nDone. Status page: http://localhost:3001/status/{STATUS_PAGE_SLUG}")
    finally:
        api.disconnect()


if __name__ == "__main__":
    main()
