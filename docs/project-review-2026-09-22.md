# Đánh giá và định hướng VassilStudio — 22/09/2026

Đánh giá trên commit `7f85b95` (version `0.1.0`). Working tree sạch khi bắt đầu. Báo cáo này bổ sung tài liệu; chưa sửa mã ứng dụng.

**Cập nhật sau đánh giá:** các lỗi triển khai trong mục 3 và các lỗi vận hành/UI liên quan đã được
sửa trong working tree ngày 22/09/2026. Xem [biên bản xác minh sửa lỗi](qa/2026-09-22-reliability-fixes.md)
để biết phạm vi và kết quả mới. Nội dung đánh giá bên dưới được giữ làm mốc trước sửa; roadmap
tính năng như projects, model manager, lưu phiên realtime và backup/restore vẫn là công việc tiếp theo.

**Kết luận chính.** VassilStudio đã có nền tảng của một voice studio local tương đối hoàn chỉnh: tạo giọng, tạo tiếng nói, nhận dạng, hiệu đính transcript, quản lý tác vụ và chẩn đoán. Hướng phát triển phù hợp là làm cho các quy trình này an toàn, phục hồi được và dễ sử dụng trên máy mới, rồi mở rộng công việc sáng tạo theo đoạn và nhiều bản thu. Có một lỗi ranh giới filesystem cần xử lý trước phát hành, cùng một số lỗi workflow mà bộ test hiện tại chưa bao phủ.

Định hướng trong báo cáo lấy **local-first, một chủ workspace, tiếng Việt/Anh** làm giả định theo tài liệu sản phẩm hiện hành. Đây là đề xuất kỹ thuật/sản phẩm, chưa phải cam kết lịch phát hành hoặc kết luận đã kiểm chứng nhu cầu thị trường.

**1. Phạm vi và mức độ kiểm chứng**

Đã rà các nhóm mã do dự án quản lý: backend, frontend React và legacy, API contracts, config, scripts, tests, CI, Docker, release và tài liệu sản phẩm/benchmark. Repository có 238 file được Git theo dõi tại thời điểm kiểm tra. Phần model binary và upstream clone trong `foundation` được xem theo vai trò tích hợp; không kiểm toán toàn bộ mã upstream, không đọc nội dung audio/transcript riêng tư.

| Kiểm tra đã chạy | Kết quả hiện tại |
| --- | --- |
| Python tests, với `PYTHONPATH=backend` như launcher kiểm tra của dự án | **170 passed**, 22,36 giây |
| Ruff cho `backend scripts tests` | Đạt |
| React `npm run lint` | Đạt sau khi thêm thư mục Node vào đầu PATH của phiên kiểm tra |
| React `npm run build` — TypeScript và Vite | Đạt |
| `scripts/doctor.py` | Đạt: dependencies, đường dẫn model VI/EN, phonemizer và kiểm tra cấu hình |
| Reproducer filesystem, metadata hỏng và WebSocket input | Xác nhận các lỗi mô tả bên dưới bằng fixture tạm/in-memory |
| Kiểm tra contract ASR rerun | WAV hợp lệ bị từ chối khi mang tên `.mp3`, `.webm`, `.m4a` |

Lần gọi pytest trực tiếp ban đầu thiếu đường dẫn import `backend`; chạy với môi trường tương đương `check.ps1` đã đạt. `npm` ban đầu lỗi tìm Node trong tiến trình con; thêm đường dẫn Node đã giải quyết, đúng vấn đề PATH được audit tháng 8 ghi nhận. Hai việc này chưa được sửa trong script dự án.

Chưa chạy lại inference ASR/TTS thật, browser QA, microphone vật lý, Docker runtime, cài đặt máy sạch, load/soak test hoặc benchmark latency trong đợt này. Doctor đạt không đồng nghĩa đã kiểm chứng chất lượng tiếng nói. Các số liệu hiệu năng trong tài liệu tháng 8 là bằng chứng lịch sử trên cấu hình tương ứng.

**2. Bản đồ hệ thống và năng lực đã có**

Luồng chính: **React Studio → FastAPI routers → domain services/jobs → runtime ASR/TTS → model và dữ liệu local**.

