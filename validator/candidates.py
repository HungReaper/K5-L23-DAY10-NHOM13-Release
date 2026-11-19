"""Pha 2 — sinh ứng viên lỗi gán nhãn bằng cách đối chiếu detection <-> panoptic.

Chỉ đọc thư mục delivery truyền vào; chỉ thư viện chuẩn (+ scripts/pngutil.py).

Ý tưởng: dùng PIXEL của mask, không chỉ IoU bbox.
  - mỗi box detection (pixel) được đếm xem trong nó có bao nhiêu pixel của từng segment thing;
  - IoU pixel giữa box và segment = giao / (area box + area segment - giao);
  - ghép một-một theo IoU giảm dần, rồi xét từng cặp / phần dư.

Ứng viên (chưa phải lỗi, phải mở ảnh xem):
  class_mismatch : box và segment trùng vị trí nhưng khác lớp  (class_swap HOẶC category_swap)
  bbox_drift     : cùng lớp nhưng box lệch khỏi segment
  missing_box    : segment thing lớn không có box nào
  instance_merge : một segment phủ hai box cùng lớp
"""
from __future__ import annotations

import csv  # noqa: F401
import json
import sys
from array import array
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import pngutil  # noqa: E402

# --------------------------------------------------------------------------
# Ngưỡng (đo lại trên runs/clean; xem REPORT.md)
# --------------------------------------------------------------------------
PAIR_MIN_IOU = 0.15        # IoU pixel tối thiểu để coi box và segment là "cùng một vật"
SWAP_MIN_IOU = 0.55        # cặp khác lớp phải trùng vị trí tới mức này mới là class_mismatch
DRIFT_MIN_INSIDE = 0.95    # cặp cùng lớp: tỉ lệ pixel segment nằm trong box dưới mức này -> bbox_drift
                           # (KHÔNG dùng IoU: vật bị che làm segment nhỏ hơn box nên IoU thấp tự nhiên)
MISSING_MIN_FRAC = 0.01    # segment không box phải chiếm >= 1% diện tích ảnh mới là missing_box
MERGE_MIN_SHARE = 0.20     # instance_merge: mỗi box chứa >= 20% pixel của segment
MERGE_MIN_COVER = 0.50     # ... và >= 50% box nằm trong segment


