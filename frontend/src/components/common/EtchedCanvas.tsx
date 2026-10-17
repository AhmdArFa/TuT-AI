'use client';

import { useEffect, useRef } from 'react';

export function EtchedCanvas() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const cv = canvasRef.current;
    if (!cv) return;
    const c = cv.getContext('2d');
    if (!c) return;

    let W = window.innerWidth;
    let H = window.innerHeight;
    let d = Math.min(window.devicePixelRatio || 1, 2);
    let mx = W * 0.6;
    let my = H * 0.3;
    let tx = mx;
    let ty = my;
    let act = 0;
    const S = 26;
    const t0 = performance.now();
    const rm = window.matchMedia('(prefers-reduced-motion:reduce)').matches;
    let animId: number;

    function rs() {
      if (!cv || !c) return;
      d = Math.min(window.devicePixelRatio || 1, 2);
      W = window.innerWidth;
      H = window.innerHeight;
      cv.width = W * d;
      cv.height = H * d;
      c.setTransform(d, 0, 0, d, 0, 0);
      mx = tx = W * 0.6;
      my = ty = H * 0.3;
    }

    rs();
    window.addEventListener('resize', rs);

    const onPointerMove = (e: PointerEvent) => {
      tx = e.clientX;
      ty = e.clientY;
      act = 1;

      // Update cursor coords for pearl cards/buttons
      const target = (e.target as HTMLElement)?.closest?.('.card-obsidian, .go, .btn-pearl, .card') as HTMLElement;
      if (target) {
        const r = target.getBoundingClientRect();
        target.style.setProperty('--bx', `${e.clientX - r.left}px`);
        target.style.setProperty('--by', `${e.clientY - r.top}px`);
      }
    };

    const onPointerLeave = () => {
      act = 0;
    };

    window.addEventListener('pointermove', onPointerMove, { passive: true });
    document.addEventListener('pointerleave', onPointerLeave);

    function draw(now: number) {
      if (!c) return;
      const t = (now - t0) / 1000;
      mx += (tx - mx) * 0.16;
      my += (ty - my) * 0.16;
      c.clearRect(0, 0, W, H);
      c.lineCap = 'round';

      for (let y = S / 2; y < H; y += S) {
        for (let x = S / 2; x < W; x += S) {
          const dx = mx - x;
          const dy = my - y;
          const q = Math.sqrt(dx * dx + dy * dy);
          let k = act ? Math.max(0, 1 - q / 200) : 0;
          k = k * k * (3 - 2 * k);

          const b = (Math.sin(x * 0.011 + t * 0.5) + Math.cos(y * 0.013 - t * 0.4)) * 0.9;
          const g = Math.atan2(dy, dx);
          const ax = Math.cos(b) * (1 - k) + Math.cos(g) * k;
          const ay = Math.sin(b) * (1 - k) + Math.sin(g) * k;
          const a = Math.atan2(ay, ax);
          const l = (4 + k * 13) / 2;

          c.strokeStyle = `rgba(239,236,228,${(0.06 + k * 0.5).toFixed(3)})`;
          c.lineWidth = 1 + k * 1.1;
          c.beginPath();
          c.moveTo(x - Math.cos(a) * l, y - Math.sin(a) * l);
          c.lineTo(x + Math.cos(a) * l, y + Math.sin(a) * l);
          c.stroke();
        }
      }

      if (!rm) {
        animId = requestAnimationFrame(draw);
      }
    }

    animId = requestAnimationFrame(draw);

    return () => {
      window.removeEventListener('resize', rs);
      window.removeEventListener('pointermove', onPointerMove);
      document.removeEventListener('pointerleave', onPointerLeave);
      cancelAnimationFrame(animId);
    };
  }, []);

  return (
    <>
      <canvas id="tx" ref={canvasRef} aria-hidden="true" />
      <div className="grain" aria-hidden="true" />
    </>
  );
}
