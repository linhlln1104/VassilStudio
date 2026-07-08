# VassilStudio Local-First Product Plan

## Mục tiêu sản phẩm

Biến VassilStudio từ một demo kỹ thuật thành một sản phẩm nhỏ nhưng hoàn chỉnh: người dùng cài local, mở Studio, tạo hoặc nhập voice profile, generate TTS, transcribe ASR, chạy realtime ASR, theo dõi jobs/history, kiểm tra model readiness, cấu hình hệ thống, và tự chẩn đoán lỗi mà không cần hiểu codebase.

Định vị sản phẩm:

| Trục | Quyết định |
| --- | --- |
| Product category | Local-first voice studio |
| Primary buyer/user | Creator, researcher, indie engineer, nội bộ team cần voice tooling tiếng Việt/tiếng Anh |
| Runtime model | Chạy local trước, không phụ thuộc cloud |
| Account model MVP | Local workspace owner account, không multi-tenant SaaS ngay |
| Security model MVP | Session cookie cho Studio, API key cho automation/scripts |
| Business model future | Local license key trước, Stripe subscription/customer portal sau nếu có cloud hoặc paid distribution |
| Non-goal MVP | Không xây full SaaS admin, team workspace, cloud asset sync, marketplace model |

## Product Completeness Checklist

Một sản phẩm nhỏ nhưng hoàn chỉnh cần có đủ các lớp sau:

| Lớp | Cần có trong MVP | Ghi chú triển khai |
| --- | --- | --- |
| Public product shell | Landing page, docs/download, changelog, support/troubleshooting | Tách khỏi Studio để hết cảm giác demo |
| First-run onboarding | Tạo local admin, chọn model path, kiểm tra readiness, import voice đầu tiên | Dẫn người dùng tới aha moment: import voice -> generate audio |
| Auth/session | Setup account, login, logout, protected Studio, session expiry | Local-first nên dùng secure cookie session; giữ API key cho CLI |
| Core workflows | Generate, Voices, Jobs, Transcribe, Realtime, Settings | Mỗi workflow có empty/loading/error/success states |
| Runtime reliability | Warmup, readiness, model missing/error handling, smoke quality tests | Ưu tiên rõ lỗi hơn là im lặng fail |
| Data management | Storage usage, cleanup jobs, output export, voice deletion confirmation | Người dùng hiểu dữ liệu nằm ở đâu |
| Observability | Request ID, job ID, local logs, diagnostics bundle, optional Sentry later | Không leak API key, transcript/audio nhạy cảm |
| Distribution | Docker, native local run, `.env.example`, model layout docs | Windows path issues cần được ghi rõ |
| Quality gate | `scripts/check.ps1`, smoke scripts, frontend build/lint/typecheck | Mỗi phase production phải pass |
| Trust/legal | Privacy note, license/model attribution, terms/license page | Local-first vẫn cần minh bạch data retention |

## Research Baselines

Các baseline nên dùng để thiết kế phần sản phẩm và bảo mật:

| Chủ đề | Baseline | Source | Áp dụng cho VassilStudio |
| --- | --- | --- | --- |
| Web app security | OWASP ASVS | <https://owasp.org/www-project-application-security-verification-standard/> | Checklist cho auth, session, access control, validation |
| Session security | OWASP Session Management Cheat Sheet | <https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html> | Cookie flags, session lifecycle, logout, expiry |
| FastAPI auth | FastAPI OAuth2/JWT docs | <https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/> | Tham khảo pattern password hashing/token; MVP ưu tiên cookie session local |
| Billing future | Stripe Subscriptions và Customer Portal | <https://docs.stripe.com/subscriptions>, <https://docs.stripe.com/customer-management/integrate-customer-portal> | Chỉ đưa vào roadmap, chưa cần implement nếu chưa bán subscription |
| Product onboarding | Product-led onboarding/aha moment | <https://openviewpartners.com/blog/your-guide-to-product-led-onboarding/> | Onboarding phải dẫn tới output thật, không chỉ tour UI |
| Observability | OpenTelemetry, Sentry | <https://opentelemetry.io/>, <https://docs.sentry.io/> | MVP dùng structured logs/local diagnostics; external telemetry opt-in |

## Product Surface

### Public Site

