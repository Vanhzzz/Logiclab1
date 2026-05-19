# Refund Reference Blackbox Lab

Blackbox CTF lab về lỗi business logic trong luồng refund của một shop giả lập.

## Chạy lab

```bash
unzip refund-ref-mysql-store-cart-lab.zip
cd refund-ref-mysql-store-cart-lab
docker compose up --build
```

Mở trình duyệt:

```text
http://localhost:5000
```

## Tài khoản

```text
user1 / user1
```

## Thông tin chính

- Database: MySQL 8
- Wallet ban đầu: `$100.00`
- Chỉ có một tài khoản user
- Trang chủ dạng product catalog giống giao diện mẫu
- Trang cart có bảng sản phẩm, nút `-`, `+`, `Remove`, coupon và `Place order`
- My account hiển thị coupon giảm 10%: `BLACKBOX10`
- Khi đặt hàng, request checkout là POST body để có thể quan sát bằng Burp
- Mã sản phẩm và mã đơn hàng đều là chuỗi random, không có prefix `prd_` hoặc `ord_`
- Bấm refund sẽ hiện `Wait admin accept...` và tự xử lý sau 5 giây
- Vào chi tiết sản phẩm `$1337.00` sẽ thấy dòng:

```text
The flag will appear when this order is completed.
```

## Giá sản phẩm

```text
Lightweight "l33t" Leather Jacket: $1337.00
Balance Beams: $16.11
High-End Gift Wrapping: $15.77
Giant Pillow Thing: $33.13
WebSec Pro Trial Box: $49.99
```

## Reset lab

Bấm nút `Reset lab` ở góc trái trên cùng để đưa lab về trạng thái ban đầu.

## Mục tiêu

Tìm lỗi business logic trong quy trình refund để tăng wallet, sau đó hoàn tất đơn hàng `$1337.00` và lấy flag.
