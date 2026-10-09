# -*- coding: utf-8 -*-
"""
多国语言包（界面语言）
支持：中文 / English / 日本語 / 한국어 / ไทย / Tiếng Việt / Русский / Français / Deutsch
用法：i18n.t("nav_dashboard", lang)
未翻译的词条自动回退中文；中文未定义则回退 key。
"""
import settings as _settings
import os

LANGUAGES = {
    "zh": "中文",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
    "th": "ไทย",
    "vi": "Tiếng Việt",
    "ru": "Русский",
    "fr": "Français",
    "de": "Deutsch",
}


def tr_json(lang=None):
    """返回当前语言的中文原文 -> 译文 映射（供前端 JS 运行时翻译 window._TRJSON）"""
    if not lang:
        lang = current_lang()
    if lang == "zh":
        return {}
    return _RAW_TR.get(lang, {})

# 中文原文（key -> 中文）
# 词条表从 i18n/ 目录加载（定义与加载见文件尾部 _load_zh / _load_translations）


def _load_zh():
    """从 i18n/zh.json 加载中文原文表（key 式词条），缺失回退空表。"""
    import json as _json
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "i18n", "zh.json"), "r", encoding="utf-8") as _f:
            return _json.load(_f)
    except Exception:
        return {}

# 各语言翻译表（缺失自动回退中文）
_TR = {
    "en": {
        "nav_dashboard": "Dashboard", "nav_locations": "Rack Management",
        "nav_parts_manage": "Parts Master", "nav_parts": "Parts Query",
        "nav_stale": "Stale Parts", "nav_apply": "Stock Applications",
        "nav_inout": "Stock In/Out", "nav_approval": "Valuable Approval",
        "nav_departments": "Departments", "nav_lines": "Lines & Equipment",
        "nav_users": "Users", "nav_permissions": "Permissions",
        "nav_settings": "Settings", "nav_restore": "Backup & Restore",
        "nav_screen_config": "Screen Config", "nav_screen": "Data Screen",
        "nav_recycle": "Recycle Bin", "nav_logout": "Logout",
        "page_dashboard": "Dashboard", "page_parts": "Parts Query",
        "page_parts_manage": "Parts Master", "page_locations": "Rack Management",
        "page_stale": "Stale Parts", "page_applications": "Stock Applications",
        "page_inout": "Stock In/Out", "page_approval": "Valuable Out Approval",
        "page_departments": "Departments", "page_lines": "Lines & Equipment",
        "page_users": "Users", "page_permissions": "Permissions",
        "page_settings": "Settings", "page_restore": "Backup & Restore",
        "page_screen_config": "Screen Config", "page_recycle": "Recycle Bin",
        "page_my_records": "My Applications", "page_transfer": "Transfer Request",
        "page_password": "Change Password", "page_login": "Sign In",
        "btn_search": "Search", "btn_reset": "Reset", "btn_export": "Export",
        "btn_save": "Save", "btn_cancel": "Cancel", "btn_confirm": "Confirm",
        "btn_add": "Add", "btn_edit": "Edit", "btn_delete": "Delete",
        "btn_submit": "Submit", "btn_back": "Back", "btn_close": "Close",
        "btn_ok": "OK", "btn_execute": "Execute", "btn_approve": "Approve",
        "btn_reject": "Reject", "btn_details": "Details", "btn_import": "Import",
        "type_in": "In", "type_out": "Out", "type_transfer": "Transfer",
        "type_adjust": "Move", "type_all": "All",
        "status_pending": "Pending", "status_approved": "Approved",
        "status_rejected": "Rejected", "status_completed": "Completed",
        "status_cancel_req": "Cancel Request", "status_canceled": "Canceled",
        "status_valuable": "Valuable", "status_pending_short": "Held",
        "th_no": "No.", "th_time": "Time", "th_code": "Code", "th_name": "Name",
        "th_type": "Type", "th_quantity": "Qty", "th_location": "Location",
        "th_status": "Status", "th_ops": "Action", "th_remark": "Remark",
        "th_applicant": "Applicant", "th_approver": "Approver", "th_unit": "Unit",
        "th_price": "Price", "th_amount": "Amount", "th_operator": "Operator",
        "th_line": "Line", "th_device": "Device", "th_reason": "Reason",
        "th_total": "Total", "th_date": "Date", "th_part": "Code/Name",
        "fld_username": "Username", "fld_password": "Password", "fld_name": "Name",
        "fld_department": "Department", "fld_role": "Role", "fld_keyword": "Keyword",
        "fld_date_from": "Start Date", "fld_date_to": "End Date",
        "role_admin": "Admin", "role_manager": "Manager", "role_warehouse": "Warehouse",
        "role_user": "User", "role_guest": "Guest",
        "misc_system": "Spare Parts Management System", "misc_login": "Sign In",
        "misc_guest": "Guest", "misc_version": "Internal Deployment",
        "misc_language": "Language", "misc_none": "None", "misc_unknown": "Unknown",
        "misc_welcome": "Welcome", "misc_logout_confirm": "Are you sure to logout?",
        "misc_confirm_delete": "Are you sure to delete?", "misc_yes": "Yes", "misc_no": "No",
        "misc_loading": "Loading...", "misc_required": "Required",
        "misc_no_data": "No Data", "misc_optional": "Optional",
    },
    "ja": {
        "nav_dashboard": "ダッシュボード", "nav_locations": "棚管理",
        "nav_parts_manage": "部品情報管理", "nav_parts": "部品検索",
        "nav_stale": "滞留部品", "nav_apply": "入出庫・棚替申請",
        "nav_inout": "入出庫管理", "nav_approval": "貴重部品出庫承認",
        "nav_departments": "部門設定", "nav_lines": "ライン・設備設定",
        "nav_users": "ユーザー管理", "nav_permissions": "権限設定",
        "nav_settings": "システム設定", "nav_restore": "バックアップ復元",
        "nav_screen_config": "画面設定", "nav_screen": "データ画面",
        "nav_recycle": "ごみ箱", "nav_logout": "ログアウト",
        "page_dashboard": "ダッシュボード", "page_parts": "部品検索",
        "page_parts_manage": "部品情報管理", "page_locations": "棚管理",
        "page_stale": "滞留部品", "page_applications": "入出庫・棚替申請",
        "page_inout": "入出庫管理", "page_approval": "貴重部品出庫承認",
        "page_departments": "部門設定", "page_lines": "ライン・設備設定",
        "page_users": "ユーザー管理", "page_permissions": "権限設定",
        "page_settings": "システム設定", "page_restore": "バックアップ復元",
        "page_screen_config": "画面設定", "page_recycle": "ごみ箱",
        "page_my_records": "自分の申請", "page_transfer": "棚替申請",
        "page_password": "パスワード変更", "page_login": "ログイン",
        "btn_search": "検索", "btn_reset": "リセット", "btn_export": "エクスポート",
        "btn_save": "保存", "btn_cancel": "キャンセル", "btn_confirm": "確認",
        "btn_add": "追加", "btn_edit": "編集", "btn_delete": "削除",
        "btn_submit": "送信", "btn_back": "戻る", "btn_close": "閉じる",
        "btn_ok": "OK", "btn_execute": "実行", "btn_approve": "承認",
        "btn_reject": "却下", "btn_details": "詳細", "btn_import": "インポート",
        "type_in": "入庫", "type_out": "出庫", "type_transfer": "棚替",
        "type_adjust": "位置調整", "type_all": "すべて",
        "status_pending": "処理待ち", "status_approved": "承認済み",
        "status_rejected": "却下済み", "status_completed": "完了",
        "status_cancel_req": "取消承認待ち", "status_canceled": "取消済み",
        "status_valuable": "貴重", "status_pending_short": "保留",
        "th_no": "番号", "th_time": "時間", "th_code": "品番", "th_name": "名称",
        "th_type": "種別", "th_quantity": "数量", "th_location": "保管場所",
        "th_status": "状態", "th_ops": "操作", "th_remark": "備考",
        "th_applicant": "申請者", "th_approver": "承認者", "th_unit": "単位",
        "th_price": "単価", "th_amount": "金額(円)", "th_operator": "操作者",
        "th_line": "ライン", "th_device": "設備", "th_reason": "理由",
        "th_total": "合計", "th_date": "日付", "th_part": "品番/名称",
        "fld_username": "ユーザー名", "fld_password": "パスワード", "fld_name": "氏名",
        "fld_department": "部門", "fld_role": "役割", "fld_keyword": "キーワード",
        "fld_date_from": "開始日", "fld_date_to": "終了日",
        "role_admin": "管理者", "role_manager": "管理者(部長)", "role_warehouse": "倉庫",
        "role_user": "一般", "role_guest": "ゲスト",
        "misc_system": "部品管理システム", "misc_login": "ログイン",
        "misc_guest": "ゲスト", "misc_version": "社内展開",
        "misc_language": "言語", "misc_none": "なし", "misc_unknown": "不明",
        "misc_welcome": "ようこそ", "misc_logout_confirm": "ログアウトしますか？",
        "misc_confirm_delete": "削除しますか？", "misc_yes": "はい", "misc_no": "いいえ",
        "misc_loading": "読み込み中…", "misc_required": "必須",
        "misc_no_data": "データなし", "misc_optional": "任意",
    },
    "ko": {
        "nav_dashboard": "대시보드", "nav_locations": "랙 관리",
        "nav_parts_manage": "부품 정보 관리", "nav_parts": "부품 조회",
        "nav_stale": "지체 자재", "nav_apply": "입출고·이동 신청",
        "nav_inout": "입출고 관리", "nav_approval": "고가 부품 출고 승인",
        "nav_departments": "부서 설정", "nav_lines": "라인·설비 설정",
        "nav_users": "사용자 관리", "nav_permissions": "권한 설정",
        "nav_settings": "시스템 설정", "nav_restore": "백업 복원",
        "nav_screen_config": "화면 설정", "nav_screen": "데이터 화면",
        "nav_recycle": "휴지통", "nav_logout": "로그아웃",
        "page_dashboard": "대시보드", "page_parts": "부품 조회",
        "page_parts_manage": "부품 정보 관리", "page_locations": "랙 관리",
        "page_stale": "지체 자재", "page_applications": "입출고·이동 신청",
        "page_inout": "입출고 관리", "page_approval": "고가 부품 출고 승인",
        "page_departments": "부서 설정", "page_lines": "라인·설비 설정",
        "page_users": "사용자 관리", "page_permissions": "권한 설정",
        "page_settings": "시스템 설정", "page_restore": "백업 복원",
        "page_screen_config": "화면 설정", "page_recycle": "휴지통",
        "page_my_records": "내 신청 내역", "page_transfer": "이동 신청",
        "page_password": "비밀번호 변경", "page_login": "로그인",
        "btn_search": "검색", "btn_reset": "초기화", "btn_export": "내보내기",
        "btn_save": "저장", "btn_cancel": "취소", "btn_confirm": "확인",
        "btn_add": "추가", "btn_edit": "편집", "btn_delete": "삭제",
        "btn_submit": "제출", "btn_back": "뒤로", "btn_close": "닫기",
        "btn_ok": "확인", "btn_execute": "실행", "btn_approve": "승인",
        "btn_reject": "반려", "btn_details": "상세", "btn_import": "가져오기",
        "type_in": "입고", "type_out": "출고", "type_transfer": "이동",
        "type_adjust": "위치 조정", "type_all": "전체",
        "status_pending": "처리 대기", "status_approved": "승인됨",
        "status_rejected": "반려됨", "status_completed": "완료",
        "status_cancel_req": "취소 승인 대기", "status_canceled": "취소됨",
        "status_valuable": "고가", "status_pending_short": "보류",
        "th_no": "번호", "th_time": "시간", "th_code": "품번", "th_name": "명칭",
        "th_type": "유형", "th_quantity": "수량", "th_location": "위치",
        "th_status": "상태", "th_ops": "작업", "th_remark": "비고",
        "th_applicant": "신청자", "th_approver": "승인자", "th_unit": "단위",
        "th_price": "단가", "th_amount": "금액(원)", "th_operator": "작업자",
        "th_line": "라인", "th_device": "설비", "th_reason": "사유",
        "th_total": "합계", "th_date": "날짜", "th_part": "품번/명칭",
        "fld_username": "사용자명", "fld_password": "비밀번호", "fld_name": "이름",
        "fld_department": "부서", "fld_role": "역할", "fld_keyword": "키워드",
        "fld_date_from": "시작일", "fld_date_to": "종료일",
        "role_admin": "관리자", "role_manager": "매니저", "role_warehouse": "창고",
        "role_user": "일반", "role_guest": "게스트",
        "misc_system": "부품 관리 시스템", "misc_login": "로그인",
        "misc_guest": "게스트", "misc_version": "사내 배포",
        "misc_language": "언어", "misc_none": "없음", "misc_unknown": "알 수 없음",
        "misc_welcome": "환영합니다", "misc_logout_confirm": "로그아웃 하시겠습니까?",
        "misc_confirm_delete": "삭제하시겠습니까?", "misc_yes": "예", "misc_no": "아니오",
        "misc_loading": "로딩 중…", "misc_required": "필수",
        "misc_no_data": "데이터 없음", "misc_optional": "선택",
    },
    "th": {
        "nav_dashboard": "แดชบอร์ด", "nav_locations": "จัดการชั้นวาง",
        "nav_parts_manage": "จัดการข้อมูลอะไหล่", "nav_parts": "ค้นหาอะไหล่",
        "nav_stale": "อะไหล่ค้าง", "nav_apply": "คำขอเบิก-จ่าย/ย้าย",
        "nav_inout": "จัดการเบิก-จ่าย", "nav_approval": "อนุมัติเบิกอะไหล่มีค่า",
        "nav_departments": "ตั้งค่าแผนก", "nav_lines": "ตั้งค่าไลน์/เครื่องจักร",
        "nav_users": "จัดการผู้ใช้", "nav_permissions": "ตั้งค่าสิทธิ์",
        "nav_settings": "ตั้งค่าระบบ", "nav_restore": "สำรอง/กู้คืน",
        "nav_screen_config": "ตั้งค่าจอแสดงผล", "nav_screen": "จอแสดงผล",
        "nav_recycle": "ถังขยะ", "nav_logout": "ออกจากระบบ",
        "page_dashboard": "แดชบอร์ด", "page_parts": "ค้นหาอะไหล่",
        "page_parts_manage": "จัดการข้อมูลอะไหล่", "page_locations": "จัดการชั้นวาง",
        "page_stale": "อะไหล่ค้าง", "page_applications": "คำขอเบิก-จ่าย/ย้าย",
        "page_inout": "จัดการเบิก-จ่าย", "page_approval": "อนุมัติเบิกอะไหล่มีค่า",
        "page_departments": "ตั้งค่าแผนก", "page_lines": "ตั้งค่าไลน์/เครื่องจักร",
        "page_users": "จัดการผู้ใช้", "page_permissions": "ตั้งค่าสิทธิ์",
        "page_settings": "ตั้งค่าระบบ", "page_restore": "สำรอง/กู้คืน",
        "page_screen_config": "ตั้งค่าจอแสดงผล", "page_recycle": "ถังขยะ",
        "page_my_records": "บันทึกคำขอของฉัน", "page_transfer": "คำขอย้าย",
        "page_password": "เปลี่ยนรหัสผ่าน", "page_login": "เข้าสู่ระบบ",
        "btn_search": "ค้นหา", "btn_reset": "รีเซ็ต", "btn_export": "ส่งออก",
        "btn_save": "บันทึก", "btn_cancel": "ยกเลิก", "btn_confirm": "ยืนยัน",
        "btn_add": "เพิ่ม", "btn_edit": "แก้ไข", "btn_delete": "ลบ",
        "btn_submit": "ส่ง", "btn_back": "ย้อนกลับ", "btn_close": "ปิด",
        "btn_ok": "ตกลง", "btn_execute": "ดำเนินการ", "btn_approve": "อนุมัติ",
        "btn_reject": "ไม่อนุมัติ", "btn_details": "รายละเอียด", "btn_import": "นำเข้า",
        "type_in": "รับเข้า", "type_out": "เบิกออก", "type_transfer": "ย้าย",
        "type_adjust": "ปรับตำแหน่ง", "type_all": "ทั้งหมด",
        "status_pending": "รอดำเนินการ", "status_approved": "อนุมัติแล้ว",
        "status_rejected": "ไม่อนุมัติแล้ว", "status_completed": "เสร็จสิ้น",
        "status_cancel_req": "รออนุมัติยกเลิก", "status_canceled": "ยกเลิกแล้ว",
        "status_valuable": "มีค่า", "status_pending_short": "พักไว้",
        "th_no": "เลขที่", "th_time": "เวลา", "th_code": "รหัส", "th_name": "ชื่อ",
        "th_type": "ประเภท", "th_quantity": "จำนวน", "th_location": "ตำแหน่ง",
        "th_status": "สถานะ", "th_ops": "จัดการ", "th_remark": "หมายเหตุ",
        "th_applicant": "ผู้ขอ", "th_approver": "ผู้อนุมัติ", "th_unit": "หน่วย",
        "th_price": "ราคา", "th_amount": "จำนวนเงิน", "th_operator": "ผู้ดำเนินการ",
        "th_line": "ไลน์", "th_device": "เครื่องจักร", "th_reason": "เหตุผล",
        "th_total": "รวม", "th_date": "วันที่", "th_part": "รหัส/ชื่อ",
        "fld_username": "ชื่อผู้ใช้", "fld_password": "รหัสผ่าน", "fld_name": "ชื่อ",
        "fld_department": "แผนก", "fld_role": "บทบาท", "fld_keyword": "คำค้น",
        "fld_date_from": "วันที่เริ่ม", "fld_date_to": "วันที่สิ้นสุด",
        "role_admin": "ผู้ดูแลระบบ", "role_manager": "ผู้จัดการ", "role_warehouse": "คลัง",
        "role_user": "ผู้ใช้ทั่วไป", "role_guest": "แขก",
        "misc_system": "ระบบจัดการอะไหล่", "misc_login": "เข้าสู่ระบบ",
        "misc_guest": "แขก", "misc_version": "ติดตั้งในองค์กร",
        "misc_language": "ภาษา", "misc_none": "ไม่มี", "misc_unknown": "ไม่ทราบ",
        "misc_welcome": "ยินดีต้อนรับ", "misc_logout_confirm": "ยืนยันออกจากระบบ?",
        "misc_confirm_delete": "ยืนยันการลบ?", "misc_yes": "ใช่", "misc_no": "ไม่",
        "misc_loading": "กำลังโหลด…", "misc_required": "จำเป็น",
        "misc_no_data": "ไม่มีข้อมูล", "misc_optional": "ไม่บังคับ",
    },
    "vi": {
        "nav_dashboard": "Bảng điều khiển", "nav_locations": "Quản lý kệ",
        "nav_parts_manage": "Quản lý phụ tùng", "nav_parts": "Tra cứu phụ tùng",
        "nav_stale": "Vật tư tồn lâu", "nav_apply": "Yêu cầu nhập-xuất/di chuyển",
        "nav_inout": "Quản lý nhập/xuất", "nav_approval": "Duyệt xuất phụ tùng giá trị",
        "nav_departments": "Cấu hình phòng ban", "nav_lines": "Cấu hình line/thiết bị",
        "nav_users": "Quản lý người dùng", "nav_permissions": "Cấu hình quyền",
        "nav_settings": "Cài đặt hệ thống", "nav_restore": "Sao lưu/phục hồi",
        "nav_screen_config": "Cấu hình màn hình", "nav_screen": "Màn hình dữ liệu",
        "nav_recycle": "Thùng rác", "nav_logout": "Đăng xuất",
        "page_dashboard": "Bảng điều khiển", "page_parts": "Tra cứu phụ tùng",
        "page_parts_manage": "Quản lý phụ tùng", "page_locations": "Quản lý kệ",
        "page_stale": "Vật tư tồn lâu", "page_applications": "Yêu cầu nhập-xuất/di chuyển",
        "page_inout": "Quản lý nhập/xuất", "page_approval": "Duyệt xuất phụ tùng giá trị",
        "page_departments": "Cấu hình phòng ban", "page_lines": "Cấu hình line/thiết bị",
        "page_users": "Quản lý người dùng", "page_permissions": "Cấu hình quyền",
        "page_settings": "Cài đặt hệ thống", "page_restore": "Sao lưu/phục hồi",
        "page_screen_config": "Cấu hình màn hình", "page_recycle": "Thùng rác",
        "page_my_records": "Yêu cầu của tôi", "page_transfer": "Yêu cầu di chuyển",
        "page_password": "Đổi mật khẩu", "page_login": "Đăng nhập",
        "btn_search": "Tìm kiếm", "btn_reset": "Đặt lại", "btn_export": "Xuất",
        "btn_save": "Lưu", "btn_cancel": "Hủy", "btn_confirm": "Xác nhận",
        "btn_add": "Thêm", "btn_edit": "Sửa", "btn_delete": "Xóa",
        "btn_submit": "Gửi", "btn_back": "Quay lại", "btn_close": "Đóng",
        "btn_ok": "OK", "btn_execute": "Thực hiện", "btn_approve": "Duyệt",
        "btn_reject": "Từ chối", "btn_details": "Chi tiết", "btn_import": "Nhập",
        "type_in": "Nhập", "type_out": "Xuất", "type_transfer": "Di chuyển",
        "type_adjust": "Điều chỉnh vị trí", "type_all": "Tất cả",
        "status_pending": "Đang xử lý", "status_approved": "Đã duyệt",
        "status_rejected": "Đã từ chối", "status_completed": "Hoàn thành",
        "status_cancel_req": "Chờ duyệt hủy", "status_canceled": "Đã hủy",
        "status_valuable": "Giá trị", "status_pending_short": "Tạm giữ",
        "th_no": "Số", "th_time": "Thời gian", "th_code": "Mã", "th_name": "Tên",
        "th_type": "Loại", "th_quantity": "Số lượng", "th_location": "Vị trí",
        "th_status": "Trạng thái", "th_ops": "Thao tác", "th_remark": "Ghi chú",
        "th_applicant": "Người yêu cầu", "th_approver": "Người duyệt", "th_unit": "Đơn vị",
        "th_price": "Đơn giá", "th_amount": "Thành tiền", "th_operator": "Người thao tác",
        "th_line": "Line", "th_device": "Thiết bị", "th_reason": "Lý do",
        "th_total": "Tổng", "th_date": "Ngày", "th_part": "Mã/Tên",
        "fld_username": "Tên đăng nhập", "fld_password": "Mật khẩu", "fld_name": "Họ tên",
        "fld_department": "Phòng ban", "fld_role": "Vai trò", "fld_keyword": "Từ khóa",
        "fld_date_from": "Từ ngày", "fld_date_to": "Đến ngày",
        "role_admin": "Quản trị", "role_manager": "Quản lý", "role_warehouse": "Kho",
        "role_user": "Người dùng", "role_guest": "Khách",
        "misc_system": "Hệ thống quản lý phụ tùng", "misc_login": "Đăng nhập",
        "misc_guest": "Khách", "misc_version": "Triển khai nội bộ",
        "misc_language": "Ngôn ngữ", "misc_none": "Không", "misc_unknown": "Không rõ",
        "misc_welcome": "Chào mừng", "misc_logout_confirm": "Xác nhận đăng xuất?",
        "misc_confirm_delete": "Xác nhận xóa?", "misc_yes": "Có", "misc_no": "Không",
        "misc_loading": "Đang tải…", "misc_required": "Bắt buộc",
        "misc_no_data": "Không có dữ liệu", "misc_optional": "Tùy chọn",
    },
    "ru": {
        "nav_dashboard": "Панель", "nav_locations": "Управление стеллажами",
        "nav_parts_manage": "Справочник запчастей", "nav_parts": "Поиск запчастей",
        "nav_stale": "Залежалые детали", "nav_apply": "Заявки приём/выдача/перемещение",
        "nav_inout": "Приём/выдача", "nav_approval": "Согласование выдачи ценных",
        "nav_departments": "Отделы", "nav_lines": "Линии и оборудование",
        "nav_users": "Пользователи", "nav_permissions": "Права доступа",
        "nav_settings": "Настройки", "nav_restore": "Резервное копирование",
        "nav_screen_config": "Настройка экрана", "nav_screen": "Экран данных",
        "nav_recycle": "Корзина", "nav_logout": "Выход",
        "page_dashboard": "Панель", "page_parts": "Поиск запчастей",
        "page_parts_manage": "Справочник запчастей", "page_locations": "Управление стеллажами",
        "page_stale": "Залежалые детали", "page_applications": "Заявки приём/выдача/перемещение",
        "page_inout": "Приём/выдача", "page_approval": "Согласование выдачи ценных",
        "page_departments": "Отделы", "page_lines": "Линии и оборудование",
        "page_users": "Пользователи", "page_permissions": "Права доступа",
        "page_settings": "Настройки", "page_restore": "Резервное копирование",
        "page_screen_config": "Настройка экрана", "page_recycle": "Корзина",
        "page_my_records": "Мои заявки", "page_transfer": "Заявка на перемещение",
        "page_password": "Смена пароля", "page_login": "Вход",
        "btn_search": "Найти", "btn_reset": "Сброс", "btn_export": "Экспорт",
        "btn_save": "Сохранить", "btn_cancel": "Отмена", "btn_confirm": "Подтвердить",
        "btn_add": "Добавить", "btn_edit": "Изменить", "btn_delete": "Удалить",
        "btn_submit": "Отправить", "btn_back": "Назад", "btn_close": "Закрыть",
        "btn_ok": "OK", "btn_execute": "Выполнить", "btn_approve": "Согласовать",
        "btn_reject": "Отклонить", "btn_details": "Детали", "btn_import": "Импорт",
        "type_in": "Приём", "type_out": "Выдача", "type_transfer": "Перемещение",
        "type_adjust": "Перестановка", "type_all": "Все",
        "status_pending": "Ожидает", "status_approved": "Согласовано",
        "status_rejected": "Отклонено", "status_completed": "Выполнено",
        "status_cancel_req": "Запрос отмены", "status_canceled": "Отменено",
        "status_valuable": "Ценный", "status_pending_short": "На удержании",
        "th_no": "№", "th_time": "Время", "th_code": "Код", "th_name": "Название",
        "th_type": "Тип", "th_quantity": "Кол-во", "th_location": "Место",
        "th_status": "Статус", "th_ops": "Действия", "th_remark": "Примечание",
        "th_applicant": "Заявитель", "th_approver": "Согласующий", "th_unit": "Ед.",
        "th_price": "Цена", "th_amount": "Сумма", "th_operator": "Оператор",
        "th_line": "Линия", "th_device": "Оборуд.", "th_reason": "Причина",
        "th_total": "Итого", "th_date": "Дата", "th_part": "Код/Название",
        "fld_username": "Имя пользователя", "fld_password": "Пароль", "fld_name": "Имя",
        "fld_department": "Отдел", "fld_role": "Роль", "fld_keyword": "Ключевое слово",
        "fld_date_from": "Начало", "fld_date_to": "Конец",
        "role_admin": "Администратор", "role_manager": "Руководитель", "role_warehouse": "Склад",
        "role_user": "Пользователь", "role_guest": "Гость",
        "misc_system": "Система управления запчастями", "misc_login": "Вход",
        "misc_guest": "Гость", "misc_version": "Внутреннее развёртывание",
        "misc_language": "Язык", "misc_none": "Нет", "misc_unknown": "Неизвестно",
        "misc_welcome": "Добро пожаловать", "misc_logout_confirm": "Выйти из системы?",
        "misc_confirm_delete": "Подтвердить удаление?", "misc_yes": "Да", "misc_no": "Нет",
        "misc_loading": "Загрузка…", "misc_required": "Обязательно",
        "misc_no_data": "Нет данных", "misc_optional": "Необязательно",
    },
    "fr": {
        "nav_dashboard": "Tableau de bord", "nav_locations": "Gestion des rayonnages",
        "nav_parts_manage": "Fiche pièces", "nav_parts": "Recherche pièces",
        "nav_stale": "Pièces dormantes", "nav_apply": "Demandes entrée/sortie/transfert",
        "nav_inout": "Entrée/Sortie", "nav_approval": "Approbation sortie pièces de valeur",
        "nav_departments": "Départements", "nav_lines": "Lignes & équipements",
        "nav_users": "Utilisateurs", "nav_permissions": "Permissions",
        "nav_settings": "Paramètres", "nav_restore": "Sauvegarde & restauration",
        "nav_screen_config": "Config écran", "nav_screen": "Écran de données",
        "nav_recycle": "Corbeille", "nav_logout": "Déconnexion",
        "page_dashboard": "Tableau de bord", "page_parts": "Recherche pièces",
        "page_parts_manage": "Fiche pièces", "page_locations": "Gestion des rayonnages",
        "page_stale": "Pièces dormantes", "page_applications": "Demandes entrée/sortie/transfert",
        "page_inout": "Entrée/Sortie", "page_approval": "Approbation sortie pièces de valeur",
        "page_departments": "Départements", "page_lines": "Lignes & équipements",
        "page_users": "Utilisateurs", "page_permissions": "Permissions",
        "page_settings": "Paramètres", "page_restore": "Sauvegarde & restauration",
        "page_screen_config": "Config écran", "page_recycle": "Corbeille",
        "page_my_records": "Mes demandes", "page_transfer": "Demande de transfert",
        "page_password": "Changer le mot de passe", "page_login": "Connexion",
        "btn_search": "Rechercher", "btn_reset": "Réinitialiser", "btn_export": "Exporter",
        "btn_save": "Enregistrer", "btn_cancel": "Annuler", "btn_confirm": "Confirmer",
        "btn_add": "Ajouter", "btn_edit": "Modifier", "btn_delete": "Supprimer",
        "btn_submit": "Envoyer", "btn_back": "Retour", "btn_close": "Fermer",
        "btn_ok": "OK", "btn_execute": "Exécuter", "btn_approve": "Approuver",
        "btn_reject": "Rejeter", "btn_details": "Détails", "btn_import": "Importer",
        "type_in": "Entrée", "type_out": "Sortie", "type_transfer": "Transfert",
        "type_adjust": "Déplacement", "type_all": "Tous",
        "status_pending": "En attente", "status_approved": "Approuvé",
        "status_rejected": "Rejeté", "status_completed": "Terminé",
        "status_cancel_req": "Demande d'annulation", "status_canceled": "Annulé",
        "status_valuable": "De valeur", "status_pending_short": "En retenue",
        "th_no": "N°", "th_time": "Heure", "th_code": "Code", "th_name": "Nom",
        "th_type": "Type", "th_quantity": "Qté", "th_location": "Emplacement",
        "th_status": "Statut", "th_ops": "Actions", "th_remark": "Remarque",
        "th_applicant": "Demandeur", "th_approver": "Approbateur", "th_unit": "Unité",
        "th_price": "Prix", "th_amount": "Montant", "th_operator": "Opérateur",
        "th_line": "Ligne", "th_device": "Équipement", "th_reason": "Motif",
        "th_total": "Total", "th_date": "Date", "th_part": "Code/Nom",
        "fld_username": "Nom d'utilisateur", "fld_password": "Mot de passe", "fld_name": "Nom",
        "fld_department": "Département", "fld_role": "Rôle", "fld_keyword": "Mot-clé",
        "fld_date_from": "Date début", "fld_date_to": "Date fin",
        "role_admin": "Administrateur", "role_manager": "Responsable", "role_warehouse": "Magasin",
        "role_user": "Utilisateur", "role_guest": "Invité",
        "misc_system": "Système de gestion des pièces de rechange", "misc_login": "Connexion",
        "misc_guest": "Invité", "misc_version": "Déploiement interne",
        "misc_language": "Langue", "misc_none": "Aucun", "misc_unknown": "Inconnu",
        "misc_welcome": "Bienvenue", "misc_logout_confirm": "Confirmer la déconnexion?",
        "misc_confirm_delete": "Confirmer la suppression?", "misc_yes": "Oui", "misc_no": "Non",
        "misc_loading": "Chargement…", "misc_required": "Obligatoire",
        "misc_no_data": "Aucune donnée", "misc_optional": "Facultatif",
    },
    "de": {
        "nav_dashboard": "Dashboard", "nav_locations": "Regalverwaltung",
        "nav_parts_manage": "Teilestamm", "nav_parts": "Teilesuche",
        "nav_stale": "Langsamdreher", "nav_apply": "Anträge Ein/Aus/Umlagerung",
        "nav_inout": "Ein-/Ausgang", "nav_approval": "Freigabe wertvolle Teile",
        "nav_departments": "Abteilungen", "nav_lines": "Linien & Anlagen",
        "nav_users": "Benutzer", "nav_permissions": "Berechtigungen",
        "nav_settings": "Einstellungen", "nav_restore": "Sicherung & Wiederherstellung",
        "nav_screen_config": "Bildschirm-Konfig.", "nav_screen": "Daten-Screen",
        "nav_recycle": "Papierkorb", "nav_logout": "Abmelden",
        "page_dashboard": "Dashboard", "page_parts": "Teilesuche",
        "page_parts_manage": "Teilestamm", "page_locations": "Regalverwaltung",
        "page_stale": "Langsamdreher", "page_applications": "Anträge Ein/Aus/Umlagerung",
        "page_inout": "Ein-/Ausgang", "page_approval": "Freigabe wertvolle Teile",
        "page_departments": "Abteilungen", "page_lines": "Linien & Anlagen",
        "page_users": "Benutzer", "page_permissions": "Berechtigungen",
        "page_settings": "Einstellungen", "page_restore": "Sicherung & Wiederherstellung",
        "page_screen_config": "Bildschirm-Konfig.", "page_recycle": "Papierkorb",
        "page_my_records": "Meine Anträge", "page_transfer": "Umlagerungsantrag",
        "page_password": "Passwort ändern", "page_login": "Anmelden",
        "btn_search": "Suchen", "btn_reset": "Zurücksetzen", "btn_export": "Exportieren",
        "btn_save": "Speichern", "btn_cancel": "Abbrechen", "btn_confirm": "Bestätigen",
        "btn_add": "Hinzufügen", "btn_edit": "Bearbeiten", "btn_delete": "Löschen",
        "btn_submit": "Senden", "btn_back": "Zurück", "btn_close": "Schließen",
        "btn_ok": "OK", "btn_execute": "Ausführen", "btn_approve": "Genehmigen",
        "btn_reject": "Ablehnen", "btn_details": "Details", "btn_import": "Importieren",
        "type_in": "Eingang", "type_out": "Ausgang", "type_transfer": "Umlagerung",
        "type_adjust": "Positionswechsel", "type_all": "Alle",
        "status_pending": "Offen", "status_approved": "Genehmigt",
        "status_rejected": "Abgelehnt", "status_completed": "Abgeschlossen",
        "status_cancel_req": "Storno-Anfrage", "status_canceled": "Storniert",
        "status_valuable": "Wertvoll", "status_pending_short": "Zurückgehalten",
        "th_no": "Nr.", "th_time": "Zeit", "th_code": "Code", "th_name": "Name",
        "th_type": "Typ", "th_quantity": "Menge", "th_location": "Lagerort",
        "th_status": "Status", "th_ops": "Aktion", "th_remark": "Bemerkung",
        "th_applicant": "Antragsteller", "th_approver": "Genehmiger", "th_unit": "Einheit",
        "th_price": "Preis", "th_amount": "Betrag", "th_operator": "Bearbeiter",
        "th_line": "Linie", "th_device": "Anlage", "th_reason": "Grund",
        "th_total": "Summe", "th_date": "Datum", "th_part": "Code/Name",
        "fld_username": "Benutzername", "fld_password": "Passwort", "fld_name": "Name",
        "fld_department": "Abteilung", "fld_role": "Rolle", "fld_keyword": "Stichwort",
        "fld_date_from": "Startdatum", "fld_date_to": "Enddatum",
        "role_admin": "Administrator", "role_manager": "Leiter", "role_warehouse": "Lager",
        "role_user": "Benutzer", "role_guest": "Gast",
        "misc_system": "Ersatzteil-Managementsystem", "misc_login": "Anmelden",
        "misc_guest": "Gast", "misc_version": "Interner Betrieb",
        "misc_language": "Sprache", "misc_none": "Keine", "misc_unknown": "Unbekannt",
        "misc_welcome": "Willkommen", "misc_logout_confirm": "Abmelden?",
        "misc_confirm_delete": "Löschen bestätigen?", "misc_yes": "Ja", "misc_no": "Nein",
        "misc_loading": "Laden…", "misc_required": "Pflichtfeld",
        "misc_no_data": "Keine Daten", "misc_optional": "Optional",
    },
}

