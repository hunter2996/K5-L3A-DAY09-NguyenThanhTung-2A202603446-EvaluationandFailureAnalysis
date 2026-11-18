# Trace case: từ trace tới quyết định sai đầu tiên

Lệnh đối chứng đã chạy trong `src/`:
```bash
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11
```

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, thuộc report `E-seeded_regression-20261118-68cf` (`src/reports/eval_seeded_regression.json`) |
| Triệu chứng | `lab8.metrics.trial_pass` FAIL (`status resolved != denied`); đồng thời `DbFactKept` FAIL (`1 override event(s)`) và `RefundAmountCorrect` FAIL (`ledger=20000 != label=0`). Reply nói `"Dạ, LogiX đã hoàn 20.000đ cho đơn O-202."` trong khi nhãn yêu cầu từ chối (`0đ`). |
| Bước sai đầu tiên | Event **3** · `model_override` · `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | Event **1** (`handoff`) tạo handoff đúng allowlist read-only (`lookup_order`, `lookup_policy`, `compute_compensation`, `facts={}`, không rò secret). Event **2** (`investigator`) truy xuất đúng dòng DB `O-202` với `delay_days: 2` (`shipping_fee_vnd: 20000`). Tới event **3**, agent lại tin số `"5 ngày"` trong ticket và ghi đè `order["delay_days"] = 5`, kéo theo event **4** (`quote`) tính sai thành `20000` và ghi vào ledger. |
| Failure mode | `FM-03` (`ticket_trust — tin ticket hơn DB`) trong `docs/failure_taxonomy.md` |
| Đối chứng | Trên `fixed C-002@11` (`E-fixed-20261118-68cf`): event **1** (`handoff`) và **2** (`investigator` với `delay_days: 2`) giống hệt, **không** có event `model_override`; event **3** (`quote`) ra `amount_vnd: 0, reason: "no_entitlement"`, event **4** (`reply`) từ chối đúng theo DB (`ledger=0, status=denied`). |
| Regression test | [`src/tests/test_lab9_trace_case.py::test_trace_case_c002_seed11_regression_and_fixed`](file:///d:/Code/CodeStudy/LabVinuni/K5-L3A-DAY09-NguyenThanhTung-2A202603446-EvaluationandFailureAnalysis/src/tests/test_lab9_trace_case.py) dùng `lab9.graders.DbFactKept` và `lab9.graders.RefundAmountCorrect`: đã kiểm chứng FAIL đúng các assert trên `seeded_regression` và PASS trên `fixed`. |
| Chưa chắc chắn | Trace trên `MockLLM` không phản ánh xác suất model thật tự suy diễn `delay_days` mà không phát sinh event `model_override` (tình huống `quiet_override` ở biến thể ẩn cần dựa vào `RefundAmountCorrect` / slice `denial` ở mức outcome). |
