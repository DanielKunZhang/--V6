# V6 GitHub and Reporting SOP

- Created: 2026-05-11
- Scope: V6 branch management, GitHub upload, read-only weekly/monthly/quarterly reporting.
- Boundary: This SOP does not authorize live trading. V6-A live pilot still requires explicit manual confirmation.

## Current GitHub State

- Remote: `git@github.com:DanielKunZhang/my-trading-system-1.git`
- Auth: SSH authentication has passed.
- V6 working branch: `v6-governance-and-reporting`

## Upload Code To GitHub

Check current branch:

```bash
git status --short --branch
```

If not on the V6 branch:

```bash
git switch v6-governance-and-reporting
```

Review changed files before staging:

```bash
git status --short
```

Stage only V6 reporting/governance files:

```bash
git add v6_reporting.py
git add v6_strategy_lab/configs/v6_reporting_policy_v1.json
git add V6_GITHUB_AND_REPORTING_SOP.md
git add V6_STRATEGY_LAB.md
```

Commit:

```bash
git commit -m "feat: add V6 reporting and governance SOP"
```

First push of a new branch:

```bash
git push -u origin v6-governance-and-reporting
```

Future pushes on the same branch:

```bash
git push
```

## Permission Model

GitHub upload works through SSH. If push fails with `Permission denied (publickey)`, check:

```bash
ssh -T git@github.com
```

Expected result:

```text
Hi DanielKunZhang/my-trading-system-1! You've successfully authenticated, but GitHub does not provide shell access.
```

If this message appears, SSH permission is fine. A failed push is then usually caused by branch protection, remote mismatch, or trying to push to a different repo.

## V6 Reporting

Generate a weekly report without email:

```bash
python3 v6_reporting.py --period weekly
```

Generate monthly or quarterly reports:

```bash
python3 v6_reporting.py --period monthly
python3 v6_reporting.py --period quarterly
```

Outputs:

```text
backtest_results/v6_reporting/latest_weekly.json
backtest_results/v6_reporting/latest_weekly.md
backtest_results/v6_reporting/latest_weekly.html
backtest_results/v6_reporting/runs/
```

The report summarizes:

- V6-A launch policy, release gate, latest preview orders, and pilot status.
- V6-B scorecard and live-forward state.
- Allocator case and current sleeve weights.
- Required user action: `不动 / 需要用户确认 / 禁止实盘`.

## Optional Email

Email is disabled by default. V6 first reuses the existing V3 notifier, which loads local email config through `.ic_env.local` and sends to `quanyi_zk@163.com`.

Run:

```bash
python3 v6_reporting.py --period weekly --send-email
```

If the V3 notifier is unavailable, V6 falls back to dedicated `V6_EMAIL_*` variables:

```bash
export V6_EMAIL_SMTP_SERVER="smtp.example.com"
export V6_EMAIL_SMTP_PORT="465"
export V6_EMAIL_SENDER="sender@example.com"
export V6_EMAIL_PASSWORD="app_password"
export V6_EMAIL_RECIPIENT="recipient@example.com"
```

Then run:

```bash
python3 v6_reporting.py --period weekly --send-email
```

Email is read-only. It must not be used as an automatic trading trigger.

## Reporting Cadence

- Daily: operational check only. OpenD, orders, account snapshot, exceptions.
- Weekly: V6-A vs actual state, V6-B live-forward, allocator state, whether user action is needed.
- Monthly: Dynamic Universe refresh review and missed-opportunity review.
- Quarterly: full replay, release gate, black swan, rolling windows, robustness, tradability, engine/core pool review.

## Git Hygiene

Do not commit:

- API keys, SMTP passwords, Futu credentials.
- Full unmasked account statements.
- Tax PDFs or raw broker exports.
- Sensitive full trade history unless explicitly masked.

Commit:

- Code.
- Config without secrets.
- SOPs.
- Strategy specs.
- Non-sensitive summary reports.
