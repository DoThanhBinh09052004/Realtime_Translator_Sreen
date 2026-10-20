# Tài Liệu Thiết Kế: Giao Diện Dashboard Controller Hiện Đại (Modern Cyber/Gaming Dark)

- **Ngày tạo:** 2026-10-20
- **Trạng thái:** Đã phê duyệt (Approved)
- **Tác giả:** Antigravity & User

---

## 1. Mục Tiêu & Bối Cảnh

Ứng dụng **Realtime Translator Screen** là công cụ dịch thuật màn hình theo thời gian thực (chuyên dụng cho game và video) xây dựng trên nền tảng Python + PyQt5. 

Hiện tại, cửa sổ điều khiển (`ControllerWindow`) sử dụng bố cục cuộn dọc một cột truyền thống. Mục tiêu của đợt thiết kế lại này là:
1. **Nâng cấp trải nghiệm toàn diện:** Chuyển sang mô hình **Split View Dashboard** (Left Sidebar + Multi-page Content Panels) chuẩn gaming/developer tools (tương tự Discord, Razer Synapse, GeForce Experience).
2. **Nâng tầm thẩm mỹ:** Áp dụng hệ màu **Modern Cyber Dark** (Deep Slate background, viền phát sáng nhẹ Neon Mint/Indigo/Rose, bo góc tinh xảo, typography hiện đại).
3. **Thêm tính năng Live Preview:** Cho phép xem trước hộp phụ đề (màu chữ, màu nền, độ trong suốt) ngay trong tab Tùy biến Phụ đề mà không cần khởi động quét game.
4. **Giữ nguyên 100% tính tương thích:** Tương thích hoàn toàn với kiến trúc nền tảng gồm `TranslationWorker`, `core/config.py`, và `engines/translator.py`.

---

## 2. Hệ Thống Design Tokens & Styling

### 2.1. Bảng Màu (Palette)
- **Cửa sổ chính (Main Background):** `#0d0e17` (Deep Cyber Void)
- **Thanh Sidebar (Navigation Background):** `#141622` (Cyber Slate)
- **Thẻ nội dung (Cards / Panels):** `#1a1d2e`
- **Đường viền ngăn cách (Borders):** `1px solid #282c44`
- **Màu chữ chính (Primary Text):** `#f1f5f9` (Slate 100)
- **Màu chữ phụ (Muted Text / Labels):** `#94a3b8` (Slate 400)
- **Accent - Neon Emerald (Start / Success / Active):** `#10b981` (hover `#34d399`, glow `#10b98133`)
- **Accent - Neon Rose (Stop / Error / Danger):** `#f43f5e` (hover `#fb7185`, glow `#f43f5e33`)
- **Accent - Cyber Indigo (Focus / Primary Nav / Slider):** `#6366f1` (hover `#818cf8`)
- **Accent - Warm Amber (Cảnh báo API key):** `#fbbf24`

### 2.2. Typography & Controls
- **Font gia đình:** `"Segoe UI", -apple-system, Roboto, sans-serif`
- **Độ bo góc (Border Radius):**
  - Card/Panels: `10px`
  - Nút bấm & Input: `8px`
  - Pill badges & Indicators: `12px` (hoặc tròn)
- **Inputs & Comboboxes:** Nền `#22263d`, viền `#2e3452`, focus viền `#6366f1` kèm outline nhẹ.

---

## 3. Kiến Trúc Giao Diện (Layout & Pages)

### 3.1. Cấu Trúc Tổng Thể (Split View Layout)
- **Kích thước mặc định:** `720 x 540 px` (Minimum size: `640 x 480 px`, co giãn phản hồi tốt).
- **Phân tách 2 cột:**
  - **Left Sidebar (Cố định width ~190px):**
    - Logo thương hiệu: Biểu tượng `⚡` + `TRANSLATE HUD` + Subtitle `Realtime OCR Engine`.
    - 4 Nút danh mục điều hướng (Nav Buttons) với icon và viền chỉ báo (active indicator).
    - Sidebar Footer: Trạng thái hệ thống (`● STOPPED` / `● ACTIVE`) và Nút `Thoát (Quit)`.
  - **Right Content Area (QStackedWidget):**
    - Header trang hiển thị tiêu đề tab hiện tại và mô tả ngắn.
    - Khu vực cuộn `QScrollArea` chứa các Card nội dung của từng trang tương ứng.

---

### 3.2. Chi Tiết Các Tab Trang

#### 🕹️ Tab 1: Console (Tổng quan & Điều khiển nhanh)
- **Hero Actions:**
  - Nút **START** (Xanh lục Neon `#10b981`, font 13px bold, icon `▶`)
  - Nút **STOP** (Đỏ Neon `#f43f5e`, font 13px bold, icon `⏹`)
