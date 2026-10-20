# Tài Liệu Thiết Kế: Giao Diện Chuyên Nghiệp (Linear / Raycast Pro) & Lucide Icons

- **Ngày tạo:** 2026-10-20
- **Trạng thái:** Đã phê duyệt (Approved)
- **Tác giả:** Antigravity & User

---

## 1. Mục Tiêu & Bối Cảnh

Giao diện trước đó đã hoàn thành chuyển đổi sang mô hình **Split-View Dashboard**. Tuy nhiên, phong cách cũ sử dụng nhiều ký tự emoji unicode (🕹️, 🤖, 🌐, 🎨, ⚡, 🎯, 👁️) và màu sắc neon mang hơi hướng gaming phổ thông.

Mục tiêu của đợt cập nhật này là:
1. **Nâng cấp thẩm mỹ sang chuẩn chuyên nghiệp:** Phong cách **Linear / Raycast Pro** với nền đen nhám xám than `#0e0f12`, viền xám mảnh 1px `#23252e`, các thẻ card `#191a21` sang trọng và độ tương phản cao, hiện đại.
2. **Thay thế toàn bộ emoji bằng Lucide Icons chính thức:** Sử dụng vector SVG gốc của [Lucide](https://lucide.dev) thông qua module `ui/icons.py` dựng bằng `PyQt5.QtSvg.QSvgRenderer`. Icon sắc nét 100% trên mọi tỷ lệ màn hình (Retina / 2K / 4K) và hỗ trợ đổi màu động khi hover/active.

---

## 2. Hệ Thống Design Tokens (Linear / Raycast Pro)

### 2.1. Bảng Màu (Palette)
- **Nền chính (Main Window):** `#0e0f12` (Than đen nhám sâu)
- **Thanh Sidebar (Navigation):** `#14151a`
- **Thẻ Card / Container:** `#191a21`
- **Viền ngăn cách (Borders):** `1px solid #23252e`
- **Viền Card (Card Border):** `1px solid #282a36`
- **Viền Focus (Focus Ring):** `1px solid #6366f1` (Indigo thanh lịch)
- **Ô nhập liệu (Inputs & Combos):** Nền `#1f212a`, viền `#2e313d`, hover `#252834`
- **Chữ chính (Primary Text):** `#f4f4f7` (Độ tương phản cao)
- **Chữ phụ (Secondary Text):** `#8c90a4`
- **Icon / Muted Label:** `#616578`
- **Accents:**
  - **Indigo (Primary Brand & Navigation):** `#6366f1`
  - **Emerald (Active / Running / Start):** `#10b981` (Nền nút: `#10b981` / hover `#059669`)
  - **Rose (Stop / Error):** `#f43f5e` (Nền nút: `#f43f5e` / hover `#e11d48`)
  - **Amber (Warning):** `#f59e0b`

---

## 3. Kiến Trúc Bộ Icon Lucide Vector (`ui/icons.py`)

Module `ui/icons.py` sử dụng `QSvgRenderer` để chuyển đổi mã SVG của Lucide thành `QIcon`:
```python
def get_lucide_icon(name: str, color: str = "#8c90a4", size: int = 18, stroke_width: float = 2.0) -> QIcon:
    ...
```

### 3.1. Danh Sách Icon Lucide Tuyển Chọn

| Tên Icon | Mục đích hiển thị | Mô tả trực quan |
|---|---|---|
| `zap` | Logo thương hiệu trên Sidebar | Biểu tượng tia chớp vector nét thanh |
| `layout-dashboard` | Tab 1: Tổng quan (Console) | Bố cục dashboard 4 ô |
| `bot` / `cpu` | Tab 2: AI Engine | Robot / Vi xử lý công nghệ cao |
| `languages` | Tab 3: Dịch thuật & OCR | Hai chữ cái chuyển đổi ngôn ngữ |
| `palette` | Tab 4: Giao diện Phụ đề | Bảng pha màu tinh tế |
| `play` | Nút START | Tam giác phát nét đậm |
| `square` | Nút STOP | Hình vuông dừng |
| `scan` / `crop` | Chọn vùng quét OCR | Khung ngắm quét màn hình |
| `sliders` | Thao tác nhanh tùy chỉnh | Cần gạt tinh chỉnh |
| `eye` / `eye-off` | Ẩn / Hiện API Key | Mắt đóng / mở vector |
| `check-circle` | Trạng thái API sẵn sàng | Vòng tròn tích xanh |
| `alert-circle` | Cảnh báo thiếu API Key | Dấu chấm than cảnh báo |
| `log-out` | Nút Thoát ứng dụng | Mũi tên rời khỏi cửa |
| `activity` | Metric card: Trạng thái | Nhịp tim điện tâm đồ |
| `maximize-2` | Metric card: Kích thước vùng | Mũi tên mở rộng 2 góc |

---

## 4. Tương Thích & Tính Nhẹ Gọn

- Không cần cài đặt thêm bất kỳ thư viện ngoài nào (sử dụng sẵn `PyQt5.QtSvg` đã có trong môi trường).
- Giữ nguyên 100% logic kết nối `TranslationWorker`, `Overlay`, `core/config.py`.
- Tách biệt rõ ràng giữa logic giao diện và module tài nguyên icon.