| Route | Mục tiêu | MVP scope |
| --- | --- | --- |
| `/` | Landing page | VassilStudio là gì, local-first promise, CTA mở Studio/download docs |
| `/docs` hoặc docs link | Hướng dẫn vận hành | Install, model layout, config, smoke tests, troubleshooting |
| `/changelog` | Tin cậy sản phẩm | Ghi thay đổi theo release/commit phase |
| `/support` | Tự xử lý lỗi | Diagnostic bundle, log path, issue template |
| `/privacy` | Trust | Nói rõ audio/transcript/model chạy local, telemetry mặc định tắt |
| `/license` | Pháp lý | App license, model license notes, third-party attribution |

Landing page không nên là marketing quá đà. Nó cần trả lời nhanh:

- VassilStudio chạy local.
- Hỗ trợ ZipFormer ASR và ZipVoice TTS cho tiếng Việt/tiếng Anh.
- Dữ liệu voice/audio nằm trong workspace local.
- Người dùng có thể mở Studio hoặc đọc docs setup model.

### Studio App

| Route | Workflow hoàn chỉnh |
| --- | --- |
| `/studio/generate` | Chọn voice profile, chọn language, nhập text, chọn render mode, queue/render, nghe output, mở job/output |
| `/studio/voices` | Import voice, auto/manual transcript, validate language/audio, xem readiness, rename/delete/export |
| `/studio/jobs` | Xem ASR/TTS queue/history, trạng thái lifecycle, retry/cancel/cleanup terminal jobs |
| `/studio/transcribe` | Upload audio, chọn language, direct/queued ASR, transcript result, copy/export |
| `/studio/realtime` | Microphone permission, websocket status, chunk transcript, reconnect/error states |
| `/studio/settings` | Account/session, API key, model readiness, warmup, storage cleanup, diagnostics |

## Terminology

| Term | Dùng trong UI/API docs | Tránh dùng |
| --- | --- | --- |
| Voice profile | Hồ sơ giọng dùng lại cho TTS | sample, demo voice |
| Render | Một lần generate audio | synth demo |
| Render mode | Preview hoặc Production | fast/slow magic |
| Model readiness | Trạng thái model/tokenizer/vocoder sẵn sàng | health chung chung |
| Queue | Hàng đợi job | background magic |
| Output | File WAV/result có thể nghe/tải | artifact mơ hồ |
| Local workspace | Thư mục chứa config/data/models/logs | server data |
| Diagnostics bundle | Gói log/config đã lọc secret | dump logs |

## Architecture Additions

### Auth And Account

MVP nên thêm local account thay vì cloud signup trước:

| Capability | Thiết kế đề xuất | Acceptance |
| --- | --- | --- |
| First-run setup | Nếu chưa có admin, `/setup` tạo account local owner | Không vào Studio được trước khi setup hoặc khi auth disabled có chủ đích |
| Login/logout | Email/username + password, secure session cookie | Cookie HttpOnly, SameSite, expiry rõ |
| Password storage | Hash bằng Argon2 hoặc bcrypt | Không lưu password plain text |
| Session store | File-backed hoặc SQLite-backed local store | Logout invalidates session |
| Recovery | Recovery key hoặc documented reset command | Không cần email reset trong MVP local |
| API automation | Giữ `X-Vassil-API-Key`/Bearer API key | Smoke scripts không phụ thuộc browser login |
| Secret handling | Mask secret trong UI/log/diagnostics | Không log cookie/API key/query secret |

### Data Store

Hiện tại filesystem đủ tốt cho voice/jobs. Với auth/license/settings, nên cân nhắc SQLite nhỏ:

| Data | Store MVP | Lý do |
| --- | --- | --- |
| Voice audio/job outputs | Filesystem | File lớn, dễ inspect/copy |
| Job metadata | Filesystem hiện tại, chuẩn hóa schema | Ít migration, đang hoạt động |
| Account/session/license/settings | SQLite hoặc single local JSON có lock | Cần atomic update và query rõ |
| Audit/security events | Structured log | Không cần database phức tạp |

Khuyến nghị: nếu thêm auth, dùng SQLite cho `accounts`, `sessions`, `settings`, `license`. Không refactor voice/job store ngay nếu chưa cần.

### Config And Environments

| Environment | Cần có |
| --- | --- |
| local | `config/vassil.local.json`, `.env`, paths rõ |
| dev | hot reload API/Studio, auth dev override nếu cần |
| docker | volumes `models`, `data`, `logs`, healthcheck |
| production-like | API key/session secret bắt buộc, limits rõ, logs structured |

Thêm `.env.example` với:

