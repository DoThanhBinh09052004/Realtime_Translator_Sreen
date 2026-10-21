def test_navigation_keeps_four_existing_pages(ui_window):
    assert ui_window.pages.count() == 4
    assert [item[1] for item in ui_window.nav_item_defs] == [
        'Tổng quan', 'Cấu hình AI', 'Dịch thuật & OCR', 'Giao diện Phụ đề']
    for index in (3, 1, 2, 0, 3, 0):
        ui_window.nav_buttons[index].click()
        assert ui_window.pages.currentIndex() == index
    ui_window.on_select_region_cb.assert_not_called()
    ui_window.on_quit_cb.assert_not_called()
