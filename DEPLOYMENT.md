# Deployment Information

## Public URL

https://day14-agent-vaga.onrender.com

## Platform

**Render** (Blueprint: `06-lab-complete/render.yaml`, region Singapore, plan Free).
- Web service: `day14-agent` (Docker, `rootDir: 06-lab-complete`, health check `/health`)
- Redis: `day14-redis` (Render Key Value — Valkey 8, Singapore, internal connection via `fromService`)

## Test Commands

Đặt `BASE="https://day14-agent-vaga.onrender.com"` và `AGENT_API_KEY` là key đã đặt trên Render (tab **Environment**). Mỗi lệnh chỉ in mã HTTP nên không lộ key:

```bash
BASE="https://day14-agent-vaga.onrender.com"
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'   # 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'   # 200
```

Kết quả thực tế (đo ngày 2026-11-26):

```text
200
200
401
200
```

### Health & Readiness Check

```bash
curl https://day14-agent-vaga.onrender.com/health
# {"status":"ok"}

curl https://day14-agent-vaga.onrender.com/ready
# {"status":"ready","redis":"ok"}
```

### API Test (with authentication)

```bash
curl -X POST https://day14-agent-vaga.onrender.com/ask \
  -H "X-API-Key: $AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
# {"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

## Environment Variables Set

Đặt trên nền tảng Render (không ghi giá trị secret trong code):

| Biến | Giá trị / nguồn |
|---|---|
| `PORT` | Render tự cấp |
| `ENVIRONMENT` | `production` |
| `AGENT_API_KEY` | Secret do Render tự sinh (`generateValue: true`) |
| `REDIS_URL` | `fromService` → `day14-redis` (`connectionString`) |
| `RATE_LIMIT_PER_MINUTE` | `10` |
| `DAILY_BUDGET_USD` / `MONTHLY_BUDGET_USD` | `1.0` / `10.0` |

## Screenshots

- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