# 原文词条表（key 即中文原文；供运行时/模板按中文查找翻译）
_ZH = {}
_RAW_TR = {}

def _load_zh():
    """从 i18n/zh.json 加载中文原文表（key 式词条），缺失回退空表。"""
    import json as _json
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "i18n", "zh.json"), "r", encoding="utf-8") as _f:
            return _json.load(_f)
    except Exception:
        return {}

def _load_translations():
    """从 i18n/ 目录加载 8 语言翻译表（中文原文作 key，缺文件回退空表）。"""
    import json as _json
    _dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "i18n")
    out = {}
    for _lang in ("en", "ja", "ko", "th", "vi", "ru", "fr", "de"):
        try:
            with open(os.path.join(_dir, _lang + ".json"), "r", encoding="utf-8") as _f:
                out[_lang] = _json.load(_f)
        except Exception:
            out[_lang] = {}
    return out

_ZH = _load_zh()
_RAW_TR = _load_translations()

def _load_translations():
    """从 i18n/ 目录加载 8 语言翻译表（中文原文作 key，缺文件回退空表）。"""
    import json as _json
    _dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "i18n")
    out = {}
    for _lang in ("en", "ja", "ko", "th", "vi", "ru", "fr", "de"):
        try:
            with open(os.path.join(_dir, _lang + ".json"), "r", encoding="utf-8") as _f:
                out[_lang] = _json.load(_f)
        except Exception:
            out[_lang] = {}
    return out



