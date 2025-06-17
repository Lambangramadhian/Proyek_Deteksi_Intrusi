import json
import urllib.parse
from datetime import datetime

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
    parsed_body = {}

    if isinstance(raw_payload, str):
        try:
            parsed = json.loads(raw_payload)
            if isinstance(parsed, list) and parsed:
                full_body = dict(parsed[0])
                args = full_body.pop("args", {})
                if isinstance(args, dict):
                    formdata_raw = args.get("formdata")
                    if isinstance(formdata_raw, str):
                        formdata_parsed = _extract_formdata(formdata_raw, url, ip, logger)
                        args.update(formdata_parsed)
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

    raw_value = parsed_body.get("raw")
    if isinstance(raw_value, str):
        decoded_raw = urllib.parse.unquote_plus(raw_value)
        if "formdata=" in decoded_raw:
            parsed_body.update(_extract_formdata(decoded_raw, url, ip, logger))
        else:
            try:
                parsed_body.update(dict(urllib.parse.parse_qsl(decoded_raw)))
            except Exception:
                pass

    return parsed_body

def _extract_formdata(decoded_raw: str, url: str, ip: str, logger=None) -> dict:
    try:
        formdata_encoded = decoded_raw.split("formdata=")[-1]
        formdata_encoded = urllib.parse.unquote_plus(formdata_encoded)

        stop_tokens = [" index=", " methodname=", " info=", " HTTP/", " args=", " headers="]
        for token in stop_tokens:
            if token in formdata_encoded:
                formdata_encoded = formdata_encoded.split(token)[0]

        parsed_formdata = dict(urllib.parse.parse_qsl(formdata_encoded))

        if isinstance(parsed_formdata.get("args"), dict):
            parsed_formdata.update(parsed_formdata.pop("args"))

        if logger:
            logger.info(json.dumps({
                "timestamp": now_str(),
                "level": "INFO",
                "event": "formdata_detected",
                "ip": ip,
                "url": url,
                "fields": list(parsed_formdata.keys())
            }))

            important_keys = ["name", "username", "userid", "eventtype"]
            if not all(k in parsed_formdata for k in important_keys):
                logger.warning(json.dumps({
                    "timestamp": now_str(),
                    "level": "WARN",
                    "event": "formdata_parsed_but_missing_important_fields",
                    "url": url,
                    "ip": ip,
                    "keys": list(parsed_formdata.keys())
                }))

        return parsed_formdata

    except Exception as e:
        if logger:
            logger.warning(json.dumps({
                "timestamp": now_str(),
                "level": "WARN",
                "event": "formdata_parse_failed",
                "error": str(e),
                "url": url,
                "ip": ip,
                "snippet": decoded_raw[:100]
            }))
        return {}