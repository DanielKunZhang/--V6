from typing import Dict, List


def capacity_band(actual_capital: float, capacity_control: Dict) -> str:
    if actual_capital < capacity_control["soft_actual_capital_usd"]:
        return "small"
    if actual_capital < capacity_control["auto_downgrade_to_e_actual_usd"]:
        return "medium"
    return "large"


def build_capacity_policy(
    actual_capital: float,
    groups_cap_mult: int,
    capacity_control: Dict,
) -> Dict:
    band = capacity_band(actual_capital, capacity_control)
    policy = {
        "actual_capital": actual_capital,
        "band": band,
        "band_label": {
            "small": "小资金档",
            "medium": "中资金档",
            "large": "大资金档",
        }[band],
        "difficulty": {
            "small": "低",
            "medium": "中",
            "large": "高",
        }[band],
        "cap_mult": groups_cap_mult,
        "requested_cap_mult": groups_cap_mult,
        "soft_threshold": capacity_control["soft_actual_capital_usd"],
        "downgrade_threshold": capacity_control["auto_downgrade_to_e_actual_usd"],
        "review_threshold": capacity_control["hard_review_actual_usd"],
    }
    if (
        actual_capital >= capacity_control["auto_downgrade_to_e_actual_usd"]
        and groups_cap_mult > capacity_control["downgrade_cap_mult"]
    ):
        policy["cap_mult"] = capacity_control["downgrade_cap_mult"]
        policy["auto_downgraded"] = True
    else:
        policy["auto_downgraded"] = False
    policy["batch_groups"] = capacity_control["batch_groups"][band]
    policy["needs_review"] = actual_capital >= capacity_control["hard_review_actual_usd"]
    return policy


def build_capacity_snapshot(
    assets: List[Dict],
    actual_capital: float,
    leverage: float,
    groups_cap_mult: int,
    capacity_control: Dict,
) -> Dict:
    policy = build_capacity_policy(actual_capital, groups_cap_mult, capacity_control)
    baseline_nominal = sum(asset["capital"] for asset in assets)
    nominal_capital = actual_capital * leverage
    scale = nominal_capital / max(baseline_nominal, 1)

    per_asset = []
    total_groups = 0
    total_legs = 0

    for asset in assets:
        base_groups = int(asset["max_groups"])
        estimated_groups = min(
            base_groups * int(policy["cap_mult"]),
            max(base_groups, int(base_groups * scale)),
        )
        legs = estimated_groups * 4
        batch_limit = int(policy["batch_groups"].get(asset["name"], estimated_groups))
        per_asset.append({
            "ticker": asset["ticker"],
            "name": asset["name"],
            "base_capital": float(asset["capital"]),
            "base_groups": base_groups,
            "allocation_pct": asset["capital"] / max(baseline_nominal, 1),
            "estimated_groups": estimated_groups,
            "estimated_legs": legs,
            "batch_limit": max(1, min(estimated_groups, batch_limit)),
            "hv20_threshold": float(asset.get("hv20_threshold", 0.0)),
        })
        total_groups += estimated_groups
        total_legs += legs

    return {
        **policy,
        "actual_capital": actual_capital,
        "nominal_capital": nominal_capital,
        "leverage": leverage,
        "baseline_nominal_capital": baseline_nominal,
        "scale": scale,
        "per_asset": per_asset,
        "total_groups": total_groups,
        "total_legs": total_legs,
    }