_LANG_REQUEST_CACHE = "_i18n_lang"

def current_lang():
    """当前界面语言：优先当前会话选择，否则取系统设置默认（默认中文）。
    同一请求内只解析一次（flask.g 每请求自动清空），避免每个词条重复读 settings.json。"""
    try:
        from flask import g, session
        cached = getattr(g, _LANG_REQUEST_CACHE, None)
        if cached is not None:
            return cached
        lang = session.get("lang", "")
        if not lang:
            try:
                lang = _settings.load().get("language") or "zh"
            except Exception:
                lang = "zh"
        if lang not in LANGUAGES:
            lang = "zh"
        try:
            setattr(g, _LANG_REQUEST_CACHE, lang)
        except Exception:
            pass
        return lang
    except Exception:
        # 请求上下文不可用时（如后台线程/脚本）走无缓存路径
        lang = ""
        try:
            lang = _settings.load().get("language") or "zh"
        except Exception:
            lang = "zh"
        if lang not in LANGUAGES:
            lang = "zh"
        return lang


def t(key, lang=None, **fmt):
    """按当前语言返回文本；缺失回退中文，再缺失回退 key。
    词条含 {n} 等占位符时，可通过 fmt 传入变量格式化（如 t('x', n=5)）。"""
    if not lang:
        lang = current_lang()
    if lang == "zh":
        v = _ZH.get(key, key)
    else:
        table = _TR.get(lang, {})
        v = table.get(key)
        if v is None:
            raw = _RAW_TR.get(lang, {})
            v = raw.get(key)
        if v is None:
            v = _ZH.get(key, key)
    if fmt and "{" in v:
        try:
            return v.format(**fmt)
        except (KeyError, IndexError, ValueError):
            return v
    return v
