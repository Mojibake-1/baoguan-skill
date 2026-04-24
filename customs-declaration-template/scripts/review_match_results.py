#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Review declaration commodity match candidates with quantity/box-spec gates."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


HIGH_CONFIDENCE = "高置信"
LOW_CONFIDENCE = "低置信"
NEEDS_MANUAL = "需要人工确认"
AUTO_CANDIDATE = "可自动匹配"

PACK_RE = re.compile(r"(\d+)\s*个装")
REGION_SUFFIX_RE = re.compile(r"(UK|US|EU|UC|DE|JP|CA|AU)$", re.IGNORECASE)
NORMALIZE_RE = re.compile(r"[^0-9A-Z\u4e00-\u9fff]+")


@dataclass(frozen=True)
class Thresholds:
    quantity_tolerance_units: float = 0.0
    close_pct: float = 0.02
    minor_pct: float = 0.05
    severe_pct: float = 0.15
    very_severe_pct: float = 0.30
    strong_name_similarity: float = 0.82
    high_confidence_score: float = 90.0


SUMMARY_FIELDS = [
    "seq",
    "状态",
    "是否可自动采用",
    "原商品名",
    "申报型号",
    "箱数",
    "期望数量",
    "期望箱规",
    "建议候选源行",
    "建议候选商品",
    "建议候选SKU",
    "建议候选规格型号",
    "候选箱规",
    "候选数量",
    "数量差异",
    "数量差异比例",
    "新评分",
    "旧首选源行",
    "旧首选SKU",
    "旧首选箱规",
    "旧首选数量",
    "旧首选数量差异",
    "误排原因",
    "复核/运营动作",
]

DETAIL_FIELDS = [
    "seq",
    "候选排序",
    "候选判定",
    "可自动采用",
    "源行",
    "商品内容",
    "平台SKU",
    "规格型号",
    "旧评分",
    "新评分",
    "名称相似度",
    "型号/SKU精确命中",
    "包装数一致",
    "原包装数",
    "候选包装数",
    "期望箱规",
    "候选箱规",
    "箱规差异",
    "箱规差异比例",
    "期望数量",
    "候选数量",
    "数量差异",
    "数量差异比例",
    "HS编码",
    "申报品名",
    "问题/依据",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Review trial declaration match results and export summary/detail tables."
    )
    parser.add_argument("--input", required=True, type=Path, help="trial-match-results.json")
    parser.add_argument("--output-summary", required=True, type=Path, help="summary CSV path")
    parser.add_argument("--output-detail", required=True, type=Path, help="candidate detail CSV path")
    parser.add_argument("--output-json", type=Path, help="optional reviewed JSON path")
    parser.add_argument(
        "--quantity-tolerance-units",
        type=float,
        default=0.0,
        help="absolute quantity tolerance for an exact quantity/box-spec gate",
    )
    parser.add_argument(
        "--strong-name-similarity",
        type=float,
        default=0.82,
        help="name similarity needed when SKU/model is not an exact match",
    )
    return parser.parse_args()


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def fmt_number(value: float | None, digits: int = 2) -> str:
    if value is None:
        return ""
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.{digits}f}".rstrip("0").rstrip(".")


def fmt_pct(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.1%}"


def pct_delta(delta: float | None, expected: float | None) -> float | None:
    if delta is None or expected in (None, 0):
        return None
    return delta / expected


def normalize_text(value: Any) -> str:
    text = str(value or "").upper().strip()
    text = REGION_SUFFIX_RE.sub("", text)
    return NORMALIZE_RE.sub("", text)


def name_similarity(left: Any, right: Any) -> float:
    left_norm = normalize_text(left)
    right_norm = normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def extract_pack_count(value: Any) -> int | None:
    match = PACK_RE.search(str(value or ""))
    return int(match.group(1)) if match else None


def same_text(left: Any, right: Any) -> bool:
    return normalize_text(left) == normalize_text(right) and normalize_text(left) != ""