- **Quick Status Metrics (Grid 4 thẻ tóm tắt):**
  1. *Trạng thái:* `Sẵn sàng` / `Đang chạy (Background Worker)`
  2. *AI Provider:* Tên Provider đang active (Gemini / OpenRouter / Groq...)
  3. *Ngôn ngữ:* Cặp ngôn ngữ nguồn ➔ đích (e.g. `English ➔ Vietnamese`)
  4. *Vùng OCR:* Kích thước pixel hiện tại (`800 x 200` px hoặc `Chưa thiết lập`)
- **Thao tác nhanh:** Nút "Quét nhanh vùng OCR" kích hoạt chế độ kéo chuột chọn vùng ngay tại Console.

#### 🤖 Tab 2: AI Engine (Cấu hình Model & Khóa API)
- **Provider Selector:** Dropdown chọn nhà cung cấp AI (Google Gemini, OpenRouter, Groq, Cerebras...).
- **Model Selector:** Dropdown danh sách model khả dụng, cho phép nhập tên model tùy biến (editable combobox).
- **API Key Field:** Ô nhập mật khẩu kèm nút `👁` bật/tắt hiển thị, tự động đồng bộ và lưu vào `.env` bảo mật.
- **Trạng thái API Key:** Badge hiển thị `✅ Đã cấu hình (.env)` hoặc `⚠️ Chưa có API Key`.
- **Gợi ý & Liên kết:** Đoạn hướng dẫn ngắn cách lấy API key của từng bên.

#### 🌐 Tab 3: Dịch thuật & OCR
- **Bộ chọn Ngôn ngữ:** Hai cột Source và Target xếp hàng ngang với mũi tên chuyển ngữ `➔`.
- **Tần suất quét OCR (Interval ms):**
  - SpinBox kết hợp mô tả trực quan (100ms - 2000ms).
  - Tự động lưu cấu hình `interval_ms` vào `config.json`.
- **Thông số Vùng Màn Hình:** Thẻ hiển thị tọa độ chi tiết `(X, Y, Width, Height)` kèm nút bấm "Chọn lại vùng mới".

#### 🎨 Tab 4: Giao diện Phụ đề (Subtitle & Live Preview)
- **Tùy chỉnh Màu sắc:**
  - Nút chọn Background Color kèm ô xem mã Hex và swatch màu.
  - Nút chọn Text Color.
- **Độ trong suốt nền (Background Opacity):**
  - Slider từ 0% đến 100% kèm nhãn số phần trăm hiển thị động.
- **Live Preview Box (Hộp xem trước phụ đề):**
  - Một khung demo hiển thị mẫu phụ đề với text: *"Đây là đoạn phụ đề xem trước thời gian thực..."*.
  - Khi người dùng thay đổi màu nền, độ mờ hoặc màu chữ, hộp Live Preview này và cả cửa sổ `Overlay` thật sẽ lập tức đồng bộ thời gian thực.

---

## 4. Luồng Dữ Liệu & Xử Lý Lỗi (Data Flow & Error Handling)

1. **Khởi động an toàn:**
   - Khi bấm **START**, ứng dụng kiểm tra xem Provider hiện tại đã có API key hay chưa.
   - Nếu chưa: Status chuyển sang màu cảnh báo, tự động điều hướng sang Tab 2 (AI Engine) và viền đỏ cảnh báo ô nhập API Key trong 2.5 giây.
2. **Đồng bộ Overlay:**
   - Mọi thay đổi về Subtitle Style (`bg_color`, `text_color`, `bg_opacity`) kích hoạt signal cập nhật trực tiếp `Overlay.apply_style()`.
3. **Đồng bộ Trạng thái:**
   - Các thẻ metrics trong Tab 1 tự động cập nhật khi người dùng thay đổi Provider, Model, Ngôn ngữ, hoặc Vùng chọn ở các tab khác.

---

## 5. Kế Hoạch Triển Khai Tiếp Theo

Sau khi lưu tài liệu thiết kế này, tiến trình sẽ chuyển sang skill **writing-plans** để chia nhỏ các task lập trình chi tiết:
- Bước 1: Tạo các thành phần style helper, card component, và styling QSS.
- Bước 2: Tái cấu trúc `ui/controller.py` với `QStackedWidget` và Sidebar điều hướng.
- Bước 3: Hoàn thiện 4 trang (Console, AI Engine, OCR, Subtitle Preview) và kết nối signal.
- Bước 4: Kiểm thử hiển thị, chạy ứng dụng thực tế và nghiệm thu giao diện mới.
