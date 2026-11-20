# Báo cáo nhóm 13

## 1. Số liệu luyện tập
- F1 theo seed (rule / cross_check / overall), đo bằng `score_findings.py` (làm tròn 1 chữ số):
  * seed 36 (đã xem ảnh, `review_log.csv` 12 confirmed / 3 rejected): **1.0 / 0.8 / 0.9**.
  * seed 13007, 101, 202 (chỉ chạy validator để thử lỗi luật, không xem ảnh): lỗi luật **1.0** ở cả ba seed; cross_check không chấm vì không review.
  * Lô sạch (`inject_release.py --seed 5 --no-faults`): 0 lỗi luật, 0 ứng viên.
- Số ứng viên trên lô sạch (`--no-faults`): **0** với bản chốt `validator/crosscheck.py` (bản thử đầu ra 29; bản `validator/candidates.py` ra 4, đều `bbox_drift`). Hàng đợi trên seed luyện tập: **15 ảnh** (r101: 12, r202: 15). Bản chốt dùng trong `validate.py --candidates` là `crosscheck.py`.
- Ngưỡng đã chọn và cách chọn (không dùng `_private`): viết script đo phân bố tín hiệu trên lô sạch `runs/clean` rồi so với r36.
  * Tín hiệu chính là **pixel của mask**: `cov` = số pixel segment nằm trong box / số pixel segment. Ghép box ↔ segment thing (bỏ `iscrowd`) qua **tên lớp**, theo IoU giữa bbox pixel của segment và box.
  * `bbox_drift`: trên lô sạch **mọi** cặp box–segment cùng lớp có `cov` = 1,00, nên ngưỡng `cov < 0,95` (chừa biên cho nén ảnh).
  * `instance_merge`: bản đầu ("segment có ≥ 20% pixel trong 2 box cùng lớp") ra 29 ứng viên giả trên lô sạch, vì người/sách đứng chồng nhau. Đo lại thấy cặp chồng tự nhiên luôn có 1 box chứa 100% segment, phần riêng của box kia = 0, nên đổi luật: box tốt nhất chứa < 90%, box thứ hai chứa **riêng** ≥ 10%, hai box phủ ≥ 90%.
  * Box "mồ côi" (không ghép được segment nào): lô sạch có **0** box như vậy, nên mọi box mồ côi đều vào hàng đợi (kiểu swap nếu nằm trên segment khác lớp).
  * `missing_box`: segment thing ≥ 1% diện tích ảnh và ≥ 1000 px mà không có box chưa ghép nào phủ ≥ 50%.
  * Giới hạn: lô sạch chỉ có 50 ảnh khác bộ luyện tập. Trên r36 vẫn có 3 ứng viên lệch tự nhiên (2 missing_box và 1 ca COCO gán 2 box cho 1 vật); cả 3 đã được xem ảnh và ghi `rejected` kèm lý do.

## 2. Vì sao báo hết ứng viên làm F1 giảm?
Đo trên seed 36, mỗi phương án chấm một lần bằng `score_findings.py`:

| Phương án | Số mục báo | F1 lỗi gán nhãn | F1 tổng |
|---|---:|---:|---:|
| Chỉ lỗi luật | 12 | — | 0.8 |
| Báo hết 15 ứng viên, không xem ảnh (ứng viên swap chọn `class_swap`) | 27 | **0.5** | 0.8 |
| Sau khi xem ảnh (12 confirmed, 3 rejected) | 24 | **0.8** | **0.9** |

Ứng viên chỉ là chỗ hai nguồn nhãn **bất đồng**, chưa phải lỗi. Báo hết thì precision giảm vì hai lý do:
- **Lệch tự nhiên của COCO** cũng thành ứng viên. Ví dụ ngựa vằn con rúc vào mẹ nên mask bị che, người bị cắt quá nửa ở mép ảnh, hay một vật được COCO gán 2 box khác lớp. Ba ca này báo lên là 3 FP.
- **Ứng viên swap không cho biết bên nào sai.** Đoán `class_swap` cho cả 9 ca, trong khi xem ảnh thấy 4 ca là panoptic sai (`category_swap`). Mỗi ca đoán sai type thành **1 FP + 1 FN** cùng lúc, vì cặp `(type, target)` không khớp.

Báo hết không lấy thêm được lỗi thật nào so với bản đã xem ảnh: mọi ứng viên mà người xem thấy là lỗi đều đã được giữ. Vì vậy chỉ có thêm FP, và F1 lỗi gán nhãn rơi từ 0.8 xuống 0.5. Bước xem ảnh vừa loại lệch tự nhiên, vừa chọn đúng `class_swap`/`category_swap`, nên là bước quyết định điểm.

## 3. Quyết định và lineage
- **QC v1:** 24/250 ảnh/cảnh có lỗi = 9,6% (12 lỗi luật + 12 lỗi gán nhãn đã `confirmed` trong `review_log.csv`; 3 ứng viên bị `rejected` không tính).
- **Kết luận v1: HOLD.** Theo ngưỡng Day 7, trên 2% ảnh lỗi thì không Release. Ngưỡng tính theo **tỉ lệ ảnh lỗi**, không theo số lỗi, vì lô lớn hơn sẽ có nhiều lỗi hơn mà chất lượng không đổi; tỉ lệ mới so sánh được giữa các lô.
- **Lineage** (`submission/lineage.jsonl`): `inject` release `lab250_3c9a0e0e4b9c` (seed 36) → `train` run `R-021` trên release này → `decision HOLD` cho v1 → `release lab250_3c9a0e0e4b9c_v2` với `parent lab250_3c9a0e0e4b9c`. Lệnh `lineage.py impact --release-id lab250_3c9a0e0e4b9c` trả về `R-021: affected=True action=review_or_retrain`.
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
- Không tìm thấy bug trong `scripts/`. Nhóm không sửa file nào trong `scripts/`.
- **Lưu ý khi làm trên Windows:** git mặc định `core.autocrlf=true`. `tools/build_v2.py` ghi `manifest.csv`, `README.txt`... kiểu CRLF, `pack_release.py` băm các byte CRLF đó, nhưng khi commit git đổi sang LF. Kết quả: trên máy Windows `check_handover.py` báo 17/17 PASS, còn đóng gói lại từ bản đã commit (giả lập máy người chấm bằng `git archive`) thì lệch mã `.sha256` (H15 FAIL). Nhóm thêm `.gitattributes` (`submission/** -text`) để git giữ nguyên từng byte. Đã kiểm lại: đóng gói từ bản commit khớp mã `.sha256`.
- Điểm chưa rõ: một vật có thể được COCO gán **2 box khác lớp** chồng lên nhau (vd `vase` + `bottle`, `bus` + `truck`). Khi một trong hai lớp sai, đề không nói rõ nên tính là `class_swap` hay lệch tự nhiên. Nhóm quyết theo ảnh: lớp nào sai với vật thật thì bên đó sai; nếu cả hai tên đều chấp nhận được thì `rejected`.