| Thành phần | Vai trò và hiện trạng |
| --- | --- |
| `backend/vvoice/main.py`, `core/container.py` | Ghép ứng dụng theo modular monolith, một process; quản lý service, warmup và shutdown |
| `domains/asr` | ZipFormer qua `sherpa_onnx.OfflineRecognizer`; chọn model theo ngôn ngữ; API trực tiếp và jobs |
| `domains/tts` | ZipVoice bằng ONNX trực tiếp, eSpeak phonemization, flow matching và Vocos; runtime TTS hiện dùng CPU |
| `domains/voices` | Lưu reference WAV + transcript + metadata; intake có phân tích, trim, cảnh báo, source hash và chống trùng |
| `domains/realtime` | Nhận PCM qua WebSocket, cắt cửa sổ, bỏ đoạn RMS thấp rồi gọi offline ASR; hiện chưa có trạng thái recognizer streaming |
| `shared/audio`, `shared/jobs`, `shared/security` | Decode/resample/encode, idempotency và stage contracts, session/API-key boundaries |
| `app/auth`, `app/system`, `app/studio` | Owner/session SQLite; health/readiness/diagnostics; product shell và static Studio |
| `frontend/studio-react` | React/TypeScript, TanStack Query, Radix, Tailwind; sáu khu vực Generate, Voices, Jobs, Transcribe, Realtime, Settings |
| `frontend/studio` | Giao diện cũ dùng làm fallback; chưa tương đương tính năng React |
| `contracts`, `scripts`, `.github`, `docker` | OpenAPI snapshot, kiểm tra/smoke/benchmark, CI và đóng gói |
| `models`, `data`, `logs`, `foundation` | Tài nguyên runtime, dữ liệu người dùng, log và source tham khảo; tách khỏi mã/release |

Các luồng đáng giữ nguyên nền tảng:

- **Voice:** upload/ghi âm/import local → phân tích tín hiệu và transcript → review/trim → xác nhận → lưu profile dùng lại. Kiểm tra chất lượng dựa năng lượng là một heuristic; chưa thể xem là bộ phân loại lời nói hoặc điểm chất lượng giọng hoàn chỉnh.
- **TTS:** chọn voice/ngôn ngữ/settings → tạo job có idempotency → cập nhật stage → nghe/tải WAV. Preview 4 steps và Production 8 steps có baseline lịch sử; cần benchmark lại trên corpus và thiết bị mục tiêu.
- **ASR:** upload → normalized input → job → raw transcript bất biến + bản hiệu đính theo revision → TXT/JSON hoặc SRT/VTT khi có timing thật.
- **Jobs:** stage/cancel/retry/history, audio có xác thực qua blob URL, xóa/cleanup có xác nhận. Cancellation diễn ra tại safe point, không dừng tức thời một model call đang chạy.
- **Vận hành:** owner account, session HttpOnly, API key automation, request ID, log có cấu trúc, diagnostics lọc thông tin, health và warmup.

Tài liệu có vài chỗ chưa cập nhật: `docs/architecture.md` còn mô tả TTS bằng `OfflineTtsZipvoiceModelConfig` dù implementation dùng ONNX trực tiếp; bảng gap trong `docs/product-completeness-research.md` vẫn ghi thiếu transcript editing/timing/export dù phần P1-B bên dưới đã ghi hoàn tất. Dùng code và test hiện tại làm mốc khi chọn backlog.

**3. Các vấn đề cần xử lý trước khi mở rộng**

Trong bảng này, P0 nghĩa là chặn phát hành; P1 là cần sửa trong đợt ổn định kế tiếp; P2 là cải thiện độ hoàn chỉnh. Mức ưu tiên là đánh giá cho sản phẩm local hiện tại, không phải điểm số bảo mật chuẩn hóa.

