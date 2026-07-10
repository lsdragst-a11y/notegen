export type FoldPhase = "import" | "fold" | "note";
export type GenerationStep = "receive" | "transcribe" | "structure" | "archive";
export type GenerationStatus = "queued" | "running" | "done" | "failed";

export interface GenerationVisualInput {
  stage: string;
  percent: number;
  error: string | null;
}

export interface GenerationVisualState {
  status: GenerationStatus;
  activeStep: GenerationStep;
  safePercent: number;
  label: string;
}

export function clampFoldProgress(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.min(1, Math.max(0, value));
}

export function getFoldPhase(progress: number): FoldPhase {
  const safe = clampFoldProgress(progress);
  if (safe < 0.34) return "import";
  if (safe < 0.68) return "fold";
  return "note";
}

function getStepForProgress(stage: string, safePercent: number): GenerationStep {
  if (stage.includes("queue") || safePercent < 12) return "receive";
  if (stage.includes("asr") || stage.includes("whisper") || safePercent < 60) return "transcribe";
  if (stage.includes("summary") || stage.includes("chapter") || safePercent < 88) return "structure";
  return "archive";
}

export function getGenerationVisualState(input: GenerationVisualInput): GenerationVisualState {
  const stage = input.stage.toLowerCase();
  const safePercent = Math.min(100, Math.max(0, Math.round(input.percent || 0)));
  const activeStep = getStepForProgress(stage, safePercent);

  if (input.error || stage === "failed" || stage === "interrupted" || stage === "error") {
    return { status: "failed", activeStep, safePercent, label: "处理遇到问题" };
  }

  if (stage === "done") {
    return { status: "done", activeStep: "archive", safePercent: 100, label: "笔记已归档" };
  }

  if (activeStep === "receive") {
    return { status: "queued", activeStep: "receive", safePercent, label: "接收视频" };
  }

  if (activeStep === "transcribe") {
    return { status: "running", activeStep: "transcribe", safePercent, label: "转写声音" };
  }

  if (activeStep === "structure") {
    return { status: "running", activeStep: "structure", safePercent, label: "折叠章节" };
  }

  return { status: "running", activeStep: "archive", safePercent, label: "整理归档" };
}
