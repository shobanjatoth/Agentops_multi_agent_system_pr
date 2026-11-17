
import {
  LayoutDashboard,
  ListTodo,
  Activity,
  ShieldCheck,
  ClipboardCheck,
  Bot,
} from "lucide-react";

const menuItems = [
  { name: "Overview", icon: LayoutDashboard },
  { name: "Tasks", icon: ListTodo },
  { name: "Traces", icon: Activity },
  { name: "Approvals", icon: ClipboardCheck },
  { name: "Security", icon: ShieldCheck },
];

function Sidebar() {
  return (
    <aside className="flex min-h-screen w-64 flex-col border-r border-slate-800 bg-slate-950 p-5">
      <div className="mb-10 flex items-center gap-3">
        <div className="rounded-lg bg-indigo-600 p-2">
          <Bot size={24} />
        </div>
        <div>
          <h1 className="text-xl font-bold text-white">AgentOps</h1>
          <p className="text-xs text-slate-400">Operations Platform</p>
        </div>
      </div>

      <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
        Workspace
      </p>

      <nav className="space-y-2">
        {menuItems.map((item) => {
          const Icon = item.icon;

          return (
            <button
              key={item.name}
              className="flex w-full items-center gap-3 rounded-lg px-4 py-3 text-left text-sm text-slate-400 transition hover:bg-slate-800 hover:text-white"
            >
              <Icon size={19} />
              {item.name}
            </button>
          );
        })}
      </nav>

      <div className="mt-auto border-t border-slate-800 pt-5">
        <p className="text-xs text-slate-500">AgentOps Dashboard</p>
        <p className="mt-1 text-xs text-slate-600">Version 1.0.0</p>
      </div>
    </aside>
  );
}

export default Sidebar;

