# Báo cáo nhóm <<XX>>

## 1. Số liệu luyện tập
- F1 theo seed (rule / cross_check / overall):
  * seed 36: 1.0 / ... / 0.8.
  * seed 13007: 1.0 / ... / 0.8.
- Số ứng viên trên lô sạch (`--no-faults`): 4 ứng viên trên 4 ảnh; hàng đợi trên seed luyện tập: 25 ứng viên trên 23 ảnh
- Ngưỡng đã chọn và cách chọn (không dùng `_private`): <<...>>

## 2. Vì sao báo hết ứng viên làm F1 giảm?
<<Trả lời bằng số của nhóm.>>

## 3. Quyết định và lineage
- **QC v1:** 24/250 ảnh/cảnh có lỗi = 9,6% (12 lỗi luật + 12 lỗi gán nhãn đã `confirmed` trong `review_log.csv`; 3 ứng viên bị `rejected` không tính).
- **Kết luận v1: HOLD.** Theo ngưỡng Day 7, trên 2% ảnh lỗi thì không Release. Ngưỡng tính theo **tỉ lệ ảnh lỗi**, không theo số lỗi, vì lô lớn hơn sẽ có nhiều lỗi hơn mà chất lượng không đổi; tỉ lệ mới so sánh được giữa các lô.
- **Lineage** (`runs/lineage.jsonl`): `inject` release `lab250_6112a1fce312` (seed 36) → `train` run `R-021` trên release này → `decision HOLD` cho v1. Lệnh `lineage.py impact --release-id lab250_6112a1fce312` trả về `R-021: affected=True action=review_or_retrain`. Dòng `release v2 --parent` sẽ được ghi sau khi đóng gói v2.
- **Vì sao R-021 phải xem lại hoặc train lại:** R-021 đã học trực tiếp từ lô v1 có 9,6% ảnh lỗi, trong đó có nhãn sai lớp, box lệch, thiếu box và guideline cũ cho lớp `bottle`. Sửa dataset (tạo v2) không tự sửa trọng số của model đã train, nên R-021 vẫn mang các sai lệch đã học. Phải xem lại kết quả của R-021 (đặc biệt lớp bị lỗi, như `bottle` bị bỏ sót) hoặc train lại trên v2.

## 4. Hash chứng minh gì, không chứng minh gì?
- **Hash chứng minh điều gì:**
  - **Tính toàn vẹn dữ liệu (Data Integrity):** Chứng minh file nhận được hoàn toàn khớp từng byte so với thời điểm lập manifest, không bị hư hỏng tệp trong quá trình tải xuống/truyền tải (bit rot) hay bị ai đó vô tình/cố ý can thiệp chỉnh sửa sau khi đóng gói.
  - **Khả năng kiểm toán & truy vết (Auditability & Reproducibility):** Giúp định danh duy nhất phiên bản dữ liệu của lô phát hành (Release ID gắn liền với hash nội dung), đảm bảo huấn luyện mô hình ở lần chạy nào thì dùng đúng chính xác bộ dữ liệu của lần chạy đó.
- **Hash KHÔNG chứng minh điều gì:**
  - **Không chứng minh tính đúng đắn của nhãn (Data Quality/Label Correctness):** Một nhãn bị gán sai lớp (class_swap) hay vẽ lệch hộp (bbox_drift) vẫn có mã SHA256 hợp lệ. Một ảnh bị hỏng/lỗi ngay từ nguồn vẫn có mã hash tương ứng.
  - **Không chứng minh tính hợp lệ về mặt ngữ nghĩa (Semantic Validity):** Hash không thể kiểm tra xem ảnh có tuân thủ đúng phiên bản guideline hay không, cảnh có bị rò rỉ split (scene_leak) hay không. Do đó, hash chỉ là công cụ kiểm soát kỹ thuật ở tầng lưu trữ, không thể thay thế cho quy trình Data QC và kiểm tra đối chiếu bằng mắt người.

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