def load_names(root: Path):
    classes = {}
    for line in (root / "classes.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            idx, name = line.split(maxsplit=1)
            classes[int(idx)] = name.strip()
    return classes


def mask_ids(path: Path):
    """Trả (W, H, array('I')) với id = R + G*256 + B*65536 cho từng pixel."""
    w, h, px = pngutil.read_rgb(path)
    buf = bytearray(4 * w * h)
    buf[0::4] = px[0::3]
    buf[1::4] = px[1::3]
    buf[2::4] = px[2::3]
    ids = array("I")
    ids.frombytes(bytes(buf))
    if sys.byteorder != "little":
        ids.byteswap()
    return w, h, ids


def read_boxes(label_path: Path, W: int, H: int, classes: dict):
    """Box YOLO -> pixel (x1, y1, x2, y2, class_name). Bỏ qua dòng hỏng / lớp không hợp lệ."""
    boxes = []
    if not label_path.exists():
        return boxes
    for line in label_path.read_text(encoding="utf-8").splitlines():
        p = line.split()
        if len(p) != 5:
            continue
        try:
            cid = int(float(p[0]))
            xc, yc, w, h = (float(v) for v in p[1:])
        except ValueError:
            continue
        if cid not in classes:
            continue
        x1, y1 = max(0, round((xc - w / 2) * W)), max(0, round((yc - h / 2) * H))
        x2, y2 = min(W, round((xc + w / 2) * W)), min(H, round((yc + h / 2) * H))
        if x2 > x1 and y2 > y1:
            boxes.append((x1, y1, x2, y2, classes[cid]))
    return boxes


def box_counts(ids, W, box):
    """Đếm số pixel mỗi id nằm trong box."""
    x1, y1, x2, y2, _ = box
    c = Counter()
    for y in range(y1, y2):
        c.update(ids[y * W + x1 : y * W + x2])
    return c


def analyse_image(stem, ann, root, items, classes, cat_name, cat_isthing):
    mask_rel = items.get(stem, {}).get("mask") or f"masks/{ann['file_name']}"
    label_rel = items.get(stem, {}).get("label") or f"labels/{stem}.txt"
    mask_path = root / mask_rel
    if not mask_path.exists():
        return []
    W, H, ids = mask_ids(mask_path)
    total = Counter(ids)  # số pixel thật của mỗi segment
    segs = {}
    for s in ann["segments_info"]:
        if s["category_id"] in cat_name and cat_isthing.get(s["category_id"]) and not s.get("iscrowd"):
            segs[s["id"]] = (cat_name[s["category_id"]], total.get(s["id"], 0))
    boxes = read_boxes(root / label_rel, W, H, classes)
    if not segs and not boxes:
        return []

    # đếm pixel segment trong từng box
    cnt = [box_counts(ids, W, b) for b in boxes]
    box_area = [(b[2] - b[0]) * (b[3] - b[1]) for b in boxes]

    pairs = []  # (iou, box_idx, seg_id)
    for bi, c in enumerate(cnt):
        for sid, inter in c.items():
            if sid in segs and segs[sid][1] > 0:
                union = box_area[bi] + segs[sid][1] - inter
                pairs.append((inter / union, bi, sid))
    pairs.sort(reverse=True)

    out = []
    seen_msg = set()

    def emit(kind, detail):
        key = (kind, json.dumps(detail, sort_keys=True))
        if key not in seen_msg:
            seen_msg.add(key)
            out.append({"image": stem, "type": kind, **detail})

    # --- instance_merge: một segment có >=2 box cùng lớp, mỗi box chứa phần đáng kể của nó
    merged_segments = set()
    by_seg = defaultdict(list)
    for bi, c in enumerate(cnt):
        for sid, inter in c.items():
            if sid in segs and segs[sid][1] > 0 and boxes[bi][4] == segs[sid][0]:
                if inter / segs[sid][1] >= MERGE_MIN_SHARE and inter / box_area[bi] >= MERGE_MIN_COVER:
                    by_seg[sid].append(bi)
    for sid, bis in by_seg.items():
        if len(bis) >= 2:
            merged_segments.add(sid)
            emit("instance_merge", {"class": segs[sid][0], "segment_id": sid,
                                    "boxes": [list(boxes[bi][:4]) for bi in bis]})

    # --- ghép một-một theo IoU giảm dần
    used_b, used_s, matches = set(), set(), []
    for iou, bi, sid in pairs:
        if iou < PAIR_MIN_IOU:
            break
        if bi in used_b or sid in used_s:
            continue
        used_b.add(bi)
        used_s.add(sid)
        matches.append((iou, bi, sid))

    for iou, bi, sid in matches:
        det, pan = boxes[bi][4], segs[sid][0]
        inside = cnt[bi].get(sid, 0) / segs[sid][1]
        if det != pan:
            if iou >= SWAP_MIN_IOU:
                emit("class_mismatch", {"det_class": det, "pan_class": pan, "box": list(boxes[bi][:4]),
                                        "segment_id": sid, "iou": round(iou, 3)})
        elif sid not in merged_segments and inside < DRIFT_MIN_INSIDE:
            emit("bbox_drift", {"class": det, "box": list(boxes[bi][:4]), "segment_id": sid,
                                "iou": round(iou, 3), "inside": round(inside, 3)})

    # --- phần dư
    free_boxes = [bi for bi in range(len(boxes)) if bi not in used_b]
    free_segs = [sid for sid in segs if sid not in used_s and sid not in merged_segments]
    for sid in free_segs:
        name, area = segs[sid]
        if area / (W * H) < MISSING_MIN_FRAC:
            continue
        # box cùng lớp còn dư mà không chồng segment -> nhiều khả năng drift lớn, không phải missing
        if any(boxes[bi][4] == name for bi in free_boxes):
            emit("bbox_drift", {"class": name, "segment_id": sid, "iou": 0.0, "note": "box cùng lớp không chồng segment"})
        else:
            emit("missing_box", {"class": name, "segment_id": sid, "area_frac": round(area / (W * H), 4)})
    return out


def build_candidates(root: Path) -> list[dict]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))["items"]
    panoptic = json.loads((root / "panoptic.json").read_text(encoding="utf-8"))
    classes = load_names(root)
    cat_name = {c["id"]: c["name"].strip() for c in panoptic["categories"]}
    cat_isthing = {c["id"]: bool(c.get("isthing")) for c in panoptic["categories"]}
    res = []
    for ann in panoptic["annotations"]:
        stem = Path(ann["file_name"]).stem
        try:
            res += analyse_image(stem, ann, root, manifest, classes, cat_name, cat_isthing)
        except Exception as exc:  # file hỏng không được làm sập cả lô
            print(f"bỏ qua {stem}: {exc}", file=sys.stderr)
    return sorted(res, key=lambda c: (c["image"], c["type"]))


if __name__ == "__main__":  # thử nhanh: py validator/candidates.py <delivery> [out.json]
    d = Path(sys.argv[1])
    cands = build_candidates(d)
    print(len(cands), "ứng viên trên", len({c["image"] for c in cands}), "ảnh;", dict(Counter(c["type"] for c in cands)))
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(json.dumps({"candidates": cands}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
