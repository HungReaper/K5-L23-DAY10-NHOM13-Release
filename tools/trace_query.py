#!/usr/bin/env python3
"""Pha 5: truy vết ticket của team AI -> trace.json.

    python tools/trace_query.py <delivery> --out <trace.json>

Chỉ đọc thư mục <delivery>, chỉ dùng thư viện chuẩn. Không viết cứng tên lớp,
cảnh hay job: mọi thứ lấy từ file của lô.

  - Lớp bị đổi quy tắc : dòng "Lớp `X`" trong guideline/changelog.md (mục phiên bản mới nhất).
  - Phiên bản cũ       : mọi phiên bản thấp hơn phiên bản có đổi quy tắc.
  - Cảnh team AI báo   : mọi mã scene_xxx trong incoming/ticket.md.
  - Guideline của ảnh  : theo JOB (jobs.csv), KHÔNG theo guideline ghi ở từng ảnh
                         (giá trị ở ảnh có thể là lỗi guideline_mismatch).
  - "Có lớp"           : có ít nhất một box detection của lớp đó trong labels/.

tier_a : ảnh trong cảnh được báo, job guideline cũ, có box lớp đó
tier_b : ảnh khác cùng điều kiện (job guideline cũ, có box lớp đó), chưa ai báo
notify : người gán + người kiểm của mọi job chứa ảnh tier_a / tier_b
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


def version_key(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v))


def parse_changelog(text: str) -> tuple[str, str]:
    """Trả về (tên lớp bị đổi quy tắc, phiên bản có đổi quy tắc)."""
    version = None
    for line in text.splitlines():
        m = re.match(r"##\s*(v[\d.]+)", line.strip())
        if m:
            version = m.group(1)
            continue
        m = re.search(r"Lớp\s*`([^`]+)`", line)
        if m and version:
            return m.group(1).strip(), version
    raise SystemExit("changelog.md: không thấy dòng 'Lớp `<tên>`' dưới một mục phiên bản")


def trace(root: Path) -> dict:
    rule_class, rule_version = parse_changelog((root / "guideline" / "changelog.md").read_text(encoding="utf-8"))
    ticket = (root / "incoming" / "ticket.md").read_text(encoding="utf-8")
    reported = sorted(set(re.findall(r"scene_\w+", ticket)))

    with open(root / "jobs.csv", encoding="utf-8", newline="") as f:
        jobs = {r["job_id"].strip(): r for r in csv.DictReader(f)}
    old_jobs = {j for j, r in jobs.items() if version_key(r["guideline"].strip()) < version_key(rule_version)}

    classes = {}
    for line in (root / "classes.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            idx, name = line.split(maxsplit=1)
            classes[name.strip()] = idx
    if rule_class not in classes:
        raise SystemExit(f"lớp '{rule_class}' không có trong classes.txt")
    class_id = classes[rule_class]

    meta = json.loads((root / "metadata.json").read_text(encoding="utf-8"))["items"]
    tier_a, tier_b = [], []
    for m in meta:
        if m["job_id"] not in old_jobs:
            continue
        label = root / "labels" / f"{m['image']}.txt"
        if not label.exists():
            continue
        has = any(line.split()[0] == class_id for line in label.read_text(encoding="utf-8").splitlines() if line.strip())
        if not has:
            continue
        (tier_a if m["scene_id"] in reported else tier_b).append(m)

    used_jobs = {m["job_id"] for m in tier_a + tier_b}
    notify = sorted({jobs[j]["annotator"].strip() for j in used_jobs} | {jobs[j]["reviewer"].strip() for j in used_jobs})
    return {
        "tier_a": sorted(m["image"] for m in tier_a),
        "tier_b": sorted(m["image"] for m in tier_b),
        "notify": notify,
        "_info": {"rule_class": rule_class, "rule_version": rule_version, "old_jobs": sorted(old_jobs),
                  "reported_scenes": reported, "jobs_involved": sorted(used_jobs)},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Truy vết ticket -> trace.json")
    ap.add_argument("delivery", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    result = trace(args.delivery)
    info = result.pop("_info")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"lớp đổi quy tắc: {info['rule_class']} (từ {info['rule_version']}); job cũ: {info['old_jobs']}")
    print(f"cảnh được báo: {info['reported_scenes']}; job liên quan: {info['jobs_involved']}")
    print(f"tier_a={len(result['tier_a'])} tier_b={len(result['tier_b'])} notify={result['notify']} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
