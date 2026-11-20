
import os

import httpx

KEYCLOAK_BASE = "https://comp-auth.als.lbl.gov"
resp = httpx.post(
    f"{KEYCLOAK_BASE}/realms/master/protocol/openid-connect/token",
    data={
        "grant_type": "password",
        "client_id": "admin-cli",
        "username": "dmcreynolds",
        "password": os.getenv("KEYCLOAK_ADMIN_PASSWORD"),
    },
)
TOKEN = resp.json()["access_token"]
print(TOKEN)
