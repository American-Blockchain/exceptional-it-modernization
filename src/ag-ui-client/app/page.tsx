"use client";

import { useMemo, useState } from "react";
import { CopilotChat } from "@copilotkit/react-ui";
import { useCopilotChat } from "@copilotkit/react-core";
import { Badge } from "@/components/ui/badge";
import { Activity, TerminalSquare, LayoutDashboard } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function AgentCommandCenter() {
  // Hook into the CopilotKit state stream from the Python LangGraph backend
  const { isLoading, visibleMessages } = useCopilotChat();
  const [activeView, setActiveView] = useState<"chat" | "dashboard">("chat");

  // Dynamically calculate total tokens consumed across the entire MAS session
  const totalTokens = useMemo(() => {
    // PROTECT AGAINST SSR BUILD CRASH: Return 0 if undefined
    if (!visibleMessages) return 0;

    return visibleMessages
      .filter((m: any) => m.role === "system")
      .map((m: any) => {
        // Safely extract the string whether CopilotKit is using .content or .text
        const contentStr = typeof m.content === "string" ? m.content : 
                           typeof m.text === "string" ? m.text : "";
                           
        const match = contentStr.match(/Tokens Consumed:\s*(\d+)/);
        return match ? parseInt(match[1], 10) : 0;
      })
      .reduce((acc, curr) => acc + curr, 0);
  }, [visibleMessages]);

  return (
    <div className="flex flex-col h-screen max-w-7xl mx-auto p-4 md:p-8 bg-background">
      
      {/* Dynamic Header */}
      <header className="flex justify-between items-center mb-8 border-border border-b pb-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground">Multi-Agent Operations</h1>
          <p className="text-muted-foreground mt-1">Routing architecture via Semantic Kernel & Agent Lightning</p>
        </div>
        <div className="flex items-center gap-4">
          <Badge variant="outline" className="px-3 py-1 bg-green-950 text-green-400 border-green-800">
            {isLoading ? "Agents Processing..." : "System Online"}
          </Badge>
          
          {/* Live Token Counter Badge — replaces the dead NotificationPopover */}
          <Badge variant="outline" className="px-3 py-1 flex items-center gap-2 border-blue-800 bg-blue-950 text-blue-400 font-mono">
            <Activity size={14} className={isLoading ? "animate-pulse" : ""} />
            Tokens Used: {totalTokens.toLocaleString()}
          </Badge>
        </div>
      </header>

      {/* View Toggle */}
      <div className="flex gap-4 mb-4">
        <Button 
          variant={activeView === "chat" ? "default" : "outline"} 
          onClick={() => setActiveView("chat")}
          className="flex items-center gap-2"
        >
          <TerminalSquare size={16} /> Student Execution Console
        </Button>
        <Button 
          variant={activeView === "dashboard" ? "default" : "outline"} 
          onClick={() => setActiveView("dashboard")}
          className="flex items-center gap-2"
        >
          <LayoutDashboard size={16} /> Agent Lightning Dashboard
        </Button>
      </div>

      {/* Main Grid Layout */}
      <main className="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-8 overflow-hidden">
        
        {/* Left Column: Dynamic View (Chat or Dashboard) */}
        <section className="lg:col-span-2 flex flex-col h-full bg-card rounded-xl border border-border shadow-sm overflow-hidden">
          {activeView === "chat" ? (
            <>
              <div className="p-4 bg-secondary/50 border-b border-border flex justify-between items-center">
                <h2 className="font-semibold">Student Execution Console</h2>
                <Badge variant="secondary">GPT-4o-Mini Active</Badge>
              </div>
              <div className="flex-1 relative">
                <CopilotChat 
                  labels={{
                    title: "Student Agent Output",
                    initial: "Hello, I am the MAS Orchestrator. Provide a task, and I will dispatch it to the Student and Teacher models.",
                  }}
                  makeSystemMessage={(contextString) => `You are interfacing with the mas_orchestrator agent. ${contextString}`}
                />
              </div>
            </>
          ) : (
            <>
              <div className="p-4 bg-secondary/50 border-b border-border flex justify-between items-center">
                <h2 className="font-semibold">Agent Lightning APO Dashboard</h2>
                <Badge variant="secondary" className="bg-amber-900 text-amber-400 border-amber-700">Live Traces & Rewards</Badge>
              </div>
              <div className="flex-1 relative bg-white">
                {/* Embed the Agent Lightning Dashboard via Next.js Proxy */}
                <iframe src="/agl-dashboard" className="w-full h-full border-0" title="Agent Lightning Dashboard" />
              </div>
            </>
          )}
        </section>

        {/* Right Column: Live Streamed Data */}
        <section className="flex flex-col gap-6 overflow-y-auto pr-2">
          
          {/* Card: Notable Events Overview */}
          <div className="bg-card rounded-xl border border-border p-5 shadow-sm">
            <h3 className="font-semibold text-foreground mb-4">Notable Events Overview</h3>
            <ul className="space-y-4">
              {/* PROTECT AGAINST SSR BUILD CRASH: Fallback to empty array */}
              {(visibleMessages || []).filter((m: any) => m.role === "system").map((msg: any, i: number) => {
                const textOutput = msg.content || msg.text || "";
                return (
                  <li key={i} className="flex gap-3 text-sm">
                    <span className="text-blue-500 font-bold whitespace-nowrap">Agent Event</span>
                    <span className="text-muted-foreground">{textOutput}</span>
                  </li>
                );
              })}
              {(visibleMessages || []).filter((m: any) => m.role === "system").length === 0 && (
                <span className="text-muted-foreground text-sm italic">Awaiting rollout triggers...</span>
              )}
            </ul>
          </div>
        </section>
      </main>
    </div>
  );
}