| Mức / bằng chứng | Phát hiện, ảnh hưởng | Cách xử lý và tiêu chí nghiệm thu |
| --- | --- | --- |
| **P0 — đã tái hiện qua router/store thật, fixture tạm** | `VoiceStore.get/update/delete` ghép trực tiếp `voice_id` vào path. Trên Windows, ID chứa backslash thoát khỏi voices root; DELETE đã xóa file và thư mục sibling fixture rồi trả 200. Điểm chính: `backend/vvoice/domains/voices/service.py:151`, `:171`, `:191`; router `:270`. Delete hiện xóa file trực tiếp rồi `rmdir`, không phải recursive delete. App đầy đủ vẫn áp dụng auth theo cấu hình; repro không chứng minh bypass auth. | Resolver chung kiểm tra ID, absolute/drive/separator và resolved path nằm trong root; xác minh profile trước mọi mutation. Test traversal Windows/POSIX và containment, bảo đảm file ngoài root không bị thay đổi. |
| **P1 — đã tái hiện contract** | Jobs tải ASR input đã chuẩn hóa thành WAV nhưng “Run again” giữ tên file gốc MP3/WebM/M4A. Validation từ chối vì extension/MIME/signature không khớp. `frontend/studio-react/src/features/jobs/JobsView.tsx:286`, `backend/vvoice/domains/asr/router.py:167`, `shared/validation.py:77`. | Tên retry phải là WAV, hoặc endpoint rerun phía server. Regression đi qua backend thật cho WAV/MP3/WebM/M4A. |
| **P1 — đã tái hiện startup ASR** | Một `metadata.json` không hợp lệ làm constructor job service ném `JSONDecodeError`. Startup gọi list toàn bộ nên một record có thể ngăn app khởi động. ASR `jobs.py:100`, `:389`, `:419`; TTS có cùng pattern ở `:91`, `:348`, `:378`. | Cách ly record hỏng, giữ bằng chứng để phục hồi, tiếp tục mở record tốt và đưa cảnh báo vào diagnostics. Test cả ASR/TTS; voice metadata cũng cần atomic write và xử lý record lỗi. |
| **P1 — phân tích đường gọi, chưa đo tải** | Async routes chạy decode/resample/file IO đồng bộ trước khi chuyển inference sang threadpool. `asr/router.py:40`, `:77`, `asr/jobs.py:120`; `tts/router.py:53`, `:88`. Fallback ffmpeg có thể chờ subprocess đến 90 giây. | Đưa toàn bộ preparation sang worker/threadpool; giới hạn audio sau decode bằng duration/sample count. Test health, polling và cancel vẫn phản hồi trong lúc chuẩn bị file lớn. |
| **P1 — đã tái hiện input sai; không stress memory** | WS nhận JSON array gây `AttributeError`; chunk duration dạng chuỗi sai gây `ValueError`. Config nhận chunk/buffer lên tới 1e9 giây. `realtime/router.py:101`, `:105`; `realtime/service.py:59`, `:150`. | Schema control message, số hữu hạn, giới hạn do server quyết định, cấu hình được validate trước khi cập nhật. Input sai phải trả lỗi giao thức có kiểm soát; nhiều frame không được vượt memory budget. |
| **P1 — phân tích code** | Frontend Stop realtime đóng socket sau 5 giây, trong khi backend có thể còn chờ flush ASR. Có nguy cơ mất phần cuối khi inference chậm hoặc tranh lock. `RealtimeView.tsx:374`; `realtime/router.py:118`. | Chờ ACK finalization, trạng thái incomplete/error rõ và phục hồi/export phần đã nhận. Test final result đến sau hơn 5 giây, không âm thầm báo hoàn tất. |
| **P1 — xác nhận code và tài liệu Python** | Package công bố Python `>=3.10` nhưng auth/system dùng `datetime.UTC`; API này có từ 3.11. CI hiện dùng 3.12. `pyproject.toml:12`, `app/auth/service.py:7`, `app/system/router.py:3`. | Chốt baseline được hỗ trợ, ưu tiên khớp Python 3.12 đang vận hành; đồng bộ package, lint target, docs, CI và clean-install test trên phiên bản tối thiểu công bố. |
| **P2 — phân tích code** | TTS job chỉ lưu voice ID, worker đọc lại profile khi chạy/retry. Sửa transcript hoặc xóa voice lúc queued có thể đổi input hay gây fail. `tts/jobs.py:112`, `:134`, `:297`. | Snapshot reference text/audio hash hoặc version, cùng model/settings fingerprint. Job đã nhận giữ nguyên input qua retry và sửa thư viện voice. |
| **P2 — phân tích code, chưa tái hiện browser** | VoiceRecorder chưa khóa Start khi đang xin quyền và chưa chặn stream được cấp sau unmount. `VoiceRecorder.tsx:24`, `:32`. | Trạng thái requesting permission, synchronous guard/lifecycle token; dừng stream đến muộn. Test double click và rời route trước khi cấp quyền. |
| **P2 — xác nhận cấu hình** | Vite proxy đến port 8001, launcher mặc định 8000; thiếu proxy diagnostics/readiness và WebSocket config. `vite.config.ts:17`, `scripts/run_api.ps1:2`. | Cấu hình URL thống nhất, đủ HTTP/WS proxy; smoke chế độ dev theo đúng README. |

