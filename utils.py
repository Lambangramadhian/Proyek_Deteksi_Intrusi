import json
import urllib.parse
from datetime import datetime
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

def flatten_dict(d, parent_key='', sep='||'):
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

def mask_sensitive_fields(flat_dict: dict, sensitive_keys=None) -> str:
    if sensitive_keys is None:
        sensitive_keys = ["password", "token", "auth", "key", "sesskey", "apikey", "access_token"]
    return " ".join(
        f"{k}=*****" if any(s in k.lower() for s in sensitive_keys) else f"{k}={v}"
        for k, v in flat_dict.items()
    )

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def parse_payload(raw_payload, url=None, ip=None, logger=None):
    # Decode payload hanya satu kali
    parsed_body = {}

    if isinstance(raw_payload, str):
        try:
            parsed = json.loads(raw_payload)
            if isinstance(parsed, list) and parsed:
                full_body = dict(parsed[0])
                args = full_body.pop("args", {})
                if isinstance(args, dict):
                    full_body.update(args)
                parsed_body = full_body
            elif isinstance(parsed, dict):
                parsed_body = parsed
            else:
                parsed_body = {"raw": str(parsed)}
        except json.JSONDecodeError:
            parsed_body = {"raw": raw_payload}
    elif isinstance(raw_payload, dict):
        parsed_body = raw_payload
    else:
        parsed_body = {"raw": str(raw_payload)}

    # Coba decode nilai "raw" jika ada
    raw_value = parsed_body.get("raw")
    if isinstance(raw_value, str):
        try:
            decoded_raw = urllib.parse.unquote_plus(raw_value)
            parsed_body.update(dict(urllib.parse.parse_qsl(decoded_raw)))
        except Exception:
            pass

    return parsed_body

def mask_url_query(url: str, sensitive_keys=None) -> str:
    if sensitive_keys is None:
        sensitive_keys = ["sesskey", "token", "key", "access_token", "apikey", "auth", "password"]

    parts = urlparse(url)
    query = parse_qsl(parts.query)
    masked = [
        (k, "*****" if any(s in k.lower() for s in sensitive_keys) else v)
        for k, v in query
    ]
    new_query = urlencode(masked)
    return urlunparse(parts._replace(query=new_query))