def score_box_match(delta_pct_abs: float | None, is_exact: bool, thresholds: Thresholds) -> tuple[float, str]:
    if delta_pct_abs is None:
        return 0.0, "缺少期望数量或候选数量"
    if is_exact:
        return 55.0, "数量/箱规一致"
    if delta_pct_abs <= thresholds.close_pct:
        return 25.0, "数量/箱规接近但不一致"
    if delta_pct_abs <= thresholds.minor_pct:
        return 10.0, "数量/箱规小幅不一致"
    if delta_pct_abs <= thresholds.severe_pct:
        return -15.0, "数量/箱规明显不一致"
    if delta_pct_abs <= thresholds.very_severe_pct:
        return -35.0, "数量/箱规严重不一致"
    return -55.0, "数量/箱规严重偏离"


def analyze_candidate(
    record: dict[str, Any],
    candidate: dict[str, Any],
    rank: int,
    thresholds: Thresholds,
) -> dict[str, Any]:
    cartons = as_float(record.get("cartons"))
    expected_qty = as_float(record.get("expected_qty"))
    expected_pcs = expected_qty / cartons if cartons not in (None, 0) and expected_qty is not None else None

    candidate_pcs = as_float(candidate.get("pcs_per_ctn"))
    calculated = candidate.get("calculated") or {}
    candidate_qty = as_float(calculated.get("quantity"))
    if candidate_qty is None and cartons is not None and candidate_pcs is not None:
        candidate_qty = cartons * candidate_pcs

    qty_delta = candidate_qty - expected_qty if candidate_qty is not None and expected_qty is not None else None
    qty_delta_abs = abs(qty_delta) if qty_delta is not None else None
    qty_delta_pct = pct_delta(qty_delta, expected_qty)
    qty_delta_pct_abs = abs(qty_delta_pct) if qty_delta_pct is not None else None
    quantity_exact = (
        qty_delta_abs is not None and qty_delta_abs <= thresholds.quantity_tolerance_units + 1e-9
    )

    pcs_delta = candidate_pcs - expected_pcs if candidate_pcs is not None and expected_pcs is not None else None
    pcs_delta_pct = pct_delta(pcs_delta, expected_pcs)

    declared_model = record.get("declared_model")
    model_exact = same_text(declared_model, candidate.get("platform_sku")) or same_text(
        declared_model, candidate.get("spec_model")
    )

    input_pack = extract_pack_count(record.get("raw_name")) or extract_pack_count(record.get("core_name"))
    candidate_pack = extract_pack_count(candidate.get("product_content"))
    pack_matches = input_pack is not None and candidate_pack is not None and input_pack == candidate_pack
    pack_mismatches = input_pack is not None and candidate_pack is not None and input_pack != candidate_pack

    similarity = name_similarity(record.get("core_name") or record.get("raw_name"), candidate.get("product_content"))
    box_score, box_reason = score_box_match(qty_delta_pct_abs, quantity_exact, thresholds)
    model_score = 35.0 if model_exact else 0.0
    pack_score = 10.0 if pack_matches else (-12.0 if pack_mismatches else 0.0)
    name_score = similarity * 25.0
    legacy_score = min(as_float(candidate.get("score")) or 0.0, 100.0) / 20.0
    conflict_penalty = -30.0 if model_exact and not quantity_exact and expected_qty is not None else 0.0
    adjusted_score = round(box_score + model_score + pack_score + name_score + legacy_score + conflict_penalty, 2)

    identity_ok = model_exact or similarity >= thresholds.strong_name_similarity
    auto_eligible = quantity_exact and identity_ok and not pack_mismatches

    issues: list[str] = [box_reason]
    if model_exact:
        issues.append("SKU/型号精确命中")
    if not identity_ok:
        issues.append("SKU/型号未命中且名称相似度不足")
    if pack_matches:
        issues.append("包装数一致")
    elif pack_mismatches:
        issues.append("包装数不一致")
    if model_exact and not quantity_exact and expected_qty is not None:
        issues.append("型号命中但数量/箱规冲突，不能自动高置信")

    if auto_eligible:
        candidate_status = AUTO_CANDIDATE
    elif model_exact and not quantity_exact:
        candidate_status = NEEDS_MANUAL
    elif quantity_exact:
        candidate_status = NEEDS_MANUAL
    else:
        candidate_status = LOW_CONFIDENCE

    return {
        "seq": record.get("seq"),
        "rank": rank,
        "candidate_status": candidate_status,
        "auto_eligible": auto_eligible,
        "source_row": candidate.get("source_row"),
        "product_content": candidate.get("product_content"),
        "platform_sku": candidate.get("platform_sku"),
        "spec_model": candidate.get("spec_model"),
        "legacy_score": as_float(candidate.get("score")),
        "adjusted_score": adjusted_score,
        "name_similarity": similarity,
        "model_exact": model_exact,
        "pack_matches": pack_matches,
        "pack_mismatches": pack_mismatches,
        "input_pack": input_pack,
        "candidate_pack": candidate_pack,
        "expected_pcs_per_ctn": expected_pcs,
        "candidate_pcs_per_ctn": candidate_pcs,
        "pcs_delta": pcs_delta,
        "pcs_delta_pct": pcs_delta_pct,
        "expected_qty": expected_qty,
        "candidate_qty": candidate_qty,
        "qty_delta": qty_delta,
        "qty_delta_pct": qty_delta_pct,
        "quantity_exact": quantity_exact,
        "hs_code": candidate.get("hs_code"),
        "declaration_name": candidate.get("declaration_name"),
        "issues": issues,
    }


