"use client";
import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import NavBar from "@/components/NavBar";
import FluidBG from "@/components/FluidBG";
import { apiVerify } from "@/lib/auth";

function VerifyInner() {
  const search = useSearchParams();
  const token = search.get("token") || "";
  const [state, setState] = useState<"pending" | "ok" | "fail">("pending");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (!token) { setState("fail"); setMsg("缺少验证 token"); return; }
    apiVerify(token)
      .then(r => { setState("ok"); setMsg(r.message); })
      .catch(e => { setState("fail"); setMsg(e?.message || "验证失败"); });
  }, [token]);

  return (
    <main className="relative min-h-screen">
      <FluidBG />
      <NavBar />
      <section className="relative z-10 max-w-sm mx-auto px-6 pt-24">
        <div className="apple-card p-7 text-center">
          {state === "pending" && <Loader2 size={32} className="text-[var(--accent)] animate-spin mx-auto" />}
          {state === "ok" && <CheckCircle2 size={32} className="text-[#30d158] mx-auto" />}
          {state === "fail" && <AlertCircle size={32} className="text-[#ff3b30] mx-auto" />}
          <h1 className="text-lg font-semibold mt-3 mb-1">
            {state === "pending" ? "验证中…" : state === "ok" ? "邮箱验证成功" : "验证失败"}
          </h1>
          <p className="text-sm text-[var(--fg-secondary)]">{msg}</p>
          {state !== "pending" && (
            <Link href="/login" className="apple-button inline-flex mt-4">去登录</Link>
          )}
        </div>
      </section>
    </main>
  );
}

export default function VerifyPage() {
  return (
    <Suspense fallback={<main className="min-h-screen" />}>
      <VerifyInner />
    </Suspense>
  );
}