- `VASSIL_CONFIG`
- `VASSIL_ROOT`
- `VASSIL_API_KEYS`
- `VASSIL_SESSION_SECRET`
- `VASSIL_AUTH_REQUIRED`
- `VASSIL_LOG_LEVEL`
- `VASSIL_TELEMETRY_ENABLED=false`

## Roadmap 3 Phase

### Phase 1: Stabilize

Mục tiêu: runtime, security boundary, và data lifecycle đủ chắc để làm nền cho auth/product shell.

| Workstream | Task | Acceptance | Verification |
| --- | --- | --- | --- |
| Config | Chuẩn hóa `.env.example`, config docs, required secrets khi auth bật | Local/dev/docker đọc config rõ, không secret mặc định nguy hiểm | pytest config, manual env smoke |
| Security | Audit path traversal, upload content type/size, filename normalization | Upload không ghi ngoài workspace, lỗi trả về rõ | pytest security/file safety |
| Job lifecycle | Retry/cancel/cleanup/metadata consistency đã có, bổ sung retry visibility nếu thiếu | UI và API đồng bộ state | pytest jobs, smoke cleanup |
| Health | `/livez`, `/readyz`, `/health`, `/model-status` phân biệt rõ | Docker health dùng liveness/readiness đúng | smoke_api, docker config |
| Observability | Request ID/job ID logs, diagnostics bundle bản đầu | Có thể gửi bundle đã mask secret | pytest observability |
| Model reliability | Missing model/tokenizer/vocoder errors rõ theo language | Người dùng biết thiếu file nào | doctor, model-status tests |

Deliverable commit đề xuất:

```text
feat: stabilize product runtime
```

### Phase 2: Productize

Mục tiêu: sản phẩm có public shell, first-run account, protected Studio, onboarding, và UI copy/state giống sản phẩm thật.

| Workstream | Task | Acceptance | Verification |
| --- | --- | --- | --- |
| Public shell | Landing page `/`, privacy/license/support/changelog stubs | Người dùng mở app thấy sản phẩm, không thấy demo shell | frontend build, visual QA |
| Local auth | First-run setup, login, logout, protected `/studio` | Fresh install tạo owner account; existing automation vẫn dùng API key | pytest auth, browser smoke |
| Onboarding | Checklist: model readiness, import voice, generate first output | Empty workspace có đường đi rõ tới output đầu tiên | frontend tests/manual QA |
| Studio UX | Generate/Voices/Jobs/Transcribe/Realtime/Settings đầy đủ states | No voice/model cold/job failed/no output đều có UI rõ | frontend build/manual screenshots |
| Settings | Account/session/API key/model/storage/diagnostics/license placeholder | User quản trị local workspace tại một nơi | pytest settings if API added |
| Copywriting | Chuẩn hóa terminology | Không còn demo/sample wording trong core UI | review pass |

Deliverable commits đề xuất:

```text
feat: add product shell and first-run auth
feat: complete studio onboarding states
```

### Phase 3: Operate

Mục tiêu: đóng gói, test, docs, smoke, và vận hành production-like.

| Workstream | Task | Acceptance | Verification |
| --- | --- | --- | --- |
| QA gate | Mở rộng pytest routers/services/security/jobs | Regression chính được test | `scripts/check.ps1` |
| Smoke scripts | `smoke_api`, `smoke_voices`, `smoke_tts`, `smoke_asr`, `smoke_realtime`, `smoke_language_matrix`, `smoke_docker` | Script có output rõ, exit code đúng | run selected smokes |
| Benchmark | TTS latency, ASR latency, realtime chunking | Có baseline CPU để so sánh | benchmark scripts/manual report |
| Docker | Production-like image, volumes rõ, env docs | `docker compose config` và smoke pass | `smoke_docker.ps1` |
| Docs | Install, model layout, config, auth, smoke, troubleshooting | Người mới setup được theo docs | docs review |
| Release hygiene | Changelog, version, support bundle | Mỗi release có notes/check result | manual release checklist |

Deliverable commits đề xuất:

```text
test: expand production smoke coverage
docs: add operation and troubleshooting guide
```

## MVP Implementation Order

Thứ tự đề xuất từ thời điểm hiện tại:

