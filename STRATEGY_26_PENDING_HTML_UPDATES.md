# 26 年组合策略计划 HTML 待合并更新

> 正式 HTML：`/Users/zhangkun/Desktop/AI个人投资公司/26年阶段性组合策略计划.html`
> 当前状态：2026-05-19 读取/写入被 macOS 权限拦截，先在本文件记录待合并内容。

## 合并规则

每完成一个 HQ Compounder 策略制定或重估，必须同步更新：

- 对应重估 Markdown 文件。
- `investment_screener/watchlist.json`。
- `AI_HANDOFF_CURRENT.md`。
- 26 年组合策略计划 HTML。

如果 HTML 暂时不可写，则先写入本文件，待权限恢复后合并。

## 2026-05-19 腾讯控股 HQ Compounder 重估

来源文件：`HQ_COMPOUNDER_TENCENT_20260519.md`

应同步到 HTML 的核心结论：

- 分类：`Core HQ Compounder / Hold But Deweight`
- 保留核心资格，但当前约 31.8% 总暴露过高。
- 目标仓位：`12%-15%`
- 阶段上限：`18%-20%`
- 当前 HK$460 附近不新增。
- HK$430-440 以下才重新复核是否暂停减仓或小幅回补。
- HK$380-400 以下且 thesis 未破，才进入错杀增配区。
- HK$600+ 开始更积极降权；HK$650+ 进入估值兑现/再平衡区。

应替换/补充的 HTML 表述：

```html
<td><strong>腾讯（富途 + RSU + 港股通）</strong></td>
<td>约 31.8%（2100 股，约 12.37 万 USD）</td>
<td>12%-15%（阶段上限 18%-20%）</td>
<td><span class="pill core">高质量错杀复利仓 / 当前降权</span></td>
<td>持有，等待合适窗口继续降超配；当前不新增</td>
<td>2026-05-19 HQ Compounder 重估：腾讯仍是 Core HQ Compounder，但当前不是特别错杀价。HK$430-440 以下重新复核；HK$380-400 以下且 thesis 未破才进入错杀增配区；HK$600+ 触发更积极降权复核。</td>
```

应在近期更新区补充：

```html
<div class="notice" style="margin-top:14px;">
  <strong>2026-05-19 腾讯 HQ Compounder 重估：</strong>
  腾讯 2026Q1 继续验证平台现金流质量（收入 +9%、non-IFRS 股东净利 +11%、FCF +20%），仍符合高质量错杀复利仓定义。
  但当前问题是仓位过高而非质量不足：总暴露约 31.8%，目标降至 12%-15%，阶段上限 18%-20%。当前 HK$460 不新增；HK$430-440 以下重新复核；HK$380-400 以下且 thesis 未破才进入错杀增配区。
</div>
```

