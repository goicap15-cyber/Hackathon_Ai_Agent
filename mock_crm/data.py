# mock_crm/data.py

# 1. Customers mock data (Profile KH)
CUSTOMERS = [
    {
        "id": "KH001",
        "name": "Lê Văn Khang",
        "phone": "091***888",  # Masked for PDPA compliance
        "email": "khang.le***@gmail.com",
        "type": "VIP",
        "savings_balance": 500000000, # 500 million VND
        "savings_due_date": "2026-07-15", # Savings expires on this date
        "current_loan_amount": 2000000000, # 2 billion VND mortgage loan
        "current_loan_type": "Mortgage Loan (Vay mua nhà)",
        "join_date": "2020-03-12"
    },
    {
        "id": "KH002",
        "name": "Trần Thị Bình",
        "phone": "098***999",
        "email": "binh.tran***@yahoo.com",
        "type": "Standard",
        "savings_balance": 150000000, # 150 million VND
        "savings_due_date": "2026-07-12", # Savings expires this week
        "current_loan_amount": 0,
        "current_loan_type": None,
        "join_date": "2022-05-20"
    },
    {
        "id": "KH003",
        "name": "Lê Hoàng Nam",
        "phone": "090***777",
        "email": "nam.le***@hotmail.com",
        "type": "VIP",
        "savings_balance": 1200000000, # 1.2 billion VND
        "savings_due_date": "2026-08-01",
        "current_loan_amount": 100000000, # 100 million credit card loan
        "current_loan_type": "Credit Card",
        "join_date": "2018-11-05"
    },
    {
        "id": "KH004",
        "name": "Phạm Minh Đức",
        "phone": "094***666",
        "email": "duc.pham***@gmail.com",
        "type": "Standard",
        "savings_balance": 50000000, # 50 million VND
        "savings_due_date": "2026-07-14", # Expires this week
        "current_loan_amount": 50000000,
        "current_loan_type": "Personal Loan (Vay tiêu dùng)",
        "join_date": "2023-01-15"
    },
    {
        "id": "KH005",
        "name": "Vũ Thị Thảo",
        "phone": "097***555",
        "email": "thao.vu***@outlook.com",
        "type": "VIP",
        "savings_balance": 3000000000, # 3 billion VND
        "savings_due_date": "2026-07-11", # Expires tomorrow
        "current_loan_amount": 0,
        "current_loan_type": None,
        "join_date": "2019-07-22"
    }
]

# 2. Opportunities mock data (Cơ hội bán hàng)
OPPORTUNITIES = [
    {
        "id": "OPP001",
        "customer_id": "KH001",
        "product_name": "Bảo hiểm nhân thọ liên kết tín dụng (Bancassurance)",
        "stage": "New", # New, Contacting, Closed Won, Closed Lost
        "expected_revenue": 30000000, # 30 million VND annual premium
        "created_date": "2026-07-01",
        "notes": "KH có khoản vay mua nhà lớn (2 tỷ), cần tư vấn bảo hiểm liên kết để phòng ngừa rủi ro tín dụng."
    },
    {
        "id": "OPP002",
        "customer_id": "KH002",
        "product_name": "Thẻ tín dụng Signature Bank A",
        "stage": "Contacting",
        "expected_revenue": 2000000,
        "created_date": "2026-07-05",
        "notes": "KH chuẩn bị đáo hạn tiết kiệm, có thể mời mở thẻ Signature để chi tiêu."
    },
    {
        "id": "OPP003",
        "customer_id": "KH003",
        "product_name": "Gói bảo hiểm sức khỏe Gold Care",
        "stage": "New",
        "expected_revenue": 15000000,
        "created_date": "2026-07-08",
        "notes": "KH VIP có số dư lớn, có nhu cầu bảo vệ sức khỏe gia đình."
    }
]

# 3. Customer Interactions mock data (Lịch sử tương tác)
INTERACTIONS = [
    {
        "id": "INT001",
        "customer_id": "KH001",
        "type": "Call",
        "notes": "Gọi điện chúc mừng sinh nhật KH. KH phản hồi dịch vụ tốt, đang tập trung trả nợ vay mua nhà.",
        "result": "Completed",
        "date": "2026-05-10",
        "rm_name": "Nguyễn Phương Linh"
    },
    {
        "id": "INT002",
        "customer_id": "KH001",
        "type": "Email",
        "notes": "Gửi thông tin sao kê tài khoản vay hàng tháng.",
        "result": "Sent",
        "date": "2026-06-15",
        "rm_name": "Nguyễn Phương Linh"
    },
    {
        "id": "INT003",
        "customer_id": "KH002",
        "type": "Meeting",
        "notes": "Gặp mặt tại quầy giao dịch hỗ trợ thủ tục tất toán một phần sổ tiết kiệm trước hạn.",
        "result": "Completed",
        "date": "2026-06-20",
        "rm_name": "Nguyễn Phương Linh"
    },
    {
        "id": "INT004",
        "customer_id": "KH004",
        "type": "Call",
        "notes": "Gọi điện nhắc nợ vay tiêu dùng đến hạn thanh toán tháng 6. Khách đã thanh toán đầy đủ.",
        "result": "Completed",
        "date": "2026-06-25",
        "rm_name": "Nguyễn Phương Linh"
    }
]

# 4. Campaigns mock data (Chiến dịch marketing)
CAMPAIGNS = [
    {
        "id": "CAMP001",
        "name": "Trọn Đời An Tâm - Bảo vệ gia đình",
        "target_product": "Bảo hiểm nhân thọ liên kết tín dụng",
        "description": "Ưu đãi giảm 10% phí năm đầu tiên cho khách hàng có khoản vay thế chấp từ 1 tỷ trở lên.",
        "active": True
    },
    {
        "id": "CAMP002",
        "name": "Tiết Kiệm Vàng - Đón Lộc Hè",
        "target_product": "Tiết kiệm tích lũy",
        "description": "Cộng thêm 0.2% lãi suất cho khách hàng gia hạn sổ tiết kiệm đến hạn từ 100 triệu trở lên.",
        "active": True
    },
    {
        "id": "CAMP003",
        "name": "Đặc quyền Thẻ Signature",
        "target_product": "Thẻ tín dụng Signature Bank A",
        "description": "Miễn phí thường niên năm đầu và hoàn tiền 10% chi tiêu ẩm thực cho khách hàng VIP.",
        "active": True
    }
]
