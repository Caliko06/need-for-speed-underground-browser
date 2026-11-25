#!/usr/bin/env python3
"""Update Cache-Control on existing R2 game/* objects in-place (zero upload) via S3 CopyObject MetadataDirective=REPLACE.
Run ONLY with the OWNER's go: set -a; . ~/.config/cloudflare/credentials.env; set +a; python3 tools/r2_set_immutable.py nfsu
"""
import hashlib, hmac, os, sys, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

BUCKET = sys.argv[1] if len(sys.argv) > 1 else "nfsu"
PREFIX = sys.argv[2] if len(sys.argv) > 2 else "game/"
IMMUTABLE = "public, max-age=31536000, immutable"
AK, SK, EP = os.environ["R2_ACCESS_KEY_ID"], os.environ["R2_SECRET_ACCESS_KEY"], os.environ["R2_ENDPOINT"].rstrip("/")
HOST = urllib.parse.urlparse(EP).netloc

def req(method, path, query="", extra=None):
    now = datetime.now(timezone.utc)
    amz, ds = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    ph = hashlib.sha256(b"").hexdigest()
    uri = urllib.parse.quote(path, safe="/~-._")
    hdrs = {"host": HOST, "x-amz-content-sha256": ph, "x-amz-date": amz}
    for k, v in (extra or {}).items():
        hdrs[k.lower()] = v
    sh = ";".join(sorted(hdrs))
    ch = "".join(f"{k}:{hdrs[k]}\n" for k in sorted(hdrs))
    cr = f"{method}\n{uri}\n{query}\n{ch}\n{sh}\n{ph}"
    scope = f"{ds}/auto/s3/aws4_request"
    sts = f"AWS4-HMAC-SHA256\n{amz}\n{scope}\n{hashlib.sha256(cr.encode()).hexdigest()}"
    sign = lambda k, m: hmac.new(k, m.encode(), hashlib.sha256).digest()
    key = sign(sign(sign(sign(("AWS4" + SK).encode(), ds), "auto"), "s3"), "aws4_request")
    sig = hmac.new(key, sts.encode(), hashlib.sha256).hexdigest()
    send = {k: v for k, v in hdrs.items() if k != "host"}
    send["Authorization"] = f"AWS4-HMAC-SHA256 Credential={AK}/{scope}, SignedHeaders={sh}, Signature={sig}"
    r = urllib.request.Request(f"{EP}{uri}" + (f"?{query}" if query else ""), method=method, headers=send)
    with urllib.request.urlopen(r, timeout=30) as resp:
        return resp.read(), resp.headers

keys, tok = [], None
ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
while True:
    q = f"list-type=2&prefix={urllib.parse.quote(PREFIX, safe='')}" + (f"&continuation-token={urllib.parse.quote(tok, safe='')}" if tok else "")
    root = ET.fromstring(req("GET", f"/{BUCKET}", q)[0])
    keys += [c.find("s3:Key", ns).text for c in root.findall("s3:Contents", ns)]
    nt = root.find("s3:NextContinuationToken", ns)
    if nt is None:
        break
    tok = nt.text

def update_one(k):
    _, h = req("HEAD", f"/{BUCKET}/{k}")
    if h.get("Cache-Control") == IMMUTABLE:
        return "skip"
    ct = h.get("Content-Type") or "application/octet-stream"
    src = f"/{BUCKET}/{urllib.parse.quote(k, safe='/~-._')}"
    req("PUT", f"/{BUCKET}/{k}", extra={
        "x-amz-copy-source": src, "x-amz-metadata-directive": "REPLACE",
        "cache-control": IMMUTABLE, "content-type": ct,
    })
    return "updated"

with ThreadPoolExecutor(max_workers=16) as ex:
    res = list(ex.map(update_one, keys))
print(f"{BUCKET}/{PREFIX}: total={len(keys)} updated={res.count('updated')} skipped={res.count('skip')}")
