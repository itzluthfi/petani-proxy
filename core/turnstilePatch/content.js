// Turnstile Auto-Solver Fallback Content Script
(() => {
  'use strict';

  function isVisible(el) {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function dismissCookieBanner() {
    try {
      const bannerBtns = Array.from(document.querySelectorAll('button, a, [role="button"]'));
      for (const btn of bannerBtns) {
        const txt = (btn.innerText || btn.textContent || '').trim().toLowerCase();
        if (txt === 'reject all' || txt === 'accept all' || txt === 'accept all cookies' || txt === '全部拒绝' || txt === '全部允许') {
          btn.click();
        }
      }
    } catch (_) {}
  }

  function loopSolver() {
    try {
      dismissCookieBanner();
    } catch (_) {}
  }

  // Interval check for cookie banner
  const timer = setInterval(loopSolver, 1500);

  // Stop checking after 60s
  setTimeout(() => {
    clearInterval(timer);
  }, 60000);

  document.addEventListener('DOMContentLoaded', loopSolver);
  window.addEventListener('load', loopSolver);
})();