Giới hạn Python được đối chiếu với [tài liệu chính thức về datetime.UTC](https://docs.python.org/3/library/datetime.html#datetime.UTC). Đề xuất tách preparation khỏi event loop phù hợp hướng dẫn [Python asyncio về blocking code](https://docs.python.org/3/library/asyncio-dev.html#running-blocking-code); mức ảnh hưởng thực tế của ứng dụng vẫn cần đo.

**4. Khoảng trống sản phẩm và khả năng bảo trì**

- **Realtime chưa lưu bền:** cần chọn microphone, pause/resume, xử lý disconnect, session ID, lưu transcript/timing và tùy chọn lưu source audio; mở lại/export sau refresh. Đây là P1-D trong backlog hiện tại.
- **Model operations còn cần người biết kỹ thuật:** readiness chỉ dựa nhiều vào sự tồn tại của file. Nên phân biệt missing, invalid, compatible, loaded, failed. Import model offline theo manifest trước, download có checksum/temp file/atomic promotion sau. `scripts/download_vocoder.ps1:7` hiện bỏ qua file đã tồn tại, kể cả nếu lần tải trước bị đứt.
- **Onboarding chưa khép kín:** người mới cần đi từ kiểm tra máy → model sẵn sàng → voice đầu tiên → output đầu tiên. Khi thiếu React build, legacy fallback chưa có setup/login tương đương; nên hiển thị hướng dẫn build rõ và xác định thời điểm kết thúc fallback.
- **History sẽ chậm khi tăng dữ liệu:** list và tìm idempotency quét JSON; UI poll toàn bộ rồi lọc ở client. Bổ sung pagination/filter phía server, queue admission limit và retention rõ. Đo trên 1.000/10.000 records trước khi chọn storage migration.
- **Dữ liệu cần chính sách phục hồi:** backup/restore workspace có version, kiểm tra integrity và preview trước restore. Với projects/history lớn, SQLite có migration/index là hướng tự nhiên; media vẫn lưu filesystem. Chưa cần đổi storage chỉ để đổi kiến trúc.
- **Auth/UX:** login mất deep link (`AuthPage.tsx:34`); draft script lưu chung localStorage và còn sau logout (`studio-preferences.ts:78`). Cần return path cùng origin, autosave policy, thao tác xóa draft và scope theo workspace/account.
- **Accessibility/localization:** ngôn ngữ model VI/EN chưa phải ngôn ngữ UI. Bổ sung giao diện VI/EN, h1 cho mỗi Studio route, password label đúng, keyboard/focus cho mobile drawer và kiểm tra accessibility.
- **API/frontend:** DTO hiện viết tay song song OpenAPI; có thể sinh types hoặc bổ sung contract tests. Giữ status/code/request ID trong lỗi client; thêm error boundary cho lazy route. Tách hooks/components theo use case khi chỉnh các view lớn, không cần viết lại frontend.

**5. Định hướng kiến trúc**

Giữ modular monolith và ranh giới `router → service → runtime`. Tách inference sang worker process chỉ khi đo được nhu cầu hard cancellation, isolation lỗi hoặc lập lịch tài nguyên; API và domain contract có thể giữ nguyên.

Hiện khóa chỉ bảo vệ trong một process; startup đánh dấu job chưa hoàn tất là interrupted. Do đó không tăng số app processes dùng chung storage trước khi có coordination. Tăng thread workers cũng không tự giải quyết tranh chấp inference lock giữa batch và realtime cùng ngôn ngữ.

Ưu tiên một lớp admission/scheduling dùng chung cho batch/live, giới hạn queue và quan sát wait time. Trước khi tăng chất lượng realtime, hoàn thiện session durability; sau đó thử VAD/end-of-utterance, overlap/context và benchmark. Đổi sang streaming model cần đánh giá lại model/runtime, không chỉ đổi WebSocket UI.

Hướng khác biệt nên kiểm chứng với người dùng là **quy trình sản xuất lời đọc tiếng Việt**: chia script thành đoạn, chỉnh phát âm, giữ các đoạn đã chấp nhận, tạo lại từng đoạn và xuất bản cuối. Transcript review/subtitle đã có thể phục vụ một nhóm sử dụng khác; cần chọn luồng được dùng thường xuyên nhất trước khi đầu tư sâu cả hai.

**6. Lộ trình đề xuất và điều kiện hoàn tất**

| Giai đoạn | Nội dung | Điều kiện hoàn tất |
| --- | --- | --- |
| **A — Ổn định để phát hành** | Filesystem containment, ASR rerun, record corruption recovery, async preparation, WS validation, Python/PATH/dev config; test các regression đã tìm được | Không còn lỗi chặn phát hành; file ngoài root được bảo vệ; record hỏng không khóa app; rerun đủ định dạng; lint/build/tests và browser/API smoke đạt |
| **B — Hoàn thiện realtime** | Finalization ACK, microphone lifecycle/device selector, pause/resume, reconnect có giới hạn, persist/reopen/export sessions | Stop và refresh không làm mất kết quả đã xác nhận; disconnect có trạng thái rõ; kiểm tra inference chậm và batch/live đồng thời |
| **C — Tự phục vụ trên máy mới** | Model manifest/import offline, checksum/compatibility, warm/unload; guided first output; backup/restore; UI VI/EN và accessibility | Người mới tạo output từ máy sạch bằng hướng dẫn/UI; phục hồi backup vào workspace mới; thiếu/hỏng model có đường xử lý rõ |
| **D — Công việc sáng tạo** | Project/script blocks, nhiều takes, pronunciation aliases, output có tên, export deterministic; voice snapshot/version | Sửa một đoạn không phải tạo lại đoạn đã chấp nhận; có thể so sánh/chọn take; bản xuất truy ngược được input/settings |
| **E — Tối ưu theo bằng chứng** | Corpus VI/EN, profiling, lịch batch/live, thử cache và GPU nếu cần | Đạt mục tiêu chất lượng/latency/RAM trên cấu hình mục tiêu; mọi thay đổi model/runtime có regression gate |

Nếu người dùng mục tiêu chủ yếu xử lý file và tạo lời đọc, có thể đưa onboarding/model operations ở C lên trước việc mở rộng đầy đủ realtime ở B. Các lỗi finalization/microphone vẫn nên sửa sớm. Thứ tự mặc định trên tiếp nối backlog P1-D hiện có.

**7. Cách đo tiến bộ và tổ chức quality gate**

| Mảng | Bằng chứng nên thu |
| --- | --- |
| Trải nghiệm lần đầu | Tỷ lệ và thời gian đi từ workspace mới đến WAV đầu tiên; lý do bị kẹt |
| ASR | Corpus cố định VI/EN, CER/WER, độ chính xác timing/subtitle; thêm giọng vùng miền, tên riêng, số và audio nhiễu |
| TTS | Nghe đánh giá độ rõ/tự nhiên/giữ giọng, lỗi phát âm, clipping; đánh giá riêng preset 4 và 8 steps trên từng ngôn ngữ |
| Runtime | Cold/warm latency, p50/p95, real-time factor, peak RAM, queue wait, thời gian cancel/finalize, health responsiveness |
| Dữ liệu | Restart giữa job, record lỗi, restore sang máy khác, retention không xóa active job; snapshot input không đổi sau edit voice |
| Release | Kết quả gắn commit + config + model hash + hardware/runtime fingerprint; smoke trên máy sạch |

Tách hai tầng kiểm tra: PR chạy unit/contract, lint/typecheck/build và browser fixtures; release chạy thêm browser → API thật → model/job → playback/export trong workspace cách ly. Sáu Playwright scripts hiện có chưa được gọi trong `check.ps1`/CI và phần lớn mock API; cần bổ sung một đường xuyên suốt để bắt lỗi như ASR rerun.

Corpus nên cố định và có quyền sử dụng. Smoke keyword hiện có hữu ích cho phát hiện lỗi lớn nhưng không thay thế phép đo chất lượng; dùng chính ASR để chấm TTS có thể che lỗi hoặc quy nhầm lỗi cho TTS. Không tự đặt ngưỡng chất lượng tuyệt đối trước khi có baseline và phản hồi người dùng.

Release hiện được repo định nghĩa source-first. Tiếp tục theo `docs/releasing.md`, làm mới evidence đúng commit và cập nhật các audit cũ bằng trạng thái resolved/superseded. Không suy từ nhãn “passed” của RC tháng 8 rằng toàn bộ thay đổi hiện tại đã được kiểm chứng trên máy sạch.

**8. Backlog đầu tiên có thể triển khai ngay**

1. Resolver an toàn cho voice ID và regression tests Windows/POSIX.
2. Sửa ASR Run again, kiểm thử các định dạng gốc qua backend thật.
3. Quarantine metadata hỏng và atomic metadata writes cho voice.
4. Chuyển audio preparation khỏi event loop, thêm decoded-audio/queue limits.
5. Schema/hard caps cho realtime control và ACK finalization; sửa lifecycle microphone.
6. Đồng bộ Python baseline, Node PATH, Vite proxy; đưa browser contract smoke vào quality gate.
7. Sau giai đoạn ổn định, triển khai persisted realtime session theo P1-D.

Mỗi đầu việc nên là thay đổi nhỏ có tiêu chí nghiệm thu riêng; giữ tương thích dữ liệu cũ và cập nhật OpenAPI/docs cùng lúc nếu contract thay đổi.
