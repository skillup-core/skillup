## Starting Your First Debug Session

Before using the debugger for the first time, you need to load your SKILL module once in Cadence CIW.

**Step 1 — Load SKILL Module (once per session)**

Click the **?** icon next to the CIW button to view the load command.  
Copy the displayed `load("...")` command, paste it into Cadence CIW, and run it.

**Step 2 — Set Breakpoints**

Position your cursor on the line where you want execution to stop and press **F9**.  
A red dot (●) appears next to the line number when the breakpoint is set.

**Step 3 — Start Debugging**

Press **F5** to start the debug session.  
When execution stops at a breakpoint, check the current values in the **Variables** panel,  
and control the flow with **F10** (next), **F5** (continue), and **Shift+F5** (stop).
