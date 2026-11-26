# Day 14 Lab — Mission Answers

**Lớp:** K5-L3B · **Ngày làm:** 2026-11-26

> Mọi output dưới đây là output thật khi chạy trên máy làm bài (Linux, Python 3.13, Docker 29.9). Token và key đã được che.

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found (`01-localhost-vs-production/develop/app.py`)

1. **Hardcode secret trong code** (dòng 17–18): `OPENAI_API_KEY = "sk-hardcoded-..."` và `DATABASE_URL = "postgresql://admin:password123@..."`. Push lên GitHub là lộ key và mật khẩu DB ngay, và xoá file cũng không xoá được khỏi lịch sử commit.
2. **Log ra secret** (dòng 34): `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")`. Log thường được gửi lên hệ thống log tập trung nên secret bị phát tán thêm. Khi chạy, log in đúng dòng `[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this`.
3. **Dùng `print()` thay vì logging có cấu trúc** (dòng 33, 38): không có level, timestamp hay request_id, không parse được trong Loki/Datadog, cũng không tắt được log debug ở production.
4. **Config cứng, không đọc từ env** (dòng 21–22): `DEBUG = True`, `MAX_TOKENS = 500` cố định. Muốn đổi giữa dev, staging, prod phải sửa code (vi phạm 12-Factor III, Config).
5. **Không có health check** (dòng 42): `GET /health` trả **404** khi chạy thử, nên platform không biết agent đã chết để restart, load balancer cũng không biết để ngừng route traffic.
6. **Bind `localhost`** (dòng 51): `host="localhost"` chỉ nhận kết nối trong máy. Chạy trong container thì từ ngoài không gọi được.
7. **Port cố định** (dòng 52): `port=8000`. Railway, Render, Cloud Run inject `PORT` qua env, nên cứng port sẽ làm health check của platform fail.
8. **`reload=True` khi chạy thật** (dòng 53): auto-reload là tính năng dev. Nó tốn CPU vì watch file, có thể restart ngẫu nhiên và không dùng được nhiều worker.
9. **Không xử lý shutdown**: không có lifespan hay SIGTERM handler, không đóng kết nối, không chờ request đang chạy xong.
10. **Không validate input**: `question: str` nhận qua query string, không giới hạn độ dài và không có kiểu dữ liệu rõ ràng.

### Exercise 1.2: Chạy basic version

```text
$ curl -i -X POST "http://localhost:8000/ask?question=Hello"
HTTP/1.1 200 OK
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}

$ curl -o /dev/null -w '%{http_code}\n' http://localhost:8000/health
404
$ curl -o /dev/null -w '%{http_code}\n' -X POST localhost:8000/ask -H 'Content-Type: application/json' -d '{"question":"Hello"}'
422          # bản develop nhận question qua query, không nhận JSON

# log của server:
Starting agent on localhost:8000...
INFO:     Uvicorn running on http://localhost:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [9456] using WatchFiles
[DEBUG] Got question: Hello
[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this
```

Nó chạy được, nhưng chưa production-ready: lộ secret trong log, không có `/health`, chỉ nghe ở `localhost` và có bật reloader.

### Exercise 1.3: Comparison table

Bản production (`production/app.py` + `config.py`) chạy thử:

```text
$ curl -X POST localhost:8000/ask -H 'Content-Type: application/json' -d '{"question":"Hello"}'
{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","model":"gpt-4o-mini"}
$ curl localhost:8000/health
{"status":"ok","uptime_seconds":3.8,"version":"1.0.0","environment":"development","timestamp":"2026-11-26T09:29:16.917075+00:00"}
$ curl localhost:8000/ready
{"ready":true}
$ kill -TERM <pid>
INFO:     Shutting down
INFO:     Waiting for application shutdown.
INFO:     Application shutdown complete.
```