def row_decision(record: dict[str, Any], analyzed: list[dict[str, Any]], thresholds: Thresholds) -> dict[str, Any]:
    sorted_candidates = sorted(analyzed, key=lambda row: row["adjusted_score"], reverse=True)
    legacy_top = analyzed[0] if analyzed else {}
    best_auto = next((row for row in sorted_candidates if row["auto_eligible"]), None)
    exact_model_conflicts = [row for row in sorted_candidates if row["model_exact"] and not row["quantity_exact"]]
    quantity_matches = [row for row in sorted_candidates if row["quantity_exact"]]

    if best_auto and best_auto["adjusted_score"] >= thresholds.high_confidence_score:
        status = HIGH_CONFIDENCE
        auto_adopt = "是"
        chosen = best_auto
        misrank_reason = "旧排序与数量/箱规一致，未发现阻断项"
        action = "可自动采用，建议保留抽检"
    elif exact_model_conflicts:
        status = NEEDS_MANUAL
        auto_adopt = "否"
        chosen = sorted_candidates[0] if sorted_candidates else exact_model_conflicts[0]
        conflict = exact_model_conflicts[0]
        if quantity_matches:
            misrank_reason = (
                "旧规则过度奖励SKU/型号命中，未把数量/箱规作为硬门槛；"
                "同时存在数量/箱规一致但型号或包装数冲突的候选"
            )
        else:
            misrank_reason = "SKU/型号命中候选的数量/箱规不一致，不能自动确认"
        action = (
            f"人工核对来源数量与商品库箱规；型号命中候选为{fmt_number(conflict['candidate_pcs_per_ctn'])}件/箱，"
            f"期望为{fmt_number(conflict['expected_pcs_per_ctn'])}件/箱"
        )
    elif quantity_matches:
        status = NEEDS_MANUAL
        auto_adopt = "否"
        chosen = quantity_matches[0]
        misrank_reason = "数量/箱规一致候选存在，但SKU/型号、包装数或名称证据不足"
        action = "人工确认候选商品是否为同一报关商品；必要时补正SKU映射或商品资料"
    else:
        status = LOW_CONFIDENCE
        auto_adopt = "否"
        chosen = sorted_candidates[0] if sorted_candidates else {}
        misrank_reason = "没有候选满足期望数量/箱规，旧规则主要按名称相似度排序"
        action = "运营补充准确SKU、报关品名或箱规后再匹配"

    return {
        "status": status,
        "auto_adopt": auto_adopt,
        "chosen": chosen,
        "legacy_top": legacy_top,
        "misrank_reason": misrank_reason,
        "action": action,
    }


