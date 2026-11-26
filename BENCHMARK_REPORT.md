# Benchmark & Observability Report — Day 14

**Họ tên:** Nguyen Le Trong Manh — 2A202603857
**Ngày chạy:** 2026-11-26
**Môi trường:** Linux container (4 vCPU / 15 GB RAM), Python 3.13, Docker Engine 29.9 (Compose v2). Mock LLM, không gọi API thật.

> Mọi con số dưới đây lấy từ `reports/*.json`, `benchmark-results/*.csv` và ảnh trong `screenshots/`.

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | LLM call bình thường ~150–250 ms; 500 ms để chừa chỗ cho retrieval và mạng, vẫn đủ nhanh cho chat. Dùng p95 vì phản ánh trải nghiệm của phần lớn user mà không bị 1–2 request ngoại lệ chi phối như max. Trùng ngưỡng mặc định của `load_test.py`. |
| Error rate `/ask` | < 2 % | Mock LLM có `MOCK_ERROR_RATE=0.01` (1 % lỗi upstream là "nền"), 2 % cho phép dao động bình thường; vượt 2 % nghĩa là có sự cố thật. Alert `AgentHighErrorRate` dùng ngưỡng 5 % trong 1 phút để tránh báo động giả. |
| Accuracy trên golden dataset | ≥ 85 % | Ngưỡng của job CI (`.github/workflows/eval.yml`). Không đặt 100 % cho CI vì golden dataset sẽ lớn dần; nhưng **không được có regression** so với baseline. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

300 request mỗi mức, `MOCK_SLOW_RATE=0.03` (mặc định). Nguồn: `reports/load_v2_c{1,10,50,100}.json`.

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.6 | 188.7 | 219.7 | 1686.0 | 1.00 % | ✅ PASS |
| 10 | 43.18 | 190.0 | 219.0 | 1697.8 | 0.67 % | ✅ PASS |
| 50 | 109.49 | 193.1 | 247.5 | 1686.9 | 0.67 % | ✅ PASS |
| 100 | 72.31 | 301.6 | 2340.3 | 2682.8 | 1.33 % | ❌ FAIL (p95) |

**Nhận xét:** RPS tăng gần tuyến tính từ 1 → 10 (4.6 → 43.2, ×9.4) vì agent là async: mỗi request chủ yếu *chờ* LLM (I/O), nên event loop phục vụ được nhiều request cùng lúc mà latency gần như không đổi (p50 ~190 ms). Từ 10 → 50 RPS chỉ tăng ×2.5 và từ 50 → 100 RPS **giảm** (109 → 72) trong khi p50 tăng lên 302 ms và p95 vọt lên 2340 ms: app chạy 1 process uvicorn, CPU cho JSON/log/metrics và client load test cùng chạy trên một máy đã bão hoà → request phải xếp hàng (queueing). Theo Little's Law, khi throughput không tăng nữa mà concurrency vẫn tăng thì latency phải tăng. Điểm "gãy" ở đâu đó giữa 50 và 100 concurrent → muốn chịu 100 concurrent phải scale ngang (nhiều worker/instance).

### 2.2 Tail latency

`--requests 300 --concurrency 20`, khởi động lại v2 với từng giá trị. Nguồn: `reports/load_v2_slow_{0,0.03,0.1}.json`.

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 189.1 | 216.8 | 228.2 |
| 0.03 (mặc định) | 239.2 | 221.0 | 1694.9 |
| 0.1 | 324.2 | 1680.3 | 1708.2 |

