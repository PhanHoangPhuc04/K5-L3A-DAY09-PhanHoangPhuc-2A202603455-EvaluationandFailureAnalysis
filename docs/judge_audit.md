# Judge audit

Người làm: Phan Hoàng Phúc (2A202603455). Judge chạy ở chế độ replay (phán quyết lưu sẵn trong CSV), FAIL là lớp dương.

```bash
cd src
python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 10     # exit 0
python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 10  # exit 1
```

| Tiêu chí | n | κ | Precision | Recall | Ma trận (tp/fp/fn/tn) | Tỉ lệ fail quan sát → hiệu chỉnh Rogan-Gladen | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|---|---|
| tone_ok | 100 | 0,757 | 0,857 | 0,800 | 24 / 4 / 6 / 66 | 0,28 → 0,30 | Đạt | dùng (chỉ cho tiêu chí giọng văn, không chặn release một mình) |
| helpful | 100 | 0,375 | 1,000 | 0,300 | 9 / 0 / 21 / 70 | 0,09 → 0,30 | Không đạt (κ và R dưới sàn) | loại |

## Case audit thủ công (10 bất đồng của tone, 5 của helpful)
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | Người | Xưng "em", "nha" quá suồng sã. Rubric thêm: xưng "LogiX", gọi "anh/chị"; "nha/nhé" là FAIL. |
| 2 | H-017 "bạn ơi … rồi nha" | PASS | FAIL | Người | Gọi khách là "bạn". Cùng luật xưng hô như #1, kèm ví dụ FAIL trong prompt judge. |
| 3 | H-029 "vui lòng chờ … không cần nhắn thêm" | PASS | FAIL | Người | Judge chỉ thấy "Dạ, vui lòng". Rubric thêm: câu ra lệnh, chặn khách liên hệ là FAIL dù có từ lịch sự. |
| 4 | H-042 "đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge phạt vì thiếu xin lỗi. Rubric ghi rõ: không bắt buộc xin lỗi khi đã giải quyết xong. |
| 5 | H-051 "đã refund 90.000đ" | FAIL | PASS | Người | CS LogiX cho phép "refund". Thêm danh sách từ tiếng Anh được phép. |
| 6 | H-063 "sẽ hoàn thêm cho anh/chị" | PASS | FAIL | Người | Hứa ngoài kết quả hệ thống. Đây là lỗi nội dung hơn là giọng; chuyển sang grader code (so lời hứa với ledger), không giao cho judge tone. |
| 7 | H-070 "… ạ 😂😂" | PASS | FAIL | Người | Rubric thêm: emoji trong phản hồi khiếu nại là FAIL. |
| 8 | H-081 "chưa đủ điều kiện hoàn theo chính sách" | FAIL | PASS | Judge | Ghi chú CSV: người đọc nhầm ticket. Sửa nhãn người thành FAIL, không sửa rubric. |
| 9 | H-088 "Dạ, dạ, LogiX đã hoàn…" | FAIL | PASS | Chưa chắc, nghiêng về người | Lặp "Dạ" do lỗi gõ, không xúc phạm khách. Rubric ghi: lỗi gõ nhỏ không làm FAIL tone; đưa vào hàng đợi người duyệt lại. |
| 10 | H-094 "Da, LogiX da hoan … xin loi" | PASS | FAIL | Người | Mất dấu tiếng Việt. Rubric thêm: phản hồi không dấu là FAIL. |
| 11 | HL-015 "đã hoàn 55.000đ" (ledger 40.000đ) | PASS | FAIL | Người | Judge không thấy ledger nên không thể biết sai tiền. 18/21 lần judge bỏ sót là "sai tiền": việc này thuộc grader code `reply_amount_matches_ledger` (FM-08). |
| 12 | HL-016 xin lỗi dài + "đã hoàn 55.000đ" (ledger 35.000đ) | PASS | FAIL | Người | Câu văn dài, nhiều lời xin lỗi làm judge cho PASS dù số tiền sai. Rubric: độ dài và lời xin lỗi không cộng điểm helpful. |
| 13 | HL-047 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | Người | Không nói kết quả, không nói số tiền, sai xưng hô. Rubric: helpful phải nêu kết quả cụ thể (hoàn bao nhiêu / vì sao từ chối / cần gì thêm). |
| 14 | HL-091 "Ok bạn, đơn O-233 xử lý rồi nhé." | PASS | FAIL | Người | Cùng mẫu #13; thêm ví dụ này làm ví dụ FAIL trong prompt judge. |
| 15 | HL-087 "đã hoàn 60.000đ" (ledger 90.000đ) | PASS | FAIL | Người | Sai tiền theo chiều nói thiếu; cùng hướng xử lý #11. |

## Kết luận
- `tone_ok` qua cả ba sàn, được dùng để theo dõi giọng văn. Judge này sai nhiều nhất ở xưng hô và giọng ra lệnh (6/10 bất đồng là judge bỏ sót FAIL), nên rubric cần thêm luật xưng hô và ví dụ FAIL như trên.
- `helpful` bị loại: P = 1,0 nhưng R = 0,3 (bỏ sót 21/30 phản hồi tệ), κ = 0,375. Ma trận cho thấy judge chỉ bắt được giọng cụt và trả lời lạc đề, còn 18 lần "sai tiền" thì không bắt được lần nào vì judge không đọc ledger. Dùng judge này làm gate thì gần như mọi lỗi tiền sẽ lọt; tỉ lệ fail thật sau hiệu chỉnh là 0,30 trong khi judge chỉ báo 0,09. Phần "sai tiền" tôi chấm bằng code (`reply_amount_matches_ledger`), không dùng judge.
- Rủi ro còn lại: judge chỉ được kiểm trên 100 dòng replay đã công khai, chưa có tập held-out mới; κ của tone có thể thấp hơn trên phản hồi thật. Nhãn người ở #8 đã sai một lần, nên cần hai người gắn nhãn và đo κ giữa người với người trước khi tin con số 0,757.
