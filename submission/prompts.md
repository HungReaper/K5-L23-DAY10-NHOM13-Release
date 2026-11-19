# Dùng AI

| # | Ai dùng | Công cụ | Prompt (tóm tắt) | AI sai ở đâu | Nhóm kiểm lại thế nào |
|---|---|---|---|---|---|
| 1 | Dương Trí Dũng | Claude Code (Opus 5.5) | "Làm Pha 1 và giải thích": viết `validator/validate.py` bắt 9 lỗi luật, chỉ thư viện chuẩn + `pngutil.py` | Bản đầu đặt ngưỡng theo cảm tính: `duplicate_box` cho lệch kích thước ≤ 1 px, `thing_overlap` dung sai 0 px. Đo trên lô sạch thì cặp box tự nhiên gần trùng nhất lệch kích thước 1,4 px, sát ngưỡng 1 px | Viết script đo phân bố trên `runs/clean` và `runs/r13007` (tràn mép, cặp box cùng lớp gần nhau, `area` − số pixel thật), siết ngưỡng kích thước xuống 0,5 px; chạy `score_findings.py` trên r13007, r101, r202, lô `--opaque` và 2 lô sạch: lỗi luật F1 ≈ 1.0, lô sạch 0 lỗi |
| 2 | Nguyễn Hải Nam | Antigravity (Gemini) | Viết script dựng lô v2 (tools/build_v2.py) và giải quyết ca bảo mật (security.md) | Ban đầu build_v2 đọc metadata.json dạng dict phẳng thay vì bóc tách trường 'items', và label_summary.csv liệt kê cả các lớp count=0 làm lệch điều kiện kiểm tra H9 | Chạy thử nghiệm bằng check_handover.py, đọc code kiểm tra của giảng viên và sửa lại bóc tách dữ liệu để đạt PASS toàn bộ H4-H13, H15, H17 |