| Feature | Develop | Production | Tại sao quan trọng? |
|---------|---------|------------|---------------------|
| Config | Hardcode trong code (`DEBUG = True`, key, DB URL) | `config.py` đọc env (`os.getenv("PORT", "8000")`, `AGENT_API_KEY`…), `validate()` fail fast nếu thiếu `AGENT_API_KEY` khi `ENVIRONMENT=production` | Một image chạy được ở mọi môi trường chỉ bằng cách đổi env; secret không nằm trong git; thiếu config thì crash ngay lúc start thay vì lỗi lúc đang phục vụ user |
| Secrets | Ghi thẳng trong code và in ra log | Lấy từ env/secret manager, log chỉ ghi `question_length`, không ghi key | Tránh lộ key qua repo hoặc hệ thống log |
| Health check | Không có (`/health` → 404) | `/health` (liveness: uptime, version) và `/ready` (readiness: 503 khi chưa sẵn sàng) | Platform dùng `/health` để restart container chết, LB dùng `/ready` để chỉ gửi traffic vào instance đã sẵn sàng |
| Logging | `print()` text tự do | `logging` với format JSON (`{"time":..,"level":..,"msg":..}`) và event có cấu trúc | Máy parse được, lọc và tìm theo field, có level để tắt debug ở prod |
| Shutdown | Đột ngột, không có hook | `lifespan` (startup set `is_ready`, shutdown set `is_ready=False` rồi dọn dẹp) và handler SIGTERM; uvicorn chờ request đang chạy | Khi platform deploy hoặc scale down không cắt ngang request của user |
| Host/Port | `localhost:8000` cố định | `HOST=0.0.0.0`, `PORT` từ env | Chạy được trong container và trên PaaS (PORT do platform cấp) |
| Reload/Debug | `reload=True` luôn bật | `reload=settings.debug` (chỉ bật khi `DEBUG=true`) | Không tốn tài nguyên, không restart bất ngờ ở production |
| CORS | Không cấu hình | `ALLOWED_ORIGINS` từ env | Chỉ cho các origin được phép gọi API từ trình duyệt |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions (`02-docker/develop/Dockerfile`)

1. **Base image:** `python:3.11`, bản Python đầy đủ (Debian kèm compiler và nhiều tool), nên rất nặng.
2. **Working directory:** `/app` (`WORKDIR /app`). Mọi lệnh `COPY`/`RUN`/`CMD` sau đó chạy trong thư mục này.
3. **Vì sao COPY requirements.txt trước:** Docker cache theo từng layer. Copy `requirements.txt` rồi `pip install` trước, sau đó mới `COPY app.py`. Khi chỉ sửa code, layer cài dependencies vẫn dùng lại cache và build chỉ mất vài giây. Nếu `COPY . .` trước thì mỗi lần sửa code đều phải cài lại toàn bộ dependencies.
4. **CMD vs ENTRYPOINT:** `ENTRYPOINT` là chương trình cố định của container. `CMD` là lệnh hoặc tham số mặc định, bị ghi đè khi `docker run image <lệnh khác>`. Nếu có cả hai thì `CMD` thành tham số mặc định của `ENTRYPOINT`. Ở đây chỉ dùng `CMD ["python", "app.py"]` (exec form, nên python là PID 1 và nhận SIGTERM trực tiếp), dễ ghi đè khi debug, ví dụ `docker run -it my-agent:develop bash`.

### Exercise 2.2: Build và run

```text
$ docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
$ docker run -p 8000:8000 my-agent:develop
$ curl -X POST "http://localhost:8000/ask?question=What%20is%20Docker%3F"
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
$ curl localhost:8000/health
{"status":"ok","uptime_seconds":3.9,"container":true}
$ docker exec <container> whoami
root                      # bản develop chạy bằng root
```

### Exercise 2.3: Multi-stage build và image size comparison

