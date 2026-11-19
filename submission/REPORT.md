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
- **Hash chứng minh điều gì:**
  - **Tính toàn vẹn dữ liệu (Data Integrity):** Chứng minh file nhận được hoàn toàn khớp từng byte so với thời điểm lập manifest, không bị hư hỏng tệp trong quá trình tải xuống/truyền tải (bit rot) hay bị ai đó vô tình/cố ý can thiệp chỉnh sửa sau khi đóng gói.
  - **Khả năng kiểm toán & truy vết (Auditability & Reproducibility):** Giúp định danh duy nhất phiên bản dữ liệu của lô phát hành (Release ID gắn liền với hash nội dung), đảm bảo huấn luyện mô hình ở lần chạy nào thì dùng đúng chính xác bộ dữ liệu của lần chạy đó.
- **Hash KHÔNG chứng minh điều gì:**
  - **Không chứng minh tính đúng đắn của nhãn (Data Quality/Label Correctness):** Một nhãn bị gán sai lớp (class_swap) hay vẽ lệch hộp (bbox_drift) vẫn có mã SHA256 hợp lệ. Một ảnh bị hỏng/lỗi ngay từ nguồn vẫn có mã hash tương ứng.
  - **Không chứng minh tính hợp lệ về mặt ngữ nghĩa (Semantic Validity):** Hash không thể kiểm tra xem ảnh có tuân thủ đúng phiên bản guideline hay không, cảnh có bị rò rỉ split (scene_leak) hay không. Do đó, hash chỉ là công cụ kiểm soát kỹ thuật ở tầng lưu trữ, không thể thay thế cho quy trình Data QC và kiểm tra đối chiếu bằng mắt người.

## 5. Truy vết
<<Tiêu chí tầng a/b, vì sao lấy guideline theo job.>>

## 6. Bug hoặc điểm chưa rõ trong lab (nếu có)
<<>>
