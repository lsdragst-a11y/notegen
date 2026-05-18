"use client";

/**
 * 流体背景：3 个大圆 blob，blur(80px) 给奶油般弥散感。淡灰 / 淡灰蓝 / 极浅暖白
 * 三色，alpha 0.35-0.5。slow morph 30-40s 一周期，呼吸般缓慢移动 + scale。
 * 朴素配色，避免 "AI landing page" 鲜艳渐变 vibe。
 */
export default function FluidBG() {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 z-0 overflow-hidden"
    >
      <div className="blob blob-1" />
      <div className="blob blob-2" />
      <div className="blob blob-3" />

      <style jsx>{`
        .blob {
          position: absolute;
          border-radius: 50%;
          filter: blur(80px);
          will-change: transform;
        }
        .blob-1 {
          width: 640px;
          height: 640px;
          left: -10%;
          top: -14%;
          background: hsla(215, 35%, 78%, 0.85);
          animation: float1 38s ease-in-out infinite alternate;
        }
        .blob-2 {
          width: 540px;
          height: 540px;
          right: -8%;
          top: 35%;
          background: hsla(28, 40%, 85%, 0.80);
          animation: float2 44s ease-in-out infinite alternate;
        }
        .blob-3 {
          width: 760px;
          height: 760px;
          left: 30%;
          bottom: -25%;
          background: hsla(195, 32%, 82%, 0.75);
          animation: float3 50s ease-in-out infinite alternate;
        }
        @keyframes float1 {
          from { transform: translate(0, 0) scale(1); }
          to   { transform: translate(70px, 50px) scale(1.08); }
        }
        @keyframes float2 {
          from { transform: translate(0, 0) scale(1); }
          to   { transform: translate(-60px, -40px) scale(1.10); }
        }
        @keyframes float3 {
          from { transform: translate(0, 0) scale(1); }
          to   { transform: translate(50px, -80px) scale(1.06); }
        }
        /* dark 用 data-theme（让手动 toggle 也生效） */
        :global([data-theme="dark"]) .blob-1 {
          background: hsla(215, 35%, 22%, 0.55);
        }
        :global([data-theme="dark"]) .blob-2 {
          background: hsla(28, 28%, 18%, 0.50);
        }
        :global([data-theme="dark"]) .blob-3 {
          background: hsla(195, 30%, 20%, 0.50);
        }
      `}</style>
    </div>
  );
}
