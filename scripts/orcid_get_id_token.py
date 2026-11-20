"""Run the ORCID OIDC authorization-code flow and print the id_token claims.

ORCID does not support the password or client_credentials grants for
end-user login, so this drives the interactive authorization-code flow.
ORCID also requires the redirect_uri to be https and to exactly match one
already registered for the client, so this cannot spin up a local
http://localhost callback listener — instead it opens a browser for you to
log in/consent, then asks you to paste back the URL (or just the `code`
param) that your browser was redirected to. It then exchanges the code for
tokens and decodes the id_token (without verifying its signature — this is
for inspection only).

Env vars:
  ORCID_CLIENT_ID       (required) API client ID registered with ORCID.
  ORCID_CLIENT_SECRET   (required) API client secret.
  ORCID_REDIRECT_URI    (required) Must exactly match a redirect URI
                         registered for the client (must be https).
  ORCID_ENV             "production" (default) or "sandbox".
  ORCID_SCOPE           Default: "openid".
"""

from __future__ import annotations

import base64
import json
import os
import webbrowser
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

ORCID_ENV = os.getenv("ORCID_ENV", "production")
ORCID_BASE = (
    "https://sandbox.orcid.org" if ORCID_ENV == "sandbox" else "https://orcid.org"
)

CLIENT_ID = os.environ["ORCID_CLIENT_ID"]
CLIENT_SECRET = os.environ["ORCID_CLIENT_SECRET"]
SCOPE = os.getenv("ORCID_SCOPE", "openid")
REDIRECT_URI = os.environ["ORCID_REDIRECT_URI"]


def get_authorization_code() -> str:
    """Open a browser for user login/consent; ask the user to paste back the code."""
    authorize_url = f"{ORCID_BASE}/oauth/authorize?" + urlencode(
        {
            "client_id": CLIENT_ID,
            "response_type": "code",
            "scope": SCOPE,
            "redirect_uri": REDIRECT_URI,
        }
    )
    print(f"Opening browser for ORCID login:\n  {authorize_url}\n")
    webbrowser.open(authorize_url)

    pasted = input(
        "After approving, paste the full URL you were redirected to "
        "(or just the 'code' value) here: "
    ).strip()

    parsed = urlparse(pasted)
    params = parse_qs(parsed.query)
    if "code" in params:
        return params["code"][0]
    if "error" in params:
        raise SystemExit(f"ORCID authorization failed: {params['error'][0]}")
    # Not a URL — assume the user pasted the bare code value.
    return pasted


def exchange_code_for_tokens(code: str) -> dict:
    resp = httpx.post(
        f"{ORCID_BASE}/oauth/token",
        headers={"Accept": "application/json"},
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
    )
    resp.raise_for_status()
    return resp.json()


def decode_jwt_segment(segment: str) -> dict:
    padded = segment + "=" * (-len(segment) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def get_userinfo(access_token: str) -> dict:
    resp = httpx.get(
        f"{ORCID_BASE}/oauth/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    code = get_authorization_code()
    tokens = exchange_code_for_tokens(code)

    id_token = tokens.get("id_token")
    if not id_token:
        raise SystemExit(
            f"No id_token in response — was scope=openid requested? Response: {tokens}"
        )

    header_b64, payload_b64, _signature = id_token.split(".")
    header = decode_jwt_segment(header_b64)
    claims = decode_jwt_segment(payload_b64)

    print("\n--- id_token header ---")
    print(json.dumps(header, indent=2))
    print("\n--- id_token claims ---")
    print(json.dumps(claims, indent=2))

    access_token = tokens.get("access_token")
    if access_token:
        userinfo = get_userinfo(access_token)
        print("\n--- userinfo ---")
        print(json.dumps(userinfo, indent=2))
    else:
        print("\nNo access_token in response — skipping userinfo call.")


if __name__ == "__main__":
    main()
