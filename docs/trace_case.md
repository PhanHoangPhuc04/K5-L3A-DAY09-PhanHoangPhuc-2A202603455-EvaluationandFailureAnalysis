# Trace case: từ trace tới quyết định sai đầu tiên

Người làm: Phan Hoàng Phúc (2A202603455).

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, run `E-seeded_regression-20261118-2afb` (`src/reports/eval_seeded_regression.json`, dòng E-002 seed 11) |
| Triệu chứng | `pass_rate`, `refund_amount_correct`, `db_fact_kept` đều fail. Ledger ghi 20.000đ, 1 lần hoàn; nhãn là 0đ, `denied`. Reply "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202." khớp ledger nên chỉ đọc reply thì không thấy lỗi. |
| Bước sai đầu tiên | Event 3 `model_override` `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` đúng hợp đồng (task `check_applicable_policy`, đủ 3 tool). Event 2 `investigator` đọc đúng DB: O-202 `delay_days=2`, `shipping_fee_vnd=20000`. Đến event 3 agent thay 2 ngày bằng 5 ngày khách tự khai trong ticket; event 4 `quote` 20.000đ theo `SHIP-LATE-03` chỉ là hệ quả của event 3. |
| Failure mode | FM-03 ticket_trust |
| Đối chứng | `fixed C-002@11`: event 2 giống hệt, không có `model_override`, event 3 `quote` `amount_vnd=0, reason=no_entitlement`, event 4 reply từ chối; ledger 0, grader Lab 8 PASS. Baseline `swarm` cũng có đúng lỗi này ở C-002@55 (nhánh `seed % 5 == 0` của `swarm_reference`), nên `pass_rate` baseline là 0,9857 chứ không phải 1. |
| Regression test | `src/tests/test_lab9_trace_case.py`: `test_lab9_trace_case_c002_first_wrong_step_is_override` (event 3 là `model_override` đầu tiên trên `seeded_regression`, `fixed` không có) và `test_lab9_trace_case_c002_graders_catch_regression_not_fix` (`DbFactKept`, `RefundAmountCorrect` fail trên `seeded_regression`, pass trên `fixed`). Cả hai chạy trong `pytest -m student -k lab9` và đã qua. Ở mức eval set, item E-002 mang `FM-03`. |
| Chưa chắc chắn | Trace không ghi lý do agent tin ticket (MockLLM không có chuỗi suy luận), nên tôi chỉ chứng minh được *bước* sai, không chứng minh được *vì sao* model chọn vậy. Biến thể `quiet_override` cùng lỗi nhưng không ghi event `model_override`: khi đó `DbFactKept` không thấy gì, chỉ `RefundAmountCorrect` (đọc ledger) còn bắt được. |
