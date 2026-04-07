from futu import *
import numpy as np
from datetime import date, datetime, timedelta

quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)

# 获取VIX代码（富途中VIX代码可能是US.VIX或类似的）
# 先尝试获取VIX的实时价格
ret, data = quote_ctx.get_market_snapshot(['US.VIX'])
if ret == RET_OK and not data.empty:
    print(f'VIX 当前价格: {data.iloc[0]["last_price"]:.2f}')
    print(f'VIX 涨跌幅: {data.iloc[0]["change_rate"]*100:.2f}%')
else:
    # 如果US.VIX不存在，尝试其他常见代码
    print('无法获取VIX数据，富途可能没有直接的VIX代码')
    print('尝试获取SPY作为替代参考...')
    ret, data = quote_ctx.get_market_snapshot(['US.SPY'])
    if ret == RET_OK and not data.empty:
        print(f'SPY 当前价: ${data.iloc[0]["last_price"]:.2f}')
        print(f'SPY 涨跌幅: {data.iloc[0]["change_rate"]*100:.2f}%')

quote_ctx.close()