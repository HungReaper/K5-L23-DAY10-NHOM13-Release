"""Công cụ xem ảnh ứng viên (Pha 2) — nhóm 13. Được dùng Pillow (validator thì không).

Vẽ box detection (đỏ) và viền segment panoptic (xanh) lên ảnh, kèm vùng cắt phóng to
quanh vật bị nghi, để NGƯỜI xem quyết confirmed / rejected.

  # sinh ảnh cho mọi ứng viên + index.html + review_log.csv để điền
  python tools/view.py runs/r36/delivery --candidates runs/r36/candidates.json --out runs/r36/review \
      --people "Dũng,Tùng,Hưng,Tân,Khải Hưng,Nam"

  # xem nhanh một ảnh bất kỳ (không cần ứng viên)
  python tools/view.py runs/r36/delivery --image 000000000139 --out runs/r36/review

Trong mỗi PNG:
  [ảnh đầy đủ có nhãn] [vùng cắt phóng to có nhãn] [vùng cắt phóng to KHÔNG nhãn]
  - box detection: đỏ, chữ "D:<lớp>"; box của ứng viên: VÀNG, dày
  - viền segment panoptic (thing): xanh, chữ "P:<lớp>"; segment của ứng viên: tô TÍM mờ
  - dòng dưới: loại ứng viên + detail do validator ghi

review_log.csv KHÔNG được điền sẵn verdict: người xem ảnh tự ghi confirmed/rejected,
ghi note "thấy gì" và tên người xem (RULES: AI không được thay việc xem ảnh).
"""
from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FULL_SIDE = 640      # cạnh dài của khung ảnh đầy đủ
CROP_SIDE = 480      # cạnh dài của khung cắt phóng to
CROP_MARGIN = 0.35   # nới vùng cắt thêm 35% mỗi phía
TEXT_H = 64

RED, YELLOW, CYAN = (255, 40, 40), (255, 230, 0), (0, 230, 255)
PURPLE_FILL = (200, 0, 255, 90)


def font(size: int):
    for name in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


# --------------------------------------------------------------------------
class Delivery:
    def __init__(self, root: Path):
        self.root = root
        self.items = json.loads((root / "manifest.json").read_text(encoding="utf-8"))["items"]
        pan = json.loads((root / "panoptic.json").read_text(encoding="utf-8"))
        self.cats = {c["id"]: c for c in pan["categories"]}
        self.anns = {Path(a["file_name"]).stem: a for a in pan["annotations"]}
        self.classes = {}
        for line in (root / "classes.txt").read_text(encoding="utf-8").splitlines():
            if line.strip():
                i, n = line.split(maxsplit=1)
                self.classes[int(i)] = n.strip()

    def image(self, stem: str) -> Image.Image:
        p = self.root / self.items[stem]["image"]
        return Image.open(p).convert("RGB")

    def boxes(self, stem: str, W: int, H: int) -> list[tuple[str, tuple]]:
        p = self.root / self.items[stem]["label"]
        out = []
        if not p.exists():
            return out
        for line in p.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) < 5:
                continue
            try:
                cid = int(float(parts[0]))
                xc, yc, w, h = (float(v) for v in parts[1:5])
            except ValueError:
                continue
            name = self.classes.get(cid, f"?{parts[0]}")
            bw, bh = w * W, h * H                       # YOLO chuẩn hoá -> pixel
            x1, y1 = xc * W - bw / 2, yc * H - bh / 2
            out.append((name, (x1, y1, x1 + bw, y1 + bh)))
        return out

    def segments(self, stem: str):
        """Trả về (W, H, ids, segs). segs: id -> dict(name, crowd, bbox) cho segment thing."""
        p = self.root / self.items[stem]["mask"]
        ann = self.anns.get(stem)
        if not p.exists() or ann is None:
            return None
        m = Image.open(p).convert("RGB")
        W, H = m.size
        raw = m.tobytes()
        ids = [raw[i] | (raw[i + 1] << 8) | (raw[i + 2] << 16) for i in range(0, len(raw), 3)]
        segs = {}
        for s in ann["segments_info"]:
            c = self.cats.get(s["category_id"])
            if c is None:
                segs[s["id"]] = {"name": f"?cat{s['category_id']}", "crowd": bool(s.get("iscrowd")), "bbox": None}
            elif c.get("isthing"):
                segs[s["id"]] = {"name": c["name"], "crowd": bool(s.get("iscrowd")), "bbox": None}
        # bbox của pixel thật từng segment (giống crosscheck.py)
        for i, sid in enumerate(ids):
            s = segs.get(sid)
            if s is None:
                continue
            x, y = i % W, i // W
            b = s["bbox"]
            s["bbox"] = (x, y, x + 1, y + 1) if b is None else (min(b[0], x), min(b[1], y), max(b[2], x + 1), max(b[3], y + 1))
        segs = {k: v for k, v in segs.items() if v["bbox"] is not None}
        return W, H, ids, segs


