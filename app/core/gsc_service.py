"""Google Search Console (Search Analytics) helper.

Auth uses a service-account JSON credential (Search Console has no plain API
key). The service account's email must be added as a user on the property in
Search Console. `google-auth` is imported lazily so the app still starts if the
package isn't installed yet.
"""
import json
from datetime import date, timedelta

SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"


def _access_token(sa_json: str) -> str:
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request as GoogleRequest

    info = json.loads(sa_json)
    creds = service_account.Credentials.from_service_account_info(info, scopes=[SCOPE])
    creds.refresh(GoogleRequest())
    return creds.token


def fetch_metrics(site_url: str, sa_json: str, days: int = 28) -> dict:
    import requests

    token = _access_token(sa_json)
    end = date.today()
    start = end - timedelta(days=days)
    encoded = requests.utils.quote(site_url, safe="")
    url = f"https://searchconsole.googleapis.com/webmasters/v3/sites/{encoded}/searchAnalytics/query"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def query(dimensions, row_limit=10):
        body = {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "dimensions": dimensions,
            "rowLimit": row_limit,
        }
        r = requests.post(url, headers=headers, json=body, timeout=30)
        r.raise_for_status()
        return r.json().get("rows", [])

    def fmt(rows):
        return [
            {
                "key": r["keys"][0],
                "clicks": r.get("clicks", 0),
                "impressions": r.get("impressions", 0),
                "ctr": r.get("ctr", 0),
                "position": r.get("position", 0),
            }
            for r in rows
        ]

    totals_rows = query([], 1)
    t = totals_rows[0] if totals_rows else {}
    return {
        "range": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
        "totals": {
            "clicks": t.get("clicks", 0),
            "impressions": t.get("impressions", 0),
            "ctr": t.get("ctr", 0),
            "position": t.get("position", 0),
        },
        "top_queries": fmt(query(["query"], 10)),
        "top_pages": fmt(query(["page"], 10)),
    }
