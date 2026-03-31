/**
 * QR リンク経由ログイン: /s/login/#token={token}
 */
document.addEventListener("DOMContentLoaded", function () {
  const hash = location.hash;
  if (!hash || !hash.startsWith("#token=")) return;

  const token = decodeURIComponent(hash.substring("#token=".length));
  if (!token) return;

  history.replaceState(null, "", location.pathname + location.search);

  const input = document.querySelector('input[name="token"]');
  const form = input?.closest("form");
  if (input && form) {
    input.value = token;
    form.submit();
  }
});