def overlay(W: int, H: int, ids: list[int], segs: dict, hl_seg: int | None) -> Image.Image:
    """Lớp RGBA cùng cỡ ảnh: viền segment thing (xanh) + tô tím segment ứng viên."""
    buf = bytearray(W * H * 4)
    for i, sid in enumerate(ids):
        if sid not in segs:
            continue
        x = i % W
        edge = (x + 1 < W and ids[i + 1] != sid) or (x > 0 and ids[i - 1] != sid) or \
               (i + W < len(ids) and ids[i + W] != sid) or (i - W >= 0 and ids[i - W] != sid)
        j = 4 * i
        if edge:
            buf[j:j + 4] = bytes((*CYAN, 255))
        elif sid == hl_seg:
            buf[j:j + 4] = bytes(PURPLE_FILL)
    return Image.frombytes("RGBA", (W, H), bytes(buf))


def render_view(img: Image.Image, ov: Image.Image | None, region, side: int, boxes, segs, hl_boxes, labels=True, full=False):
    """Cắt region (x1,y1,x2,y2) từ ảnh, phóng tới cạnh dài = side, vẽ nhãn sắc nét ở tỉ lệ mới."""
    x1, y1, x2, y2 = region
    s = side / max(x2 - x1, y2 - y1)
    size = (max(1, round((x2 - x1) * s)), max(1, round((y2 - y1) * s)))
    view = img.crop((x1, y1, x2, y2)).resize(size, Image.LANCZOS).convert("RGBA")
    if ov is None:
        return view.convert("RGB")
    view.alpha_composite(ov.crop((x1, y1, x2, y2)).resize(size, Image.NEAREST))
    d = ImageDraw.Draw(view)
    f = font(13 if full else 15)
    tr = lambda b: ((b[0] - x1) * s, (b[1] - y1) * s, (b[2] - x1) * s, (b[3] - y1) * s)
    placed = []  # khung chữ đã đặt, để chữ không đè nhau

    def put(x, y, txt, color):
        x = min(max(x, 0), max(0, size[0] - 8))
        for _ in range(8):
            l, t, r, btm = d.textbbox((x, y), txt, font=f, stroke_width=2)
            if not any(l < P[2] and r > P[0] and t < P[3] and btm > P[1] for P in placed):
                break
            y += btm - t + 1
        placed.append(d.textbbox((x, y), txt, font=f, stroke_width=2))
        d.text((x, y), txt, fill=color, font=f, stroke_width=2, stroke_fill="black")

    # ảnh đông vật (khung đầy đủ): chỉ ghi chữ cho vật của ứng viên, tránh rối
    crowded = full and len(boxes) + len(segs) > 24 and bool(hl_boxes)

    for k, (name, b) in enumerate(boxes):
        hl = k in hl_boxes
        d.rectangle(tr(b), outline=YELLOW if hl else RED, width=3 if hl else 1)
    # chữ: vật của ứng viên trước (được chỗ đẹp), rồi tới phần còn lại
    order = sorted(range(len(boxes)), key=lambda k: k not in hl_boxes)
    for k in order:
        hl = k in hl_boxes
        if labels and (hl or not crowded):
            bx = tr(boxes[k][1])
            put(bx[0] + 2, bx[1] + 1, "D:" + boxes[k][0], YELLOW if hl else RED)
    for sid, sg in segs.items():
        bx = tr(sg["bbox"])
        if labels and not crowded and bx[2] > 0 and bx[3] > 0 and bx[0] < size[0] and bx[1] < size[1]:
            txt = "P:" + sg["name"] + (" (crowd)" if sg["crowd"] else "")
            put(bx[0] + 2, min(bx[3], size[1]) - 18, txt, CYAN)
    return view.convert("RGB")


def same_box(a, b, tol=1.0) -> bool:
    return all(abs(p - q) <= tol for p, q in zip(a, b))