**Nhận xét:** Mỗi request "slow" cộng thêm 1500 ms. Với 3 % request chậm, avg chỉ tăng 26 % (189 → 239 ms) và p95 gần như không đổi, nhưng **p99 tăng ×7.4** (228 → 1695 ms) vì 3 % > 1 % nên p99 rơi đúng vào nhóm request chậm. Lên 10 % thì cả p95 cũng nhảy lên 1680 ms (10 % > 5 %), trong khi avg mới tăng 71 %. Percentile cao (p99, rồi p95) là chỉ số nhạy nhất với tail latency. SLO không nên đặt theo average vì average "pha loãng" vài request rất chậm vào số đông request nhanh: 3 % user chờ ~1.7 s vẫn cho avg đẹp 239 ms. User thì cảm nhận từng request, và một phiên chat nhiều lượt gần như chắc chắn dính ít nhất 1 request ở tail.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Golden dataset 23 câu. Nguồn: `reports/eval_v1.json`, `reports/eval_v2.json`, `reports/eval_v2_fixed.json`.

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.35 % (1/23) | 91.3 % (21/23) | 100 % (23/23) |
| Avg tokens / câu | 56.5 | 109.1 | 115.4 |
| Tổng cost (USD) | 0.000396 | 0.000762 | 0.000806 |
| Cost / câu đúng (USD) | 0.00039555 | 0.00003627 | 0.00003504 |
| Latency p95 (ms) | 181.0 | 215.9 | 219.5 |
| Quality gate | FAIL (ngưỡng 80 %) | PASS (ngưỡng 80 %, 0 regression so với v1) | PASS (ngưỡng 100 %, 0 regression so với v2) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| security-02 ("JWT khác gì API key?") | `token`, `hết hạn`, `chữ ký` | Thêm tài liệu keyword `["jwt", "json web token"]` vào `KNOWLEDGE_BASE`: so sánh API key tĩnh với JWT có claims, thời điểm hết hạn và chữ ký số |
| scaling-03 ("Kubernetes HPA scale dựa trên chỉ số nào?") | `cpu`, `memory`, `custom metrics` | Thêm tài liệu keyword `["hpa", "kubernetes", "autoscal"]`: HPA scale số pod theo CPU, memory hoặc custom metrics (RPS, queue length…) |

Sửa ở cả `develop/utils/mock_llm.py` và `production/utils/mock_llm.py`. Eval cuối: `Câu được cải thiện: 2`, `Câu bị regression: 0`, exit code 0.

**Quality gate trong CI:** `.github/workflows/eval.yml` chạy agent v2 rồi `python eval/run_eval.py --min-accuracy 0.85`. `run_eval.py` trả **exit code 1** khi accuracy dưới ngưỡng hoặc có regression so với `--baseline` (đã kiểm: v1 → exit 1, v2 → exit 0), nên step fail → job fail → đặt job này là *required status check* trong branch protection thì PR không merge được.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:** v2 có bước retrieval nên prompt dài gấp đôi (56.5 → 109.1 token/câu), cost tổng tăng 92 % và p95 tăng ~35 ms (retrieval ~20 ms + LLM xử lý prompt dài hơn). Đổi lại accuracy tăng từ 4 % lên 91 %. Nếu chỉ nhìn "cost / câu" thì v2 đắt hơn, nhưng **cost / câu đúng** giảm ~11 lần (0.000396 → 0.000036 USD) vì v1 tốn tiền cho câu trả lời vô dụng. Sau khi sửa KB, token tăng thêm 6 %, nhưng cost / câu đúng còn giảm tiếp. Latency vẫn nằm xa dưới SLO 500 ms → v2 thắng rõ.

---

## 4. Observability stack (production)

Stack chạy bằng `docker compose -p k5-day14-observability ...` (Prometheus, Grafana, Jaeger, Nginx, Locust).

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải: `screenshots/grafana-dashboard.png`, chụp đúng điều kiện Exercise 7.4: 2 instance, Locust **30 user / ramp up 5**. Số đọc được: 18.6 req/s, error 1.07 %, p95 294.3 ms, in-flight 8, LLM cost 1h $0.1231, không alert nào firing
- [x] Một trace chậm trong Jaeger: `screenshots/jaeger-slow-trace.png`
- [x] Một trace lỗi trong Jaeger: `screenshots/jaeger-error-trace.png` (POST /ask 503, span `chat mock-llm-small` có `error.type=upstream_unavailable`, mở rộng event `exception` thấy `exception.message`, `exception.stacktrace`, `exception.type = utils.mock_llm.LLMError`)
- [x] Trang Alerts của Prometheus: `screenshots/prometheus-alert-firing.png` (`AgentHighErrorRate` và `AgentInstanceDown` cùng **FIRING**)

