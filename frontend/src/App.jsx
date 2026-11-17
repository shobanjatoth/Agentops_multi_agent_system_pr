
// import { useEffect, useState } from "react";
// import DashboardLayout from "./components/layout/DashboardLayout.jsx";
// import { getMetrics } from "./services/api.js";

// function App() {
//   const [metrics, setMetrics] = useState(null);
//   const [loading, setLoading] = useState(true);
//   const [error, setError] = useState("");

//   useEffect(() => {
//     async function loadMetrics() {
//       try {
//         setLoading(true);
//         setError("");

//         const data = await getMetrics();
//         setMetrics(data);
//       } catch (err) {
//         setError(err.message || "Unable to load metrics");
//       } finally {
//         setLoading(false);
//       }
//     }

//     loadMetrics();
//   }, []);

//   const cards = [
//     {
//       title: "Total Tasks",
//       value: metrics?.total_tasks ?? "--",
//     },
//     {
//       title: "Total Cost",
//       value:
//         metrics?.total_cost_usd != null
//           ? `$${Number(metrics.total_cost_usd).toFixed(4)}`
//           : "--",
//     },
//     {
//       title: "Average Latency",
//       value:
//         metrics?.avg_step_latency_ms != null
//           ? `${Number(metrics.avg_step_latency_ms).toFixed(2)} ms`
//           : "--",
//     },
//     {
//       title: "Agent Steps",
//       value: metrics?.total_agent_steps ?? "--",
//     },
//   ];

//   return (
//     <DashboardLayout>
//       <div className="space-y-8">
//         <section>
//           <h1 className="text-3xl font-bold text-white">
//             Dashboard Overview
//           </h1>
//           <p className="mt-2 text-slate-400">
//             Monitor and manage your AI agent operations.
//           </p>
//         </section>

//         {error && (
//           <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
//             Backend connection failed: {error}
//           </div>
//         )}

//         <section className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4">
//           {cards.map((card) => (
//             <div
//               key={card.title}
//               className="rounded-xl border border-slate-800 bg-slate-950 p-6"
//             >
//               <p className="text-sm text-slate-400">{card.title}</p>

//               <p className="mt-4 text-2xl font-bold text-white">
//                 {loading ? "Loading..." : card.value}
//               </p>

//               <p className="mt-2 text-xs text-slate-500">
//                 Live backend metrics
//               </p>
//             </div>
//           ))}
//         </section>

//         <section className="rounded-xl border border-slate-800 bg-slate-950 p-8">
//           <h2 className="text-xl font-semibold text-white">
//             Agent Monitoring
//           </h2>

//           <p className="mt-3 text-sm text-slate-400">
//             Monitor task execution, agent performance, costs,
//             and operational activity.
//           </p>

//           {metrics && !loading && (
//             <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
//               <div className="rounded-lg bg-slate-900 p-4">
//                 <p className="text-sm text-slate-400">Failed Steps</p>
//                 <p className="mt-2 text-xl font-semibold text-white">
//                   {metrics.failed_steps ?? "--"}
//                 </p>
//               </div>

//               <div className="rounded-lg bg-slate-900 p-4">
//                 <p className="text-sm text-slate-400">Success Rate</p>
//                 <p className="mt-2 text-xl font-semibold text-white">
//                   {metrics.success_rate_pct != null
//                     ? `${metrics.success_rate_pct}%`
//                     : "Not available"}
//                 </p>
//               </div>
//             </div>
//           )}
//         </section>
//       </div>
//     </DashboardLayout>
//   );
// }

// export default App;





import { useCallback, useEffect, useState } from "react";

import DashboardLayout from "./components/layout/DashboardLayout.jsx";

import {
  getTasks,
  getTraces,
} from "./services/api.js";

import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";

import {
  RefreshCw,
  ShieldAlert,
  CheckCircle2,
  Clock,
  Activity,
  DollarSign,
  ListTodo,
} from "lucide-react";

// Handles both direct arrays and common API response wrappers.
function extractRows(response, keys) {
  if (Array.isArray(response)) return response;

  for (const key of keys) {
    if (Array.isArray(response?.[key])) {
      return response[key];
    }
  }

  return [];
}

function formatDate(value) {
  if (!value) return "--";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return String(value);

  return date.toLocaleString();
}

function MetricCard({ title, value, icon: Icon, description }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950 p-5">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-400">{title}</p>
        <Icon size={20} className="text-indigo-400" />
      </div>

      <p className="mt-4 text-2xl font-bold text-white">
        {value}
      </p>

      <p className="mt-2 text-xs text-slate-500">
        {description}
      </p>
    </div>
  );
}

