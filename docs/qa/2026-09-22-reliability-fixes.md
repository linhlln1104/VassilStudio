# Xác minh đợt sửa lỗi — 22/09/2026

Phạm vi: các lỗi triển khai xác định trong `docs/project-review-2026-09-22.md`, cùng các lỗi liên
quan phát hiện khi tích hợp. Thay đổi nằm trong working tree dựa trên commit `7f85b95`.

**Đã sửa**

| Nhóm | Kết quả |
| --- | --- |
| Filesystem | Voice/job ID và artifact path được kiểm tra containment; chặn traversal, symlink/junction và xóa ngoài kho; kiểm tra toàn bộ entry trước khi xóa |
| Dữ liệu | Metadata hỏng được cách ly và giữ nguyên để phục hồi; record tốt vẫn hoạt động; voice metadata ghi atomic; Settings hiển thị recovery warnings |
| TTS | Mỗi job giữ reference WAV/transcript/hash riêng; edit/delete voice không đổi accepted job; retry kiểm tra hash; idempotent replay vẫn hoạt động sau khi voice bị xóa |
| Hàng đợi | Giới hạn pending mặc định 32/domain, tính cả executor entries chưa tiêu thụ; queue đầy trả 429 và Retry-After |
| API/audio | Preparation, encode, storage handlers và diagnostics ra khỏi event loop; decode có giới hạn duration/samples/channels/rate; ffmpeg dùng file tạm có giới hạn; giữ source sample rate |
| ASR rerun | Downloaded WAV được gửi lại với tên/MIME/signature WAV; test các tên nguồn WAV/MP3/WebM/M4A qua API thật |
| Realtime | Control JSON được kiểm tra type/finite/caps, cấu hình validate atomic; chặn tăng buffer vượt server; frame qua ranh giới chunk không mất remainder; lỗi có envelope/close code |
| Frontend lifecycle | Stop chờ ACK, timeout báo incomplete và giữ text; microphone chống double start, permission đến muộn và unmount |
| Auth/UI | Giữ deep link, chặn return URL ngoài Studio, xóa drafts khi logout và có nút xóa thủ công; login username sai định dạng trả 401; h1/password label/mobile focus, route error boundary và ApiError metadata |
| Vận hành | Python>=3.12, Node/npm PATH, Vite HTTP/WS proxy, vocoder checksum/atomic install, model disabled được tôn trọng, readiness từ chối model rỗng, thiếu React build có trang hướng dẫn 503 |
| Quality tools | OpenAPI/auth/browser dùng workspace tạm, phục hồi environment; 7 browser suites vào default gate; thêm script smoke model thật bằng dữ liệu tổng hợp |

**Kết quả thực thi**

- `scripts/check.ps1` đã đạt: setup, doctor, OpenAPI, Ruff, React lint/typecheck/build, legacy syntax,
  pytest, auth/product smoke, 7 browser suites và Docker Compose config.
- Sau các chỉnh sửa cuối về metadata, audio và scheduling: **260 Python tests passed, 1 skipped**.
- Test skip duy nhất cần quyền tạo **file symlink** mà Windows hiện tại không cấp. Các test junction,
  directory containment và encoded traversal đã thực thi và đạt.
- Browser: Landing ở 3 kích thước; Audio, Jobs, Voice intake, Transcript review, Settings ở desktop/mobile;
  thêm 6 nhóm regression cho deep links/logout, unsafe destination, rerun, focus, recorder và realtime ACK.
- `scripts/smoke_runtime_isolated.py` đã chạy **model VI/EN thật** qua authenticated API trong workspace tạm:
  intake/review → voice → TTS job → WAV → ASR job → JSON export → WebSocket finalization → xóa voice →
  idempotent replay. Cả hai ngôn ngữ đạt; ASR đều có text đầu ra. Reference là tín hiệu tổng hợp,
  không dùng giọng hoặc dữ liệu riêng của người dùng.
- Ruff và kiểm tra whitespace diff đạt. OpenAPI canonical/legacy đã cập nhật cùng contract.

Artifacts local (không đưa vào source release): `artifacts/ui-qa/gate/` và
`artifacts/runtime-smoke/result.json`. Runtime smoke là kiểm tra pipeline, không phải đánh giá
độ tự nhiên/độ giống giọng, cũng không phải benchmark hiệu năng chuẩn hóa.

**Giới hạn và các bước phát triển còn lại**

Chưa kiểm tra microphone vật lý, stress/soak dài, Docker runtime hoặc cài đặt trên máy sạch trong
đợt này. Các tính năng roadmap như persisted realtime sessions, model manager, project/takes,
pagination, giao diện VI/EN và backup/restore chưa thuộc đợt sửa lỗi. Ứng dụng vẫn cần một process
cho mỗi workspace; chưa hỗ trợ nhiều process cùng sở hữu hàng đợi/storage.

Quarantine giữ file hỏng; không tự tái tạo nội dung đã mất. Legacy artifact path trỏ ngoài thư mục
record bị từ chối có chủ đích. Hướng dẫn giới hạn xử lý và phục hồi nằm trong `docs/operations.md`.
