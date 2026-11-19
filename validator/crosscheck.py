"""Pha 2 — đối chiếu detection (YOLO) <-> panoptic (mask) để sinh ỨNG VIÊN lỗi gán nhãn.

Chỉ thư viện chuẩn + scripts/pngutil.py. Không đọc gì ngoài thư mục delivery.

Ý tưởng:
  1. Đổi box YOLO (chuẩn hoá 0-1) sang pixel.
  2. Đọc mask, gom pixel theo segment id = R + G*256 + B*256^2. Mỗi segment lưu
     "hàng -> danh sách x đã sắp xếp" để đếm nhanh số pixel nằm trong một box.
  3. Ghép lớp hai bên qua TÊN (classes.txt <-> categories).
  4. Ghép box <-> segment thing (bỏ iscrowd) theo 3 lượt:
       a. cùng tên, IoU(bbox của pixel segment, box) cao       -> cặp chuẩn
       b. KHÁC tên, IoU cao                                     -> ứng viên swap
       c. cùng tên, IoU thấp hơn                               -> cặp lệch (drift?)
  5. Tín hiệu chính là PIXEL: cov = (pixel của segment nằm trong box) / (pixel của segment).
     Cặp đúng thì cov ~ 1. Box lệch thì cov tụt. Segment có pixel nằm trong hai box
     cùng lớp là dấu hiệu instance_merge. Segment thing lớn không có box: missing_box.
"""
from __future__ import annotations

import bisect
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import pngutil  # noqa: E402

# --------------------------------------------------------------------------
# Ngưỡng — chọn bằng cách đo trên lô sạch (runs/clean), xem REPORT.md
# --------------------------------------------------------------------------
MATCH_IOU = 0.5          # lượt a/b: IoU bbox-pixel-segment vs box để coi là cùng một vật
LOOSE_IOU = 0.1          # lượt c: cặp cùng lớp còn lại, lỏng hơn để bắt box lệch nhiều
DRIFT_COV = 0.95         # cặp cùng lớp có cov < ngưỡng -> bbox_drift (lô sạch: mọi cặp cov = 1.00)
# instance_merge: segment gộp 2 vật thì KHÔNG box nào chứa hết nó, và box thứ hai có
# phần pixel RIÊNG (ngoài vùng giao 2 box). Đo trên lô sạch: cặp vật chồng nhau tự
# nhiên luôn có 1 box chứa 100% segment, box kia chỉ chứa phần trong vùng giao (riêng = 0).
MERGE_MAX_SINGLE = 0.90  # box tốt nhất chứa < 90% pixel segment
MERGE_EXCL = 0.10        # box thứ hai chứa riêng >= 10% pixel segment
MERGE_UNION = 0.90       # hai box cộng lại phủ >= 90% pixel segment
MISSING_MIN_FRAC = 0.01  # segment không có box, diện tích >= 1% ảnh -> missing_box
MISSING_MIN_PX = 1000    # ... và >= 1000 pixel


# --------------------------------------------------------------------------
def yolo_to_px(xc: float, yc: float, w: float, h: float, W: int, H: int) -> tuple[float, float, float, float]:
    """YOLO (tâm, rộng, cao; chuẩn hoá theo kích thước ảnh) -> (x1, y1, x2, y2) pixel."""
    bw, bh = w * W, h * H
    x1, y1 = xc * W - bw / 2, yc * H - bh / 2
    return x1, y1, x1 + bw, y1 + bh


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


class Segment:
    __slots__ = ("sid", "name", "rows", "n", "bbox")

    def __init__(self, sid: int, name: str):
        self.sid, self.name = sid, name
        self.rows: dict[int, list[int]] = defaultdict(list)
        self.n = 0
        self.bbox = None

    def finish(self):
        xs0 = min(r[0] for r in self.rows.values())
        xs1 = max(r[-1] for r in self.rows.values())
        self.bbox = (xs0, min(self.rows), xs1 + 1, max(self.rows) + 1)

    def inside(self, box) -> int:
        """Số pixel của segment nằm trong box (x1, y1, x2, y2); pixel (x, y) là ô [x, x+1)."""
        x1, y1, x2, y2 = box
        lo_x, hi_x = x1 - 0.5, x2 - 0.5          # tâm pixel x+0.5 nằm trong [x1, x2)
        total = 0
        for y in range(max(int(y1 - 0.5) , self.bbox[1]), min(int(y2 + 0.5) + 1, self.bbox[3])):
            if not (y1 <= y + 0.5 < y2):
                continue
            xs = self.rows.get(y)
            if xs:
                total += bisect.bisect_left(xs, hi_x) - bisect.bisect_left(xs, lo_x)
        return total


