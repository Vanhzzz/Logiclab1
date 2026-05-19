# Writeup ngắn

## Lỗ hổng

Business logic flaw trong refund: backend dùng `product_ref` do client gửi để tính tiền hoàn, thay vì dùng `amount_cents` của order gốc.

## Khai thác

1. Đăng nhập `user1 / user1`.
2. Mở sản phẩm `$1337.00` và lấy reference của sản phẩm từ URL hoặc request `/cart/add` bằng Burp.
3. Vào `My account` lấy coupon `BLACKBOX10`.
4. Mua một sản phẩm rẻ, ví dụ `Balance Beams`.
5. Mở đơn vừa mua, bật Burp Intercept.
6. Bấm `Request refund`.
7. Sửa `product_ref` trong JSON refund thành reference của sản phẩm `$1337.00`.
8. Forward request và chờ 5 giây.
9. Wallet được cộng `$1337.00` thay vì giá đơn rẻ.
10. Mua sản phẩm `$1337.00` để nhận flag.

## Fix

Refund phải lấy số tiền từ order trong database:

```text
refund_amount = order.amount_cents
```

Không nhận `product_ref`, `amount`, hoặc dữ liệu tính tiền từ client trong luồng refund.