`02-docker/production/Dockerfile`:
- **Stage 1 (`builder`, `python:3.11-slim`):** cài build tool (`gcc`, `libpq-dev`) và `pip install --user -r requirements.txt` vào `/root/.local`. Stage này không được deploy.
- **Stage 2 (`runtime`, `python:3.11-slim`):** tạo user non-root `appuser`, chỉ `COPY --from=builder /root/.local` (các package đã cài) cùng `main.py` và `utils/`, có `HEALTHCHECK`, chạy `uvicorn ... --workers 2`.
- **Vì sao nhỏ hơn:** image cuối không chứa compiler, header, apt cache hay pip cache, và dùng base `slim` (~120 MB) thay vì `python:3.11` full (~1 GB). Bề mặt tấn công cũng nhỏ hơn và không chạy bằng root.

```text
$ docker images my-agent
IMAGE               ID             DISK USAGE   CONTENT SIZE
my-agent:advanced   d9d0c041f7bc        240MB         57.4MB
my-agent:develop    826fc1fe1079       1.67GB          426MB
```

- Develop: **1.67 GB** disk usage (426 MB content, nén)
- Production: **240 MB** disk usage (57.4 MB content)
- Difference: nhỏ hơn **85.6 %** theo disk usage ((1668 − 240) / 1668), **86.5 %** theo content size ((426 − 57.4) / 426)

Container production chạy bằng `appuser` (`docker exec ... whoami` → `appuser`), `/health` trả `{"status":"ok",...,"version":"2.0.0"}`, và `/ask` nhận JSON body.

> Ghi chú môi trường: máy làm bài đi Internet qua proxy, chỉ cho HTTPS CONNECT và chặn `deb.debian.org`. Vì vậy khi build tôi dùng một Dockerfile tạm (không commit) cài thêm CA của proxy cho `pip` và bỏ bước `apt-get install gcc libpq-dev` trong stage builder. Các gói trong `requirements.txt` đều có wheel sẵn nên không cần gcc. Stage runtime giữ nguyên nên kích thước image production không bị ảnh hưởng. Riêng image develop (single-stage) có thêm file CA 188 kB.

### Exercise 2.4: Docker Compose stack

```text
                 :80 / :443
   client ───────────────▶ nginx (nginx:alpine, reverse proxy / LB)
                              │  proxy_pass http://agent_backend  (upstream agent:8000)
                              ▼
                        agent (build từ 02-docker/production/Dockerfile, target runtime)
                         │                     │
            REDIS_URL=redis://redis:6379/0   QDRANT_URL=http://qdrant:6333
                         ▼                     ▼
              redis (redis:7-alpine,     qdrant (qdrant/qdrant:v1.9.0,
              cache/session, LRU 256MB)  vector DB)
              volume redis_data          volume qdrant_data

   Tất cả trong network bridge "internal"; chỉ nginx publish cổng ra host.
```

- Service được start: `redis`, `qdrant` (có healthcheck) → `agent` (chờ `depends_on: condition: service_healthy`) → `nginx`.
- Cách giao tiếp: các container gọi nhau bằng **tên service** qua DNS nội bộ của network `internal` (`agent:8000`, `redis:6379`, `qdrant:6333`). Chỉ Nginx mở cổng 80/443 ra ngoài. Agent, Redis và Qdrant không public.

