import base64
import json
import os
import re
import time

import httpx

KEYCLOAK_BASE = "https://comp-auth-local.als.lbl.gov"
REALM = "als-computing"
KEYCLOAK_URL = f"{KEYCLOAK_BASE}/admin/realms/{REALM}"
IDP_ALIAS = "orcid"  # the alias of your recreated identity provider

# KEYCLOAK_BASE above is a direct-to-origin hostname used to bypass a
# Cloudflare WAF rule that blocks /admin/* traffic on the public hostname.
# Its TLS certificate is issued for the public hostname, not this one, so
# set KEYCLOAK_TLS_SNI_HOST to that public hostname to validate the
# certificate against the name it actually covers. This still fully
# verifies the cert chain and hostname — it just checks the right name —
# unlike disabling verification outright.
KEYCLOAK_TLS_SNI_HOST = os.getenv("KEYCLOAK_TLS_SNI_HOST")

# Realm to authenticate against for token refresh. Most admin-cli logins
# authenticate against "master" even when administering another realm;
# override with KEYCLOAK_TOKEN_REALM if your admin user lives in `REALM`.
TOKEN_REALM = os.getenv("KEYCLOAK_TOKEN_REALM", "master")
TOKEN_URL = f"{KEYCLOAK_BASE}/realms/{TOKEN_REALM}/protocol/openid-connect/token"
TOKEN_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "admin-cli")

ORCID_PATTERN = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")


def sni_request_kwargs() -> dict:
    """Extra httpx request kwargs to validate TLS against KEYCLOAK_TLS_SNI_HOST
    (the public hostname the cert is issued for) while actually connecting to
    KEYCLOAK_BASE's host. No-op when KEYCLOAK_TLS_SNI_HOST is unset."""
    if not KEYCLOAK_TLS_SNI_HOST:
        return {}
    return {
        "headers": {"Host": KEYCLOAK_TLS_SNI_HOST},
        "extensions": {"sni_hostname": KEYCLOAK_TLS_SNI_HOST},
    }


def fetch_token() -> str:
    """Obtain a fresh admin access token.

    Supports whichever credentials are available, in this priority order:
    - KEYCLOAK_ADMIN_TOKEN (used as-is, e.g. pasted from `keycloak_get_token.py`
      or `kcadm.sh` — takes priority since providing a token directly is an
      explicit choice, but note it cannot be refreshed: if it expires
      mid-run, every retry will just hit the same expired token again)
    - KEYCLOAK_CLIENT_ID + KEYCLOAK_CLIENT_SECRET (client_credentials grant)
    - KEYCLOAK_ADMIN_USERNAME + KEYCLOAK_ADMIN_PASSWORD (password grant, admin-cli)
    """
    static_token = os.getenv("KEYCLOAK_ADMIN_TOKEN")
    if static_token:
        return static_token

    client_secret = os.getenv("KEYCLOAK_CLIENT_SECRET")
    username = os.getenv("KEYCLOAK_ADMIN_USERNAME")
    password = os.getenv("KEYCLOAK_ADMIN_PASSWORD")

    if client_secret:
        data = {
            "grant_type": "client_credentials",
            "client_id": TOKEN_CLIENT_ID,
            "client_secret": client_secret,
        }
    elif username and password:
        data = {
            "grant_type": "password",
            "client_id": TOKEN_CLIENT_ID,
            "username": username,
            "password": password,
        }
    else:
        raise SystemExit(
            "No credentials found. Set KEYCLOAK_ADMIN_TOKEN, "
            "KEYCLOAK_CLIENT_ID/KEYCLOAK_CLIENT_SECRET, or "
            "KEYCLOAK_ADMIN_USERNAME/KEYCLOAK_ADMIN_PASSWORD."
        )

    resp = httpx.post(TOKEN_URL, data=data, **sni_request_kwargs())
    resp.raise_for_status()
    return resp.json()["access_token"]


