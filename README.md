# Realtime Translator Screen

Ứng dụng Windows nhận dạng văn bản trong vùng màn hình và hiển thị phụ đề dịch.

## Chạy ứng dụng

Dùng Python 3.10 64-bit trên Windows. Trong PowerShell, tại thư mục dự án:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Thiết lập nhà cung cấp dịch và API key trong giao diện trước khi bắt đầu dịch. Kết nối mạng cần thiết để tải mô hình OCR lần đầu và gọi dịch vụ dịch. `config.json` lưu cấu hình ứng dụng; không commit thông tin xác thực cá nhân.

## Các nhánh

- `main`: mã chạy hệ thống (`main.py`, `core/`, `engines/`, `ui/`), cấu hình và thư viện cần thiết.
- `develop`: mã phát triển, test, benchmark, công cụ và tài liệu kỹ thuật.

Khi phát hành, đưa các thay đổi mã chạy đã kiểm thử từ `develop` sang nhánh release dựa trên `main`, rồi tạo PR vào `main`. Không merge trực tiếp toàn bộ `develop` nếu muốn giữ test ngoài `main`. `.gitignore` không ngăn file đã được theo dõi quay lại khi merge.

Các thư mục build, bản đóng gói, cache IDE và file phát triển không nằm trong cây hiện tại của `main`. Bản đóng gói có thể được phân phối qua GitHub Releases.