```text
$ docker compose -p k5-day14-docker ps
SERVICE   IMAGE                   STATUS                    PORTS
agent     k5-day14-docker-agent   Up 25 seconds (healthy)   8000/tcp
nginx     nginx:alpine            Up 25 seconds             0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
qdrant    qdrant/qdrant:v1.9.0    Up 35 seconds (healthy)   6333-6334/tcp
redis     redis:7-alpine          Up 35 seconds (healthy)   6379/tcp

$ curl -i http://localhost/health
HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":24.3,"version":"2.0.0","timestamp":"2026-11-26T09:34:56.144822"}

$ curl http://localhost/ask -X POST -H "Content-Type: application/json" -d '{"question": "Explain microservices"}'
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

---

## Part 3: Cloud Deployment

### Exercise 3.1 / 3.2: Deploy agent Part 6

> ⏳ **Chưa deploy.** Cần tài khoản Railway/Render của sinh viên. URL, ảnh và output của 4 lệnh tự kiểm sẽ điền vào đây và vào `DEPLOYMENT.md` sau khi deploy.

- Platform: _(Railway hoặc Render)_
- URL: _(điền sau khi deploy)_
- Screenshot: `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png`

### So sánh `railway.toml` và `render.yaml` (trong `06-lab-complete/`)

| Khía cạnh | `railway.toml` | `render.yaml` |
|---|---|---|
| Phạm vi | Chỉ cấu hình **một service** (cách build và deploy) | **Blueprint, Infrastructure-as-Code** cho nhiều tài nguyên: service web `day14-agent` và Redis `day14-redis` (type `keyvalue`) |
| Build | `builder = "DOCKERFILE"`, `dockerfilePath` | `runtime: docker`, `rootDir`, `dockerfilePath`, `dockerContext` (vì file nằm trong thư mục con `06-lab-complete/`) |
| Health check | `healthcheckPath = "/health"`, `healthcheckTimeout = 60` | `healthCheckPath: /health` |
| Restart | `restartPolicyType = "ON_FAILURE"`, tối đa 3 lần | Render tự quản lý, không khai báo |
| Biến môi trường | **Không** khai báo trong file; đặt bằng `railway variables --set` hoặc dashboard | Khai báo ngay trong file: giá trị thường (`RATE_LIMIT_PER_MINUTE`…), secret do Render tự sinh (`AGENT_API_KEY: generateValue: true`), và tham chiếu tài nguyên khác (`REDIS_URL: fromService ... connectionString`) |
| Redis | Thêm plugin Redis trong project rồi gán `REDIS_URL=${{Redis.REDIS_URL}}` thủ công | Tạo Redis cùng lúc với service, nối `REDIS_URL` tự động |
| Plan/region | Chọn trên dashboard | `plan: free`, `region: singapore` ghi trong file |

**Vì sao khác:** Railway thiên về CLI và dashboard. File toml chỉ mô tả cách build/deploy của một service, còn tài nguyên và biến môi trường quản lý ngoài file. Render Blueprint mô tả toàn bộ hạ tầng trong một file YAML có thể review và tái tạo (GitOps). Vì vậy nó phải có cú pháp riêng cho secret (`generateValue`, `sync: false`) để không ghi giá trị secret vào git, và cú pháp tham chiếu giữa các service (`fromService`).

### Exercise 3.3: Cloud Run CI/CD pipeline (`03-cloud-deployment/production-cloud-run/`)

`cloudbuild.yaml` chạy 4 bước nối tiếp nhau (`waitFor`), mỗi lần push lên GitHub (Cloud Build trigger):
1. **test:** trong image `python:3.11-slim`, cài requirements + pytest rồi chạy `pytest tests/`. Fail thì dừng pipeline, không build.
2. **build:** `docker build` với 2 tag `gcr.io/$PROJECT_ID/ai-agent:$COMMIT_SHA` và `:latest`, dùng `--cache-from :latest` để tận dụng layer cache.
3. **push:** đẩy mọi tag lên Container Registry.
4. **deploy:** `gcloud run deploy ai-agent` với image theo `$COMMIT_SHA` (truy vết và rollback được), region `asia-southeast1`, `min-instances=1` (tránh cold start), `max-instances=10`, 512Mi/1 CPU, timeout 60s, `OPENAI_API_KEY` lấy từ **Secret Manager** (`--set-secrets`).

`service.yaml` là khai báo Knative tương đương: autoscale 1–10 instance, `containerConcurrency: 80`, secret qua `secretKeyRef`, `livenessProbe` gọi `/health` và `startupProbe` gọi `/ready`.

---

## Part 4: API Security

### Exercise 4.1: API Key authentication (`04-api-gateway/develop/app.py`)

- **Check ở đâu:** dependency `verify_api_key()` đọc header `X-API-Key` (`APIKeyHeader(name="X-API-Key", auto_error=False)`), gắn vào endpoint bằng `Depends(verify_api_key)`. Key đúng lấy từ env `AGENT_API_KEY`.
- **Sai key thì sao:** thiếu header → **401** `Missing API key`; có header nhưng sai → **403** `Invalid API key.` Request bị chặn trước khi gọi LLM.
- **Rotate key:** đổi env `AGENT_API_KEY` rồi restart hoặc redeploy, không cần sửa code. Muốn không downtime thì cho phép tạm thời 2 key (cũ + mới, ví dụ `AGENT_API_KEYS=old,new`), báo client chuyển sang key mới, sau đó gỡ key cũ.

```text
$ AGENT_API_KEY=secret-key-123 python app.py

