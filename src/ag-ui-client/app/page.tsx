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
    let tokens = 0;
    visibleMessages.forEach((msg) => {
      if (typeof msg.content === "string") {
        const match = msg.content.match(/Tokens Consumed: (\d+)/);
        if (match) {
          tokens += parseInt(match[1], 10);
        }
      }
    });
    return tokens;
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
          
          {/* Card: Live APO Critiques from Teacher */}
          <div className="bg-card rounded-xl border border-border p-5 shadow-sm">
            <h3 className="font-semibold text-foreground mb-4">Teacher APO Critiques</h3>
            <div className="space-y-4">
              {visibleMessages
                .filter((m) => typeof m.content === "string" && m.content.includes("APO Critique"))
                .reverse()
                .map((msg, i) => (
                  <div key={i} className="text-sm p-3 bg-secondary/30 border border-secondary rounded-lg">
                    {msg.content}
                  </div>
              ))}
              {visibleMessages.length === 0 && (
                <span className="text-muted-foreground text-sm italic">Awaiting rollout triggers...</span>
              )}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