function Section({ title, icon: Icon, children }) {
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-950 p-6">
      <div className="mb-6 flex items-center gap-3">
        {Icon && <Icon size={20} className="text-indigo-400" />}
        <h2 className="text-lg font-semibold text-white">{title}</h2>
      </div>
      {children}
    </section>
  );
}

function DataTable({ columns, rows, emptyMessage }) {
  if (!rows.length) {
    return (
      <p className="py-8 text-center text-sm text-slate-500">
        {emptyMessage}
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-slate-800 text-slate-400">
            {columns.map((column) => (
              <th key={column.key} className="whitespace-nowrap px-4 py-3 font-medium">
                {column.label}
              </th>
            ))}
          </tr>
        </thead>

        <tbody>
          {rows.map((row, index) => (
            <tr
              key={row.id ?? row.task_id ?? index}
              className="border-b border-slate-800/70 text-slate-300 last:border-0 hover:bg-slate-900/70"
            >
              {columns.map((column) => (
                <td key={column.key} className="max-w-xs px-4 py-3">
                  {column.render
                    ? column.render(row[column.key], row)
                    : row[column.key] ?? "--"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function App() {
  const [tasks, setTasks] = useState([]);
  const [traces, setTraces] = useState([]);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const loadDashboard = useCallback(async (initial = false) => {
    if (initial) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }

    try {
      setError("");

      const [taskResponse, traceResponse] = await Promise.all([
        getTasks(),
        getTraces(),
      ]);

      setTasks(
        extractRows(taskResponse, ["tasks", "items", "data"])
      );

      setTraces(
        extractRows(traceResponse, ["traces", "items", "data"])
      );
    } catch (err) {
      setError(err.message || "Unable to load dashboard data");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadDashboard(true);

    const interval = setInterval(() => {
      loadDashboard(false);
    }, 15000);

    return () => clearInterval(interval);
  }, [loadDashboard]);

  // Calculate the same metrics as the original Streamlit dashboard.
  const totalTasks = tasks.length;

  const totalCost = traces.reduce(
    (sum, trace) => sum + (Number(trace.cost_usd) || 0),
    0
  );

  const averageLatency = traces.length
    ? traces.reduce(
        (sum, trace) => sum + (Number(trace.latency_ms) || 0),
        0
      ) / traces.length
    : 0;

  const passedSteps = traces.filter(
    (trace) =>
      trace.passed === true ||
      trace.passed === 1 ||
      trace.passed === "true"
  ).length;

  const passRate = traces.length
    ? (passedSteps / traces.length) * 100
    : 0;

  const pendingTasks = tasks.filter(
    (task) => task.status === "awaiting_approval"
  );

  // Average latency grouped by agent node.
  const latencyMap = {};

  traces.forEach((trace) => {
    const node = trace.node || "unknown";

    if (!latencyMap[node]) {
      latencyMap[node] = { total: 0, count: 0 };
    }

    latencyMap[node].total += Number(trace.latency_ms) || 0;
    latencyMap[node].count += 1;
  });

  const latencyData = Object.entries(latencyMap).map(
    ([node, values]) => ({
      node,
      latency: values.total / values.count,
    })
  );

  // Total cost grouped by agent node.
  const costMap = {};

  traces.forEach((trace) => {
    const node = trace.node || "unknown";

    costMap[node] =
      (costMap[node] || 0) + (Number(trace.cost_usd) || 0);
  });

  const costData = Object.entries(costMap).map(
    ([node, cost]) => ({
      node,
      cost,
    })
  );

  // Prompt injection security events.
  const securityEvents = traces.filter(
    (trace) => trace.node === "research.security"
  );

  // Most recent traces first.
  const recentTraces = [...traces]
    .sort(
      (a, b) =>
        new Date(b.created_at || 0).getTime() -
        new Date(a.created_at || 0).getTime()
    )
    .slice(0, 100);

  return (
    <DashboardLayout>
      <div className="space-y-8">

        {/* Page heading */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-white">
              AgentOps Overview
            </h1>
            <p className="mt-2 text-sm text-slate-400">
              Live observability for your multi-agent system.
            </p>
          </div>

          <button
            onClick={() => loadDashboard(false)}
            disabled={refreshing}
            className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            <RefreshCw
              size={16}
              className={refreshing ? "animate-spin" : ""}
            />
            Refresh
          </button>
        </div>

        {/* Error message */}
        {error && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
            Dashboard error: {error}
          </div>
        )}

        {/* Top metrics */}
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-5">
          <MetricCard
            title="Total Tasks"
            value={loading ? "..." : totalTasks}
            icon={ListTodo}
            description="Recorded agent tasks"
          />

          <MetricCard
            title="Total Cost"
            value={loading ? "..." : `$${totalCost.toFixed(6)}`}
          
            icon={DollarSign}
            description="Total execution cost"
          />

          <MetricCard
            title="Avg Latency"
            value={loading ? "..." : `${averageLatency.toFixed(2)} ms`}
            icon={Clock}
            description="Average latency per step"
          />

          <MetricCard
            title="Step Pass Rate"
            value={loading ? "..." : `${passRate.toFixed(1)}%`}
            icon={CheckCircle2}
            description={`${passedSteps} / ${traces.length} passed steps`}
          />

          <MetricCard
            title="Pending Approvals"
            value={loading ? "..." : pendingTasks.length}
            icon={Activity}
            description="Awaiting human review"
          />
        </div>

        {/* Performance charts */}
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">

          <Section title="Average Latency by Node">
            {latencyData.length ? (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={latencyData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="node" stroke="#94a3b8" />
                  <YAxis stroke="#94a3b8" />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#0f172a",
                      border: "1px solid #334155",
                      color: "#fff",
                    }}
                  />
                  <Bar dataKey="latency" name="Latency (ms)" fill="#818cf8" radius={[5, 5, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="py-12 text-center text-slate-500">
                No latency data available.
              </p>
            )}
          </Section>

          <Section title="Total Cost by Node">
            {costData.length ? (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={costData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="node" stroke="#94a3b8" />
                  <YAxis stroke="#94a3b8" />
                  <Tooltip
                    formatter={(value) => `$${Number(value).toFixed(6)}`}
                    contentStyle={{
                      backgroundColor: "#0f172a",
                      border: "1px solid #334155",
                      color: "#fff",
                    }}
                  />
                  <Bar dataKey="cost" name="Cost (USD)" fill="#34d399" radius={[5, 5, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="py-12 text-center text-slate-500">
                No cost data available.
              </p>
            )}
          </Section>
        </div>

        {/* Security events */}
        <Section title="Security Events — Prompt Injection" icon={ShieldAlert}>
          {securityEvents.length === 0 ? (
            <div className="flex items-center gap-3 rounded-lg bg-emerald-500/10 p-4 text-emerald-400">
              <CheckCircle2 size={20} />
              <p className="text-sm">
                No injection attempts detected in the recorded traces.
              </p>
            </div>
          ) : (
            <>
              <div className="mb-4 rounded-lg bg-red-500/10 p-4 text-sm text-red-400">
                {securityEvents.length} potential prompt injection event(s) detected.
              </div>

              <DataTable
                rows={securityEvents}
                emptyMessage="No security events."
                columns={[
                  { key: "task_id", label: "Task ID" },
                  { key: "input_summary", label: "Input Summary" },
                  { key: "output_summary", label: "Output Summary" },
                  {
                    key: "created_at",
                    label: "Created At",
                    render: (value) => formatDate(value),
                  },
                ]}
              />
            </>
          )}
        </Section>

        {/* Pending approvals */}
        <Section title="Tasks Awaiting Human Approval" icon={Clock}>
          <DataTable
            rows={pendingTasks}
            emptyMessage="No tasks are awaiting approval."
            columns={[
              { key: "id", label: "Task ID" },
              { key: "description", label: "Description" },
              {
                key: "created_at",
                label: "Created At",
                render: (value) => formatDate(value),
              },
            ]}
          />
        </Section>

        {/* Recent traces */}
        <Section title="Recent Agent Steps" icon={Activity}>
          <DataTable
            rows={recentTraces}
            emptyMessage="No traces yet. Send a task to the API using POST /tasks to see data here."
            columns={[
              { key: "task_id", label: "Task ID" },
              { key: "node", label: "Node" },
              {
                key: "latency_ms",
                label: "Latency",
                render: (value) =>
                  value != null ? `${Number(value).toFixed(2)} ms` : "--",
              },
              { key: "input_tokens", label: "Input Tokens" },
              { key: "output_tokens", label: "Output Tokens" },
              {
                key: "cost_usd",
                label: "Cost",
                render: (value) =>
                  value != null ? `$${Number(value).toFixed(6)}` : "--",
              },
              {
                key: "passed",
                label: "Status",
                render: (value) => {
                  const passed =
                    value === true ||
                    value === 1 ||
                    value === "true";

                  return (
                    <span
                      className={
                        passed
                          ? "rounded-full bg-emerald-500/10 px-3 py-1 text-xs text-emerald-400"
                          : "rounded-full bg-red-500/10 px-3 py-1 text-xs text-red-400"
                      }
                    >
                      {passed ? "Passed" : "Failed"}
                    </span>
                  );
                },
              },
              {
                key: "created_at",
                label: "Created At",
                render: (value) => formatDate(value),
              },
            ]}
          />
        </Section>

        <p className="text-center text-xs text-slate-600">
          AgentOps Observability Dashboard · Auto-refresh every 15 seconds
        </p>
      </div>
    </DashboardLayout>
  );
}

export default App;
