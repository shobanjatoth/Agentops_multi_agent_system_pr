
import { Bell, Search, CircleUserRound } from "lucide-react";

function Header() {
  return (
    <header className="flex h-20 items-center justify-between border-b border-slate-800 bg-slate-950 px-8">
      <div>
        <h2 className="text-xl font-semibold text-white">
          Agent Operations
        </h2>
        <p className="text-sm text-slate-400">
          Monitor and manage your AI agents
        </p>
      </div>

      <div className="flex items-center gap-5">
        <div className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2">
          <Search size={17} className="text-slate-400" />
          <span className="text-sm text-slate-500">Search...</span>
        </div>

        <button className="text-slate-400 hover:text-white">
          <Bell size={20} />
        </button>

        <div className="flex items-center gap-2">
          <CircleUserRound size={27} className="text-indigo-400" />
          <span className="text-sm text-slate-300">Admin</span>
        </div>
      </div>
    </header>
  );
}

export default Header;

