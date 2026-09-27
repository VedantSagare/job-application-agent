import { useMemo, useState } from "react";
import { FileText, MapPin, Search, Sparkles } from "lucide-react";
import { api, STATUS_META, type JobSummary, type Stats, type Status } from "../api";
import { Button, Card, ScoreBadge, useAction } from "./ui";

const TABS: { id: string; label: string; statuses: Status[] }[] = [
  { id: "matches", label: "Matches", statuses: ["tailored", "scored"] },
  { id: "applied", label: "Applied", statuses: ["applied"] },
  { id: "new", label: "Not scored yet", statuses: ["new"] },
  { id: "low", label: "Low match", statuses: ["skipped"] },
  { id: "all", label: "All", statuses: ["new", "scored", "tailored", "applied", "skipped", "dismissed", "error"] },
];

const SOURCE_LABEL: Record<string, string> = {
  greenhouse: "Career site", lever: "Career site", ashby: "Career site", linkedin: "LinkedIn", naukri: "Naukri", instahyre: "Instahyre",
};

function ago(iso: string) {
  const d = (Date.now() - new Date(iso).getTime()) / 86400000;
  return d < 1 ? "today" : d < 2 ? "yesterday" : `${Math.floor(d)}d ago`;
}

export function JobsTable({ jobs, stats, selected, onSelect, running, onStarted }: {
  jobs: JobSummary[]; stats: Stats | null; selected: string | null; onSelect: (id: string) => void;
  running: boolean; onStarted: () => void;
}) {
  const [tab, setTab] = useState("matches");
  const [query, setQuery] = useState("");
  const [scoreN, setScoreN] = useState(30);
  const { busy, run } = useAction();

  const current = TABS.find((t) => t.id === tab)!;
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return jobs
      .filter((j) => current.statuses.includes(j.status))
      .filter((j) => !q || `${j.company} ${j.title} ${j.location ?? ""}`.toLowerCase().includes(q))
      .sort((a, b) => (b.score ?? -1) - (a.score ?? -1) || b.discovered_at.localeCompare(a.discovered_at));
  }, [jobs, current, query]);

  const count = (t: (typeof TABS)[number]) => jobs.filter((j) => t.statuses.includes(j.status)).length;

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 px-4 pt-3">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`-mb-px border-b-2 px-3 pb-2.5 text-sm font-medium transition-colors ${
              tab === t.id ? "border-blue-600 text-blue-700" : "border-transparent text-slate-500 hover:text-slate-700"
            }`}
          >
            {t.label} <span className="ml-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{count(t)}</span>
          </button>
        ))}
        <div className="ml-auto mb-2 flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5">
          <Search className="size-4 text-slate-400" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter by company, role, location"
            className="w-60 bg-transparent text-sm outline-none"
          />
        </div>
      </div>

      {/* Bulk actions relevant to the current tab */}
      {tab === "new" && (stats?.new ?? 0) > 0 && (
        <div className="flex items-center gap-2 border-b border-slate-100 bg-violet-50/50 px-4 py-2.5 text-sm">
          <Sparkles className="size-4 text-violet-500" /> Score the next
          <input type="number" min={1} max={500} value={scoreN} onChange={(e) => setScoreN(Number(e.target.value))}
            className="w-16 rounded border border-slate-300 bg-white px-1.5 py-0.5" />
          jobs (India &amp; remote first)
          <Button variant="primary" disabled={running} loading={busy === "score"} className="ml-2 py-1.5"
            onClick={() => run("score", async () => { await api.score(scoreN); onStarted(); }, "Scoring started")}>
            Score
          </Button>
        </div>
      )}

      {rows.length === 0 ? (
        <div className="px-4 py-14 text-center text-sm text-slate-500">
          {jobs.length === 0 ? "No jobs yet - run a search above." : "Nothing here yet."}
        </div>
      ) : (
        <div className="max-h-[560px] overflow-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 z-10 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="w-16 px-4 py-2.5 font-medium">Match</th>
                <th className="px-2 py-2.5 font-medium">Role</th>
                <th className="px-2 py-2.5 font-medium">Location</th>
                <th className="px-2 py-2.5 font-medium">Source</th>
                <th className="px-2 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 text-right font-medium">Found</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((j) => (
                <tr
                  key={j.id}
                  onClick={() => onSelect(j.id)}
                  className={`cursor-pointer border-t border-slate-100 transition-colors hover:bg-blue-50/60 ${
                    selected === j.id ? "bg-blue-50" : ""
                  }`}
                >
                  <td className="px-4 py-2.5"><ScoreBadge score={j.score} /></td>
                  <td className="px-2 py-2.5">
                    <div className="font-medium text-slate-900">{j.title}</div>
                    <div className="text-slate-500">{j.company}</div>
                  </td>
                  <td className="max-w-56 px-2 py-2.5 text-slate-600">
                    <span className="line-clamp-2 inline-flex items-start gap-1">
                      <MapPin className="mt-0.5 size-3.5 shrink-0 text-slate-400" />
                      {j.location || "—"}
                    </span>
                  </td>
                  <td className="px-2 py-2.5 text-slate-600">{SOURCE_LABEL[j.source] ?? j.source}</td>
                  <td className="px-2 py-2.5">
                    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_META[j.status].cls}`}>
                      {j.has_resume && j.status !== "applied" && <FileText className="size-3" />}
                      {STATUS_META[j.status].label}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right text-slate-500">{ago(j.discovered_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
