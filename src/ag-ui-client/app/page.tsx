"use client";

import { CopilotChat } from "@copilotkit/react-ui";
import { NotificationPopover } from "@/components/demo";
import { Badge } from "@/components/ui/badge";

export default function AgentCommandCenter() {
  return (
    <div className="flex h-screen w-full flex-col bg-background p-6 lg:p-10">
      
      {/* Header with Tracking and Notifications */}
      <header className="flex w-full items-center justify-between pb-6 mb-6 border-b border-border">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground">
            Elite MAS - Agent Lightning Control
          </h1>
          <p className="text-muted-foreground mt-2 text-sm">
            Real-time observability into the Teacher (GPT-4.5) & Student (GPT-4o-Mini) workflow.
          </p>
        </div>
        
        <div className="flex items-center gap-4">
          <Badge variant="outline" className="px-3 py-1 bg-green-950 text-green-400 border-green-800">
            System Online 
          </Badge>
          <NotificationPopover />
        </div>
      </header>

      {/* Main Grid Layout for Innovative Data Splitting */}
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
                initial: "Hello, I am your specialized agent. What tasks do you need executed?",
              }}
            />
          </div>
        </section>

        {/* Right Column: Teacher Analysis & Highlights */}
        <section className="flex flex-col gap-6 overflow-y-auto">
          
          {/* Card: Teacher Critiques (Textual Gradients) */}
          <div className="bg-card rounded-xl border border-destructive/30 p-5 shadow-sm space-y-4">
            <div className="flex justify-between items-center">
              <h3 className="font-bold text-destructive">APO Critiques (Teacher)</h3>
              <Badge variant="destructive">GPT-4.5-Preview</Badge>
            </div>
            <p className="text-sm text-foreground/80 leading-relaxed border-l-2 border-destructive pl-4 py-1 italic">
              "The student failed to parse the JSON schema on step 3. Suggest explicitly injecting strict mode formatting into the system prompt."
            </p>
            <p className="text-sm text-foreground/80 leading-relaxed border-l-2 border-destructive pl-4 py-1 italic">
              "Tool call timeout detected in API bridge. Instruct the student to verify connection thresholds prior to sequential loops."
            </p>
          </div>

          {/* Card: Key Moments & Event Highlights */}
          <div className="bg-card rounded-xl border border-border p-5 shadow-sm flex-1">
            <h3 className="font-bold mb-4 text-foreground">Notable Events Overview</h3>
            <ul className="space-y-4">
              <li className="flex gap-3 text-sm">
                <span className="text-blue-500 font-bold whitespace-nowrap">12:45 PM</span>
                <span className="text-muted-foreground">Automated Prompt Optimization updated template hash <Badge variant="secondary">a1b2c3d</Badge></span>
              </li>
              <li className="flex gap-3 text-sm">
                <span className="text-blue-500 font-bold whitespace-nowrap">12:40 PM</span>
                <span className="text-muted-foreground">Teacher evaluated batch processing score: <span className="text-green-500 font-medium">94/100</span></span>
              </li>
              <li className="flex gap-3 text-sm">
                <span className="text-blue-500 font-bold whitespace-nowrap">11:15 AM</span>
                <span className="text-muted-foreground">Azure Container Apps Orchestrator re-deployed Python specialist trace listeners.</span>
              </li>
            </ul>
          </div>

        </section>
      </main>
    </div>
  );
}
