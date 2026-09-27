import { useCallback, useEffect, useRef, useState } from "react";
import { Briefcase, CircleAlert, FileText, Loader2, Search, Settings } from "lucide-react";
import { api, type Config, type JobSummary, type Stats, type Task } from "./api";
import { JobDrawer } from "./components/JobDrawer";
import { JobsTable } from "./components/JobsTable";
import { ResumePage } from "./components/ResumePage";
import { SearchPanel } from "./components/SearchPanel";
import { SettingsPage } from "./components/SettingsPage";
import { TaskPanel } from "./components/TaskPanel";
import { Card, ToastProvider } from "./components/ui";

type Page = "jobs" | "resume" | "settings";

function StatCard({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <Card className="px-4 py-3">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${tone}`}>{value}</div>
    </Card>
  );
}

export default function App() {
  const [page, setPage] = useState<Page>("jobs");
  const [stats, setStats] = useState<Stats | null>(null);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [config, setConfig] = useState<Config | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [log, setLog] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [version, setVersion] = useState(0); // bumps when data changes -> detail views reload
  const [offline, setOffline] = useState(false);
  const wasRunning = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const [s, j] = await Promise.all([api.stats(), api.jobs()]);
      setStats(s);
      setJobs(j);
      setVersion((v) => v + 1);
      setOffline(false);
    } catch {
      setOffline(true);
    }
  }, []);

  const pollTask = useCallback(async () => {
    try {
      const { task: t, log: l } = await api.task();
      setTask(t);
      setLog(l);
      setOffline(false);
      const running = !!t?.running;
      if (wasRunning.current && !running) refresh(); // task just finished
      wasRunning.current = running;
    } catch {
      setOffline(true);
    }
  }, [refresh]);

  useEffect(() => {
    refresh();
    pollTask();
    api.config().then(setConfig).catch(() => {});
  }, [refresh, pollTask]);

  // Poll the task every 1.5 s; while something runs, also refresh the results every 4 s
  // so new jobs / scores appear live.
  useEffect(() => {
    const t = setInterval(pollTask, 1500);
    return () => clearInterval(t);
  }, [pollTask]);
  useEffect(() => {
    if (!task?.running) return;
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, [task?.running, refresh]);

  const onStarted = () => {
    wasRunning.current = true;
    pollTask();
  };
  const running = !!task?.running;

  const NAV: { id: Page; label: string; icon: React.ReactNode }[] = [
    { id: "jobs", label: "Search & jobs", icon: <Search className="size-4" /> },
    { id: "resume", label: "My resume", icon: <FileText className="size-4" /> },
    { id: "settings", label: "Settings", icon: <Settings className="size-4" /> },
  ];

  return (
    <ToastProvider>
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-6 px-6 py-3">
          <div className="flex items-center gap-2 font-semibold">
            <span className="flex size-8 items-center justify-center rounded-lg bg-blue-600 text-white">
              <Briefcase className="size-4" />
            </span>
            Job Agent
          </div>
          <nav className="flex gap-1">
            {NAV.map((n) => (
              <button key={n.id} onClick={() => setPage(n.id)}
                className={`inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium ${
                  page === n.id ? "bg-blue-50 text-blue-700" : "text-slate-600 hover:bg-slate-100"
                }`}>
                {n.icon}{n.label}
              </button>
            ))}
          </nav>
          {running && (
            <div className="ml-auto inline-flex items-center gap-2 rounded-full bg-blue-50 px-3 py-1 text-sm text-blue-700">
              <Loader2 className="size-4 animate-spin" /> {task!.label}
            </div>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-5 px-6 py-6">
        {offline && (
          <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            <CircleAlert className="size-4" /> Can't reach the agent. Is the "Job Agent Dashboard" window still open?
          </div>
        )}
        {stats && !stats.has_resume && page !== "resume" && (
          <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
            <CircleAlert className="size-4" /> Upload your resume on the
            <button className="font-medium underline" onClick={() => setPage("resume")}>My resume</button> page first.
          </div>
        )}

        {page === "jobs" && (
          <>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
              <StatCard label="Jobs found" value={stats?.total ?? 0} tone="text-slate-900" />
              <StatCard label="Not scored" value={stats?.new ?? 0} tone="text-slate-600" />
              <StatCard label="Good matches" value={(stats?.scored ?? 0) + (stats?.tailored ?? 0)} tone="text-blue-700" />
              <StatCard label="Resumes ready" value={stats?.tailored ?? 0} tone="text-indigo-700" />
              <StatCard label="Applied" value={stats?.applied ?? 0} tone="text-emerald-700" />
              <StatCard label="Low match" value={stats?.skipped ?? 0} tone="text-slate-400" />
            </div>
            <SearchPanel config={config} running={running} onStarted={onStarted} />
            <TaskPanel task={task} log={log} />
            <JobsTable jobs={jobs} stats={stats} selected={selected} onSelect={setSelected} running={running}
              onStarted={onStarted} />
          </>
        )}
        {page === "resume" && (
          <>
            {running && task?.args[0] === "parse-resume" && <TaskPanel task={task} log={log} />}
            <ResumePage running={running} version={version} onStarted={onStarted} />
          </>
        )}
        {page === "settings" && <SettingsPage />}
      </main>

      {selected && (
        <JobDrawer jobId={selected} task={task} version={version} onClose={() => setSelected(null)}
          onChanged={() => { refresh(); pollTask(); }} />
      )}
    </ToastProvider>
  );
}
