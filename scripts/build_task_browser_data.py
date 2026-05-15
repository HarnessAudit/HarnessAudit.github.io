#!/usr/bin/env python3
"""Build the static Task Browser data snapshot from HarnessAudit multi-agent YAMLs."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

TASKS_PER_DOMAIN = 15

DOMAIN_META: dict[str, dict[str, str]] = {
    "finance": {
        "label": "Finance",
        "emoji": "💳",
        "color": "#2563eb",
        "blurb": "Portfolio, lending, insurance, and financial-planning workflows with scoped customer records and bounded execution authority.",
    },
    "ecommerce": {
        "label": "E-commerce",
        "emoji": "🛍️",
        "color": "#7c3aed",
        "blurb": "Marketplace, order, refund, adjustment, and seller/buyer workflows with payment and customer-data boundaries.",
    },
    "healthcare": {
        "label": "Healthcare",
        "emoji": "🩺",
        "color": "#ef4444",
        "blurb": "Clinical consultation and prescription tasks with per-patient scoping, evidence handling, and medical-safety checkpoints.",
    },
    "office": {
        "label": "Office Ops",
        "emoji": "🏢",
        "color": "#0d9488",
        "blurb": "Personnel, asset, finance, and partnership operations with department-scoped resources and approval gates.",
    },
    "social_interaction": {
        "label": "Social Interaction",
        "emoji": "💬",
        "color": "#db2777",
        "blurb": "Content moderation, public communication, report review, and voice/community workflows with private-public information-flow controls.",
    },
    "daily_life": {
        "label": "Daily Life",
        "emoji": "🌞",
        "color": "#d97706",
        "blurb": "Consumer concierge tasks across dining, travel, housing, and wellness with household/customer privacy and payment controls.",
    },
    "legal_compliance": {
        "label": "Legal Compliance",
        "emoji": "⚖️",
        "color": "#475569",
        "blurb": "Contract, litigation, and audit workflows with privileged strategy, matter-scoped evidence, and counsel/action approval boundaries.",
    },
    "software_engineering": {
        "label": "Software Engineering",
        "emoji": "💻",
        "color": "#0ea5e9",
        "blurb": "Repository-update tasks with source-code, test, pull-request, secret, production, and deployment boundary checks.",
    },
}

DOMAIN_ORDER = list(DOMAIN_META)


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def _natural_key(value: str) -> list[Any]:
    parts = re.split(r"(\d+)", value)
    return [int(p) if p.isdigit() else p for p in parts]


def _clean_text(value: Any, *, limit: int | None = None) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if limit is not None and len(text) > limit:
        return text[: max(0, limit - 1)].rstrip() + "…"
    return text


def _title_from_task(task: dict[str, Any]) -> str:
    metadata = task.get("metadata") or {}
    scenario = metadata.get("business_scenario")
    if scenario:
        return _clean_text(scenario, limit=96)
    goal = _clean_text(task.get("goal"), limit=140)
    if not goal:
        return f"{task.get('task_id', 'task')} · {task.get('category', 'task')}"
    first = re.split(r"(?<=[.!?])\s+", goal, maxsplit=1)[0]
    return _clean_text(first, limit=96)


def _tool_sort_key(tool_order: dict[str, int], name: str) -> tuple[int, list[Any]]:
    return (tool_order.get(name, 10_000), _natural_key(name))


def _metadata_summary(metadata: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    preferred = ["business_scenario", "hub_role", "difficulty"]
    for key in preferred:
        if key in metadata:
            out[key] = _clean_text(metadata[key], limit=220)
    for key in sorted(metadata):
        if key in out or key == "agents":
            continue
        value = metadata[key]
        if key.endswith("_id") or key in {"case_id", "client_id", "customer_id", "request_id", "matter_id", "order_id"}:
            if isinstance(value, (str, int, float, bool)):
                out[key] = value
            elif isinstance(value, list) and len(value) <= 8 and all(isinstance(v, (str, int, float, bool)) for v in value):
                out[key] = value
    return out


def _counter_dict(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def load_catalogs(source_root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, int]]]:
    tools_dir = source_root / "multi_agent" / "tools"
    catalogs: dict[str, Any] = {}
    tool_maps: dict[str, dict[str, Any]] = {}
    tool_orders: dict[str, dict[str, int]] = {}
    for path in sorted(tools_dir.glob("*.yaml")):
        catalog = _load_yaml(path)
        domain = catalog.get("domain")
        if domain not in DOMAIN_META:
            raise ValueError(f"Unexpected tool catalog domain {domain!r} in {path}")
        tools = catalog.get("tools") or []
        if not isinstance(tools, list):
            raise ValueError(f"tools must be a list in {path}")
        tool_maps[domain] = {tool["name"]: tool for tool in tools}
        tool_orders[domain] = {tool["name"]: idx for idx, tool in enumerate(tools)}
        catalogs[domain] = {
            "domain": domain,
            "name": catalog.get("name") or DOMAIN_META[domain]["label"],
            "description": _clean_text(catalog.get("description"), limit=360),
            "tools": [
                {
                    "name": tool.get("name"),
                    "description": _clean_text(tool.get("description"), limit=320),
                    "params": tool.get("params") or {},
                    "is_resource": bool(tool.get("is_resource")),
                    "backend_type": tool.get("backend_type") or "mock",
                }
                for tool in tools
            ],
        }
    missing = set(DOMAIN_META) - set(catalogs)
    if missing:
        raise ValueError(f"Missing tool catalogs for domains: {sorted(missing)}")
    return catalogs, tool_maps, tool_orders


def _balanced_domain_sample(
    task_records: list[dict[str, Any]],
    *,
    per_domain: int = TASKS_PER_DOMAIN,
) -> list[dict[str, Any]]:
    """Select a deterministic category-balanced display sample per domain."""

    selected: list[dict[str, Any]] = []
    for domain in DOMAIN_ORDER:
        domain_tasks = [task for task in task_records if task["domain"] == domain]
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for task in sorted(domain_tasks, key=lambda item: _natural_key(item["id"])):
            buckets[task["category"]].append(task)

        domain_selected: list[dict[str, Any]] = []
        categories = sorted(buckets, key=_natural_key)
        while categories and len(domain_selected) < per_domain:
            next_categories: list[str] = []
            for category in categories:
                if len(domain_selected) >= per_domain:
                    break
                bucket = buckets[category]
                if bucket:
                    domain_selected.append(bucket.pop(0))
                if bucket:
                    next_categories.append(category)
            categories = next_categories

        selected.extend(domain_selected)
    return selected


def build_data(source_root: Path) -> dict[str, Any]:
    tasks_dir = source_root / "multi_agent" / "tasks"
    tools_dir = source_root / "multi_agent" / "tools"
    if not tasks_dir.is_dir():
        raise FileNotFoundError(f"Task directory not found: {tasks_dir}")
    if not tools_dir.is_dir():
        raise FileNotFoundError(f"Tool directory not found: {tools_dir}")

    source_files = list(tasks_dir.rglob("*.yaml")) + list(tools_dir.glob("*.yaml"))
    snapshot_time = max((path.stat().st_mtime for path in source_files), default=0)
    generated_at = datetime.fromtimestamp(snapshot_time, timezone.utc).isoformat().replace("+00:00", "Z")

    catalogs, tool_maps, tool_orders = load_catalogs(source_root)
    task_records: list[dict[str, Any]] = []
    role_names: set[str] = set()
    category_pairs: set[tuple[str, str]] = set()
    all_task_tool_pairs: set[tuple[str, str]] = set()

    for path in sorted(tasks_dir.rglob("*.yaml"), key=lambda p: _natural_key(str(p.relative_to(tasks_dir)))):
        raw = _load_yaml(path)
        task_id = raw.get("task_id")
        domain = raw.get("domain")
        category = raw.get("category") or path.parent.name
        if not task_id or not domain:
            raise ValueError(f"Task missing task_id/domain: {path}")
        if domain not in DOMAIN_META:
            raise ValueError(f"Unexpected task domain {domain!r} in {path}")
        if domain not in tool_maps:
            raise ValueError(f"No tool catalog loaded for domain {domain!r}")
        if not raw.get("goal"):
            raise ValueError(f"Task missing goal: {path}")

        catalog_tools = tool_maps[domain]
        tool_order = tool_orders[domain]
        agents_out: list[dict[str, Any]] = []
        task_tools: set[str] = set()

        for agent in raw.get("agents") or []:
            role = agent.get("role")
            if not role:
                raise ValueError(f"Agent missing role in {path}")
            role_names.add(role)
            necessity = agent.get("tool_necessity")
            if not isinstance(necessity, dict):
                raise ValueError(f"Agent {role!r} missing tool_necessity in {path}")
            tiers: dict[str, list[str]] = {}
            for tier in ("useful", "unnecessary", "forbidden"):
                names = list(necessity.get(tier) or [])
                unknown = sorted(set(names) - set(catalog_tools))
                if unknown:
                    raise ValueError(f"Unknown {tier} tools for {role!r} in {path}: {unknown}")
                tiers[tier] = sorted(names, key=lambda n: _tool_sort_key(tool_order, n))
                task_tools.update(names)
            agents_out.append(
                {
                    "role": role,
                    "description": _clean_text(agent.get("description"), limit=240),
                    "useful_tools": tiers["useful"],
                    "unnecessary_tools": tiers["unnecessary"],
                    "forbidden_tools": tiers["forbidden"],
                }
            )

        for paths in (raw.get("ground_truth_tool_paths") or {}).values():
            for tool_path in paths or []:
                task_tools.update(name for name in tool_path if name in catalog_tools)

        access_types: list[str] = []
        severities: list[str] = []
        for rule in raw.get("access_rules") or []:
            access_type = rule.get("access_type") or "unknown"
            access_types.append(access_type)
            if rule.get("severity"):
                severities.append(str(rule.get("severity")))
            tool_name = (rule.get("match") or {}).get("tool")
            if tool_name in catalog_tools:
                task_tools.add(tool_name)

        checkpoint_types: list[str] = []
        checkpoint_rule_types: list[str] = []
        checkpoint_names: list[str] = []
        for checkpoint in raw.get("completion_checkpoints") or []:
            ctype = checkpoint.get("type") or "unknown"
            checkpoint_types.append(ctype)
            if checkpoint.get("rule_type"):
                checkpoint_rule_types.append(str(checkpoint.get("rule_type")))
            if checkpoint.get("name"):
                checkpoint_names.append(str(checkpoint.get("name")))
            tool_name = checkpoint.get("tool_name")
            if tool_name in catalog_tools:
                task_tools.add(tool_name)

        ordered_task_tools = sorted(task_tools, key=lambda n: _tool_sort_key(tool_order, n))
        resource_tools = [name for name in ordered_task_tools if bool(catalog_tools[name].get("is_resource"))]
        for name in ordered_task_tools:
            all_task_tool_pairs.add((domain, name))
        category_pairs.add((domain, category))

        input_assets = []
        for asset in raw.get("input_assets") or []:
            input_assets.append(
                {
                    "asset_type": asset.get("asset_type"),
                    "path": asset.get("path"),
                    "description": _clean_text(asset.get("description"), limit=220),
                }
            )

        task_records.append(
            {
                "id": task_id,
                "task_id": task_id,
                "domain": domain,
                "category": category,
                "modality": raw.get("modality") or "text_only",
                "fixture": raw.get("fixture"),
                "title": _title_from_task(raw),
                "goal": _clean_text(raw.get("goal"), limit=1600),
                "source_path": str(path.relative_to(source_root)),
                "metadata": _metadata_summary(raw.get("metadata") or {}),
                "input_assets": input_assets,
                "roles": [agent["role"] for agent in agents_out],
                "agents": agents_out,
                "tools": ordered_task_tools,
                "resource_tools": resource_tools,
                "access_summary": {
                    "total": len(raw.get("access_rules") or []),
                    "by_type": _counter_dict(access_types),
                    "by_severity": _counter_dict(severities),
                },
                "completion_summary": {
                    "total": len(raw.get("completion_checkpoints") or []),
                    "by_type": _counter_dict(checkpoint_types),
                    "rule_types": _counter_dict(checkpoint_rule_types),
                    "names": checkpoint_names,
                },
            }
        )

    display_task_records = _balanced_domain_sample(task_records)

    by_domain: dict[str, dict[str, Any]] = {}
    for domain in DOMAIN_ORDER:
        domain_tasks = [task for task in display_task_records if task["domain"] == domain]
        domain_roles = {role for task in domain_tasks for role in task["roles"]}
        domain_tools = {tool for task in domain_tasks for tool in task["tools"]}
        by_domain[domain] = {
            "task_count": len(domain_tasks),
            "category_count": len({task["category"] for task in domain_tasks}),
            "role_count": len(domain_roles),
            "task_tool_count": len(domain_tools),
            "resource_tool_count": len({tool for task in domain_tasks for tool in task["resource_tools"]}),
            "multimodal_task_count": sum(1 for task in domain_tasks if task["modality"] == "multimodal"),
        }

    total_tool_defs = sum(len(catalog["tools"]) for catalog in catalogs.values())
    total_resource_tool_defs = sum(
        1 for catalog in catalogs.values() for tool in catalog["tools"] if tool["is_resource"]
    )

    return {
        "generated_at": generated_at,
        "source": {
            "repo": "HarnessAudit",
            "tasks_dir": "multi_agent/tasks",
            "tools_dir": "multi_agent/tools",
        },
        "stats": {
            "task_count": len(display_task_records),
            "source_task_count": len(task_records),
            "display_tasks_per_domain": TASKS_PER_DOMAIN,
            "domain_count": len(DOMAIN_ORDER),
            "category_count": len(category_pairs),
            "role_template_count": len(role_names),
            "tool_definition_count": total_tool_defs,
            "resource_tool_definition_count": total_resource_tool_defs,
            "task_tool_count": len(all_task_tool_pairs),
            "multimodal_task_count": sum(1 for task in display_task_records if task["modality"] == "multimodal"),
            "by_domain": by_domain,
        },
        "domains": [
            {"id": domain, **DOMAIN_META[domain]}
            for domain in DOMAIN_ORDER
        ],
        "tools": {domain: catalogs[domain] for domain in DOMAIN_ORDER},
        "tasks": display_task_records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "HarnessAudit",
        help="Path to the HarnessAudit repo root containing multi_agent/tasks and multi_agent/tools.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "static" / "js" / "task_data.js",
        help="Output JS file path.",
    )
    args = parser.parse_args()

    source_root = args.source.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    data = build_data(source_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    output_path.write_text(
        "// Generated by scripts/build_task_browser_data.py. Do not edit manually.\n"
        f"window.HA_TASK_BROWSER_DATA = {payload};\n",
        encoding="utf-8",
    )
    print(
        f"wrote {output_path} "
        f"({data['stats']['task_count']} tasks, {data['stats']['tool_definition_count']} tools)"
    )


if __name__ == "__main__":
    main()
