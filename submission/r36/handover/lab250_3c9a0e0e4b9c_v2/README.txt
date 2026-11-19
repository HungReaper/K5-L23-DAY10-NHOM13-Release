Release: lab250_3c9a0e0e4b9c_v2
Parent: lab250_3c9a0e0e4b9c
Số ảnh: 237
Số nhãn: 1657
Guideline: v1.2 (J01-J04), v1.3 (J05-J10)
QC v1: 24/250 = 9.6%
Kết luận v1: Hold — Tỉ lệ ảnh lỗi 9.6% (24/250) vượt ngưỡng 2% cho phép release
Kết luận v2: Release — Đã tách 13 ảnh lỗi sang rework_queue.csv, chuẩn hóa split cảnh và cập nhật hash thực tế
Ghi chú: Lô v2 chỉ giữ các ảnh và nhãn detection đạt chuẩn; các ảnh lỗi detection được chuyển cho đúng annotator và reviewer theo jobs.csv để gán lại; các cảnh rò rỉ split đã được thống nhất về một split duy nhất; ảnh bị sai hash (000000001993) đã mở kiểm tra tệp ảnh còn nguyên vẹn nên cập nhật hash thật và giữ trong v2; các ảnh chỉ lỗi panoptic (000000007386, 000000008899, 000000009483, 000000014007, 000000018380, 000000018833, 000000020333) giữ nguyên trong v2 và đã báo team panoptic.