def load_segments(mask_path: Path, ann: dict, cat_by_id: dict) -> tuple[list[Segment], int, int]:
    W, H, px = pngutil.read_rgb(mask_path)
    wanted = {}
    for s in ann["segments_info"]:
        cat = cat_by_id.get(s["category_id"])
        if cat and cat.get("isthing") and not s.get("iscrowd"):
            wanted[s["id"]] = Segment(s["id"], cat["name"])
    if wanted:
        for y in range(H):
            base = y * W * 3
            row_px = px[base: base + W * 3]
            for x in range(W):
                i = 3 * x
                sid = row_px[i] | (row_px[i + 1] << 8) | (row_px[i + 2] << 16)
                seg = wanted.get(sid)
                if seg is not None:
                    seg.rows[y].append(x)       # x tăng dần -> đã sắp xếp
                    seg.n += 1
    segs = [s for s in wanted.values() if s.n > 0]
    for s in segs:
        s.finish()
    return segs, W, H


def check_image(stem: str, boxes: list[tuple[str, tuple]], segs: list[Segment], W: int, H: int) -> list[dict]:
    """boxes: list (tên lớp, (x1,y1,x2,y2)). Trả về danh sách ứng viên của ảnh."""
    out = []
    pairs = []  # (iou, bi, si)
    for bi, (_, b) in enumerate(boxes):
        for si, s in enumerate(segs):
            v = iou(b, s.bbox)
            if v > 0:
                pairs.append((v, bi, si))
    pairs.sort(reverse=True)
    used_b, used_s, match = set(), set(), {}

    def greedy(cond, min_iou):
        for v, bi, si in pairs:
            if v < min_iou or bi in used_b or si in used_s:
                continue
            if cond(boxes[bi][0], segs[si].name):
                used_b.add(bi); used_s.add(si); match[si] = (bi, v)

    greedy(lambda a, b: a == b, MATCH_IOU)      # a. cùng lớp, trùng vị trí
    swap_pairs = []
    for v, bi, si in pairs:                       # b. khác lớp, trùng vị trí
        if v >= MATCH_IOU and bi not in used_b and si not in used_s and boxes[bi][0] != segs[si].name:
            used_b.add(bi); used_s.add(si); swap_pairs.append((bi, si, v))
    greedy(lambda a, b: a == b, LOOSE_IOU)      # c. cùng lớp, lệch nhiều hơn

    # --- swap: detection và panoptic khác lớp trên cùng một vật
    for bi, si, v in swap_pairs:
        out.append({
            "image": stem, "type": "class_swap|category_swap", "score": round(v, 3),
            "detail": f"box '{boxes[bi][0]}' trùng segment '{segs[si].name}' (IoU {v:.2f}); mở ảnh xem bên nào đúng",
            "box": [round(c, 1) for c in boxes[bi][1]], "segment_bbox": list(segs[si].bbox),
        })

    # --- instance_merge: một segment có pixel phủ >= 2 box cùng lớp
    merged = set()
    for si, s in enumerate(segs):
        shares = sorted(((s.inside(b) / s.n, bi) for bi, (name, b) in enumerate(boxes)
                         if name == s.name and iou(b, s.bbox) > 0), reverse=True)
        if len(shares) < 2 or shares[0][0] >= MERGE_MAX_SINGLE:
            continue
        b1, b2 = boxes[shares[0][1]][1], boxes[shares[1][1]][1]
        ib = (max(b1[0], b2[0]), max(b1[1], b2[1]), min(b1[2], b2[2]), min(b1[3], b2[3]))
        inter = s.inside(ib) / s.n if ib[2] > ib[0] and ib[3] > ib[1] else 0.0
        excl2, union = shares[1][0] - inter, shares[0][0] + shares[1][0] - inter
        if excl2 >= MERGE_EXCL and union >= MERGE_UNION:
            merged.add(si)
            out.append({
                "image": stem, "type": "instance_merge", "score": round(excl2, 3),
                "detail": f"segment '{s.name}' ({s.n} px): box tốt nhất chỉ chứa {shares[0][0]:.0%}, "
                          f"box cùng lớp thứ hai chứa riêng {excl2:.0%}, hai box phủ {union:.0%}",
                "segment_bbox": list(s.bbox), "boxes": [[round(c, 1) for c in b] for b in (b1, b2)],
            })

    # --- bbox_drift: cặp cùng lớp mà pixel segment rơi ra ngoài box
    for si, (bi, v) in match.items():
        if si in merged:
            continue
        s = segs[si]
        cov = s.inside(boxes[bi][1]) / s.n
        if cov < DRIFT_COV:
            out.append({
                "image": stem, "type": "bbox_drift", "score": round(1 - cov, 3),
                "detail": f"'{s.name}': chỉ {cov:.0%} pixel segment nằm trong box (IoU bbox {v:.2f})",
                "box": [round(c, 1) for c in boxes[bi][1]], "segment_bbox": list(s.bbox),
            })

    # --- bbox_drift (lệch hẳn): box không ghép được, nhưng ảnh còn segment CÙNG lớp chưa có box
    for bi, (name, b) in enumerate(boxes):
        if bi in used_b:
            continue
        free = [s for si, s in enumerate(segs) if s.name == name and si not in used_s and si not in merged]
        if not free:
            continue
        bw, bh = b[2] - b[0], b[3] - b[1]
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        # segment cùng lớp gần nhất, khoảng cách tâm chuẩn hoá theo kích thước box
        def dist(s):
            sx, sy = (s.bbox[0] + s.bbox[2]) / 2, (s.bbox[1] + s.bbox[3]) / 2
            return ((sx - cx) / max(bw, 1)) ** 2 + ((sy - cy) / max(bh, 1)) ** 2
        s = min(free, key=dist)
        cov = s.inside(b) / s.n
        out.append({
            "image": stem, "type": "bbox_drift", "score": round(1 - cov, 3),
            "detail": f"box '{name}' không ghép được vật nào; segment '{name}' gần nhất ({s.n} px) "
                      f"chỉ có {cov:.0%} pixel trong box",
            "box": [round(c, 1) for c in b], "segment_bbox": list(s.bbox),
        })
        used_s.add(segs.index(s))

    # --- box mồ côi: không ghép được segment nào (lô sạch: 0 box như vậy)
    #   a) box phủ một segment KHÁC lớp -> swap? (có thể COCO tự gán 2 box khác lớp cho 1 vật)
    #   b) box nằm trên vùng không có segment thing nào -> drift? / panoptic thiếu vật
    for bi, (name, b) in enumerate(boxes):
        if bi in used_b:
            continue
        cover = sorted(((iou(b, s.bbox), s.inside(b) / s.n, s) for s in segs if s.name != name), key=lambda x: -x[0])
        if cover and cover[0][0] >= MATCH_IOU and cover[0][1] >= 0.8:
            v, cov, s = cover[0]
            has_own = any(n2 == s.name and iou(b2, s.bbox) >= MATCH_IOU for n2, b2 in boxes)
            out.append({
                "image": stem, "type": "class_swap|category_swap", "score": round(v * (0.5 if has_own else 1), 3),
                "detail": f"box '{name}' nằm trên segment '{s.name}' (IoU {v:.2f})" +
                          (f"; segment này ĐÃ có box '{s.name}' riêng -> có thể COCO gán 2 lớp cho 1 vật" if has_own else ""),
                "box": [round(c, 1) for c in b], "segment_bbox": list(s.bbox),
            })
        elif not any(s.inside(b) for s in segs if s.name == name):
            out.append({
                "image": stem, "type": "bbox_drift", "score": 0.0,
                "detail": f"box '{name}' không phủ segment '{name}' nào (box mồ côi); xem vật có ở đó không",
                "box": [round(c, 1) for c in b],
            })

    # --- missing_box: segment thing lớn không ghép được box nào
    min_px = max(MISSING_MIN_PX, MISSING_MIN_FRAC * W * H)
    for si, s in enumerate(segs):
        if si in used_s or si in merged or s.n < min_px:
            continue
        # có box cùng lớp nào đã phủ phần lớn segment không? (vd box của vật bị che)
        # chỉ tính box CHƯA ghép: box đã thuộc vật khác (vd sandwich to bên cạnh) không thay được box của vật này
        if any(bi not in used_b and name == s.name and s.inside(b) / s.n >= 0.5 for bi, (name, b) in enumerate(boxes)):
            continue
        out.append({
            "image": stem, "type": "missing_box", "score": round(s.n / (W * H), 4),
            "detail": f"segment '{s.name}' {s.n} px ({s.n / (W * H):.1%} ảnh) không có box",
            "segment_bbox": list(s.bbox),
        })
    return out