def render(dl: Delivery, stem: str, cand: dict | None, out_png: Path):
    img = dl.image(stem)
    W, H = img.size
    boxes = dl.boxes(stem, W, H)
    seg = dl.segments(stem)
    if seg is None:
        ids, segs, ov = [], {}, None
    else:
        Wm, Hm, ids, segs = seg
        if (Wm, Hm) != (W, H):  # mask lệch cỡ ảnh: phóng mask cho khớp để vẫn xem được
            ov_small = overlay(Wm, Hm, ids, segs, None)
            ov = ov_small.resize((W, H), Image.NEAREST)
        else:
            ov = None

    # vật của ứng viên
    hl_boxes, hl_seg, focus = set(), None, []
    if cand:
        want = [cand["box"]] if cand.get("box") else []
        want += cand.get("boxes", [])
        for k, (_, b) in enumerate(boxes):
            if any(same_box(b, w) for w in want):
                hl_boxes.add(k)
        focus += want
        if cand.get("segment_bbox"):
            sb = tuple(cand["segment_bbox"])
            hl_seg = next((sid for sid, sg in segs.items() if tuple(sg["bbox"]) == sb), None)
            focus.append(sb)
    if seg is not None and ov is None:
        ov = overlay(W, H, ids, segs, hl_seg)

    full = render_view(img, ov, (0, 0, W, H), FULL_SIDE, boxes, segs, hl_boxes, full=True)
    panels = [full]
    if focus:
        fx1, fy1 = min(b[0] for b in focus), min(b[1] for b in focus)
        fx2, fy2 = max(b[2] for b in focus), max(b[3] for b in focus)
        mw, mh = (fx2 - fx1) * CROP_MARGIN + 8, (fy2 - fy1) * CROP_MARGIN + 8
        region = (max(0, int(fx1 - mw)), max(0, int(fy1 - mh)), min(W, int(fx2 + mw) + 1), min(H, int(fy2 + mh) + 1))
        panels.append(render_view(img, ov, region, CROP_SIDE, boxes, segs, hl_boxes))
        panels.append(render_view(img, None, region, CROP_SIDE, [], {}, set(), labels=False))

    gap = 8
    total_w = sum(p.width for p in panels) + gap * (len(panels) - 1)
    total_h = max(p.height for p in panels) + TEXT_H
    canvas = Image.new("RGB", (total_w, total_h), (30, 30, 30))
    x = 0
    for p in panels:
        canvas.paste(p, (x, 0))
        x += p.width + gap
    d = ImageDraw.Draw(canvas)
    head = f"{stem}  {W}x{H}" + (f"  |  {cand['type']}" if cand else "")
    d.text((8, total_h - TEXT_H + 6), head, fill="white", font=font(16))
    if cand:
        d.text((8, total_h - TEXT_H + 30), cand.get("detail", ""), fill=(220, 220, 220), font=font(14))
    out_png.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_png)


# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Xem ảnh ứng viên: box detection + viền segment panoptic")
    ap.add_argument("delivery", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--candidates", type=Path)
    ap.add_argument("--image", action="append", default=[], help="tên ảnh (không đuôi), lặp lại được")
    ap.add_argument("--people", default="", help="tên người xem, cách nhau dấu phẩy: chia hàng đợi xoay vòng")
    args = ap.parse_args()

    dl = Delivery(args.delivery)
    jobs = []  # (stem, cand)
    if args.candidates:
        cands = json.loads(args.candidates.read_text(encoding="utf-8"))["candidates"]
        jobs += [(c["image"], c) for c in cands]
    jobs += [(s, None) for s in args.image]
    if not jobs:
        ap.error("cần --candidates hoặc --image")

    people = [p.strip() for p in args.people.split(",") if p.strip()]
    rows = []
    for k, (stem, cand) in enumerate(jobs):
        if stem not in dl.items:
            print(f"bỏ qua {stem}: không có trong manifest")
            continue
        name = f"{k + 1:03d}_{stem}.png" if cand else f"{stem}.png"
        try:
            render(dl, stem, cand, args.out / name)
        except OSError as e:  # ảnh thiếu / hỏng
            print(f"không mở được {stem}: {e}")
            continue
        who = people[k % len(people)] if people else ""
        rows.append((name, stem, cand, who))
        print(f"[{k + 1}/{len(jobs)}] {name}" + (f"  -> {who}" if who else ""))

    if args.candidates:
        # trang xem nhanh
        body = []
        for name, stem, cand, who in rows:
            body.append(
                f"<div class=c><h3>{html.escape(name)} · <code>{html.escape(cand['type'])}</code>"
                + (f" · người xem: <b>{html.escape(who)}</b>" if who else "")
                + f"</h3><p>{html.escape(cand.get('detail', ''))}</p>"
                + (f"<p class=also>khác: {html.escape(' | '.join(cand['also']))}</p>" if cand.get("also") else "")
                + f"<img src='{html.escape(name)}'></div>")
        (args.out / "index.html").write_text(
            "<!doctype html><meta charset=utf-8><title>Review</title><style>body{background:#222;color:#eee;"
            "font-family:sans-serif}img{max-width:100%}.c{margin:0 0 40px}.also{color:#aaa}</style>"
            f"<h1>{len(rows)} ứng viên</h1>" + "\n".join(body), encoding="utf-8")

        # review_log để NGƯỜI điền; không ghi đè file đã có
        log = args.out / "review_log.csv"
        if log.exists():
            print(f"{log} đã có, không ghi đè")
        else:
            with open(log, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(["image", "type", "verdict", "note"])
                for name, stem, cand, who in rows:
                    w.writerow([stem, cand["type"], "", f"[{who}] " if who else ""])
            print(f"-> {log}: điền verdict (confirmed/rejected) + note 'thấy gì'; "
                  "với 'class_swap|category_swap' sửa type thành loại đúng sau khi xem ảnh")
        print(f"-> mở {args.out / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
