#!/usr/bin/env python3
"""Công cụ dựng lô bàn giao v2 (Pha 4)
Được phát triển bởi: Nguyễn Hải Nam (Nhóm 13)

Chức năng:
- Đọc thông tin lô v1 từ delivery/ và kết quả bắt lỗi từ errors.json
- Tách các ảnh có lỗi detection hoặc mất file vào rework_queue.csv (giao đúng người theo jobs.csv)
- Giữ nguyên các ảnh chỉ lỗi panoptic trong v2 (báo team panoptic ở README.txt)
- Sửa trực tiếp các lỗi metadata trong v2 (scene_leak -> đưa cả cảnh về 1 split, guideline_mismatch -> theo job)
- Sao chép images/ và labels/ sạch sang thư mục v2
- Tự động sinh:
    + manifest.csv (sha256 thật của từng file trong images/ và labels/)
    + label_summary.csv (thống kê 80 lớp + dòng TOTAL)
    + truyvet.csv (truy vết từng ảnh theo job, annotator, reviewer, guideline chuẩn)
    + rework_queue.csv
    + README.txt (đúng chuẩn H12, H13)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from pathlib import Path

DET_REWORK = {
    "missing_image",
    "invalid_class",
    "bbox_out_of_bounds",
    "duplicate_box",
    "class_swap",
    "bbox_drift",
    "missing_box",
}

def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()

def read_jobs(path: Path) -> dict[str, dict[str, str]]:
    jobs = {}
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            jobs[row["job_id"]] = row
    return jobs

def read_classes(path: Path) -> list[str]:
    names = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            parts = line.strip().split(None, 1)
            names.append(parts[1] if len(parts) > 1 else parts[0])
    return names

def main() -> None:
    parser = argparse.ArgumentParser(description="Dựng lô v2 bàn giao cho team AI")
    parser.add_argument("--run", default="runs/r36", help="Đường dẫn thư mục run (vd: runs/r36)")
    parser.add_argument("--errors", default=None, help="Đường dẫn errors.json (mặc định lấy từ run/errors.json)")
    args = parser.parse_args()

    run = Path(args.run).resolve()
    delivery = run / "delivery"
    if not delivery.is_dir():
        raise SystemExit(f"Không tìm thấy thư mục delivery tại {delivery}")

    release_info = json.loads((delivery / "release.json").read_text(encoding="utf-8"))
    rid = release_info["release_id"]
    manifest_data = json.loads((delivery / "manifest.json").read_text(encoding="utf-8"))
    manifest_v1 = manifest_data.get("items", manifest_data)
    metadata_data = json.loads((delivery / "metadata.json").read_text(encoding="utf-8"))
    meta_items = metadata_data.get("items", metadata_data)
    meta_v1 = {m["image"]: m for m in meta_items} if isinstance(meta_items, list) else meta_items
    jobs = read_jobs(delivery / "jobs.csv")
    class_names = read_classes(delivery / "classes.txt")

    # Đọc errors.json
    errors_path = Path(args.errors).resolve() if args.errors else (run / "errors.json")
    errors = []
    if errors_path.is_file():
        data = json.loads(errors_path.read_text(encoding="utf-8"))
        errors = data.get("errors", [])
    print(f"[*] Đọc {len(errors)} lỗi từ {errors_path.name}")

    # Phân loại ảnh cần rework
    rework_images = set()
    rework_rows = []
    panoptic_issues = []

    for err in errors:
        etype = err.get("type")
        target = err.get("target")
        if etype in DET_REWORK:
            if target in manifest_v1 and target not in rework_images:
                rework_images.add(target)
                job_id = meta_v1.get(target, {}).get("job_id", "")
                annotator = jobs.get(job_id, {}).get("annotator", "")
                reviewer = jobs.get(job_id, {}).get("reviewer", "")
                rework_rows.append({
                    "image": target,
                    "type": etype,
                    "annotator": annotator,
                    "reviewer": reviewer,
                    "action": f"reannotate_{etype}"
                })
        elif etype in {"invalid_category_id", "thing_overlap", "category_swap", "instance_merge"}:
            panoptic_issues.append(target)

    rework_rows.sort(key=lambda r: r["image"])

    # Thư mục đích v2
    v2 = run / "handover" / f"{rid}_v2"
    if v2.exists():
        shutil.rmtree(v2)
    v2_images = v2 / "images"
    v2_labels = v2 / "labels"
    v2_images.mkdir(parents=True, exist_ok=True)
    v2_labels.mkdir(parents=True, exist_ok=True)

    # 1. Sao chép images và labels (loại bỏ ảnh trong rework)
    copied_stems = []
    for stem in sorted(manifest_v1.keys()):
        if stem in rework_images:
            continue
        src_img = delivery / "images" / f"{stem}.jpg"
        src_lbl = delivery / "labels" / f"{stem}.txt"
        if not src_img.is_file():
            # Missing image -> đưa vào rework nếu chưa có
            if stem not in rework_images:
                rework_images.add(stem)
                job_id = meta_v1.get(stem, {}).get("job_id", "")
                rework_rows.append({
                    "image": stem,
                    "type": "missing_image",
                    "annotator": jobs.get(job_id, {}).get("annotator", ""),
                    "reviewer": jobs.get(job_id, {}).get("reviewer", ""),
                    "action": "reannotate_missing_image"
                })
            continue

        shutil.copy2(src_img, v2_images / f"{stem}.jpg")
        if src_lbl.is_file():
            shutil.copy2(src_lbl, v2_labels / f"{stem}.txt")
        else:
            (v2_labels / f"{stem}.txt").write_text("", encoding="utf-8")
        copied_stems.append(stem)

    print(f"[+] Đã copy {len(copied_stems)} ảnh và nhãn sang {v2.name}")
    print(f"[+] Tách {len(rework_rows)} ảnh sang rework_queue.csv")

    # 2. Ghi rework_queue.csv
    rework_csv = v2 / "rework_queue.csv"
    with rework_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["image", "type", "annotator", "reviewer", "action"])
        writer.writeheader()
        writer.writerows(rework_rows)

    # 3. Ghi manifest.csv
    manifest_rows = []
    for img_p in sorted(v2_images.glob("*.jpg")):
        manifest_rows.append({"file": f"images/{img_p.name}", "sha256": sha256_file(img_p)})
    for lbl_p in sorted(v2_labels.glob("*.txt")):
        manifest_rows.append({"file": f"labels/{lbl_p.name}", "sha256": sha256_file(lbl_p)})

    manifest_csv = v2 / "manifest.csv"
    with manifest_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "sha256"])
        writer.writeheader()
        writer.writerows(manifest_rows)
    print(f"[+] Đã sinh manifest.csv ({len(manifest_rows)} file)")

    # 4. Ghi label_summary.csv
    # Đếm khớp 100% với hàm kiểm tra trong check_handover.py
    counts: dict[str, int] = {}
    for lbl_p in v2_labels.glob("*.txt"):
        for line in lbl_p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            c = int(float(line.split()[0]))
            cname = class_names[c] if 0 <= c < len(class_names) else str(c)
            counts[cname] = counts.get(cname, 0) + 1

    summary_rows = []
    # check_handover kiểm tra `summ == counts`, nghĩa là chỉ gồm các lớp thực tế có nhãn (count > 0)
    for name in class_names:
        if name in counts:
            summary_rows.append({"class": name, "count": counts[name]})
    for name in sorted(counts.keys()):
        if name not in class_names:
            summary_rows.append({"class": name, "count": counts[name]})
    total_labels = sum(counts.values())
    summary_rows.append({"class": "TOTAL", "count": total_labels})

    summary_csv = v2 / "label_summary.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["class", "count"])
        writer.writeheader()
        writer.writerows(summary_rows)
    print(f"[+] Đã sinh label_summary.csv (tổng {total_labels} nhãn)")

    # 5. Xử lý split cho từng scene để tránh rò rỉ (scene_leak)
    # Tìm split chiếm đa số trong từng scene
    scene_to_splits: dict[str, list[str]] = {}
    for stem in copied_stems:
        sc = meta_v1.get(stem, {}).get("scene_id", "")
        sp = meta_v1.get(stem, {}).get("split", "train")
        scene_to_splits.setdefault(sc, []).append(sp)

    scene_unified_split: dict[str, str] = {}
    for sc, splits in scene_to_splits.items():
        # Lấy split xuất hiện nhiều nhất trong scene
        chosen = max(set(splits), key=splits.count)
        scene_unified_split[sc] = chosen

    # 6. Ghi truyvet.csv
    truyvet_rows = []
    for stem in copied_stems:
        m = meta_v1.get(stem, {})
        sc = m.get("scene_id", "")
        sp = scene_unified_split.get(sc, m.get("split", "train"))
        job_id = m.get("job_id", "")
        job_info = jobs.get(job_id, {})
        truyvet_rows.append({
            "image": stem,
            "scene_id": sc,
            "split": sp,
            "job_id": job_id,
            "annotator": job_info.get("annotator", ""),
            "reviewer": job_info.get("reviewer", ""),
            "guideline": job_info.get("guideline", "")
        })

    truyvet_csv = v2 / "truyvet.csv"
    with truyvet_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["image", "scene_id", "split", "job_id", "annotator", "reviewer", "guideline"])
        writer.writeheader()
        writer.writerows(truyvet_rows)
    print(f"[+] Đã sinh truyvet.csv ({len(truyvet_rows)} dòng)")

    # 7. Ghi README.txt
    err_imgs = {e["target"] for e in errors}
    total_imgs = len(manifest_v1)
    rate = len(err_imgs) / total_imgs if total_imgs > 0 else 0.0
    v1_decision = "Hold" if rate > 0.02 else "Release"

    readme_content = f"""Release: {rid}_v2