| Step | Việc làm | Lý do ưu tiên |
| --- | --- | --- |
| 1 | Tạo `.env.example` và docs config/auth target | Cần nền trước khi thêm auth/session |
| 2 | Thiết kế auth backend tối thiểu: account/session/settings store | Quyết định data boundary sớm |
| 3 | Implement first-run setup + login/logout API | Chặn Studio đúng kiểu sản phẩm |
| 4 | Protected Studio route + API auth compatibility | Không phá scripts/smoke hiện tại |
| 5 | Landing page `/` + public docs/support/privacy/license stubs | Tạo product shell |
| 6 | Settings Account/Session/License/Diagnostics UI | Người dùng quản trị workspace |
| 7 | Onboarding checklist trong Studio | Dẫn tới first successful output |
| 8 | Diagnostics bundle + secret masking tests | Hỗ trợ vận hành thực tế |
| 9 | Smoke/browser QA cho first-run -> generate | Chứng minh sản phẩm hoàn chỉnh nhỏ |
| 10 | Commit, `scripts/check.ps1`, push, working tree clean | Giữ chuẩn production |

## Auth MVP Detail

### Backend API

| Endpoint | Purpose | Notes |
| --- | --- | --- |
| `GET /api/v1/auth/status` | Cho biết auth enabled, setup required, current user | Public-safe, không leak config secret |
| `POST /api/v1/auth/setup` | Tạo local owner account lần đầu | Chỉ chạy khi chưa có account |
| `POST /api/v1/auth/login` | Tạo session cookie | Rate limit nhẹ nếu có thể |
| `POST /api/v1/auth/logout` | Invalidate session | Clear cookie |
| `GET /api/v1/auth/me` | Current account | Protected |
| `POST /api/v1/auth/change-password` | Đổi password | Protected |

### Frontend Routes

| Route | State |
| --- | --- |
| `/setup` | Chỉ hiện khi `setup_required=true` |
| `/login` | Hiện khi auth required và chưa có session |
| `/studio/*` | Protected, redirect login/setup nếu cần |
| `/` | Public landing, CTA mở Studio |

### Security Acceptance

- Password hash không reversible.
- Session cookie `HttpOnly`, `SameSite=Lax` hoặc `Strict`; `Secure` bật khi HTTPS.
- Không lưu session token vào localStorage.
- Logout xóa cookie và session server-side.
- Diagnostics bundle mask API keys, session secret, cookies, Authorization headers.
- Browser UI chỉ hiển thị API key dạng masked.
- API key automation tiếp tục hoạt động cho scripts hiện có.

## Landing Page MVP Detail

Landing page cần gọn và product-first:

| Section | Nội dung |
| --- | --- |
| Hero | VassilStudio, local-first voice studio cho ASR/TTS tiếng Việt/tiếng Anh |
| Runtime promise | Audio, transcript, voice profiles chạy và lưu local |
| Workflow preview | Import voice -> Generate -> Transcribe -> Jobs/history |
| Readiness | Model status, warmup, diagnostics |
| CTA | Open Studio, Read setup docs |
| Trust strip | Local data, API key/session auth, Docker-ready |

Không cần pricing page trong MVP nếu chưa bán. Thêm `License` placeholder trong Settings và docs để không khóa kiến trúc về sau.

## Studio UX Acceptance

| Workflow | Empty state | Error state | Success state |
| --- | --- | --- | --- |
| Generate | Chưa có voice profile hoặc model cold | Invalid language, missing model, failed job | Audio output nghe/tải được, job linked |
| Voices | Chưa import voice | Audio quá lớn/sai format/transcript invalid | Voice profile ready, có language |
| Jobs | Chưa có job | Failed/cancelled có reason | Succeeded có output/transcript |
| Transcribe | Chưa upload audio | Decode failed/model missing | Transcript copy/export |
| Realtime | Chưa cấp mic hoặc chưa connect | WebSocket/mic/model error | Streaming transcript chunks |
| Settings | Config chưa đầy đủ | Secret missing/model path invalid | Readiness pass, warmup started/done |

## Testing Matrix

| Area | Tests cần có |
| --- | --- |
| Config | env precedence, missing session secret, local/dev/docker modes |
| Auth | setup once, login success/fail, logout, protected Studio, API key compatibility |
| Session | cookie flags, expiry, invalidation, no localStorage token |
| Security | upload size/type, path traversal, secret masking |
| Jobs | lifecycle, cancel, retry metadata, cleanup terminal jobs |
| Model readiness | missing language/model/tokenizer/vocoder, warmup state |
| Frontend | build/lint/typecheck, auth redirects, empty/error states |
| Smoke | API, voices, TTS, ASR, realtime, language matrix, docker |

Default gate:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1
```

Optional gates trước release:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1 -RunE2E
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1 -RunLanguageMatrix
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1 -RunDocker
```

## Deployment And Ops Checklist