def build_summary_row(record: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    chosen = decision["chosen"]
    legacy_top = decision["legacy_top"]
    cartons = as_float(record.get("cartons"))
    expected_qty = as_float(record.get("expected_qty"))
    expected_pcs = expected_qty / cartons if cartons not in (None, 0) and expected_qty is not None else None

    return {
        "seq": record.get("seq"),
        "状态": decision["status"],
        "是否可自动采用": decision["auto_adopt"],
        "原商品名": record.get("raw_name", ""),
        "申报型号": record.get("declared_model", ""),
        "箱数": fmt_number(cartons),
        "期望数量": fmt_number(expected_qty),
        "期望箱规": fmt_number(expected_pcs),
        "建议候选源行": chosen.get("source_row", ""),
        "建议候选商品": chosen.get("product_content", ""),
        "建议候选SKU": chosen.get("platform_sku", ""),
        "建议候选规格型号": chosen.get("spec_model", ""),
        "候选箱规": fmt_number(chosen.get("candidate_pcs_per_ctn")),
        "候选数量": fmt_number(chosen.get("candidate_qty")),
        "数量差异": fmt_number(chosen.get("qty_delta")),
        "数量差异比例": fmt_pct(chosen.get("qty_delta_pct")),
        "新评分": fmt_number(chosen.get("adjusted_score")),
        "旧首选源行": legacy_top.get("source_row", ""),
        "旧首选SKU": legacy_top.get("platform_sku", ""),
        "旧首选箱规": fmt_number(legacy_top.get("candidate_pcs_per_ctn")),
        "旧首选数量": fmt_number(legacy_top.get("candidate_qty")),
        "旧首选数量差异": fmt_number(legacy_top.get("qty_delta")),
        "误排原因": decision["misrank_reason"],
        "复核/运营动作": decision["action"],
    }


def build_detail_row(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "seq": candidate["seq"],
        "候选排序": candidate["rank"],
        "候选判定": candidate["candidate_status"],
        "可自动采用": "是" if candidate["auto_eligible"] else "否",
        "源行": candidate.get("source_row", ""),
        "商品内容": candidate.get("product_content", ""),
        "平台SKU": candidate.get("platform_sku", ""),
        "规格型号": candidate.get("spec_model", ""),
        "旧评分": fmt_number(candidate.get("legacy_score")),
        "新评分": fmt_number(candidate.get("adjusted_score")),
        "名称相似度": fmt_pct(candidate.get("name_similarity")),
        "型号/SKU精确命中": "是" if candidate["model_exact"] else "否",
        "包装数一致": "是" if candidate["pack_matches"] else ("否" if candidate["pack_mismatches"] else ""),
        "原包装数": fmt_number(candidate.get("input_pack")),
        "候选包装数": fmt_number(candidate.get("candidate_pack")),
        "期望箱规": fmt_number(candidate.get("expected_pcs_per_ctn")),
        "候选箱规": fmt_number(candidate.get("candidate_pcs_per_ctn")),
        "箱规差异": fmt_number(candidate.get("pcs_delta")),
        "箱规差异比例": fmt_pct(candidate.get("pcs_delta_pct")),
        "期望数量": fmt_number(candidate.get("expected_qty")),
        "候选数量": fmt_number(candidate.get("candidate_qty")),
        "数量差异": fmt_number(candidate.get("qty_delta")),
        "数量差异比例": fmt_pct(candidate.get("qty_delta_pct")),
        "HS编码": candidate.get("hs_code", ""),
        "申报品名": candidate.get("declaration_name", ""),
        "问题/依据": "；".join(candidate["issues"]),
    }


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    thresholds = Thresholds(
        quantity_tolerance_units=args.quantity_tolerance_units,
        strong_name_similarity=args.strong_name_similarity,
    )

    with args.input.open("r", encoding="utf-8-sig") as handle:
        records = json.load(handle)
    if not isinstance(records, list):
        raise ValueError("Input JSON must be a list of match result records.")

    summary_rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []
    reviewed_records: list[dict[str, Any]] = []

    for record in records:
        candidates = record.get("candidates") or []
        analyzed = [
            analyze_candidate(record, candidate, rank=index + 1, thresholds=thresholds)
            for index, candidate in enumerate(candidates)
        ]
        decision = row_decision(record, analyzed, thresholds)
        summary_rows.append(build_summary_row(record, decision))
        detail_rows.extend(build_detail_row(candidate) for candidate in analyzed)
        reviewed_records.append(
            {
                "seq": record.get("seq"),
                "status": decision["status"],
                "auto_adopt": decision["auto_adopt"] == "是",
                "chosen_source_row": decision["chosen"].get("source_row") if decision["chosen"] else None,
                "reason": decision["misrank_reason"],
                "action": decision["action"],
                "candidates": analyzed,
            }
        )

    write_csv(args.output_summary, SUMMARY_FIELDS, summary_rows)
    write_csv(args.output_detail, DETAIL_FIELDS, detail_rows)

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        with args.output_json.open("w", encoding="utf-8") as handle:
            json.dump(reviewed_records, handle, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
