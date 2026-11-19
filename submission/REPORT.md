# Báo cáo nhóm <<XX>>

## 1. Số liệu luyện tập
- F1 theo seed (rule / cross_check / overall): <<seed: ... / ... / ...>>
- Số ứng viên trên lô sạch (`--no-faults`): <<...>>; hàng đợi trên seed luyện tập: <<... ảnh>>
- Ngưỡng đã chọn và cách chọn (không dùng `_private`): <<...>>

## 2. Vì sao báo hết ứng viên làm F1 giảm?
<<Trả lời bằng số của nhóm.>>

## 3. Quyết định và lineage
<<QC v1 a/b, kết luận, vì sao R-021 phải xem lại hoặc train lại.>>

## 4. Hash chứng minh gì, không chứng minh gì?
<<>>

## 5. Truy vết
Script `tools/trace_query.py` đọc từ `delivery/` của lô (không viết cứng lớp, cảnh hay job):
- Lớp bị đổi quy tắc lấy từ `guideline/changelog.md` (dòng "Lớp `X`" trong mục phiên bản mới). Seed 36: `bottle`, đổi từ v1.3.
- Cảnh team AI báo lấy từ `incoming/ticket.md`. Seed 36: `scene_742`, `scene_768`.
- Job guideline cũ là job có guideline trong `jobs.csv` thấp hơn phiên bản đổi quy tắc. Seed 36: J01–J04.
- "Có lớp" nghĩa là có ít nhất một box detection của lớp đó trong `labels/` (không tính panoptic).
- `tier_a`: ảnh trong cảnh được báo, thuộc job cũ, có box `bottle` (2 ảnh). `tier_b`: cùng điều kiện nhưng ở cảnh khác (4 ảnh). `notify`: người gán và người kiểm của các job chứa ảnh tier_a/tier_b (J02, J03, J04): A02, A03, A05, Q01, Q02, Q03.
- `score_findings.py --run runs/r36` tự đo: tier_a, tier_b, notify đều F1 ≈ 1.0.

**Vì sao lấy guideline theo job, không theo ảnh?** Guideline là quy tắc mà người gán đã làm theo khi gán cả job, nên job quyết định ảnh có bị ảnh hưởng bởi quy tắc cũ hay không. Giá trị `guideline_version` ghi ở từng ảnh có thể chính là lỗi `guideline_mismatch` (ảnh bị ghi sai), nên dùng nó sẽ đưa ảnh vào hoặc loại ảnh ra nhầm.

## 6. Bug hoặc điểm chưa rõ trong lab (nếu có)
<<>>
