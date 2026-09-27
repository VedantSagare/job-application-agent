import { useEffect, useState } from "react";
import {
  Check, CircleAlert, Download, ExternalLink, FileText, FolderOpen, Mail, MapPin, MousePointerClick, Sparkles,
  Undo2, WandSparkles, X,
} from "lucide-react";
import { api, STATUS_META, type JobDetail, type Task } from "../api";
import { Button, ScoreBadge, useAction } from "./ui";

type Tab = "match" | "resume" | "cover" | "jd";

export function JobDrawer({ jobId, task, version, onClose, onChanged }: {
  jobId: string; task: Task | null; version: number; onClose: () => void; onChanged: () => void;
}) {
  const [job, setJob] = useState<JobDetail | null>(null);
  const [tab, setTab] = useState<Tab>("match");
  const { busy, run } = useAction();
  const running = !!task?.running;
  const applyOpen = running && task?.args[0] === "apply-one" && task.args[1] === jobId;

  useEffect(() => {
    api.job(jobId).then(setJob).catch(() => setJob(null));
  }, [jobId, version]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const act = (key: string, fn: () => Promise<unknown>, msg?: string) =>
    run(key, async () => { await fn(); onChanged(); }, msg);

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: "match", label: "Why it matches", icon: <Sparkles className="size-4" /> },
    { id: "resume", label: "Tailored resume", icon: <FileText className="size-4" /> },
    { id: "cover", label: "Cover letter", icon: <Mail className="size-4" /> },
    { id: "jd", label: "Job description", icon: <FileText className="size-4" /> },
  ];

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-slate-900/30" onClick={onClose} />
      <aside className="relative flex h-full w-full max-w-3xl flex-col bg-white shadow-2xl">
        {!job ? (
          <div className="p-8 text-slate-500">Loading...</div>
        ) : (
          <>
            {/* Header */}
            <div className="border-b border-slate-200 px-6 py-5">
              <div className="flex items-start gap-4">
                <ScoreBadge score={job.score} size="lg" />
                <div className="min-w-0 flex-1">
                  <h2 className="text-xl font-semibold text-slate-900">{job.title}</h2>
                  <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-600">
                    <span className="font-medium">{job.company}</span>
                    <span className="inline-flex items-center gap-1"><MapPin className="size-3.5" />{job.location || "—"}</span>
                    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_META[job.status].cls}`}>
                      {STATUS_META[job.status].label}
                    </span>
                  </div>
                </div>
                <button onClick={onClose} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600">
                  <X className="size-5" />
                </button>
              </div>

              {/* Actions */}
              <div className="mt-4 flex flex-wrap gap-2">
                {job.status === "new" && (
                  <Button variant="primary" icon={<Sparkles className="size-4" />} disabled={running} loading={busy === "score"}
                    onClick={() => act("score", () => api.scoreOne(job.id), "Scoring started")}>
                    Score this job
                  </Button>
                )}
                <Button variant={job.has_resume ? "secondary" : "primary"} icon={<WandSparkles className="size-4" />}
                  disabled={running} loading={busy === "tailor"}
                  title="Rewrites your resume and a cover letter for this job description (~30-60 s)"
                  onClick={() => act("tailor", () => api.tailorOne(job.id), "Tailoring started (~30-60 s)")}>
                  {job.has_resume ? "Re-tailor resume" : "Tailor resume"}
                </Button>
                {!job.has_resume && (
                  <Button variant="primary" icon={<WandSparkles className="size-4" />} disabled={running}
                    loading={busy === "tailor-apply"}
                    title="Tailors the resume, then opens the application in Chrome and fills it in"
                    onClick={() => act("tailor-apply", () => api.applyOne(job.id, true),
                      "Tailoring, then opening the application...")}>
                    Tailor &amp; auto-fill
                  </Button>
                )}
                <Button variant="primary" icon={<MousePointerClick className="size-4" />} disabled={running}
                  loading={busy === "apply"}
                  title={job.has_resume
                    ? "Opens the application in Chrome and fills it in with your tailored resume"
                    : "Opens the application in Chrome and fills it in with your original resume"}
                  onClick={() => act("apply", () => api.applyOne(job.id), "Opening the application in Chrome...")}>
                  {job.has_resume ? "Auto-fill application" : "Auto-fill (original resume)"}
                </Button>
                {job.status !== "applied" && (
                  <Button icon={<Check className="size-4" />} loading={busy === "applied"}
                    onClick={() => act("applied", () => api.setStatus(job.id, "applied"), "Marked as applied")}>
                    Mark applied
                  </Button>
                )}
                {["skipped", "dismissed", "error", "applied"].includes(job.status) ? (
                  <Button icon={<Undo2 className="size-4" />} loading={busy === "restore"}
                    onClick={() => act("restore", () => api.setStatus(job.id, "scored"), "Moved to matches")}>
                    Move to matches
                  </Button>
                ) : (
                  <Button variant="ghost" icon={<X className="size-4" />} loading={busy === "dismiss"}
                    onClick={() => act("dismiss", () => api.setStatus(job.id, "dismissed"), "Dismissed")}>
                    Dismiss
                  </Button>
                )}
                <a href={job.url} target="_blank" rel="noreferrer"
                  className="inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium text-blue-700 hover:bg-blue-50">
                  <ExternalLink className="size-4" /> View posting
                </a>
              </div>

              {applyOpen && (
                <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm">
                  <div className="font-medium text-blue-900">The application is open in Chrome.</div>
                  <div className="mt-0.5 text-blue-800">
                    Fields outlined <b className="text-red-600">red</b> need your answer, <b className="text-orange-600">orange</b> couldn't be
                    filled. Check everything, click <b>Submit</b> there yourself, then press <b>Mark applied</b>.
                  </div>
                  <div className="mt-2 flex gap-2">
                    <Button icon={<Sparkles className="size-4" />} loading={busy === "fill"}
                      title="After clicking Next / Easy Apply, or if fields loaded late"
                      onClick={() => run("fill", () => api.applyCommand("fill"), "Filling the current page...")}>
                      Fill current page
                    </Button>
                    <Button variant="ghost" icon={<X className="size-4" />}
                      onClick={() => run("close", () => api.applyCommand("close"))}>
                      Close browser
                    </Button>
                  </div>
                </div>
              )}
              {job.status === "error" && job.error && (
                <div className="mt-3 flex items-start gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-700">
                  <CircleAlert className="mt-0.5 size-4 shrink-0" /> {job.error}
                </div>
              )}
            </div>

            {/* Tabs */}
            <div className="flex gap-1 border-b border-slate-200 px-4">
              {tabs.map((t) => (
                <button key={t.id} onClick={() => setTab(t.id)}
                  className={`-mb-px inline-flex items-center gap-1.5 border-b-2 px-3 py-3 text-sm font-medium ${
                    tab === t.id ? "border-blue-600 text-blue-700" : "border-transparent text-slate-500 hover:text-slate-700"
                  }`}>
                  {t.icon}{t.label}
                </button>
              ))}
            </div>

            <div className="flex-1 overflow-auto px-6 py-5">
              {tab === "match" && (
                job.match ? (
                  <div className="grid gap-6 md:grid-cols-2">
                    <div>
                      <h3 className="mb-2 font-semibold text-emerald-700">Why it fits</h3>
                      <ul className="list-disc space-y-1.5 pl-5 text-sm">{job.match.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
                    </div>
                    <div>
                      <h3 className="mb-2 font-semibold text-amber-700">Gaps</h3>
                      {job.match.missing_requirements.length ? (
                        <ul className="list-disc space-y-1.5 pl-5 text-sm">
                          {job.match.missing_requirements.map((r) => <li key={r}>{r}</li>)}
                        </ul>
                      ) : <p className="text-sm text-slate-500">None noted.</p>}
                    </div>
                  </div>
                ) : <p className="text-sm text-slate-500">Not scored yet - press <b>Score this job</b>.</p>
              )}

              {tab === "resume" && (
                job.has_resume ? (
                  <div className="flex h-full flex-col gap-4">
                    <div className="flex flex-wrap gap-2">
                      <a href={`/api/jobs/${job.id}/resume.pdf`} target="_blank" rel="noreferrer"
                        className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3.5 py-2 text-sm font-medium hover:bg-slate-50">
                        <ExternalLink className="size-4" /> Open in new tab
                      </a>
                      <a href={`/api/jobs/${job.id}/resume.pdf`} download={job.resume_file ?? undefined}
                        className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3.5 py-2 text-sm font-medium hover:bg-slate-50">
                        <Download className="size-4" /> Download
                      </a>
                      <Button icon={<FolderOpen className="size-4" />} onClick={() => run("folder", () => api.openFolder(job.id))}>
                        Open folder
                      </Button>
                    </div>
                    {job.changes.filter((c) => c.startsWith("Added skills")).map((c) => (
                      <div key={c} className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                        <CircleAlert className="mt-0.5 size-4 shrink-0" />
                        <span><b>Added skills</b>{c.slice("Added skills".length)}</span>
                      </div>
                    ))}
                    {job.changes.length > 0 && (
                      <details open className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm">
                        <summary className="cursor-pointer font-medium">What was changed from your base resume</summary>
                        <ul className="mt-2 list-disc space-y-1 pl-5 text-slate-700">
                          {job.changes.filter((c) => !c.startsWith("Added skills")).map((c) => <li key={c}>{c}</li>)}
                        </ul>
                      </details>
                    )}
                    <iframe title="Tailored resume" src={`/api/jobs/${job.id}/resume.pdf#view=FitH`}
                      className="min-h-[900px] w-full flex-1 rounded-lg border border-slate-200" />
                  </div>
                ) : (
                  <div className="space-y-3">
                    <p className="text-sm text-slate-500">
                      Not tailored yet - press <b>Tailor resume</b> to rewrite your resume for this job. Until then,
                      <b> Auto-fill</b> uploads your original resume:
                    </p>
                    <iframe title="Original resume" src="/api/resume/original.pdf#view=FitH"
                      className="min-h-[900px] w-full rounded-lg border border-slate-200" />
                  </div>
                )
              )}

              {tab === "cover" && (
                job.cover_letter ? (
                  <div className="space-y-3">
                    <a href={`/api/jobs/${job.id}/cover.pdf`} target="_blank" rel="noreferrer"
                      className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3.5 py-2 text-sm font-medium hover:bg-slate-50">
                      <ExternalLink className="size-4" /> Open PDF
                    </a>
                    <div className="whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-50 p-5 text-sm leading-relaxed">
                      {job.cover_letter}
                    </div>
                  </div>
                ) : <p className="text-sm text-slate-500">Written when you press <b>Tailor resume</b>.</p>
              )}

              {tab === "jd" && (
                <div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">{job.description}</div>
              )}
            </div>
          </>
        )}
      </aside>
    </div>
  );
}
