# Deployment Information

> ⏳ **Chưa deploy.** Các chỗ có `<...>` sẽ được thay bằng URL thật và kết quả chạy thật sau khi deploy agent Part 6 (`06-lab-complete/`).

## Public URL

`<https://...>`

## Platform

`<Railway | Render>`. Deploy thư mục `06-lab-complete/`, dùng `railway.toml` hoặc `render.yaml`. Redis: `<Railway Redis | Render Key Value day14-redis>`.

## Test Commands

Đặt `BASE` là URL public và `AGENT_API_KEY` là key đã đặt trên nền tảng. Mỗi lệnh chỉ in mã HTTP nên chụp ảnh không lộ key.

```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'   # 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'   # 200
```

Kết quả thực tế:

```text
<dán output 4 lệnh ở đây>
```

### Health check

```bash
curl "$BASE/health"
# {"status":"ok"}
```

### API test (with authentication)

```bash
curl -X POST "$BASE/ask" \
  -H "X-API-Key: $AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
```

## Environment Variables Set

Đặt trên nền tảng, không ghi trong code:

| Biến | Giá trị / nguồn |
|---|---|
| `PORT` | Nền tảng tự cấp |
| `ENVIRONMENT` | `production` |
| `AGENT_API_KEY` | Secret (Render: `generateValue: true`; Railway: `railway variables --set`) |
| `REDIS_URL` | Railway: `${{Redis.REDIS_URL}}`; Render: `fromService` → `day14-redis` |
| `RATE_LIMIT_PER_MINUTE` | `10` |
| `DAILY_BUDGET_USD` / `MONTHLY_BUDGET_USD` | `1.0` / `10.0` |
| `LOG_LEVEL` | `INFO` |

Nếu `/ready` hoặc `/ask` trả 503 thì agent chưa kết nối được Redis. Xem dòng log `redis_unreachable` hoặc `ready_failed` (host đã che mật khẩu) để biết nguyên nhân.

## Screenshots

- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