def decode_jwt_claims(token: str) -> dict:
    payload_b64 = token.split(".")[1]
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def describe_token_authorization(token: str) -> None:
    """Print what the access token is actually authorized to do, to make
    permission problems (wrong realm, missing realm-management roles)
    obvious instead of discovering them via a bare 401."""
    claims = decode_jwt_claims(token)
    print(f"Full decoded token claims:\n{json.dumps(claims, indent=2)}")
    print(f"Token issuer: {claims.get('iss')}")
    print(f"Token subject: {claims.get('preferred_username', claims.get('sub'))}")

    realm_roles = set(claims.get("realm_access", {}).get("roles", []))
    print(f"Realm roles ({TOKEN_REALM}): {sorted(realm_roles) or '(none)'}")

    resource_access = claims.get("resource_access", {})
    # If the token was issued by `master` to manage a *different* realm,
    # Keycloak exposes that realm's rights via a "{realm}-realm" client.
    # If the token was issued directly by the target realm (e.g. a service
    # account defined in that realm managing itself), the relevant client
    # is that realm's own built-in "realm-management" client instead.
    candidates = (
        [f"{REALM}-realm", "realm-management"]
        if TOKEN_REALM != REALM
        else ["realm-management"]
    )
    found_any = False
    for client_name in candidates:
        target_roles = set(resource_access.get(client_name, {}).get("roles", []))
        if target_roles:
            found_any = True
            print(f"'{client_name}' client roles: {sorted(target_roles)}")
    if not found_any:
        print(
            f"No roles found on any of {candidates} — this token cannot manage "
            f"the '{REALM}' realm's users. In the Keycloak admin console, go to "
            f"Clients → {claims.get('azp', '<client>')} → Service account roles, "
            f"assign roles from client 'realm-management', and grant at least "
            f"'manage-users' (plus 'view-users'/'query-users' for listing)."
        )


class AuthedSession:
    """An httpx wrapper that transparently re-authenticates on 401 and
    retries transient network errors with backoff."""

    _RETRYABLE = (httpx.ReadError, httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadTimeout)
    _MAX_ATTEMPTS = 8
    _MAX_BACKOFF = 30

    def __init__(self) -> None:
        self.token = fetch_token()
        self._client = httpx.Client(timeout=30.0)

    def _headers(self) -> dict:
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        headers.update(sni_request_kwargs().get("headers", {}))
        return headers

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        kwargs.setdefault("extensions", sni_request_kwargs().get("extensions"))
        for attempt in range(self._MAX_ATTEMPTS):
            try:
                resp = self._client.request(method, url, headers=self._headers(), **kwargs)
            except self._RETRYABLE as exc:
                if attempt == self._MAX_ATTEMPTS - 1:
                    raise
                wait = min(2**attempt, self._MAX_BACKOFF)
                print(f"\n  Connection error ({exc}), retrying in {wait}s...")
                time.sleep(wait)
                continue
            if resp.status_code == 401 and attempt < self._MAX_ATTEMPTS - 1:
                self.token = fetch_token()
                continue
            return resp
        raise RuntimeError("unreachable")

    def get(self, url: str, **kwargs) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> httpx.Response:
        return self.request("POST", url, **kwargs)


def link_user(session: AuthedSession, user: dict) -> str:
    orcid_id = user["username"]
    resp = session.post(
        f"{KEYCLOAK_URL}/users/{user['id']}/federated-identity/{IDP_ALIAS}",
        json={"identityProvider": IDP_ALIAS, "userId": orcid_id, "userName": orcid_id},
    )
    already_linked = resp.status_code == 409 and "already linked" in resp.text
    if resp.status_code in (204, 201):
        return "OK"
    if already_linked:
        return "OK (already linked)"
    return f"FAILED ({resp.status_code}): {resp.text}"


session = AuthedSession()
describe_token_authorization(session.token)

# Paginate through all users — Keycloak defaults to a max of 100 per page,
# but this realm's endpoint has been observed returning only 1 per call
# regardless, so we advance by the actual page size received and link each
# ORCID-formatted user as soon as their page arrives. That way a failure
# partway through only costs the next unprocessed user, not the whole run —
# and reruns are safe since re-linking an already-linked user is a no-op 409.
# Set KEYCLOAK_SYNC_START_FIRST to resume a scan that died partway through.
first = int(os.getenv("KEYCLOAK_SYNC_START_FIRST", "0"))
page_size = 100
fetched_count = 0
orcid_count = 0
try:
    while True:
        resp = session.get(
            f"{KEYCLOAK_URL}/users",
            params={"first": first, "max": page_size},
        )
        if first == 0:
            print(f"Request URL: {resp.request.url}")
        if resp.status_code != 200:
            raise RuntimeError(
                f"GET /users failed at first={first}: "
                f"HTTP {resp.status_code}: {resp.text[:2000]!r}"
            )
        batch = resp.json()
        if not batch:
            break
        fetched_count += len(batch)
        first += len(batch)

        for user in batch:
            if not isinstance(user, dict):
                print(f"\nUnexpected item in batch (not an object): {user!r}")
                continue
            if not ORCID_PATTERN.match(user["username"]):
                continue
            orcid_count += 1
            status = link_user(session, user)
            print(f"[{orcid_count}] {user['username']}: {status}")

        print(
            f"\r  ...{fetched_count} users scanned so far" + " " * 10,
            end="",
            flush=True,
        )
except Exception:
    print(f"\n\nFailed while scanning users. Resume with: KEYCLOAK_SYNC_START_FIRST={first}")
    raise

print(f"\rDone. Scanned {fetched_count} users, linked {orcid_count} ORCID-formatted ones." + " " * 10)
