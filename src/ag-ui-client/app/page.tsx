"use client";

import { useMemo } from "react";
import { CopilotChat } from "@copilotkit/react-ui";
import { useCopilotChat } from "@copilotkit/react-core";
import { Badge } from "@/components/ui/badge";
import { Activity } from "lucide-react";

export default function AgentCommandCenter() {
  // Hook into the CopilotKit state stream from the Python LangGraph backend
  const { isLoading, visibleMessages } = useCopilotChat();

  // Dynamically calculate total tokens consumed across the entire MAS session
  const totalTokens = useMemo(() => {
    return visibleMessages
      .filter((m) => m.role === "system")
      .map((m) => {
        // Regex to extract the token integer broadcasted by Python's notable_events
        const match = m.content.match(/Tokens Consumed:\s*(\d+)/);
        return match ? parseInt(match[1], 10) : 0;
      })
      .reduce((acc, curr) => acc + curr, 0);
  }, [visibleMessages]);

  return (
    <div className="flex h-screen w-full flex-col bg-background p-6 lg:p-10">
      
      {/* Header with Live Token Tracking */}
      <header className="flex w-full items-center justify-between pb-6 mb-6 border-b border-border">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground">
            Elite MAS - Agent Lightning Control
          </h1>
          <p className="text-muted-foreground mt-2 text-sm">
            Real-time observability into the Teacher &amp; Student workflow.
          </p>
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

      {/* Main Grid Layout */}
      <main className="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-8 overflow-hidden">
        
        {/* Left Column: Copilot Chat (The Student Interface) */}
        <section className="lg:col-span-2 flex flex-col h-full bg-card rounded-xl border border-border shadow-sm overflow-hidden">
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
        </section>

        {/* Right Column: Live Streamed Data */}
        <section className="flex flex-col gap-6 overflow-y-auto">
          
          {/* Card: Live APO Critiques from Teacher */}
          <div className="bg-card rounded-xl border border-destructive/30 p-5 shadow-sm space-y-4">
            <div className="flex justify-between items-center">
              <h3 className="font-bold text-destructive">Live APO Critiques</h3>
              <Badge variant="destructive">GPT-4.5</Badge>
            </div>
            
            {/* Skeleton loader while the Teacher node is executing in Python */}
            {isLoading && (
              <div className="animate-pulse flex space-x-4">
                <div className="flex-1 space-y-4 py-1">
                  <div className="h-2 bg-destructive/20 rounded"></div>
                  <div className="h-2 bg-destructive/20 rounded w-5/6"></div>
                </div>
              </div>
            )}
            {!isLoading && (
               <p className="text-sm text-foreground/80 leading-relaxed border-l-2 border-destructive pl-4 py-1 italic">
                 Awaiting execution loop...
               </p>
            )}
          </div>

          {/* Card: Live Trace Events from LangGraph execution */}
          <div className="bg-card rounded-xl border border-border p-5 shadow-sm flex-1">
            <h3 className="font-bold mb-4 text-foreground">Trace Events</h3>
            <ul className="space-y-4">
              <li className="flex gap-3 text-sm">
                 <span className="text-blue-500 font-bold whitespace-nowrap">System</span>
                 <span className="text-muted-foreground">Connected to C# YARP Gateway.</span>
              </li>
              {/* Messages from LangGraph execution auto-populate via CopilotKit state sync */}
              {visibleMessages.filter(m => m.role === "system").map((msg, i) => (
                <li key={i} className="flex gap-3 text-sm">
                  <span className="text-blue-500 font-bold whitespace-nowrap">Agent Event</span>
                  <span className="text-muted-foreground">{msg.content}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>
      </main>
    </div>
  );
}
