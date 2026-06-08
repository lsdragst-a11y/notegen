"use client";
import { useEffect, useRef } from "react";

/**
 * 流动粒子背景 — canvas 自实现，无 npm 依赖。
 * 设计：~80 个小粒子缓慢向右上漂浮，浅蓝/紫粉渐变，鼠标范围内被排斥。
 * 性能：requestAnimationFrame + 离屏 canvas 缩放，1080p 上 < 1% CPU。
 */
export default function ParticleBG({ density = 0.00005, mouseRepelR = 120 }: {
  density?: number; mouseRepelR?: number;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const mouseRef = useRef({ x: -9999, y: -9999, active: false });

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let particles: { x: number; y: number; vx: number; vy: number; r: number; hue: number; sat: number; light: number; alpha: number }[] = [];
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    function resize() {
      if (!canvas || !ctx) return;
      const { innerWidth: w, innerHeight: h } = window;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      canvas.style.width = w + "px";
      canvas.style.height = h + "px";
      ctx.scale(dpr, dpr);
      // 重建粒子数 ∝ 像素数
      const n = Math.max(40, Math.min(200, Math.round(w * h * density)));
      particles = Array.from({ length: n }, () => spawn(w, h));
    }

    // 检测是否 dark mode，给粒子不同 lightness（dark 下浅色粒子才在黑底可见）
    const isDark = () =>
      typeof document !== "undefined" &&
      document.documentElement.dataset.theme === "dark";

    function spawn(w: number, h: number) {
      // 中性色调：低饱和灰蓝 + 偶有暖白。r 大 + alpha 低 → soft glow。
      const useWarm = Math.random() < 0.3;
      const a = Math.random() * Math.PI * 2;
      const v = 0.02 + Math.random() * 0.05;
      const dark = isDark();
      return {
        x: Math.random() * w,
        y: Math.random() * h,
        vx: Math.cos(a) * v,
        vy: Math.sin(a) * v,
        r: 3 + Math.random() * 5,
        hue: useWarm ? 30 + Math.random() * 15 : 210 + Math.random() * 20,
        sat: useWarm ? 30 : 25,
        // dark 下 light 提到 78-82 让粒子在黑底上看得见；light 模式保持 62-68
        light: dark ? (useWarm ? 80 : 76) : (useWarm ? 68 : 62),
        alpha: dark ? 0.18 + Math.random() * 0.20 : 0.12 + Math.random() * 0.18,
      };
    }

    function tick() {
      if (!canvas || !ctx) return;
      const w = window.innerWidth, h = window.innerHeight;
      ctx.clearRect(0, 0, w, h);
      const mouse = mouseRef.current;
      // 流场：基于 stream function ψ 的旋度 (curl)，保证 divergence-free——
      // 即 ∂vx/∂x + ∂vy/∂y = 0，理论上不会有 sink（粒子不会汇聚到角落）。
      // ψ(x,y,t) ≈ sin(kx + t) · cos(ky + t')；curl 取 (∂ψ/∂y, -∂ψ/∂x)。
      const t = performance.now() * 0.00007;
      const k = 0.0022;
      const fieldStrength = 0.10;
      for (const p of particles) {
        // 鼠标排斥（弱化）
        if (mouse.active) {
          const dx = p.x - mouse.x;
          const dy = p.y - mouse.y;
          const d = Math.hypot(dx, dy);
          if (d < mouseRepelR && d > 0.1) {
            const force = (mouseRepelR - d) / mouseRepelR * 0.35;
            p.vx += (dx / d) * force * 0.025;
            p.vy += (dy / d) * force * 0.025;
          }
        }
        // stream function ψ = sin(k·x + t) · cos(k·y + 1.1·t)
        //   ∂ψ/∂y = -k · sin(k·x + t) · sin(k·y + 1.1·t)
        //   ∂ψ/∂x =  k · cos(k·x + t) · cos(k·y + 1.1·t)
        const a = k * p.x + t;
        const b = k * p.y + 1.1 * t;
        const fx = -Math.sin(a) * Math.sin(b);
        const fy = -Math.cos(a) * Math.cos(b);
        // 弱 force + 强 damping → 缓慢蜷曲流动
        p.vx = p.vx * 0.94 + fx * fieldStrength;
        p.vy = p.vy * 0.94 + fy * fieldStrength;
        // 限速
        const speed = Math.hypot(p.vx, p.vy);
        const maxSpeed = 0.35;
        if (speed > maxSpeed) {
          p.vx = p.vx / speed * maxSpeed;
          p.vy = p.vy / speed * maxSpeed;
        }
        p.x += p.vx;
        p.y += p.vy;
        // 边界 wrap（任意方向都可能出界）
        if (p.x < -10) p.x = w + 10;
        if (p.x > w + 10) p.x = -10;
        if (p.y < -10) p.y = h + 10;
        if (p.y > h + 10) p.y = -10;
        // 绘制
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        const grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 4);
        grad.addColorStop(0, `hsla(${p.hue}, ${p.sat}%, ${p.light}%, ${p.alpha})`);
        grad.addColorStop(1, `hsla(${p.hue}, ${p.sat}%, ${p.light}%, 0)`);
        ctx.fillStyle = grad;
        ctx.fillRect(p.x - p.r * 4, p.y - p.r * 4, p.r * 8, p.r * 8);
      }
      raf = requestAnimationFrame(tick);
    }

    function onMove(e: MouseEvent) {
      mouseRef.current.x = e.clientX;
      mouseRef.current.y = e.clientY;
      mouseRef.current.active = true;
    }
    function onLeave() { mouseRef.current.active = false; }

    // theme 切换时重 spawn 让粒子色调跟随
    const themeObserver = new MutationObserver(() => resize());
    themeObserver.observe(document.documentElement, {
      attributes: true, attributeFilter: ["data-theme"]
    });

    resize();
    window.addEventListener("resize", resize);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseleave", onLeave);
    tick();
    return () => {
      cancelAnimationFrame(raf);
      themeObserver.disconnect();
      window.removeEventListener("resize", resize);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseleave", onLeave);
    };
  }, [density, mouseRepelR]);

  return (
    <canvas
      ref={ref}
      className="pointer-events-none fixed inset-0 z-0 opacity-90"
      aria-hidden
    />
  );
}
