#!/usr/bin/env python3
"""调试到期日接口"""
from futu import *
from datetime import datetime

quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
result = quote_ctx.get_option_expiration_date('HK.00700')
print(f"result type={type(result)}, len={len(result)}")
for i, r in enumerate(result):
    print(f"[{i}] type={type(r)}, val={r}")
quote_ctx.close()