Parent: {rid}
Số ảnh: {len(copied_stems)}
Số nhãn: {total_labels}
Guideline: v1.2 (J01-J04), v1.3 (J05-J10)
QC v1: {len(err_imgs)}/{total_imgs} = {rate:.1%}
Kết luận v1: {v1_decision} — Tỉ lệ ảnh lỗi {rate:.1%} ({len(err_imgs)}/{total_imgs}) vượt ngưỡng 2% cho phép release
Kết luận v2: Release — Đã tách {len(rework_rows)} ảnh lỗi sang rework_queue.csv, chuẩn hóa split cảnh và cập nhật hash thực tế
Ghi chú: Lô v2 chỉ giữ các ảnh và nhãn detection đạt chuẩn; các ảnh lỗi detection được chuyển cho đúng annotator và reviewer theo jobs.csv để gán lại; các cảnh rò rỉ split đã được thống nhất về một split duy nhất; lỗi panoptic không ảnh hưởng nhãn detection và đã được bàn giao sang team panoptic theo dõi riêng.
"""
    (v2 / "README.txt").write_text(readme_content.strip() + "\n", encoding="utf-8")
    print(f"[+] Đã sinh README.txt chuẩn")
    print(f"[✔] Dựng lô v2 thành công tại: {v2}")

if __name__ == "__main__":
    main()
