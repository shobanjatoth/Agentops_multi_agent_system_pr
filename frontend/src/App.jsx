
import { useCallback, useEffect, useState } from "react";

import DashboardLayout from "./components/layout/DashboardLayout.jsx";

import {
  getTasks,
  getTraces,
  getPendingApprovals,
  createTaskStream,
  resolveApproval,
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
  Play,
  Check,
  X,
  Terminal,
} from "lucide-react";

// ---------------------------------------------------------
// Helpers
// ---------------------------------------------------------

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

function formatAction(action) {
  if (!action) return "--";

  return JSON.stringify(action, null, 2);
}

// ---------------------------------------------------------
// Reusable components
// ---------------------------------------------------------

function MetricCard({ title, value, icon: Icon, description }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950 p-5">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-400">{title}</p>
        <Icon size={20} className="text-indigo-400" />
      </div>

      <p className="mt-4 text-2xl font-bold text-white">{value}</p>

      <p className="mt-2 text-xs text-slate-500">{description}</p>
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
              <th
                key={column.key}
                className="whitespace-nowrap px-4 py-3 font-medium"
              >
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

// ---------------------------------------------------------
// Main application
// ---------------------------------------------------------

function App() {
  // Dashboard data
  const [tasks, setTasks] = useState([]);
  const [traces, setTraces] = useState([]);
  const [approvals, setApprovals] = useState([]);

  // Dashboard loading
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  // Task creation
  const [description, setDescription] = useState("");
  const [repo, setRepo] = useState("");
  const [creatingTask, setCreatingTask] = useState(false);
  const [taskError, setTaskError] = useState("");
  const [executionEvents, setExecutionEvents] = useState([]);
  const [executionStatus, setExecutionStatus] = useState("");

  // Approval actions
  const [processingApproval, setProcessingApproval] = useState("");

  // -------------------------------------------------------
  // Load dashboard data
  // -------------------------------------------------------

  const loadDashboard = useCallback(async (initial = false) => {
    if (initial) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }

    try {
      setError("");

      const [
        taskResponse,
        traceResponse,
        approvalResponse,
      ] = await Promise.all([
        getTasks(),
        getTraces(),
        getPendingApprovals(),
      ]);

      setTasks(
        extractRows(taskResponse, ["tasks", "items", "data"])
      );

      setTraces(
        extractRows(traceResponse, ["traces", "items", "data"])
      );

      // Backend returns approvals keyed by task_id.
      const approvalRows = Object.entries(
        approvalResponse || {}
      ).map(([task_id, approval]) => ({
        task_id,
        ...approval,
      }));

      setApprovals(approvalRows);
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

  // -------------------------------------------------------
  // Create task and consume SSE events
  // -------------------------------------------------------

  async function handleCreateTask(event) {
    event.preventDefault();

    if (!description.trim()) {
      setTaskError("Please enter a task description.");
      return;
    }

    setCreatingTask(true);
    setTaskError("");
    setExecutionEvents([]);
    setExecutionStatus("Running agent workflow...");

    try {
      const taskPayload = {
        description: description.trim(),
        ...(repo.trim() ? { repo: repo.trim() } : {}),
      };

      await createTaskStream(taskPayload, (eventData) => {
        setExecutionEvents((previous) => [
          ...previous,
          {
            ...eventData,
            receivedAt: new Date().toISOString(),
          },
        ]);

        switch (eventData.event) {
          case "node_complete":
            setExecutionStatus(
              `Agent node completed: ${eventData.data.node || "unknown"}`
            );
            break;

          case "awaiting_approval":
            setExecutionStatus("Waiting for human approval.");
            break;

          case "execution_complete":
            setExecutionStatus("Action execution completed.");
            break;

          case "done":
            setExecutionStatus("Task completed successfully.");
            break;

          case "error":
            setExecutionStatus(
              eventData.data.message ||
              eventData.data.error ||
              "Task execution failed."
            );
            break;

          default:
            setExecutionStatus(`Received event: ${eventData.event}`);
        }
      });

      setDescription("");
      await loadDashboard(false);
    } catch (err) {
      setTaskError(err.message || "Unable to execute task.");
      setExecutionStatus("Task request failed.");
    } finally {
      setCreatingTask(false);
      await loadDashboard(false);
    }
  }

  // -------------------------------------------------------
  // Approve or reject an action
  // -------------------------------------------------------

  async function handleApproval(taskId, approved) {
    const actionLabel = approved ? "approval" : "rejection";

    setProcessingApproval(taskId);
    setError("");

    try {
      const result = await resolveApproval(taskId, approved);

      setExecutionStatus(
        approved
          ? `Approval processed. Task status: ${result.status}`
          : "Action rejected successfully."
      );

      await loadDashboard(false);
    } catch (err) {
      setError(
        `Unable to process ${actionLabel}: ${err.message}`
      );
    } finally {
      setProcessingApproval("");
    }
  }

  // -------------------------------------------------------
  // Dashboard metrics
  // -------------------------------------------------------

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

  // -------------------------------------------------------
  // UI
  // -------------------------------------------------------

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

        {/* Dashboard error */}
        {error && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
            {error}
          </div>
        )}

        {/* ------------------------------------------------ */}
        {/* Create task */}
        {/* ------------------------------------------------ */}

        <Section title="Create Agent Task" icon={Play}>
          <form onSubmit={handleCreateTask} className="space-y-4">

            <div>
              <label className="mb-2 block text-sm font-medium text-slate-300">
                Task Description
              </label>

              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Example: Research the latest deployment failures and suggest a fix."
                maxLength={8000}
                rows={4}
                disabled={creatingTask}
                className="w-full rounded-lg border border-slate-700 bg-slate-900 p-3 text-sm text-white outline-none placeholder:text-slate-500 focus:border-indigo-500 disabled:opacity-50"
              />

              <p className="mt-1 text-right text-xs text-slate-500">
                {description.length}/8000 characters
              </p>
            </div>

            <div>
              <label className="mb-2 block text-sm font-medium text-slate-300">
                GitHub Repository (Optional)
              </label>

              <input
                type="text"
                value={repo}
                onChange={(event) => setRepo(event.target.value)}
                placeholder="owner/repository"
                disabled={creatingTask}
                className="w-full rounded-lg border border-slate-700 bg-slate-900 p-3 text-sm text-white outline-none placeholder:text-slate-500 focus:border-indigo-500 disabled:opacity-50"
              />
            </div>

            {taskError && (
              <p className="text-sm text-red-400">{taskError}</p>
            )}

            <button
              type="submit"
              disabled={creatingTask || !description.trim()}
              className="flex items-center gap-2 rounded-lg bg-indigo-600 px-5 py-3 text-sm font-medium text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {creatingTask ? (
                <>
                  <RefreshCw size={16} className="animate-spin" />
                  Executing...
                </>
              ) : (
                <>
                  <Play size={16} />
                  Run Agent Task
                </>
              )}
            </button>
          </form>
        </Section>

        {/* ------------------------------------------------ */}
        {/* Live execution */}
        {/* ------------------------------------------------ */}

        {(executionEvents.length > 0 || executionStatus) && (
          <Section title="Live Agent Execution" icon={Terminal}>
            <div className="mb-4 rounded-lg border border-slate-800 bg-slate-900 p-4">
              <p className="text-sm text-slate-400">Current status</p>

              <p className="mt-2 text-sm font-medium text-indigo-300">
                {executionStatus}
              </p>
            </div>

            <div className="max-h-96 space-y-3 overflow-y-auto">
              {executionEvents.map((item, index) => (
                <div
                  key={`${index}-${item.event}`}
                  className="rounded-lg border border-slate-800 bg-slate-900 p-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-indigo-300">
                      {item.event}
                    </span>

                    <span className="text-xs text-slate-500">
                      {formatDate(item.receivedAt)}
                    </span>
                  </div>

                  <pre className="mt-3 overflow-x-auto whitespace-pre-wrap break-words text-xs text-slate-300">
                    {JSON.stringify(item.data, null, 2)}
                  </pre>
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* ------------------------------------------------ */}
        {/* Metrics */}
        {/* ------------------------------------------------ */}

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
            value={loading ? "..." : approvals.length}
            icon={Activity}
            description="Awaiting human review"
          />
        </div>

        {/* ------------------------------------------------ */}
        {/* Performance charts */}
        {/* ------------------------------------------------ */}

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
                  <Bar
                    dataKey="latency"
                    name="Latency (ms)"
                    fill="#818cf8"
                    radius={[5, 5, 0, 0]}
                  />
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
                  <Bar
                    dataKey="cost"
                    name="Cost (USD)"
                    fill="#34d399"
                    radius={[5, 5, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="py-12 text-center text-slate-500">
                No cost data available.
              </p>
            )}
          </Section>
        </div>

        {/* ------------------------------------------------ */}
        {/* Security events */}
        {/* ------------------------------------------------ */}

        <Section
          title="Security Events - Prompt Injection"
          icon={ShieldAlert}
        >
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
                {securityEvents.length} potential prompt injection event(s)
                detected.
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

        {/* ------------------------------------------------ */}
        {/* Human approval queue */}
        {/* ------------------------------------------------ */}

        <Section title="Human Approval Queue" icon={ShieldAlert}>
          {!approvals.length ? (
            <div className="rounded-lg bg-emerald-500/10 p-4 text-sm text-emerald-400">
              <CheckCircle2 size={18} className="mr-2 inline" />
              No pending actions require human approval.
            </div>
          ) : (
            <div className="space-y-5">
              {approvals.map((approval) => (
                <div
                  key={approval.task_id}
                  className="rounded-xl border border-slate-800 bg-slate-900 p-5"
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-white">
                        Task ID
                      </p>

                      <p className="mt-1 break-all text-xs text-slate-400">
                        {approval.task_id}
                      </p>
                    </div>

                    <span className="rounded-full bg-amber-500/10 px-3 py-1 text-xs font-medium text-amber-400">
                      Awaiting approval
                    </span>
                  </div>

                  <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <div>
                      <p className="text-xs text-slate-500">
                        Proposed action
                      </p>

                      <p className="mt-1 text-sm font-medium text-white">
                        {approval.action?.type || "Unknown action"}
                      </p>
                    </div>

                    <div>
                      <p className="text-xs text-slate-500">
                        Risk score
                      </p>

                      <p className="mt-1 text-sm font-semibold text-amber-400">
                        {Number(approval.risk_score ?? 0).toFixed(2)}
                      </p>
                    </div>
                  </div>

                  <details className="mt-4">
                    <summary className="cursor-pointer text-sm text-indigo-400 hover:text-indigo-300">
                      Inspect proposed action
                    </summary>

                    <pre className="mt-3 overflow-x-auto whitespace-pre-wrap break-words rounded-lg bg-slate-950 p-4 text-xs text-slate-300">
                      {formatAction(approval.action)}
                    </pre>
                  </details>

                  <div className="mt-5 flex flex-wrap gap-3">
                    <button
                      onClick={() =>
                        handleApproval(approval.task_id, true)
                      }
                      disabled={processingApproval === approval.task_id}
                      className="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
                    >
                      <Check size={16} />
                      {processingApproval === approval.task_id
                        ? "Processing..."
                        : "Approve"}
                    </button>

                    <button
                      onClick={() =>
                        handleApproval(approval.task_id, false)
                      }
                      disabled={processingApproval === approval.task_id}
                      className="flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
                    >
                      <X size={16} />
                      Reject
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Section>

        {/* ------------------------------------------------ */}
        {/* Recent agent steps */}
        {/* ------------------------------------------------ */}

        <Section title="Recent Agent Steps" icon={Activity}>
          <DataTable
            rows={recentTraces}
            emptyMessage="No traces yet. Create a task to see agent execution data here."
            columns={[
              { key: "task_id", label: "Task ID" },
              { key: "node", label: "Node" },
              {
                key: "latency_ms",
                label: "Latency",
                render: (value) =>
                  value != null
                    ? `${Number(value).toFixed(2)} ms`
                    : "--",
              },
              { key: "input_tokens", label: "Input Tokens" },
              { key: "output_tokens", label: "Output Tokens" },
              {
                key: "cost_usd",
                label: "Cost",
                render: (value) =>
                  value != null
                    ? `$${Number(value).toFixed(6)}`
                    : "--",
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




// import { useCallback, useEffect, useState } from "react";

// import DashboardLayout from "./components/layout/DashboardLayout.jsx";

// import {
//   getTasks,
//   getTraces,
// } from "./services/api.js";

// import {
//   ResponsiveContainer,
//   BarChart,
//   Bar,
//   XAxis,
//   YAxis,
//   CartesianGrid,
//   Tooltip,
// } from "recharts";

// import {
//   RefreshCw,
//   ShieldAlert,
//   CheckCircle2,
//   Clock,
//   Activity,
//   DollarSign,
//   ListTodo,
// } from "lucide-react";

// // Handles both direct arrays and common API response wrappers.
// function extractRows(response, keys) {
//   if (Array.isArray(response)) return response;

//   for (const key of keys) {
//     if (Array.isArray(response?.[key])) {
//       return response[key];
//     }
//   }

//   return [];
// }

// function formatDate(value) {
//   if (!value) return "--";

//   const date = new Date(value);

//   if (Number.isNaN(date.getTime())) return String(value);

//   return date.toLocaleString();
// }

// function MetricCard({ title, value, icon: Icon, description }) {
//   return (
//     <div className="rounded-xl border border-slate-800 bg-slate-950 p-5">
//       <div className="flex items-center justify-between">
//         <p className="text-sm text-slate-400">{title}</p>
//         <Icon size={20} className="text-indigo-400" />
//       </div>

//       <p className="mt-4 text-2xl font-bold text-white">
//         {value}
//       </p>

//       <p className="mt-2 text-xs text-slate-500">
//         {description}
//       </p>
//     </div>
//   );
// }

// function Section({ title, icon: Icon, children }) {
//   return (
//     <section className="rounded-xl border border-slate-800 bg-slate-950 p-6">
//       <div className="mb-6 flex items-center gap-3">
//         {Icon && <Icon size={20} className="text-indigo-400" />}
//         <h2 className="text-lg font-semibold text-white">{title}</h2>
//       </div>
//       {children}
//     </section>
//   );
// }

// function DataTable({ columns, rows, emptyMessage }) {
//   if (!rows.length) {
//     return (
//       <p className="py-8 text-center text-sm text-slate-500">
//         {emptyMessage}
//       </p>
//     );
//   }

//   return (
//     <div className="overflow-x-auto">
//       <table className="w-full text-left text-sm">
//         <thead>
//           <tr className="border-b border-slate-800 text-slate-400">
//             {columns.map((column) => (
//               <th key={column.key} className="whitespace-nowrap px-4 py-3 font-medium">
//                 {column.label}
//               </th>
//             ))}
//           </tr>
//         </thead>

//         <tbody>
//           {rows.map((row, index) => (
//             <tr
//               key={row.id ?? row.task_id ?? index}
//               className="border-b border-slate-800/70 text-slate-300 last:border-0 hover:bg-slate-900/70"
//             >
//               {columns.map((column) => (
//                 <td key={column.key} className="max-w-xs px-4 py-3">
//                   {column.render
//                     ? column.render(row[column.key], row)
//                     : row[column.key] ?? "--"}
//                 </td>
//               ))}
//             </tr>
//           ))}
//         </tbody>
//       </table>
//     </div>
//   );
// }

// function App() {
//   const [tasks, setTasks] = useState([]);
//   const [traces, setTraces] = useState([]);

//   const [loading, setLoading] = useState(true);
//   const [refreshing, setRefreshing] = useState(false);
//   const [error, setError] = useState("");

//   const loadDashboard = useCallback(async (initial = false) => {
//     if (initial) {
//       setLoading(true);
//     } else {
//       setRefreshing(true);
//     }

//     try {
//       setError("");

//       const [taskResponse, traceResponse] = await Promise.all([
//         getTasks(),
//         getTraces(),
//       ]);

//       setTasks(
//         extractRows(taskResponse, ["tasks", "items", "data"])
//       );

//       setTraces(
//         extractRows(traceResponse, ["traces", "items", "data"])
//       );
//     } catch (err) {
//       setError(err.message || "Unable to load dashboard data");
//     } finally {
//       setLoading(false);
//       setRefreshing(false);
//     }
//   }, []);

//   useEffect(() => {
//     loadDashboard(true);

//     const interval = setInterval(() => {
//       loadDashboard(false);
//     }, 15000);

//     return () => clearInterval(interval);
//   }, [loadDashboard]);

//   // Calculate the same metrics as the original Streamlit dashboard.
//   const totalTasks = tasks.length;

//   const totalCost = traces.reduce(
//     (sum, trace) => sum + (Number(trace.cost_usd) || 0),
//     0
//   );

//   const averageLatency = traces.length
//     ? traces.reduce(
//         (sum, trace) => sum + (Number(trace.latency_ms) || 0),
//         0
//       ) / traces.length
//     : 0;

//   const passedSteps = traces.filter(
//     (trace) =>
//       trace.passed === true ||
//       trace.passed === 1 ||
//       trace.passed === "true"
//   ).length;

//   const passRate = traces.length
//     ? (passedSteps / traces.length) * 100
//     : 0;

//   const pendingTasks = tasks.filter(
//     (task) => task.status === "awaiting_approval"
//   );

//   // Average latency grouped by agent node.
//   const latencyMap = {};

//   traces.forEach((trace) => {
//     const node = trace.node || "unknown";

//     if (!latencyMap[node]) {
//       latencyMap[node] = { total: 0, count: 0 };
//     }

//     latencyMap[node].total += Number(trace.latency_ms) || 0;
//     latencyMap[node].count += 1;
//   });

//   const latencyData = Object.entries(latencyMap).map(
//     ([node, values]) => ({
//       node,
//       latency: values.total / values.count,
//     })
//   );

//   // Total cost grouped by agent node.
//   const costMap = {};

//   traces.forEach((trace) => {
//     const node = trace.node || "unknown";

//     costMap[node] =
//       (costMap[node] || 0) + (Number(trace.cost_usd) || 0);
//   });

//   const costData = Object.entries(costMap).map(
//     ([node, cost]) => ({
//       node,
//       cost,
//     })
//   );

//   // Prompt injection security events.
//   const securityEvents = traces.filter(
//     (trace) => trace.node === "research.security"
//   );

//   // Most recent traces first.
//   const recentTraces = [...traces]
//     .sort(
//       (a, b) =>
//         new Date(b.created_at || 0).getTime() -
//         new Date(a.created_at || 0).getTime()
//     )
//     .slice(0, 100);

//   return (
//     <DashboardLayout>
//       <div className="space-y-8">

//         {/* Page heading */}
//         <div className="flex flex-wrap items-center justify-between gap-4">
//           <div>
//             <h1 className="text-3xl font-bold text-white">
//               AgentOps Overview
//             </h1>
//             <p className="mt-2 text-sm text-slate-400">
//               Live observability for your multi-agent system.
//             </p>
//           </div>

//           <button
//             onClick={() => loadDashboard(false)}
//             disabled={refreshing}
//             className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
//           >
//             <RefreshCw
//               size={16}
//               className={refreshing ? "animate-spin" : ""}
//             />
//             Refresh
//           </button>
//         </div>

//         {/* Error message */}
//         {error && (
//           <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
//             Dashboard error: {error}
//           </div>
//         )}

//         {/* Top metrics */}
//         <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-5">
//           <MetricCard
//             title="Total Tasks"
//             value={loading ? "..." : totalTasks}
//             icon={ListTodo}
//             description="Recorded agent tasks"
//           />

//           <MetricCard
//             title="Total Cost"
//             value={loading ? "..." : `$${totalCost.toFixed(6)}`}
          
//             icon={DollarSign}
//             description="Total execution cost"
//           />

//           <MetricCard
//             title="Avg Latency"
//             value={loading ? "..." : `${averageLatency.toFixed(2)} ms`}
//             icon={Clock}
//             description="Average latency per step"
//           />

//           <MetricCard
//             title="Step Pass Rate"
//             value={loading ? "..." : `${passRate.toFixed(1)}%`}
//             icon={CheckCircle2}
//             description={`${passedSteps} / ${traces.length} passed steps`}
//           />

//           <MetricCard
//             title="Pending Approvals"
//             value={loading ? "..." : pendingTasks.length}
//             icon={Activity}
//             description="Awaiting human review"
//           />
//         </div>

//         {/* Performance charts */}
//         <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">

//           <Section title="Average Latency by Node">
//             {latencyData.length ? (
//               <ResponsiveContainer width="100%" height={300}>
//                 <BarChart data={latencyData}>
//                   <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
//                   <XAxis dataKey="node" stroke="#94a3b8" />
//                   <YAxis stroke="#94a3b8" />
//                   <Tooltip
//                     contentStyle={{
//                       backgroundColor: "#0f172a",
//                       border: "1px solid #334155",
//                       color: "#fff",
//                     }}
//                   />
//                   <Bar dataKey="latency" name="Latency (ms)" fill="#818cf8" radius={[5, 5, 0, 0]} />
//                 </BarChart>
//               </ResponsiveContainer>
//             ) : (
//               <p className="py-12 text-center text-slate-500">
//                 No latency data available.
//               </p>
//             )}
//           </Section>

//           <Section title="Total Cost by Node">
//             {costData.length ? (
//               <ResponsiveContainer width="100%" height={300}>
//                 <BarChart data={costData}>
//                   <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
//                   <XAxis dataKey="node" stroke="#94a3b8" />
//                   <YAxis stroke="#94a3b8" />
//                   <Tooltip
//                     formatter={(value) => `$${Number(value).toFixed(6)}`}
//                     contentStyle={{
//                       backgroundColor: "#0f172a",
//                       border: "1px solid #334155",
//                       color: "#fff",
//                     }}
//                   />
//                   <Bar dataKey="cost" name="Cost (USD)" fill="#34d399" radius={[5, 5, 0, 0]} />
//                 </BarChart>
//               </ResponsiveContainer>
//             ) : (
//               <p className="py-12 text-center text-slate-500">
//                 No cost data available.
//               </p>
//             )}
//           </Section>
//         </div>

//         {/* Security events */}
//         <Section title="Security Events — Prompt Injection" icon={ShieldAlert}>
//           {securityEvents.length === 0 ? (
//             <div className="flex items-center gap-3 rounded-lg bg-emerald-500/10 p-4 text-emerald-400">
//               <CheckCircle2 size={20} />
//               <p className="text-sm">
//                 No injection attempts detected in the recorded traces.
//               </p>
//             </div>
//           ) : (
//             <>
//               <div className="mb-4 rounded-lg bg-red-500/10 p-4 text-sm text-red-400">
//                 {securityEvents.length} potential prompt injection event(s) detected.
//               </div>

//               <DataTable
//                 rows={securityEvents}
//                 emptyMessage="No security events."
//                 columns={[
//                   { key: "task_id", label: "Task ID" },
//                   { key: "input_summary", label: "Input Summary" },
//                   { key: "output_summary", label: "Output Summary" },
//                   {
//                     key: "created_at",
//                     label: "Created At",
//                     render: (value) => formatDate(value),
//                   },
//                 ]}
//               />
//             </>
//           )}
//         </Section>

//         {/* Pending approvals */}
//         <Section title="Tasks Awaiting Human Approval" icon={Clock}>
//           <DataTable
//             rows={pendingTasks}
//             emptyMessage="No tasks are awaiting approval."
//             columns={[
//               { key: "id", label: "Task ID" },
//               { key: "description", label: "Description" },
//               {
//                 key: "created_at",
//                 label: "Created At",
//                 render: (value) => formatDate(value),
//               },
//             ]}
//           />
//         </Section>

//         {/* Recent traces */}
//         <Section title="Recent Agent Steps" icon={Activity}>
//           <DataTable
//             rows={recentTraces}
//             emptyMessage="No traces yet. Send a task to the API using POST /tasks to see data here."
//             columns={[
//               { key: "task_id", label: "Task ID" },
//               { key: "node", label: "Node" },
//               {
//                 key: "latency_ms",
//                 label: "Latency",
//                 render: (value) =>
//                   value != null ? `${Number(value).toFixed(2)} ms` : "--",
//               },
//               { key: "input_tokens", label: "Input Tokens" },
//               { key: "output_tokens", label: "Output Tokens" },
//               {
//                 key: "cost_usd",
//                 label: "Cost",
//                 render: (value) =>
//                   value != null ? `$${Number(value).toFixed(6)}` : "--",
//               },
//               {
//                 key: "passed",
//                 label: "Status",
//                 render: (value) => {
//                   const passed =
//                     value === true ||
//                     value === 1 ||
//                     value === "true";

//                   return (
//                     <span
//                       className={
//                         passed
//                           ? "rounded-full bg-emerald-500/10 px-3 py-1 text-xs text-emerald-400"
//                           : "rounded-full bg-red-500/10 px-3 py-1 text-xs text-red-400"
//                       }
//                     >
//                       {passed ? "Passed" : "Failed"}
//                     </span>
//                   );
//                 },
//               },
//               {
//                 key: "created_at",
//                 label: "Created At",
//                 render: (value) => formatDate(value),
//               },
//             ]}
//           />
//         </Section>

//         <p className="text-center text-xs text-slate-600">
//           AgentOps Observability Dashboard · Auto-refresh every 15 seconds
//         </p>
//       </div>
//     </DashboardLayout>
//   );
// }

// export default App;
