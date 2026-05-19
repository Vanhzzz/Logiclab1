function setText(id, text, cls) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.className = 'result-box ' + (cls || '');
}

async function postJson(url, data) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || 'Request failed');
  return body;
}

const refundBtn = document.getElementById('refund-btn');
if (refundBtn) {
  refundBtn.addEventListener('click', async () => {
    const wait = document.getElementById('refund-wait');
    const orderRef = refundBtn.dataset.orderRef;
    const productRef = refundBtn.dataset.productRef;
    const reason = (document.getElementById('refund-reason')?.value || 'Payment issue').trim();

    refundBtn.disabled = true;
    wait.classList.remove('hidden');
    setText('refund-result', '', '');

    try {
      const created = await postJson('/api/refund/request', {
        product_ref: productRef,
        order_ref: orderRef,
        reason: reason
      });

      const poll = async () => {
        const res = await fetch('/api/refund/status/' + encodeURIComponent(created.refund_ref));
        const status = await res.json();
        if (status.status === 'PENDING') {
          setTimeout(poll, 1000);
          return;
        }
        wait.classList.add('hidden');
        setText('refund-result', 'Refund ' + status.status + '. Amount: ' + status.refund_amount + '. Wallet: ' + status.wallet, 'success');
        setTimeout(() => window.location.reload(), 1200);
      };
      setTimeout(poll, 1000);
    } catch (err) {
      wait.classList.add('hidden');
      refundBtn.disabled = false;
      setText('refund-result', err.message, 'error');
    }
  });
}

const completeBtn = document.getElementById('complete-order-btn');
if (completeBtn) {
  completeBtn.addEventListener('click', async () => {
    completeBtn.disabled = true;
    setText('complete-result', 'Completing order...', '');
    try {
      const out = await postJson('/api/order/complete', {
        order_ref: completeBtn.dataset.orderRef
      });
      setText('complete-result', out.flag || out.message, 'success');
      setTimeout(() => window.location.reload(), 900);
    } catch (err) {
      completeBtn.disabled = false;
      setText('complete-result', err.message, 'error');
    }
  });
}