$ curl -i http://localhost:8000/ask -X POST -H "Content-Type: application/json" -d '{"question": "Hello"}'
HTTP/1.1 401 Unauthorized
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

$ curl -i http://localhost:8000/ask -X POST -H "X-API-Key: wrong" -H "Content-Type: application/json" -d '{"question": "Hello"}'
HTTP/1.1 403 Forbidden
{"detail":"Invalid API key."}

$ curl -i http://localhost:8000/ask -X POST -H "X-API-Key: secret-key-123" -H "Content-Type: application/json" -d '{"question": "Hello"}'
HTTP/1.1 200 OK
{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

### Exercise 4.2: JWT authentication (`04-api-gateway/production/`)

Flow: `POST /auth/token` (username/password) → server ký JWT HS256 với `JWT_SECRET`, payload gồm `sub`, `role`, `iat`, `exp` (60 phút) → client gửi `Authorization: Bearer <token>` → `verify_token()` kiểm chữ ký và hạn, lấy `username`/`role` từ payload mà **không cần tra DB**.

```text
$ curl -X POST localhost:8000/auth/token -H "Content-Type: application/json" -d '{"username": "student", "password": "demo123"}'
{"access_token": "eyJhbGciOiJI...<redacted>", "token_type": "bearer", "expires_in_minutes": 60, ...}

$ curl -i localhost:8000/ask -X POST -H "Content-Type: application/json" -d '{"question": "Explain JWT"}'
HTTP/1.1 401 Unauthorized
{"detail":"Authentication required. Include: Authorization: Bearer <token>"}

$ curl -i localhost:8000/ask -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"question": "Explain JWT"}'
HTTP/1.1 200 OK
{"question":"Explain JWT","answer":"Tôi là AI agent được deploy lên cloud. ...","usage":{"requests_remaining":9,...}}
```

### Exercise 4.3: Rate limiting

- **Algorithm:** **sliding window log**. Mỗi user có một `deque` timestamp; mỗi request bỏ các timestamp cũ hơn 60 s rồi đếm. Đủ `max_requests` thì trả 429 kèm `Retry-After`.
- **Limit:** user `10 req/phút` (`rate_limiter_user`), admin `100 req/phút` (`rate_limiter_admin`).
- **Bypass cho admin:** `app.py` chọn limiter theo `role` trong JWT (`limiter = rate_limiter_admin if role == "admin" else rate_limiter_user`), nên tài khoản `teacher` (role admin) có hạn mức cao hơn. Muốn bỏ hẳn giới hạn thì bỏ qua `check()` khi `role == "admin"`.
- **Hạn chế:** state nằm trong RAM của process, nên nhiều instance sẽ mỗi cái đếm riêng. Part 6 đã chuyển sang Redis sorted set.

Vòng lặp 20 request bằng token `student` (request đầu tiên ở 4.2 đã dùng 1 lượt):

```text
 1 HTTP/1.1 200 OK {"question":"Test 1",...,"usage":{"requests_remaining":8,...}}
 2 HTTP/1.1 200 OK {"question":"Test 2",...,"usage":{"requests_remaining":7,...}}
 ...
 9 HTTP/1.1 200 OK {"question":"Test 9",...,"usage":{"requests_remaining":0,...}}
10 HTTP/1.1 429 Too Many Requests {"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
 ...
20 HTTP/1.1 429 Too Many Requests {"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}

$ curl -i ... (request thứ 21)
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795685798
retry-after: 59
```

### Exercise 4.4: Cost guard implementation

`04-api-gateway/production/cost_guard.py` (bản demo, in-memory): mỗi user một `UsageRecord` theo ngày (input/output token → USD theo giá gpt-4o-mini). `check_budget()` chạy **trước** khi gọi LLM: vượt budget toàn hệ thống ($10/ngày) → **503**; user vượt $1/ngày → **402 Payment Required**; dùng tới 80 % thì log warning. `record_usage()` cộng chi phí **sau** khi gọi. `GET /me/usage` khi chạy thử: `{"requests":10,"input_tokens":40,"output_tokens":296,"cost_usd":0.000184,"budget_usd":1.0,...}`.

Cách tôi làm trong agent Part 6 (`06-lab-complete/app/cost_guard.py`), **state trong Redis** để mọi instance dùng chung và không mất khi restart:

```python
def _keys():
    now = datetime.now(timezone.utc)
    return f"cost:daily:{now:%Y-%m-%d}", f"cost:monthly:{now:%Y-%m}"   # key theo ngày/tháng → tự "reset" đầu kỳ

def check_budget():                       # gọi TRƯỚC khi gọi LLM
    daily, monthly = r.mget(*_keys())
    if float(daily or 0)  >= settings.daily_budget_usd:   raise HTTPException(402, "Daily budget exceeded")
    if float(monthly or 0) >= settings.monthly_budget_usd: raise HTTPException(402, "Monthly budget exceeded")

def record_cost(input_tokens, output_tokens):   # gọi SAU khi gọi LLM
    cost = input_tokens/1000*0.00015 + output_tokens/1000*0.0006
    pipe = r.pipeline(transaction=True)          # MULTI/EXEC: cộng dồn nguyên tử
    pipe.incrbyfloat(daily_key, cost);   pipe.expire(daily_key, 2*24*3600)
    pipe.incrbyfloat(monthly_key, cost); pipe.expire(monthly_key, 32*24*3600)
    pipe.execute()
```

- Budget (`DAILY_BUDGET_USD`, `MONTHLY_BUDGET_USD` = $10/tháng) đọc từ env.
- Reset đầu tháng không cần cron: key mang tên tháng (`cost:monthly:2026-11`), sang tháng mới là key mới; `EXPIRE` 32 ngày tự dọn key cũ.
- `INCRBYFLOAT` trong transaction nên nhiều worker hoặc instance cộng cùng lúc không bị mất cập nhật.
- `check_production_ready.py` kiểm: đặt budget rất nhỏ → **402** ngay ở request thứ 1.
- **Rate limit vs cost guard:** rate limit bảo vệ *tốc độ* (chống spam hoặc DoS một user), cost guard bảo vệ *tiền* (10 req/phút vẫn có thể đốt nhiều tiền nếu prompt dài hoặc model đắt). Cần cả hai.

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health checks (`05-scaling-reliability/develop/app.py`)

- `/health` (**liveness**): process còn sống thì trả 200, kèm uptime và mức dùng memory. Không phụ thuộc DB/Redis, vì dependency chết mà restart agent cũng không giải quyết được gì.
- `/ready` (**readiness**): trả 503 khi chưa khởi động xong hoặc đang shutdown (`_is_ready = False`), trả 200 khi sẵn sàng. LB chỉ route vào instance ready.

```text
$ curl localhost:8000/health
{"status":"ok","uptime_seconds":3.8,"version":"1.0.0","environment":"development",...,"checks":{"memory":{"status":"ok","used_percent":5.1}}}
$ curl localhost:8000/ready
{"ready":true,"in_flight_requests":1}
```

Ở Part 6, `/ready` ping Redis: mất Redis → 503, còn `/health` vẫn 200 (đã kiểm bằng `check_production_ready.py`).

### Exercise 5.2: Graceful shutdown

Uvicorn bắt SIGTERM: ngừng nhận kết nối mới, chờ request đang chạy xong (`timeout_graceful_shutdown=30`), rồi chạy phần shutdown của `lifespan` (`_is_ready=False`, chờ `_in_flight_requests` về 0, đóng kết nối). Handler `handle_sigterm` chỉ log thêm.

Test: gửi request rồi `kill -TERM` ngay sau 0,1 s:

```text
request: {"answer":"Đây là câu trả lời từ AI agent (mock). ..."} [200 in 3.015534s]
exit code của process: 0

INFO:     Shutting down
INFO:     127.0.0.1:57516 - "POST /ask?question=Long%20task HTTP/1.1" 200 OK     ← request vẫn hoàn thành
INFO:     Waiting for application shutdown.
2026-11-26 09:35:59,657 INFO 🔄 Graceful shutdown initiated...
2026-11-26 09:35:59,657 INFO ✅ Shutdown complete
INFO:     Application shutdown complete.
INFO:     Finished server process [11951]
```

Request gửi trước SIGTERM vẫn trả 200, process tự thoát với exit code 0. Trong Docker cần CMD dạng exec (để uvicorn là PID 1 nhận SIGTERM) và thời gian graceful nhỏ hơn timeout của `docker stop` (10 s). Agent Part 6 dùng `--timeout-graceful-shutdown 8`; `docker stop` đo được 0,8 s, exit code 0.

### Exercise 5.3: Stateless design

`05-scaling-reliability/production/app.py` lưu history theo `session_id` trong **Redis** (`REDIS_URL`), không lưu trong dict trong RAM. Lý do: khi scale ra N instance, mỗi instance có RAM riêng. Request 1 vào instance A, request 2 vào instance B thì B không thấy history của A. Instance restart hay bị scale down cũng mất hết. Đưa state ra Redis thì instance nào cũng phục vụ được mọi session, nên scale ngang, rolling deploy và tự restart đều an toàn. Agent Part 6 cũng stateless: rate limit (sorted set) và cost (counter) đều nằm trong Redis.

### Exercise 5.4: Load balancing

```text
$ docker compose -p k5-day14-scaling up -d --build --scale agent=3
NAME                       STATUS
k5-day14-scaling-agent-1   Up 20 seconds (healthy)
k5-day14-scaling-agent-2   Up 20 seconds (healthy)
k5-day14-scaling-agent-3   Up 20 seconds (healthy)
k5-day14-scaling-nginx-1   Up 20 seconds
k5-day14-scaling-redis-1   Up 31 seconds (healthy)

$ for i in 1..6: curl -X POST localhost:8080/chat -d '{"question": "Request i"}'   → served_by
instance-99e303
instance-f3d460
instance-169776
instance-99e303
instance-f3d460
instance-169776
```

Nginx (`upstream` trỏ tới service `agent`, Docker DNS trả về 3 IP) chia **round-robin** đều cho 3 instance.

**Tắt 1 instance:** `docker stop k5-day14-scaling-agent-1` rồi gọi tiếp 4 lượt cùng session. Cả 4 đều 200, do `instance-f3d460` và `instance-169776` phục vụ luân phiên, và history vẫn đủ 10 message. Traffic tự chuyển sang các instance còn sống.

### Exercise 5.5: Test stateless

```text
$ python test_stateless.py
...
Request 4: [instance-99e303]
  Q: How does load balancing work?
Request 5: [instance-f3d460]
  Q: What is Redis used for?
------------------------------------------------------------
Total requests: 5
Instances used: {'instance-f3d460', 'instance-169776', 'instance-99e303'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
  [user]: What is Docker?...
  [assistant]: Container là cách đóng gói app để chạy ở mọi nơi. Build once...
  ...
✅ Session history preserved across all instances via Redis!
```

**Giải thích:** 5 câu trong cùng một session được Nginx chia cho cả 3 instance, nhưng đọc history vẫn thấy đủ 10 message (5 user + 5 assistant) theo đúng thứ tự. Điều đó chứng minh history nằm trong Redis dùng chung chứ không nằm trong RAM của từng instance. Nếu lưu trong RAM thì mỗi instance chỉ thấy phần history của mình.

---

## Part 6: Final Project — output `check_production_ready.py`

Chạy bản đầy đủ (có Docker) trong `06-lab-complete/`:

```text
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

Chi tiết đo được: image **248 MB**; `docker stop` tắt êm (exit code 0, **0.8 s**); SIGTERM lúc đang có request → request vẫn 200; hết budget → 402 ở request thứ 1; mọi dòng log là JSON hợp lệ.

---

## Part 7 (bổ sung): Exercise 7.1

Chi tiết Part 7 nằm trong [`BENCHMARK_REPORT.md`](BENCHMARK_REPORT.md).

1. Ví dụ từ `curl localhost:8002/metrics`:
   - **Counter:** `http_requests_total{method="POST",route="/ask",status="200"} 1.0`, `llm_tokens_total`, `llm_cost_usd_total` (chỉ tăng).
   - **Gauge:** `agent_in_flight_requests 0.0`, `agent_info{model="mock-llm-small",version="v2"} 1.0` (lên xuống được).
   - **Histogram:** `http_request_duration_seconds_bucket{le="0.2",method="POST",route="/ask"} 1.0` cùng `_count` và `_sum` (đếm theo bucket để tính percentile bằng `histogram_quantile`).
2. Nếu label `route` dùng `request.url.path` thật, mỗi URL lạ mà bot quét (`/wp-admin`, `/.env`, `/a1b2c3`…) sẽ tạo một **time series mới** cho mọi metric có label đó, nhân với số bucket của histogram và số giá trị status. Cardinality bùng nổ: Prometheus hết RAM, query chậm, dashboard vỡ, và kẻ tấn công có thể cố tình làm sập monitoring. Dùng template `route.path` (hữu hạn) và gom URL không khớp vào `unmatched` thì số series luôn bị chặn.
3. Đã thêm `agent_question_length_chars` (Histogram, buckets 20…2000) vào `develop/app.py`. Kiểm tra: `agent_question_length_chars_count 1.0`, `agent_question_length_chars_sum 40.0`.

---

## AI usage log

Bài làm có dùng trợ lý AI (Claude Code) theo [RULES.md](RULES.md). Những việc AI hỗ trợ:

| Việc | AI làm gì | Tôi kiểm tra thế nào |
|---|---|---|
| Part 6 (`06-lab-complete/`) | Gợi ý và viết code cho các TODO (auth, rate limit Redis, cost guard, `/ready`, SIGTERM, Dockerfile multi-stage, compose, `render.yaml`/`railway.toml`) | Chạy `check_production_ready.py` bản đầy đủ → PASS 12/12; đọc lại từng file |
| Part 1–5 | Chạy các ví dụ, gom output thật, soạn nháp câu trả lời | Đối chiếu với code và output trong terminal |
| Part 7 | Chạy load test, eval, stack Docker, chụp ảnh, soạn nháp `BENCHMARK_REPORT.md`; sửa `KNOWLEDGE_BASE`, thêm metric 7.1, viết job CI; phát hiện và sửa lỗi `PYTHONUSERBASE` trong Dockerfile production | Mọi số trong báo cáo đều lấy từ file JSON/CSV đã nộp |
| Môi trường | Xử lý việc build Docker sau proxy (Dockerfile tạm cài CA, không commit) | Kiểm tra `git status`: không có file tạm hoặc CA nào bị commit |
