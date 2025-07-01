# =====================
# Library Internal (modul bawaan Python)
# =====================
import json                                 # Untuk serialisasi dan deserialisasi data JSON
import re                                   # Untuk pencocokan pola string menggunakan regular expressions
import urllib.parse                         # Untuk parsing dan manipulasi URL (redundan dengan baris di bawah)

from datetime import datetime               # Untuk manipulasi dan format data waktu/tanggal
from urllib.parse import (                  # Ekstraksi dan manipulasi bagian-bagian URL secara spesifik
    urlparse,                               # Memecah URL menjadi bagian-bagian (skema, host, path, dll.)
    parse_qsl,                              # Parsing query string menjadi list pasangan key-value
    urlencode,                              # Mengubah dictionary menjadi query string URL
    urlunparse,                             # Menggabungkan kembali bagian-bagian URL
    unquote_plus                            # Menghapus encoding dari query string
)

def flatten_dict(d, parent_key='', sep='||'):
    """Meratakan kamus bersarang menjadi kamus tingkat tunggal dengan kunci sebagai string yang digabungkan."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

def mask_sensitive_fields(flat_dict: dict, sensitive_keys=None) -> str:
    """Mengembalikan string yang berisi pasangan key-value dari kamus, dengan nilai sensitif yang dimasker."""
    if sensitive_keys is None:
        sensitive_keys = ["password", "token", "auth", "key", "sesskey", "apikey", "access_token"]

    # Pastikan semua kunci sensitif dalam huruf kecil untuk pencocokan yang konsisten
    pairs = []
    for k, v in flat_dict.items():
        key_lower = k.lower()
        is_sensitive = any(s in key_lower for s in sensitive_keys)

        # Decode nilai jika bukan sensitif, atau mask jika sensitif
        v_str = urllib.parse.unquote_plus(str(v)) if isinstance(v, str) else str(v)
        if is_sensitive:
            v_str = "*****"

        # Tambahkan pasangan key-value ke daftar
        pairs.append(f"{k}={v_str}")
    return " ".join(pairs)

def now_str():
    """Mengembalikan string waktu saat ini dalam format 'YYYY-MM-DD HH:MM:SS'."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def parse_payload(raw_payload, url=None, ip=None, logger=None):
    """
    Mengurai payload dari permintaan HTTP menjadi kamus Python yang dapat diproses oleh model.
    Menangani:
    - JSON string (berisi list/dict)
    - dict langsung
    - string URL-encoded
    - field `formdata` yang mengandung query string
    """
    parsed_body = {}

    # Tahap 1: Coba parse dari JSON string
    if isinstance(raw_payload, str):
        try:
            parsed = json.loads(raw_payload)
            if isinstance(parsed, list) and parsed:
                full_body = dict(parsed[0])
                args = full_body.pop("args", {})

                # Tangani args jika berupa list of {"name":..., "value":...}
                if isinstance(args, list):
                    parsed_args = {}
                    for arg in args:
                        k = arg.get("name")
                        v = arg.get("value")
                        if k:
                            # Jika value berupa query string, parse ulang
                            if isinstance(v, str) and "=" in v and "&" in v:
                                try:
                                    sub_items = dict(parse_qsl(v))
                                    for sub_k, sub_v in sub_items.items():
                                        parsed_args[f"{k}.{sub_k}"] = sub_v
                                except Exception:
                                    parsed_args[k] = v
                            else:
                                parsed_args[k] = v
                    full_body.update(parsed_args)

                elif isinstance(args, dict):
                    full_body.update(args)

                parsed_body = full_body

            elif isinstance(parsed, dict):
                parsed_body = parsed
            else:
                parsed_body = {"raw": str(parsed)}

        except json.JSONDecodeError:
            parsed_body = {"raw": raw_payload}

    # Tahap 2: Jika sudah dict sejak awal
    elif isinstance(raw_payload, dict):
        parsed_body = raw_payload

    # Tahap 3: Fallback, jika bukan dict/string
    else:
        parsed_body = {"raw": str(raw_payload)}

    # Tahap 4: Coba decode bagian "raw" jika masih ada
    raw_value = parsed_body.get("raw")
    if isinstance(raw_value, str):
        try:
            decoded_raw = unquote_plus(raw_value)
            parsed_qs = dict(parse_qsl(decoded_raw))
            parsed_body.update(parsed_qs)
        except Exception:
            pass

    # Tahap 5: Tangani formdata jika ada (khusus Moodle/AJAX)
    formdata_value = parsed_body.get("formdata")
    if isinstance(formdata_value, str) and "=" in formdata_value:
        try:
            formdata_parsed = dict(parse_qsl(formdata_value))
            parsed_body.update(formdata_parsed)
        except Exception:
            pass

    return parsed_body

def mask_url_query(url: str, sensitive_keys=None) -> str:
    """Menyembunyikan parameter kueri dalam URL, mengganti kunci sensitif dengan '*****'."""
    if sensitive_keys is None:
        sensitive_keys = ["sesskey", "token", "key", "access_token", "apikey", "auth", "password"]

    # Jika URL tidak valid, kembalikan seperti semula
    parts = urlparse(url)
    query = parse_qsl(parts.query)
    masked = [
        (k, "*****" if any(s in k.lower() for s in sensitive_keys) else v)
        for k, v in query
    ]
    new_query = urlencode(masked)
    return urlunparse(parts._replace(query=new_query))

def mask_inline_sensitive_fields(s: str, sensitive_keys=None) -> str:
    """Menyembunyikan nilai sensitif dalam string dengan mengganti nilai kunci tertentu dengan '*****'."""
    if sensitive_keys is None:
        sensitive_keys = ["sesskey", "token", "auth", "key", "apikey", "access_token", "password"]

    # Gunakan regex untuk mencari dan mengganti nilai kunci sensitif
    for key in sensitive_keys:
        s = re.sub(
            rf'(?<=&){key}=.*?(?=&|$)',
            f'{key}=*****',
            s,
            flags=re.IGNORECASE
        )
    return s