**Exercise 7.4: trả lời câu hỏi** (số đọc từ ảnh Grafana và query Prometheus cùng lúc chụp: 30 user, 2 instance)

1. **p95 = 294 ms, avg = 242 ms, p99 = 1862 ms.** p95 và avg gần nhau nên ~95 % request đồng đều quanh ~200–300 ms. Còn p99 gấp ~7.7 lần avg là do ~3 % request bị chậm thêm 1500 ms (`MOCK_SLOW_RATE=0.03`, tail latency): nhìn avg sẽ không thấy nhóm này. Error rate 1.07 % (cam) cũng do lỗi giả lập `MOCK_ERROR_RATE=0.01`, vẫn dưới SLO 2 %.
2. **Có chia đều.** Panel "Requests/s theo instance" có 2 đường gần trùng nhau: 172.18.0.4 = 9.29 req/s, 172.18.0.6 = 9.31 req/s, vì Nginx `upstream` mặc định round-robin.
3. **Input tokens/s (~1432) lớn hơn output tokens/s (~752)** vì agent v2 nhét câu hỏi + system prompt + tài liệu retrieval vào prompt, còn câu trả lời ngắn. Log `llm_call` cho thấy điển hình `input_tokens=95, output_tokens=55`. Nhưng output token đắt gấp 4 lần input (0.0006 so với 0.00015 USD/1K), nên cần theo dõi cả hai.
4. `curl http://localhost:8080/metrics` trả về **404 Not Found** của Nginx. Lý do là `nginx.conf` có `location = /metrics { return 404; }`: metrics để Prometheus scrape trực tiếp từng agent trong mạng nội bộ `obs_net`, không mở ra ngoài, vì nó lộ route, lưu lượng và thông tin hệ thống. Thêm nữa, qua load balancer mỗi lần sẽ trúng một instance khác nhau nên số liệu cũng vô nghĩa.

Unit test alert rules: `promtool test rules /p/alert_rules_test.yml` → `SUCCESS`.

### 4.2 Thí nghiệm "phá hệ thống"