| Item | Done when |
| --- | --- |
| Dockerfile | Builds backend + React Studio, no model baked into image |
| Compose | Mounts `models`, `data`, `logs`; ports/env documented |
| `.env.example` | Covers config path, API keys, session secret, auth required, log level |
| Model docs | Lists required ASR/TTS files per language |
| Windows docs | Warns about native DLL/model paths and spaces |
| Logs | Structured JSON, request/job IDs, no secrets |
| Diagnostics | Creates redacted support bundle |
| Backup | Documents `data/voices`, `data/jobs`, account/settings DB |
| Cleanup | Terminal jobs/output cleanup configurable |

## Definition Of Done For Each Phase

Một phase chỉ xem là xong khi:

- Scope đã implement đúng acceptance criteria.
- Tests liên quan đã được thêm hoặc cập nhật.
- `scripts/check.ps1` pass, hoặc ghi rõ lý do nếu chỉ docs-only và không chạy.
- Docs/changelog được cập nhật nếu user-facing behavior thay đổi.
- Conventional commit đã tạo.
- Push lên `origin/main`.
- `git status --short --branch` sạch.

## Top Product Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Auth làm hỏng local automation | Smoke/scripts fail, mất developer ergonomics | Giữ API key path độc lập với browser session |
| Quá sớm xây SaaS | Tốn scope, lệch local-first | MVP chỉ local owner account/license placeholder |
| Model missing errors mơ hồ | Người dùng bỏ cuộc trước khi có output | Readiness theo file/language, docs model layout |
| UI giống demo | Sản phẩm thiếu tin cậy | Product shell, onboarding, state/copy chuẩn |
| Secret leak trong logs/UI | Rủi ro bảo mật | Redaction middleware/tests, no query logging |
| Job metadata drift | Jobs/history không đáng tin | Schema/version, tests lifecycle |
| Windows path/runtime lỗi | Install fail trên máy target | Docs path, smoke native, avoid spaces warning |
| Cold start chậm | Người dùng tưởng app hỏng | Warmup states, latency copy ngắn, readiness detail |
| Test gate quá nặng | Phase chậm, dễ skip quality | Default check nhanh; optional E2E/docker trước release |
| Scope lan rộng | Không hoàn chỉnh được | Phase nhỏ, mỗi phase có commit và acceptance rõ |

## Recommended Next Action

Bắt đầu Phase 2 theo lát cắt nhỏ: **Product Shell + Local Auth Foundation**.

Deliverable đầu tiên nên gồm:

- `.env.example`
- auth config keys
- local account/session store skeleton
- `GET /api/v1/auth/status`
- `POST /api/v1/auth/setup`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- protected `/studio` behavior behind config flag
- frontend setup/login screens tối giản
- tests cho setup/login/protected Studio/API key compatibility

Commit mục tiêu:

```text
feat: add local auth foundation
```

## Implementation Progress

| Date | Slice | Status | Evidence |
| --- | --- | --- | --- |
| 2026-07-08 | Product Shell + Local Auth Foundation | Done | `.env.example`, `/api/v1/auth/*`, local SQLite account/session store, `/` product shell, `/setup`, `/login`, protected `/studio`, auth/API key compatibility tests, `scripts/check.ps1` pass |
| 2026-07-08 | Settings Account, License, Diagnostics | Done | `/diagnostics` redacted metadata endpoint, Settings account/session surface, local license placeholder, `scripts/check.ps1` pass |
| 2026-07-08 | First Output Onboarding | Done | Generate first-run checklist for runtime readiness, voice profile, script, queued render, playable output, and `scripts/check.ps1` pass |
| 2026-07-08 | Redacted Diagnostics Bundle | Done | `/diagnostics/bundle` zip endpoint, Settings download action, redaction tests, and `scripts/check.ps1` pass |
| 2026-07-08 | Storage Usage And Retention | Done | `/diagnostics` storage byte/file counts, Settings terminal job retention cleanup controls, and `scripts/check.ps1` pass |
| 2026-07-08 | Auth Product Smoke | Done | `scripts/smoke_auth.py` isolated first-run setup/login/logout/protected Studio/API key smoke in `scripts/check.ps1` |
| 2026-07-08 | Latency Benchmark Scripts | Done | `benchmark_tts_latency`, `benchmark_asr_latency`, and `benchmark_realtime_chunking` scripts with JSON summaries; `scripts/check.ps1` pass |
| 2026-07-08 | Changelog And Release Hygiene | Done | Public `/changelog` route, repository `CHANGELOG.md`, and `scripts/check.ps1` pass |
