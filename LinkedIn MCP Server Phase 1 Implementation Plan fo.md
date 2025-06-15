# Implementation Plan: Main Agent → LinkedIn Agent → Playwright MCP Server

This plan refactors and extends your existing code to separate concerns clearly. The overall flow is:

1. **Main Jarvis Agent**  
2. **LinkedIn Specialist Agent**  
3. **Playwright MCP Server**  

Each layer focuses on distinct responsibilities: orchestration, navigation logic, and low-level browser automation.

---

## 1. Main Jarvis Agent Integration

### Responsibilities

- Detect LinkedIn-related queries  
- Delegate execution to the LinkedIn specialist agent  
- Integrate results into the global conversation flow  

### Key Steps

1. **Tool Registration**  
   Register the LinkedIn agent as an AgentTool within your main ADK agent configuration.  
2. **Delegation Logic**  
   Use a keyword-based or LLM-based router to invoke `linkedin_specialist.search_jobs` for queries containing “LinkedIn” or “job”[1].  
3. **Result Aggregation**  
   Receive JSON job listings and format them for user output.

```python
# main_agent.py (simplified)
from google.adk.agents import LlmAgent
from google.adk.tools import AgentTool
from linkedin_agent import LinkedInSpecialistAgent

linkedin_tool = AgentTool(
    agent=LinkedInSpecialistAgent(),
    name="linkedin_job_search",
    description="Search LinkedIn recommended jobs"
)
main_agent = LlmAgent(
    name="jarvis_main",
    tools=[linkedin_tool, ...]
)
```

---

## 2. LinkedIn Specialist Agent

### Responsibilities

- Orchestrate page navigation logic  
- Handle login checks and authentication  
- Call the Playwright MCP server for low-level actions  

### Refactoring the Attached Code

- **Extract Navigation Sequences** (e.g., login, navigate to jobs) into reusable methods.  
- **Wrap MCP Calls** behind clear methods: `login_if_needed()`, `go_to_recommended_jobs()`, `extract_job_cards()`.  

```python
# linkedin_agent.py
class LinkedInSpecialistAgent:
    async def search_jobs(self, user_id, max_results=5):
        # 1. Ensure login
        await mcp_client.call_tool("login")  
        # 2. Navigate to recommended jobs
        await mcp_client.call_tool("go_to_jobs")  
        # 3. Extract job cards
        raw = await mcp_client.call_tool("search_jobs", {"max_results": max_results})
        return json.loads(raw[0].text)
```

### Suggested Method Breakouts

| Method                    | Purpose                                         |
|---------------------------|-------------------------------------------------|
| `login_if_needed()`       | Check current URL; call `"login"` MCP tool     |
| `go_to_recommended_jobs()`| Call `"navigate_to_jobs"` MCP tool             |
| `extract_job_cards(n)`    | Call `"search_jobs"` to return structured data  |

---

## 3. Playwright MCP Server Refinements

### Responsibilities

- Perform browser automation via Playwright  
- Expose tools: `login`, `navigate_to_jobs`, `search_jobs`  

### Recommended Refactors

1. **Split Large Functions**  
   - `initialize()`, `apply_stealth_mode()`, and `cleanup()` remain in `LinkedInAutomation`.  
   - Create discrete MCP tools in `ADK_LINKEDIN_TOOLS`:  

```python
# src/index.py snippet
ADK_LINKEDIN_TOOLS = {
    "login": FunctionTool(func=linkedin_automation.initialize),
    "navigate_to_jobs": FunctionTool(func=linkedin_automation.go_to_jobs_page),
    "search_jobs": FunctionTool(func=linkedin_automation.search_jobs),
}
```

2. **Add `go_to_jobs_page()`**  
   Factor out navigation logic from `search_jobs()` into its own async function:

```python
async def go_to_jobs_page() -> str:
    await automation.page.goto('https://linkedin.com/jobs/collections/recommended/')
    await automation.page.wait_for_selector('div.jobs-search-results-list', timeout=15000)
    return "navigated"
```

3. **Parameterize Selectors and Delays**  
   Move selectors and timeout values into a `linkedin_config.py` module for easy maintenance.

---

## 4. End-to-End Workflow

1. **User Query** → Main Agent  
2. Main Agent invokes **LinkedInSpecialistAgent.search_jobs**  
3. Specialist calls MCP tools in sequence:  
   - `"login"` → `"navigate_to_jobs"` → `"search_jobs"`  
4. **MCP Server** runs corresponding Playwright actions, returns JSON  
5. Specialist formats JSON, returns to Main Agent  
6. Main Agent responds to user with job list  

---

## 5. Timeline & Milestones

| Week | Task                                                                 |
|------|----------------------------------------------------------------------|
| 1    | Refactor MCP server: split tools (`login`, `navigate_to_jobs`)      |
| 2    | Implement LinkedInSpecialistAgent with orchestrated tool calls      |
| 3    | Integrate specialist as AgentTool into main agent; router logic     |
| 4    | End-to-end testing, error handling (timeouts, re-login)              |

---

## References

[1] Google ADK Agents: orchestration patterns.

[1] <https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/15186568/fdf8f14d-0367-4018-a6a7-e12aff339d80/paste.txt>