Locust giữ 30 user, 3 agent. Mốc thời gian (UTC) lấy từ script poll `GET /api/v1/alerts` mỗi 5 s.

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` (recreate agent lúc 09:23:39) | `AgentHighErrorRate` (giá trị 21.1 %) | **~82 s**: pending 09:24:01 (activeAt 09:23:57), firing 09:25:01 | Error rate (stat đỏ), "Requests/s theo status code" (503 tăng), "LLM calls theo kết quả" (error tăng) |
| B | `MOCK_SLOW_RATE=0.3` | Không chạy (chọn A và D) | — | (dự kiến: Latency p50/p95/p99, `AgentHighLatencyP95` sau ~2 phút) |
| C | `LLM_MODEL=mock-llm-large` | Không chạy riêng. Có ghi nhận: khi Locust 100 user với model small, `LLMCostBurnRateHigh` đã **firing** lúc 09:23:06 (cost burn rate ~$6/giờ > $2/giờ) | — | Cost burn rate (USD/giờ) |
| D | `docker pause k5-day14-observability-agent-1` (09:25:02) | `AgentInstanceDown` (instance 172.18.0.6:8000, `up=0`) | **~44 s**: pending 09:25:16 (activeAt 09:25:12), firing 09:25:46 | Instances up (3 → 2). Error rate của agent không đỏ thêm; Locust ghi 28 lỗi 504 Gateway Time-out và 227 lỗi 502 từ Nginx |
| E | `AGENT_VERSION=v1` | Không có (lý thuyết + đã đo ở mục 3) | — | Retrieval hit ratio, Tokens/s, bảng "Phiên bản đang chạy" |

Phân tích:
- **A:** thời gian tới firing = thời gian `rate(...[1m])` vượt 5 % (~1 lần scrape 5 s + eval 15 s) cộng `for: 1m`. `for` giúp tránh báo động giả khi lỗi chỉ thoáng qua, đổi lại chậm hơn khoảng 1 phút.
- **D:** dùng `pause` chứ không `stop`. Container bị pause vẫn còn trong DNS nhưng không trả lời scrape → `up == 0`. Còn container bị stop sẽ biến khỏi service discovery, target biến mất chứ không "down". `for: 30s` ngắn hơn nên firing nhanh hơn A. Lỗi 502/504 xảy ra ở Nginx (upstream treo, chờ tới timeout), request chưa từng tới agent nên **metric của agent không thấy**. Vì vậy cần giám sát thêm ở tầng load balancer hoặc synthetic check từ bên ngoài.
- Khi recreate container để áp dụng env mới, `AgentInstanceDown` chuyển sang pending trong vài giây rồi tự hết. `for: 30s` lọc đúng trường hợp này, không gây báo động giả khi rolling restart.

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Lỗi chất lượng không làm hạ tầng đỏ: latency, error rate, up đều bình thường (v1 còn nhanh và rẻ hơn). Muốn bắt được phải đo **chất lượng**:
1. **Quality gate trước deploy:** chạy eval golden dataset trong CI/CD (exit code 1 chặn merge/deploy). Mục 3 cho thấy v1 sẽ bị chặn vì accuracy 4 %.
2. **Online eval sau deploy:** định kỳ chạy golden dataset vào production (synthetic probe), lấy mẫu traffic thật chấm bằng LLM-as-judge, xuất metric `agent_eval_accuracy` rồi alert khi giảm.
3. **Metric proxy:** retrieval hit ratio giảm về 0, tokens/câu giảm đột ngột, `agent_info{version}` đổi. Alert khi hit ratio < ngưỡng.
4. **Tín hiệu từ người dùng:** thumbs-down, tỉ lệ hỏi lại, escalation.

### 4.3 Debug bằng trace

Trace chậm nhất trong lúc chạy 100 user / 3 instance:

- `trace_id`: `9fdac38321af69fa20aba44a17f0d4a6`
- Tổng thời gian: **1718.7 ms** (span gốc `POST /ask`)
- Span chiếm nhiều thời gian nhất: **`chat mock-llm-small`** (1697.4 ms, **98.8 %**). `agent.retrieve_context` chỉ 19.2 ms (1.1 %). Đây là request bị "slow" của LLM (+1500 ms), không phải lỗi của retrieval hay của app → muốn giảm phải xử lý ở tầng LLM (timeout + retry/hedging, model fallback, cache).
- Dòng log tương ứng (`docker compose -p k5-day14-observability logs agent | grep 9fdac38321af69fa20aba44a17f0d4a6`):

```json
{"ts": "2026-11-26T09:19:45.734647+00:00", "level": "INFO", "service": "observable-agent", "instance": "86a51d79cfd7", "event": "llm_call", "trace_id": "9fdac38321af69fa20aba44a17f0d4a6", "span_id": "ef0aa56da17a80a3", "request_id": "0cfb3796d7b0", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1698.2}
{"ts": "2026-11-26T09:19:45.735118+00:00", "level": "INFO", "service": "observable-agent", "instance": "86a51d79cfd7", "event": "http_request", "trace_id": "9fdac38321af69fa20aba44a17f0d4a6", "span_id": "ef0aa56da17a80a3", "request_id": "0cfb3796d7b0", "method": "POST", "route": "/ask", "status": 200, "ms": 1718.1}
```

Trace lỗi (ảnh `jaeger-error-trace.png`, chạy với `MOCK_ERROR_RATE=0.3` để dễ bắt lỗi): `trace_id` `04d46e119b0be831ab26c30476eb7878`, tổng 104 ms, span `chat mock-llm-small` 87.7 ms mang status error. Event `exception` (tại 103.13 ms) có `exception.type = utils.mock_llm.LLMError`, `exception.message = Upstream LLM error: 503 Service Unavailable (mock)` và stacktrace trỏ tới `app/main.py` dòng 153 (`run_agent` → `mock_llm.generate`). Hai dòng log cùng `trace_id`:

```json
{"ts": "2026-11-26T10:02:16.281849+00:00", "level": "INFO", "service": "observable-agent", "instance": "0606752f2999", "event": "llm_error", "trace_id": "04d46e119b0be831ab26c30476eb7878", "span_id": "695179617cef46b1", "request_id": "99292ac570b2", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
{"ts": "2026-11-26T10:02:16.282149+00:00", "level": "INFO", "service": "observable-agent", "instance": "0606752f2999", "event": "http_request", "trace_id": "04d46e119b0be831ab26c30476eb7878", "span_id": "695179617cef46b1", "request_id": "99292ac570b2", "method": "POST", "route": "/ask", "status": 503, "ms": 103.6}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu của dòng `POST /ask`. Nguồn: `benchmark-results/scale_1_stats.csv` và `scale_3_stats.csv`.

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 59.88 | 190 | 250 | 1700 | 89 / 7132 (1.25 %) |
| 3 | 59.98 | 190 | 220 | 1700 | 81 / 7144 (1.13 %) |

(Aggregated, gồm cả `/health`: 1 instance 65.80 RPS, p95 240 ms; 3 instance 66.37 RPS, p95 220 ms.)

**Giải thích kết quả:** Scale 1 → 3 **chỉ cải thiện p95 một chút** (250 → 220 ms, −12 %), RPS gần như giữ nguyên, p50 và p99 không đổi. Lý do:
- **RPS bị giới hạn bởi tải sinh ra chứ không phải bởi server.** Locust có `wait_time = between(0.5, 2)`, nên 100 user chỉ gửi tối đa ≈ 100 / (0.19 s + 1.25 s) ≈ 69 req/s. Một instance đã phục vụ đủ, thêm instance không tạo thêm request.
- **Latency bị chi phối bởi LLM** (mock 120 ms × hệ số + jitter, cộng 1500 ms cho 3 % request slow). Đây là thời gian *chờ* upstream, scale ngang không rút ngắn được. Vì vậy p50 ~190 ms và p99 ~1700 ms giữ nguyên.
- Phần p95 giảm được là do bớt queueing trên một container bị giới hạn `cpus: 0.5`.
- Nút thắt là **LLM upstream** (latency và tỉ lệ slow/lỗi) và **phía load generator**. Muốn thấy scale có tác dụng phải tăng tải tới khi 1 instance bão hoà (nhiều user hơn, `wait_time` thấp hơn, như mức concurrency 100 ở mục 2.1). Muốn giảm tail latency thì xử lý ở LLM: timeout ngắn + retry, hedged request, cache câu hỏi lặp lại.

---

## 6. Kết luận

- 3 điều học được về benchmark & observability:
  1. **Percentile quan trọng hơn trung bình:** 3 % request chậm làm p99 tăng ×7 trong khi avg chỉ tăng 26 %. SLO và alert phải đặt theo p95/p99.
  2. **Metric hạ tầng không thấy lỗi chất lượng:** agent v1 nhanh hơn, rẻ hơn, không lỗi 5xx nhưng chỉ đúng 4 %. Cần eval (golden dataset, quality gate bằng exit code) song song với monitoring, và so sánh bằng **cost / câu đúng**.
  3. **Mỗi service chỉ đo được những gì nó nhìn thấy:** khi pause 1 instance, lỗi 502/504 nằm ở Nginx, không có trong metric của agent. Trace + log JSON có chung `trace_id` giúp đi từ một dòng log tới đúng span gây chậm (98.8 % thời gian nằm ở LLM call).
- Nếu đưa agent này lên production thật, sẽ thêm:
  - Metric và alert ở **tầng Nginx/LB** (tỉ lệ 5xx, upstream timeout) và **synthetic check** từ bên ngoài.
  - **Online eval accuracy** và **retrieval hit ratio** có alert, để bắt regression kiểu thí nghiệm E.
  - **Alert theo error budget burn rate** (multi-window: 1 h/5 m và 6 h/30 m) thay cho ngưỡng cố định, để vừa nhạy vừa ít báo động giả.
  - Cost theo user/tenant (qua log, không qua label để tránh cardinality), budget hằng ngày, `agent_question_length_chars` (đã thêm ở Exercise 7.1) để phát hiện prompt bất thường.
  - Alertmanager gửi Slack/PagerDuty, kèm runbook cho từng alert.