def find_candidates(root: Path, d: dict, sizes: dict, skip: set[str], read_labels) -> list[dict]:
    """d: kết quả load_delivery; skip: ảnh đã có lỗi luật (mỗi ảnh nhiều nhất một lỗi)."""
    cat_by_id = {c["id"]: c for c in d["panoptic"]["categories"]}
    anns = {Path(a["file_name"]).stem: a for a in d["panoptic"]["annotations"]}
    out = []
    for stem, item in sorted(d["items"].items()):
        if stem in skip or stem not in anns:
            continue
        mask_path = root / (item.get("mask") or f"masks/{anns[stem]['file_name']}")
        rows = read_labels(root / item["label"])
        if rows is None or not mask_path.exists():
            continue
        segs, Wm, Hm = load_segments(mask_path, anns[stem], cat_by_id)
        W, H = sizes.get(stem, (Wm, Hm))
        boxes = []
        for token, xc, yc, w, h in rows:
            try:
                name = d["classes"][int(float(token))]
            except (ValueError, KeyError):
                continue
            boxes.append((name, yolo_to_px(xc, yc, w, h, W, H)))
        out += check_image(stem, boxes, segs, W, H)
    # mỗi ảnh nhiều nhất một lỗi: giữ ứng viên đầu tiên theo thứ tự ưu tiên
    # swap > instance_merge > bbox_drift > missing_box; các ứng viên khác ghi kèm ở "also"
    best = {}
    for c in out:
        prev = best.get(c["image"])
        if prev is None:
            best[c["image"]] = c
        else:
            prev.setdefault("also", []).append(f"{c['type']}: {c['detail']}")
    return sorted(best.values(), key=lambda c: (c["type"], -c["score"], c["image"]))
