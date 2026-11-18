# Judge audit

Chạy:
- `python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 10`
- `python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 10`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| `tone_ok` | 100 | 0.757 | 0.857 | 0.800 | Có (`tp=24, fp=4, fn=6, tn=66`, obs fail `0.28` → Rogan-Gladen `0.30`) | **Dùng được** (theo dõi thêm khi đổi prompt/model) |
| `helpful` | 100 | 0.375 | 1.000 | 0.300 | Không (`tp=9, fp=0, fn=21, tn=70`, obs fail `0.09` → Rogan-Gladen `0.30`) | **Loại** — không được dùng làm gate |

## Audit thủ công các bất đồng (≥5 case)

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú & hành động sửa rubric |
|---|---|---|---|---|---|
| 1 | `H-008` | PASS | FAIL | Người đúng | `"Em đã hoàn tiền cho anh rồi nha..."` — xưng hô suồng sã; sửa rubric cấm đại từ thân mật (`em`, `bạn`, `nha`) và chỉ cho phép `LogiX` – `anh/chị`. |
| 2 | `H-017` | PASS | FAIL | Người đúng | `"Dạ, bạn ơi LogiX đã hoàn 25.000đ... rồi nha."` — có `"Dạ"` nên judge bỏ qua lỗi xưng `"bạn"` + `"nha"`; bổ sung negative examples có từ lịch sự giả tạo. |
| 3 | `H-029` | PASS | FAIL | Người đúng | `"Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm."` — giọng ra lệnh; cập nhật rubric kiểm toàn câu, không chỉ mở đầu bằng `"Dạ, vui lòng"`. |
| 4 | `H-063` | PASS | FAIL | Người đúng | `"Dạ, LogiX đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ."` — hứa hoàn thêm ngoài kết quả hệ thống; cấm cam kết nghiệp vụ ngoài ledger trong rubric. |
| 5 | `H-070` | PASS | FAIL | Người đúng | `"Dạ, LogiX đã hoàn 90.000đ cho đơn O-909 ạ 😂😂"` — dùng emoji trong ngữ cảnh khiếu nại; thêm quy tắc cấm emoji/emoticon. |
| 6 | `H-094` | PASS | FAIL | Người đúng | `"Da, LogiX da hoan 40.000đ..., xin loi vi su bat tien."` — thiếu dấu tiếng Việt; bắt buộc tiếng Việt có dấu chuẩn trong rubric. |
| 7 | `H-042` | FAIL | PASS | Người đúng | `"Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ."` — ngắn gọn đủ ý, judge phạt nhầm vì thiếu lời xin lỗi khi đã hoàn tiền; làm rõ không bắt buộc xin lỗi với ca `resolved`. |
| 8 | `H-051` | FAIL | PASS | Người đúng | `"Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ."` — CSKH cho phép thuật ngữ `"refund"`; liệt kê whitelist từ tiếng Anh nghiệp vụ được phép. |
| 9 | `H-081` | FAIL | PASS | Judge đúng | Nhãn người đánh nhầm khi đọc nhầm ticket (`"Dạ, đơn O-107 chưa đủ điều kiện..."` là lịch sự đúng chuẩn); sửa nhãn ground-truth và double-check nhãn người. |
| 10 | `HL-015` / `HL-016` (`helpful`) | PASS | FAIL | Người đúng | Reply xin lỗi rất dài dòng, lịch sự nhưng nói **sai số tiền** (`55.000đ` so với ledger `40.000đ`/`35.000đ`); **không** dùng judge `helpful` để chấm tính đúng đắn số tiền — tách riêng code grader `reply_amount_matches_ledger`. |

## Kết luận
- **`helpful` bị loại:** Trong ma trận nhầm lẫn (`tp=9, fp=0, fn=21, tn=70`), judge chỉ bắt được 9/30 ca lỗi (`Recall = 0.300`, `κ = 0.375`), bỏ sót 21 ca (`FN = 21`) nên tỉ lệ lỗi quan sát bị nén xuống `0.09` trong khi tỉ lệ lỗi thực sau hiệu chỉnh Rogan-Gladen là `0.30`. Nguyên nhân chính là judge thiên vị văn phong xin lỗi dài dòng và không có dữ liệu `refund_ledger` để đối chiếu số tiền (15+ ca nói sai tiền đều bị judge chấm `PASS`). Không được dùng `helpful` làm CI gate; phần kiểm số tiền phải giao cho code grader (`reply_amount_matches_ledger`).
- **`tone_ok` đạt chuẩn calibration** (`κ = 0.757 ≥ 0.6`, `P = 0.857 ≥ 0.8`, `R = 0.800 ≥ 0.7`), đủ điều kiện theo dõi giọng điệu sau khi siết rubric các lỗi xưng hô/emoji/không dấu như bảng trên.
- **Rủi ro còn lại:** Cả hai judge mới kiểm trên tập replay CSV công khai (`n=100`); cần thu thập thêm tập nhãn người held-out độc lập nếu triển khai trên model/prompt mới.
