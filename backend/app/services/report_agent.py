"""
Report Agent service.

Implements ReACT-style simulation report generation using LangChain + Zep.

Features:
1. Generate a report from the simulation requirement and the Zep knowledge graph.
2. Plan the table of contents first, then generate one section at a time.
3. Each section uses a ReACT multi-round thought and reflection loop.
4. Support a chat mode that can autonomously invoke retrieval tools.
"""

import os
import json
import time
import re
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from ..utils.locale import get_language_instruction, t
from .zep_tools import (
    ZepToolsService, 
    SearchResult, 
    InsightForgeResult, 
    PanoramaResult,
    InterviewResult
)

logger = get_logger('mirofish.report_agent')


class ReportLogger:
    """
    Detailed log recorder for the Report Agent.

    Writes an ``agent_log.jsonl`` file inside the report folder that captures every
    step of agent activity. Each line is a complete JSON object containing a
    timestamp, the action type, and the detailed payload.
    """

    def __init__(self, report_id: str):
        """
        Initialize the log recorder.

        Args:
            report_id: Report ID used to determine the log file path.
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'agent_log.jsonl'
        )
        self.start_time = datetime.now()
        self._ensure_log_file()
    
    def _ensure_log_file(self):
        """Ensure the directory for the log file exists."""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)

    def _get_elapsed_time(self) -> float:
        """Return the elapsed time in seconds since start."""
        return (datetime.now() - self.start_time).total_seconds()
    
    def log(
        self, 
        action: str, 
        stage: str,
        details: Dict[str, Any],
        section_title: str = None,
        section_index: int = None
    ):
        """
        Record a single log entry.

        Args:
            action: Action type, e.g. ``"start"``, ``"tool_call"``, ``"llm_response"``,
                ``"section_complete"``, etc.
            stage: Current stage, e.g. ``"planning"``, ``"generating"``, ``"completed"``.
            details: Detail payload dict; never truncated.
            section_title: Title of the current section (optional).
            section_index: Index of the current section (optional).
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": round(self._get_elapsed_time(), 2),
            "report_id": self.report_id,
            "action": action,
            "stage": stage,
            "section_title": section_title,
            "section_index": section_index,
            "details": details
        }
        
        with open(self.log_file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    
    def log_start(self, simulation_id: str, graph_id: str, simulation_requirement: str):
        """Record the start of a report generation run."""
        self.log(
            action="report_start",
            stage="pending",
            details={
                "simulation_id": simulation_id,
                "graph_id": graph_id,
                "simulation_requirement": simulation_requirement,
                "message": t('report.taskStarted')
            }
        )
    
    def log_planning_start(self):
        """Record the start of outline planning."""
        self.log(
            action="planning_start",
            stage="planning",
            details={"message": t('report.planningStart')}
        )
    
    def log_planning_context(self, context: Dict[str, Any]):
        """Record the context retrieved during planning."""
        self.log(
            action="planning_context",
            stage="planning",
            details={
                "message": t('report.fetchSimContext'),
                "context": context
            }
        )
    
    def log_planning_complete(self, outline_dict: Dict[str, Any]):
        """Record the completion of outline planning."""
        self.log(
            action="planning_complete",
            stage="planning",
            details={
                "message": t('report.planningComplete'),
                "outline": outline_dict
            }
        )
    
    def log_section_start(self, section_title: str, section_index: int):
        """Record the start of section generation."""
        self.log(
            action="section_start",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={"message": t('report.sectionStart', title=section_title)}
        )
    
    def log_react_thought(self, section_title: str, section_index: int, iteration: int, thought: str):
        """Record a ReACT thought step."""
        self.log(
            action="react_thought",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "thought": thought,
                "message": t('report.reactThought', iteration=iteration)
            }
        )
    
    def log_tool_call(
        self, 
        section_title: str, 
        section_index: int,
        tool_name: str, 
        parameters: Dict[str, Any],
        iteration: int
    ):
        """Record a tool invocation."""
        self.log(
            action="tool_call",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "parameters": parameters,
                "message": t('report.toolCall', toolName=tool_name)
            }
        )
    
    def log_tool_result(
        self,
        section_title: str,
        section_index: int,
        tool_name: str,
        result: str,
        iteration: int
    ):
        """Record a tool-call result (full content, never truncated)."""
        self.log(
            action="tool_result",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "result": result,  # Full result, no truncation.
                "result_length": len(result),
                "message": t('report.toolResult', toolName=tool_name)
            }
        )
    
    def log_llm_response(
        self,
        section_title: str,
        section_index: int,
        response: str,
        iteration: int,
        has_tool_calls: bool,
        has_final_answer: bool
    ):
        """Record an LLM response (full content, never truncated)."""
        self.log(
            action="llm_response",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "response": response,  # Full response, no truncation.
                "response_length": len(response),
                "has_tool_calls": has_tool_calls,
                "has_final_answer": has_final_answer,
                "message": t('report.llmResponse', hasToolCalls=has_tool_calls, hasFinalAnswer=has_final_answer)
            }
        )
    
    def log_section_content(
        self,
        section_title: str,
        section_index: int,
        content: str,
        tool_calls_count: int
    ):
        """Record completion of section-content generation (content only; not full section completion)."""
        self.log(
            action="section_content",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": content,  # Full content, no truncation.
                "content_length": len(content),
                "tool_calls_count": tool_calls_count,
                "message": t('report.sectionContentDone', title=section_title)
            }
        )
    
    def log_section_full_complete(
        self,
        section_title: str,
        section_index: int,
        full_content: str
    ):
        """
        Record full completion of a section.

        The frontend should listen for this log entry to detect when a section is
        truly finished and to retrieve its full content.
        """
        self.log(
            action="section_complete",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": full_content,
                "content_length": len(full_content),
                "message": t('report.sectionComplete', title=section_title)
            }
        )
    
    def log_report_complete(self, total_sections: int, total_time_seconds: float):
        """Record completion of the entire report."""
        self.log(
            action="report_complete",
            stage="completed",
            details={
                "total_sections": total_sections,
                "total_time_seconds": round(total_time_seconds, 2),
                "message": t('report.reportComplete')
            }
        )
    
    def log_error(self, error_message: str, stage: str, section_title: str = None):
        """Record an error."""
        self.log(
            action="error",
            stage=stage,
            section_title=section_title,
            section_index=None,
            details={
                "error": error_message,
                "message": t('report.errorOccurred', error=error_message)
            }
        )


class ReportConsoleLogger:
    """
    Console-style log recorder for the Report Agent.

    Mirrors console-style log output (INFO, WARNING, etc.) into a
    ``console_log.txt`` file in the report folder. These are plain-text console
    logs, distinct from the structured ``agent_log.jsonl`` entries.
    """

    def __init__(self, report_id: str):
        """
        Initialize the console log recorder.

        Args:
            report_id: Report ID used to determine the log file path.
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'console_log.txt'
        )
        self._ensure_log_file()
        self._file_handler = None
        self._setup_file_handler()
    
    def _ensure_log_file(self):
        """Ensure the directory for the log file exists."""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)

    def _setup_file_handler(self):
        """Set up the file handler so log records are also written to disk."""
        import logging

        self._file_handler = logging.FileHandler(
            self.log_file_path,
            mode='a',
            encoding='utf-8'
        )
        self._file_handler.setLevel(logging.INFO)

        # Use the same compact format as the console handler.
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        self._file_handler.setFormatter(formatter)

        loggers_to_attach = [
            'mirofish.report_agent',
            'mirofish.zep_tools',
        ]

        for logger_name in loggers_to_attach:
            target_logger = logging.getLogger(logger_name)
            # Guard against attaching the same handler twice.
            if self._file_handler not in target_logger.handlers:
                target_logger.addHandler(self._file_handler)
    
    def close(self):
        """Close the file handler and detach it from the loggers."""
        import logging
        
        if self._file_handler:
            loggers_to_detach = [
                'mirofish.report_agent',
                'mirofish.zep_tools',
            ]
            
            for logger_name in loggers_to_detach:
                target_logger = logging.getLogger(logger_name)
                if self._file_handler in target_logger.handlers:
                    target_logger.removeHandler(self._file_handler)
            
            self._file_handler.close()
            self._file_handler = None
    
    def __del__(self):
        """Ensure the file handler is closed on destruction."""
        self.close()


class ReportStatus(str, Enum):
    """Report status."""
    PENDING = "pending"
    PLANNING = "planning"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ReportSection:
    """A single report section."""
    title: str
    content: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content
        }

    def to_markdown(self, level: int = 2) -> str:
        """Convert to Markdown format."""
        md = f"{'#' * level} {self.title}\n\n"
        if self.content:
            md += f"{self.content}\n\n"
        return md


@dataclass
class ReportOutline:
    """Report outline."""
    title: str
    summary: str
    sections: List[ReportSection]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "sections": [s.to_dict() for s in self.sections]
        }
    
    def to_markdown(self) -> str:
        """Convert to Markdown format."""
        md = f"# {self.title}\n\n"
        md += f"> {self.summary}\n\n"
        for section in self.sections:
            md += section.to_markdown()
        return md


@dataclass
class Report:
    """Full report."""
    report_id: str
    simulation_id: str
    graph_id: str
    simulation_requirement: str
    status: ReportStatus
    outline: Optional[ReportOutline] = None
    markdown_content: str = ""
    created_at: str = ""
    completed_at: str = ""
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "simulation_id": self.simulation_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "status": self.status.value,
            "outline": self.outline.to_dict() if self.outline else None,
            "markdown_content": self.markdown_content,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error
        }


# ═══════════════════════════════════════════════════════════════
# Prompt template constants
# ═══════════════════════════════════════════════════════════════

# ── Tool descriptions ──

TOOL_DESC_INSIGHT_FORGE = """\
[Deep Insight Retrieval — Powerful Analytical Tool]
This is our most powerful retrieval function, designed for deep analysis. It will:
1. Automatically decompose your question into multiple sub-questions.
2. Retrieve information from the simulation graph along multiple dimensions.
3. Integrate semantic search, entity analysis, and relationship-chain tracing.
4. Return the most comprehensive and in-depth retrieval content.

[When to use]
- You need an in-depth analysis of a topic.
- You need to understand multiple facets of an event.
- You need rich source material to support a report section.

[Return content]
- Relevant factual quotes (ready to cite verbatim).
- Core entity insights.
- Relationship-chain analysis."""

TOOL_DESC_PANORAMA_SEARCH = """\
[Panorama Search — Full-View Retrieval]
This tool retrieves a complete panorama of the simulation result, ideal for understanding how an event evolved. It will:
1. Pull every related node and relationship.
2. Distinguish currently valid facts from historical or expired facts.
3. Help you trace how public opinion evolved over time.

[When to use]
- You need the full timeline of an event.
- You need to compare opinion shifts between different stages.
- You need a comprehensive view of all entities and relationships.

[Return content]
- Currently valid facts (the latest simulation state).
- Historical or expired facts (the evolution record).
- Every entity involved."""

TOOL_DESC_QUICK_SEARCH = """\
[Quick Search — Lightweight Retrieval]
A lightweight retrieval tool, best for simple, direct lookups.

[When to use]
- You need a quick lookup for a specific piece of information.
- You need to verify a single fact.
- Simple information retrieval.

[Return content]
- A list of facts most relevant to the query."""

TOOL_DESC_INTERVIEW_AGENTS = """\
[Deep Interview — Real Agent Interview (Dual Platform)]
Calls the OASIS simulation environment's interview API to conduct a real interview against the running simulation agents.
This is NOT an LLM simulation — it invokes the real interview endpoint and returns the simulated agents' raw answers.
By default it interviews on both Twitter and Reddit in parallel, capturing more diverse viewpoints.

How it works:
1. Reads the persona files automatically to learn about every simulated agent.
2. Selects the agents most relevant to the interview topic (students, media, officials, etc.).
3. Generates the interview questions automatically.
4. Calls the /api/simulation/interview/batch endpoint on both platforms.
5. Integrates all interview results to provide a multi-perspective view.

[When to use]
- You need to understand an event from different role perspectives (what do students think? What does the media say? What is the official line?).
- You need to collect multi-party opinions and stances.
- You need real answers from simulated agents (sourced from the OASIS simulation environment).
- You want the report to feel vivid and include first-hand "interview transcripts".

[Return content]
- The interviewee agent's identity information.
- Each agent's interview answers on both Twitter and Reddit.
- Key quotations (ready to cite verbatim).
- Interview summary and viewpoint comparison.

[IMPORTANT] A running OASIS simulation environment is required to use this tool!"""

# ── Outline planning prompt ──

PLAN_SYSTEM_PROMPT = """\
You are an expert author of "Future Prediction Reports" with a god's-eye view of the simulated world — you can observe the behavior, statements, and interactions of every agent in the simulation.

[Core idea]
We have built a simulated world and injected a specific "simulation requirement" into it as the input variable. The way that simulated world evolves is itself a prediction of what could happen in reality. You are not looking at "experimental data" — you are watching a rehearsal of the future.

[Your task]
Author a "Future Prediction Report" that answers:
1. Under the conditions we configured, what happened in the future?
2. How did the various agent groups (populations) react and behave?
3. What noteworthy future trends and risks does this simulation reveal?

[Report framing]
- ✅ This is a prediction report grounded in a simulation; it reveals "if X, then what does the future look like".
- ✅ Focus on the predicted outcomes: how the event evolves, group reactions, emergent phenomena, latent risks.
- ✅ Treat the simulated agents' statements and behavior as the prediction of how real-world populations would behave.
- ❌ This is NOT an analysis of the present-day world.
- ❌ This is NOT a generic public-opinion summary.

[Section-count limits]
- Minimum 2 sections, maximum 5 sections.
- No sub-sections — each section is written as a single block of content.
- Keep the content focused; concentrate on the core prediction findings.
- You design the section structure freely based on the prediction outcomes.

Return the report outline as JSON in the following shape:
{
    "title": "Report title",
    "summary": "Report summary (a one-sentence distillation of the core prediction findings)",
    "sections": [
        {
            "title": "Section title",
            "description": "Section content description"
        }
    ]
}

Note: the `sections` array MUST contain at least 2 and at most 5 elements!"""

PLAN_USER_PROMPT_TEMPLATE = """\
[Prediction scenario]
The variable we injected into the simulated world (simulation requirement): {simulation_requirement}

[Simulation scale]
- Total entities participating in the simulation: {total_nodes}
- Total relationships generated between entities: {total_edges}
- Entity-type distribution: {entity_types}
- Active agent count: {total_entities}

[Sample of predicted future facts from the simulation]
{related_facts_json}

Take the god's-eye view of this future rehearsal:
1. Under the conditions we configured, what state does the future reveal?
2. How did the various populations (agents) react and behave?
3. What noteworthy future trends does this simulation reveal?

Based on these prediction outcomes, design the most appropriate section structure for the report.

[Reminder] Section count: minimum 2, maximum 5; keep the content tight and focused on the core prediction findings."""

# ── Section generation prompt ──

SECTION_SYSTEM_PROMPT_TEMPLATE = """\
You are an expert author of "Future Prediction Reports" and you are currently writing one section of the report.

Report title: {report_title}
Report summary: {report_summary}
Prediction scenario (simulation requirement): {simulation_requirement}

Section to write right now: {section_title}

═══════════════════════════════════════════════════════════════
[Core idea]
═══════════════════════════════════════════════════════════════

The simulated world is a rehearsal of the future. We injected specific conditions (the simulation requirement) into it,
and the agents' behavior and interactions in that simulation are themselves a prediction of how real populations would behave.

Your task is to:
- Reveal what happened in the future under the configured conditions.
- Predict how each population (agent group) reacted and behaved.
- Surface the noteworthy future trends, risks, and opportunities.

❌ Do not write a present-day analysis of the real world.
✅ Stay focused on "what does the future look like" — the simulation outcome IS the predicted future.

═══════════════════════════════════════════════════════════════
[Most important rules — MUST follow]
═══════════════════════════════════════════════════════════════

1. [You MUST call tools to observe the simulated world]
   - You are watching the future rehearsal from a god's-eye view.
   - All content MUST come from events and agent statements/behavior in the simulated world.
   - Do NOT use your own prior knowledge to author report content.
   - Each section MUST call retrieval tools at least 3 times (and at most 5 times) to observe the simulated world, which represents the future.

2. [You MUST quote agents' raw statements and behavior]
   - The agents' speech and actions ARE the prediction of how real populations would behave.
   - Render these predictions in the report using block-quote format, for example:
     > "A specific population would say: <verbatim quote>..."
   - These quotations are the core evidence of the simulation's prediction.

3. [Language consistency — translate quoted material into the report language]
   - Tool results may contain text in a language that differs from the report language.
   - The report MUST be authored entirely in the language requested by the user.
   - When you quote tool output that is in a different language, translate it into the report language before writing it in.
   - Preserve the original meaning during translation; the rendered text must read naturally.
   - This rule applies both to body text and to block-quote (>) content.

4. [Faithfully render the prediction outcomes]
   - The report content MUST reflect the simulated outcomes that represent the future.
   - Do NOT add information that does not exist in the simulation.
   - If the simulation lacks coverage of an aspect, say so honestly.

═══════════════════════════════════════════════════════════════
[⚠️ Formatting rules — extremely important!]
═══════════════════════════════════════════════════════════════

[One section = the smallest unit of content]
- Each section is the smallest content block in the report.
- ❌ Do NOT use any Markdown heading (#, ##, ###, ####, etc.) inside the section.
- ❌ Do NOT prepend the section's main heading at the start of the content.
- ✅ The section title is added by the system automatically — you write only the body content.
- ✅ Use **bold**, paragraph breaks, block quotes, and lists to organize the content — but no headings.

[Correct example]
```
This section analyzes how public opinion propagated around the event. A close reading of the simulated data reveals that...

**Initial-spark stage**

Platform A served as the first venue for the news, fulfilling its core role as a launcher of viral information:

> "Platform A produced 68% of the first-wave volume..."

**Emotional-amplification stage**

Platform B further amplified the event's reach:

- Strong visual impact
- High emotional resonance
```

[Wrong example]
```
## Executive Summary       ← Wrong! Do not add any heading.
### 1. Initial-spark stage ← Wrong! Do not use ### for sub-sections.
#### 1.1 Detailed analysis ← Wrong! Do not use #### either.

This section analyzes...
```

═══════════════════════════════════════════════════════════════
[Available retrieval tools] (3–5 calls per section)
═══════════════════════════════════════════════════════════════

{tools_description}

[Tool-usage guidance — mix different tools; do not rely on just one]
- insight_forge: deep analytical retrieval; auto-decomposes the question and pulls facts and relationships from multiple angles.
- panorama_search: wide-angle panoramic search; reveals the full picture of an event, its timeline, and how it evolved.
- quick_search: quick verification of a specific information point.
- interview_agents: interview the simulated agents to capture first-person viewpoints and authentic reactions across roles.

═══════════════════════════════════════════════════════════════
[Workflow]
═══════════════════════════════════════════════════════════════

Each reply may do exactly ONE of the following two things (never both):

Option A — Call a tool:
Write your reasoning, then invoke one tool using the format below:
<tool_call>
{{"name": "<tool name>", "parameters": {{"<param name>": "<param value>"}}}}
</tool_call>
The system will run the tool and return its result. You do NOT need to (and MUST not) author the tool result yourself.

Option B — Output the final content:
Once you have gathered enough information through tool calls, output the section content prefixed with "Final Answer:".

⚠️ Strictly forbidden:
- Do NOT include both a tool call and a Final Answer in the same reply.
- Do NOT fabricate tool results (Observation) yourself; all tool results are injected by the system.
- Each reply may invoke at most one tool.

═══════════════════════════════════════════════════════════════
[Section-content requirements]
═══════════════════════════════════════════════════════════════

1. The content MUST be grounded in the simulated data retrieved by the tools.
2. Quote source material liberally to make the simulation's predictions vivid.
3. Use Markdown formatting (but no headings):
   - Use **bold** to emphasize key points (instead of sub-headings).
   - Use lists (- or 1./2./3.) to organize bullet points.
   - Separate paragraphs with blank lines.
   - ❌ Do NOT use #, ##, ###, #### — no heading syntax of any kind.
4. [Quotation format — must stand alone as its own paragraph]
   A block quote MUST be its own paragraph, with a blank line above and below; do not embed it inside another paragraph:

   ✅ Correct format:
   ```
   The university's response was widely viewed as substanceless.

   > "The university's response pattern reads as rigid and slow in a fast-moving social-media environment."

   This assessment captures the public's broad dissatisfaction.
   ```

   ❌ Wrong format:
   ```
   The university's response was widely viewed as substanceless. > "The university's response pattern..." This assessment captures...
   ```
5. Maintain logical continuity with the other sections.
6. [Avoid repetition] Read the already-completed section content below carefully and do not repeat the same information.
7. [Reminder] Do NOT add any headings! Use **bold** instead of sub-section titles."""

SECTION_USER_PROMPT_TEMPLATE = """\
Already-completed section content (read carefully to avoid repeating yourself):
{previous_content}

═══════════════════════════════════════════════════════════════
[Current task] Write section: {section_title}
═══════════════════════════════════════════════════════════════

[Important reminders]
1. Read the already-completed sections above carefully and avoid repeating the same content.
2. You MUST call a retrieval tool first to obtain simulated data before writing.
3. Mix different tools — do not rely on a single one.
4. The report content MUST come from the retrieval results; do not use your own prior knowledge.

[⚠️ Formatting warning — MUST follow]
- ❌ Do NOT write any heading (no #, ##, ###, or ####).
- ❌ Do NOT write "{section_title}" as the opening line.
- ✅ The section title is added by the system automatically.
- ✅ Write the body directly; use **bold** instead of sub-section titles.

Get started:
1. First think (Thought) about what information this section needs.
2. Then call a tool (Action) to retrieve the simulated data.
3. Once you have gathered enough information, output the body prefixed with Final Answer: (plain body, no headings)."""

# ── In-loop ReACT message templates ──

REACT_OBSERVATION_TEMPLATE = """\
Observation (retrieval result):

═══ Tool {tool_name} returned ═══
{result}

═══════════════════════════════════════════════════════════════
Tool calls so far: {tool_calls_count}/{max_tool_calls} (used: {used_tools_str}){unused_hint}
- If you have enough information: output the section content prefixed with "Final Answer:" (you MUST quote the source material above).
- If you need more information: call one more tool to continue retrieving.
═══════════════════════════════════════════════════════════════"""

REACT_INSUFFICIENT_TOOLS_MSG = (
    "[Note] You have only called tools {tool_calls_count} times; at least {min_tool_calls} are required. "
    "Call more tools to gather simulation data, then output Final Answer.{unused_hint}"
)

REACT_INSUFFICIENT_TOOLS_MSG_ALT = (
    "Only {tool_calls_count} tool calls so far; at least {min_tool_calls} are required. "
    "Please call a tool to retrieve simulation data.{unused_hint}"
)

REACT_TOOL_LIMIT_MSG = (
    "Tool-call budget exhausted ({tool_calls_count}/{max_tool_calls}); no more tool calls allowed. "
    'Now, based on the information you have already gathered, output the section content prefixed with "Final Answer:".'
)

REACT_UNUSED_TOOLS_HINT = "\n💡 You haven't used: {unused_list} yet — try a different tool to get a multi-angle view."

REACT_FORCE_FINAL_MSG = "Tool-call limit reached. Please output Final Answer: directly and produce the section content."

# ── Chat prompt ──

CHAT_SYSTEM_PROMPT_TEMPLATE = """\
You are a concise and efficient simulation-prediction assistant.

[Background]
Prediction conditions: {simulation_requirement}

[Generated analytical report]
{report_content}

[Rules]
1. Prefer answering from the report above.
2. Answer the question directly; avoid lengthy meta-reasoning.
3. Only call tools when the report does not contain enough information to answer.
4. Keep your answers concise, clear, and well-structured.

[Available tools] (use only when needed; at most 1–2 calls)
{tools_description}

[Tool-call format]
<tool_call>
{{"name": "<tool name>", "parameters": {{"<param name>": "<param value>"}}}}
</tool_call>

[Answer style]
- Concise and direct — no long-form prose.
- Use the > format to quote the key source material.
- Lead with the conclusion, then explain the rationale."""

CHAT_OBSERVATION_SUFFIX = "\n\nPlease answer the question concisely."


# ═══════════════════════════════════════════════════════════════
# ReportAgent main class
# ═══════════════════════════════════════════════════════════════


class ReportAgent:
    """
    Report Agent — simulation report generator.

    Uses a ReACT (Reasoning + Acting) loop:
    1. Planning stage: analyze the simulation requirement and plan the report's
       table of contents.
    2. Generation stage: generate each section sequentially; each section may
       call retrieval tools multiple times.
    3. Reflection stage: verify content completeness and accuracy.
    """

    # Per-section maximum number of tool calls.
    MAX_TOOL_CALLS_PER_SECTION = 5

    # Maximum number of reflection rounds.
    MAX_REFLECTION_ROUNDS = 3

    # Maximum number of tool calls allowed in chat mode.
    MAX_TOOL_CALLS_PER_CHAT = 2
    
    def __init__(
        self, 
        graph_id: str,
        simulation_id: str,
        simulation_requirement: str,
        llm_client: Optional[LLMClient] = None,
        zep_tools: Optional[ZepToolsService] = None
    ):
        """
        Initialize the Report Agent.

        Args:
            graph_id: Graph ID.
            simulation_id: Simulation ID.
            simulation_requirement: Description of the simulation requirement.
            llm_client: Optional LLM client.
            zep_tools: Optional Zep tools service.
        """
        self.graph_id = graph_id
        self.simulation_id = simulation_id
        self.simulation_requirement = simulation_requirement
        
        self.llm = llm_client or LLMClient()
        self.zep_tools = zep_tools or ZepToolsService()
        
        self.tools = self._define_tools()

        # Loggers are lazily initialized inside generate_report.
        self.report_logger: Optional[ReportLogger] = None
        self.console_logger: Optional[ReportConsoleLogger] = None
        
        logger.info(t('report.agentInitDone', graphId=graph_id, simulationId=simulation_id))
    
    def _define_tools(self) -> Dict[str, Dict[str, Any]]:
        """Define the tools available to the agent."""
        return {
            "insight_forge": {
                "name": "insight_forge",
                "description": TOOL_DESC_INSIGHT_FORGE,
                "parameters": {
                    "query": "The question or topic you want to analyze in depth.",
                    "report_context": "Current report-section context (optional; helps generate sharper sub-questions)."
                }
            },
            "panorama_search": {
                "name": "panorama_search",
                "description": TOOL_DESC_PANORAMA_SEARCH,
                "parameters": {
                    "query": "Search query, used for relevance ranking.",
                    "include_expired": "Whether to include expired/historical content (default True)."
                }
            },
            "quick_search": {
                "name": "quick_search",
                "description": TOOL_DESC_QUICK_SEARCH,
                "parameters": {
                    "query": "Search query string.",
                    "limit": "Number of results to return (optional, default 10)."
                }
            },
            "interview_agents": {
                "name": "interview_agents",
                "description": TOOL_DESC_INTERVIEW_AGENTS,
                "parameters": {
                    "interview_topic": "Interview topic or requirement (e.g. 'Understand student opinion on the dorm formaldehyde incident').",
                    "max_agents": "Maximum number of agents to interview (optional; default 5, max 10)."
                }
            }
        }
    
    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any], report_context: str = "") -> str:
        """
        Execute a tool call.

        Args:
            tool_name: Tool name.
            parameters: Tool parameters.
            report_context: Report context (used by InsightForge).

        Returns:
            The tool execution result as text.
        """
        logger.info(t('report.executingTool', toolName=tool_name, params=parameters))
        
        try:
            if tool_name == "insight_forge":
                query = parameters.get("query", "")
                ctx = parameters.get("report_context", "") or report_context
                result = self.zep_tools.insight_forge(
                    graph_id=self.graph_id,
                    query=query,
                    simulation_requirement=self.simulation_requirement,
                    report_context=ctx
                )
                return result.to_text()
            
            elif tool_name == "panorama_search":
                # Wide-angle search — get the full picture.
                query = parameters.get("query", "")
                include_expired = parameters.get("include_expired", True)
                if isinstance(include_expired, str):
                    include_expired = include_expired.lower() in ['true', '1', 'yes']
                result = self.zep_tools.panorama_search(
                    graph_id=self.graph_id,
                    query=query,
                    include_expired=include_expired
                )
                return result.to_text()
            
            elif tool_name == "quick_search":
                # Lightweight search — fast retrieval.
                query = parameters.get("query", "")
                limit = parameters.get("limit", 10)
                if isinstance(limit, str):
                    limit = int(limit)
                result = self.zep_tools.quick_search(
                    graph_id=self.graph_id,
                    query=query,
                    limit=limit
                )
                return result.to_text()
            
            elif tool_name == "interview_agents":
                # Deep interview — call the real OASIS interview API to query the simulated agents on both platforms.
                interview_topic = parameters.get("interview_topic", parameters.get("query", ""))
                max_agents = parameters.get("max_agents", 5)
                if isinstance(max_agents, str):
                    max_agents = int(max_agents)
                max_agents = min(max_agents, 10)
                result = self.zep_tools.interview_agents(
                    simulation_id=self.simulation_id,
                    interview_requirement=interview_topic,
                    simulation_requirement=self.simulation_requirement,
                    max_agents=max_agents
                )
                return result.to_text()
            
            # ========== Backward-compatible legacy tools (internally redirect to the new tools). ==========

            elif tool_name == "search_graph":
                # Redirect to quick_search.
                logger.info(t('report.redirectToQuickSearch'))
                return self._execute_tool("quick_search", parameters, report_context)
            
            elif tool_name == "get_graph_statistics":
                result = self.zep_tools.get_graph_statistics(self.graph_id)
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_entity_summary":
                entity_name = parameters.get("entity_name", "")
                result = self.zep_tools.get_entity_summary(
                    graph_id=self.graph_id,
                    entity_name=entity_name
                )
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_simulation_context":
                # Redirect to insight_forge — it's the more powerful tool.
                logger.info(t('report.redirectToInsightForge'))
                query = parameters.get("query", self.simulation_requirement)
                return self._execute_tool("insight_forge", {"query": query}, report_context)
            
            elif tool_name == "get_entities_by_type":
                entity_type = parameters.get("entity_type", "")
                nodes = self.zep_tools.get_entities_by_type(
                    graph_id=self.graph_id,
                    entity_type=entity_type
                )
                result = [n.to_dict() for n in nodes]
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            else:
                return f"Unknown tool: {tool_name}. Please use one of: insight_forge, panorama_search, quick_search"

        except Exception as e:
            logger.error(t('report.toolExecFailed', toolName=tool_name, error=str(e)))
            return f"Tool execution failed: {str(e)}"
    
    # Set of legal tool names; used to validate naked-JSON fallback parses.
    VALID_TOOL_NAMES = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}

    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """
        Parse tool calls from an LLM response.

        Supported formats (in priority order):
        1. ``<tool_call>{"name": "tool_name", "parameters": {...}}</tool_call>``
        2. Naked JSON (the whole response, or a single line, is the tool-call JSON).
        """
        tool_calls = []

        # Format 1: XML-style (canonical format).
        xml_pattern = r'<tool_call>\s*(\{.*?\})\s*</tool_call>'
        for match in re.finditer(xml_pattern, response, re.DOTALL):
            try:
                call_data = json.loads(match.group(1))
                tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        if tool_calls:
            return tool_calls

        # Format 2: fallback — the LLM emits naked JSON without a <tool_call> wrapper.
        # Only tried when format 1 did not match, to avoid mis-matching JSON embedded in body text.
        stripped = response.strip()
        if stripped.startswith('{') and stripped.endswith('}'):
            try:
                call_data = json.loads(stripped)
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
                    return tool_calls
            except json.JSONDecodeError:
                pass

        # The response may include reasoning text plus naked JSON; try to extract the trailing JSON object.
        json_pattern = r'(\{"(?:name|tool)"\s*:.*?\})\s*$'
        match = re.search(json_pattern, stripped, re.DOTALL)
        if match:
            try:
                call_data = json.loads(match.group(1))
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        return tool_calls

    def _is_valid_tool_call(self, data: dict) -> bool:
        """Check that a parsed JSON object is a valid tool call."""
        # Accept both {"name": ..., "parameters": ...} and {"tool": ..., "params": ...}.
        tool_name = data.get("name") or data.get("tool")
        if tool_name and tool_name in self.VALID_TOOL_NAMES:
            # Normalize the key names to ``name`` / ``parameters``.
            if "tool" in data:
                data["name"] = data.pop("tool")
            if "params" in data and "parameters" not in data:
                data["parameters"] = data.pop("params")
            return True
        return False
    
    def _get_tools_description(self) -> str:
        """Build the descriptive tool-listing text."""
        desc_parts = ["Available tools:"]
        for name, tool in self.tools.items():
            params_desc = ", ".join([f"{k}: {v}" for k, v in tool["parameters"].items()])
            desc_parts.append(f"- {name}: {tool['description']}")
            if params_desc:
                desc_parts.append(f"  Parameters: {params_desc}")
        return "\n".join(desc_parts)
    
    def plan_outline(
        self, 
        progress_callback: Optional[Callable] = None
    ) -> ReportOutline:
        """
        Plan the report outline.

        Use the LLM to analyze the simulation requirement and plan the report's
        table of contents.

        Args:
            progress_callback: Progress callback function.

        Returns:
            ReportOutline: The report outline.
        """
        logger.info(t('report.startPlanningOutline'))
        
        if progress_callback:
            progress_callback("planning", 0, t('progress.analyzingRequirements'))
        
        # First fetch the simulation context.
        context = self.zep_tools.get_simulation_context(
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement
        )
        
        if progress_callback:
            progress_callback("planning", 30, t('progress.generatingOutline'))
        
        system_prompt = f"{PLAN_SYSTEM_PROMPT}\n\n{get_language_instruction()}"
        user_prompt = PLAN_USER_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            total_nodes=context.get('graph_statistics', {}).get('total_nodes', 0),
            total_edges=context.get('graph_statistics', {}).get('total_edges', 0),
            entity_types=list(context.get('graph_statistics', {}).get('entity_types', {}).keys()),
            total_entities=context.get('total_entities', 0),
            related_facts_json=json.dumps(context.get('related_facts', [])[:10], ensure_ascii=False, indent=2),
        )

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            if progress_callback:
                progress_callback("planning", 80, t('progress.parsingOutline'))
            
            # Parse the outline.
            sections = []
            for section_data in response.get("sections", []):
                sections.append(ReportSection(
                    title=section_data.get("title", ""),
                    content=""
                ))
            
            outline = ReportOutline(
                title=response.get("title", "Simulation Analysis Report"),
                summary=response.get("summary", ""),
                sections=sections
            )
            
            if progress_callback:
                progress_callback("planning", 100, t('progress.outlinePlanComplete'))
            
            logger.info(t('report.outlinePlanDone', count=len(sections)))
            return outline
            
        except Exception as e:
            logger.error(t('report.outlinePlanFailed', error=str(e)))
            # Return a default 3-section fallback outline.
            return ReportOutline(
                title="Future Prediction Report",
                summary="Trend and risk analysis grounded in simulation predictions.",
                sections=[
                    ReportSection(title="Scenario and Key Findings"),
                    ReportSection(title="Population Behavior Predictions"),
                    ReportSection(title="Trend Outlook and Risk Notes")
                ]
            )
    
    def _generate_section_react(
        self, 
        section: ReportSection,
        outline: ReportOutline,
        previous_sections: List[str],
        progress_callback: Optional[Callable] = None,
        section_index: int = 0
    ) -> str:
        """
        Generate a single section's content using the ReACT pattern.

        ReACT loop:
        1. Thought — analyze what information is needed.
        2. Action — call a tool to fetch information.
        3. Observation — analyze the tool result.
        4. Repeat until enough information has been gathered or the cap is hit.
        5. Final Answer — emit the section content.

        Args:
            section: The section to generate.
            outline: The full outline.
            previous_sections: Content of previously generated sections (for continuity).
            progress_callback: Progress callback.
            section_index: Section index (used for logging).

        Returns:
            The section content in Markdown format.
        """
        logger.info(t('report.reactGenerateSection', title=section.title))
        
        if self.report_logger:
            self.report_logger.log_section_start(section.title, section_index)
        
        system_prompt = SECTION_SYSTEM_PROMPT_TEMPLATE.format(
            report_title=outline.title,
            report_summary=outline.summary,
            simulation_requirement=self.simulation_requirement,
            section_title=section.title,
            tools_description=self._get_tools_description(),
        )
        system_prompt = f"{system_prompt}\n\n{get_language_instruction()}"

        # Build the user prompt — pass at most 4000 chars per completed section.
        if previous_sections:
            previous_parts = []
            for sec in previous_sections:
                # Cap at 4000 chars per section.
                truncated = sec[:4000] + "..." if len(sec) > 4000 else sec
                previous_parts.append(truncated)
            previous_content = "\n\n---\n\n".join(previous_parts)
        else:
            previous_content = "(This is the first section.)"
        
        user_prompt = SECTION_USER_PROMPT_TEMPLATE.format(
            previous_content=previous_content,
            section_title=section.title,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # ReACT loop.
        tool_calls_count = 0
        max_iterations = 5  # Max iteration rounds.
        min_tool_calls = 3  # Minimum required tool-call count.
        conflict_retries = 0  # Number of consecutive tool-call + Final-Answer conflicts.
        used_tools = set()  # Tracks the names of tools already invoked.
        all_tools = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}

        # Report context, used by InsightForge to drive sub-question generation.
        report_context = f"Section title: {section.title}\nSimulation requirement: {self.simulation_requirement}"
        
        for iteration in range(max_iterations):
            if progress_callback:
                progress_callback(
                    "generating", 
                    int((iteration / max_iterations) * 100),
                    t('progress.deepSearchAndWrite', current=tool_calls_count, max=self.MAX_TOOL_CALLS_PER_SECTION)
                )
            
            response = self.llm.chat(
                messages=messages,
                temperature=0.5,
                max_tokens=4096
            )

            # Guard against a None response (API error or empty content).
            if response is None:
                logger.warning(t('report.sectionIterNone', title=section.title, iteration=iteration + 1))
                # If iterations remain, append a nudge and retry.
                if iteration < max_iterations - 1:
                    messages.append({"role": "assistant", "content": "(empty response)"})
                    messages.append({"role": "user", "content": "Please continue generating content."})
                    continue
                # Last iteration also returned None — break out into the forced wrap-up.
                break

            logger.debug(t("log.report_agent.m001", response=response[:200]))

            # Parse once; reuse the result downstream.
            tool_calls = self._parse_tool_calls(response)
            has_tool_calls = bool(tool_calls)
            has_final_answer = "Final Answer:" in response

            # ── Conflict handling: LLM produced both a tool call and a Final Answer. ──
            if has_tool_calls and has_final_answer:
                conflict_retries += 1
                logger.warning(
                    t('report.sectionConflict', title=section.title, iteration=iteration+1, conflictCount=conflict_retries)
                )

                if conflict_retries <= 2:
                    # First two strikes: drop the response and ask the LLM to retry.
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": (
                            "[Format error] You included both a tool call and a Final Answer in the same reply, which is not allowed.\n"
                            "Each reply may do exactly one of the following:\n"
                            "- Call a single tool (output one <tool_call> block; do NOT write Final Answer).\n"
                            "- Output the final content (prefix it with 'Final Answer:'; do NOT include <tool_call>).\n"
                            "Please reply again and do only one of the two."
                        ),
                    })
                    continue
                else:
                    # Third strike: degrade — truncate at the first tool call and execute it.
                    logger.warning(
                        t('report.sectionConflictDowngrade', title=section.title, conflictCount=conflict_retries)
                    )
                    first_tool_end = response.find('</tool_call>')
                    if first_tool_end != -1:
                        response = response[:first_tool_end + len('</tool_call>')]
                        tool_calls = self._parse_tool_calls(response)
                        has_tool_calls = bool(tool_calls)
                    has_final_answer = False
                    conflict_retries = 0

            if self.report_logger:
                self.report_logger.log_llm_response(
                    section_title=section.title,
                    section_index=section_index,
                    response=response,
                    iteration=iteration + 1,
                    has_tool_calls=has_tool_calls,
                    has_final_answer=has_final_answer
                )

            # ── Case 1: LLM produced a Final Answer. ──
            if has_final_answer:
                # Not enough tool calls yet — refuse and ask the agent to keep retrieving.
                if tool_calls_count < min_tool_calls:
                    messages.append({"role": "assistant", "content": response})
                    unused_tools = all_tools - used_tools
                    unused_hint = f"(These tools have not been used yet — try them: {', '.join(unused_tools)})" if unused_tools else ""
                    messages.append({
                        "role": "user",
                        "content": REACT_INSUFFICIENT_TOOLS_MSG.format(
                            tool_calls_count=tool_calls_count,
                            min_tool_calls=min_tool_calls,
                            unused_hint=unused_hint,
                        ),
                    })
                    continue

                # Normal termination.
                final_answer = response.split("Final Answer:")[-1].strip()
                logger.info(t('report.sectionGenDone', title=section.title, count=tool_calls_count))

                if self.report_logger:
                    self.report_logger.log_section_content(
                        section_title=section.title,
                        section_index=section_index,
                        content=final_answer,
                        tool_calls_count=tool_calls_count
                    )
                return final_answer

            # ── Case 2: LLM tried to call a tool. ──
            if has_tool_calls:
                # Tool budget exhausted → tell the agent explicitly and demand a Final Answer.
                if tool_calls_count >= self.MAX_TOOL_CALLS_PER_SECTION:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": REACT_TOOL_LIMIT_MSG.format(
                            tool_calls_count=tool_calls_count,
                            max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        ),
                    })
                    continue

                # Only execute the first tool call.
                call = tool_calls[0]
                if len(tool_calls) > 1:
                    logger.info(t('report.multiToolOnlyFirst', total=len(tool_calls), toolName=call['name']))

                if self.report_logger:
                    self.report_logger.log_tool_call(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        parameters=call.get("parameters", {}),
                        iteration=iteration + 1
                    )

                result = self._execute_tool(
                    call["name"],
                    call.get("parameters", {}),
                    report_context=report_context
                )

                if self.report_logger:
                    self.report_logger.log_tool_result(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        result=result,
                        iteration=iteration + 1
                    )

                tool_calls_count += 1
                used_tools.add(call['name'])

                # Build the "unused tools" hint.
                unused_tools = all_tools - used_tools
                unused_hint = ""
                if unused_tools and tool_calls_count < self.MAX_TOOL_CALLS_PER_SECTION:
                    unused_hint = REACT_UNUSED_TOOLS_HINT.format(unused_list=", ".join(unused_tools))

                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": REACT_OBSERVATION_TEMPLATE.format(
                        tool_name=call["name"],
                        result=result,
                        tool_calls_count=tool_calls_count,
                        max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        used_tools_str=", ".join(used_tools),
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # ── Case 3: neither a tool call nor a Final Answer. ──
            messages.append({"role": "assistant", "content": response})

            if tool_calls_count < min_tool_calls:
                # Not enough tool calls yet — suggest the unused tools.
                unused_tools = all_tools - used_tools
                unused_hint = f"(These tools have not been used yet — try them: {', '.join(unused_tools)})" if unused_tools else ""

                messages.append({
                    "role": "user",
                    "content": REACT_INSUFFICIENT_TOOLS_MSG_ALT.format(
                        tool_calls_count=tool_calls_count,
                        min_tool_calls=min_tool_calls,
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # Enough tool calls already; the LLM emitted content without the "Final Answer:" prefix.
            # Treat the content as the final answer rather than spinning further.
            logger.info(t('report.sectionNoPrefix', title=section.title, count=tool_calls_count))
            final_answer = response.strip()

            if self.report_logger:
                self.report_logger.log_section_content(
                    section_title=section.title,
                    section_index=section_index,
                    content=final_answer,
                    tool_calls_count=tool_calls_count
                )
            return final_answer
        
        # Reached the iteration cap — force the content out.
        logger.warning(t('report.sectionMaxIter', title=section.title))
        messages.append({"role": "user", "content": REACT_FORCE_FINAL_MSG})
        
        response = self.llm.chat(
            messages=messages,
            temperature=0.5,
            max_tokens=4096
        )

        # Guard against a None response on the forced wrap-up call.
        if response is None:
            logger.error(t('report.sectionForceFailed', title=section.title))
            final_answer = t('report.sectionGenFailedContent')
        elif "Final Answer:" in response:
            final_answer = response.split("Final Answer:")[-1].strip()
        else:
            final_answer = response
        
        if self.report_logger:
            self.report_logger.log_section_content(
                section_title=section.title,
                section_index=section_index,
                content=final_answer,
                tool_calls_count=tool_calls_count
            )

        return final_answer
    
    def generate_report(
        self, 
        progress_callback: Optional[Callable[[str, int, str], None]] = None,
        report_id: Optional[str] = None
    ) -> Report:
        """
        Generate the full report, streaming each section out as it finishes.

        Each section is saved to disk as soon as it is generated; the caller does
        not have to wait for the whole report to complete.

        File layout::

            reports/{report_id}/
                meta.json       - Report metadata.
                outline.json    - Report outline.
                progress.json   - Generation progress.
                section_01.md   - Section 1.
                section_02.md   - Section 2.
                ...
                full_report.md  - Full report.

        Args:
            progress_callback: Progress callback ``(stage, progress, message)``.
            report_id: Optional report ID; auto-generated if not provided.

        Returns:
            Report: The completed report object.
        """
        import uuid
        
        # Auto-generate a report_id if the caller didn't supply one.
        if not report_id:
            report_id = f"report_{uuid.uuid4().hex[:12]}"
        start_time = datetime.now()
        
        report = Report(
            report_id=report_id,
            simulation_id=self.simulation_id,
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement,
            status=ReportStatus.PENDING,
            created_at=datetime.now().isoformat()
        )
        
        # Titles of sections that have already been completed (used for progress tracking).
        completed_section_titles = []

        try:
            # Bootstrap: create the report folder and persist the initial state.
            ReportManager._ensure_report_folder(report_id)

            # Initialize the structured logger (agent_log.jsonl).
            self.report_logger = ReportLogger(report_id)
            self.report_logger.log_start(
                simulation_id=self.simulation_id,
                graph_id=self.graph_id,
                simulation_requirement=self.simulation_requirement
            )
            
            # Initialize the console logger (console_log.txt).
            self.console_logger = ReportConsoleLogger(report_id)
            
            ReportManager.update_progress(
                report_id, "pending", 0, t('progress.initReport'),
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            # Stage 1: plan the outline.
            report.status = ReportStatus.PLANNING
            ReportManager.update_progress(
                report_id, "planning", 5, t('progress.startPlanningOutline'),
                completed_sections=[]
            )
            
            self.report_logger.log_planning_start()
            
            if progress_callback:
                progress_callback("planning", 0, t('progress.startPlanningOutline'))
            
            outline = self.plan_outline(
                progress_callback=lambda stage, prog, msg: 
                    progress_callback(stage, prog // 5, msg) if progress_callback else None
            )
            report.outline = outline
            
            self.report_logger.log_planning_complete(outline.to_dict())

            # Persist the outline to disk.
            ReportManager.save_outline(report_id, outline)
            ReportManager.update_progress(
                report_id, "planning", 15, t('progress.outlineDone', count=len(outline.sections)),
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            logger.info(t('report.outlineSavedToFile', reportId=report_id))
            
            # Stage 2: generate the report section by section, saving each as it completes.
            report.status = ReportStatus.GENERATING

            total_sections = len(outline.sections)
            generated_sections = []  # Keep the content around for context.
            
            for i, section in enumerate(outline.sections):
                section_num = i + 1
                base_progress = 20 + int((i / total_sections) * 70)
                
                # Update progress.
                ReportManager.update_progress(
                    report_id, "generating", base_progress,
                    t('progress.generatingSection', title=section.title, current=section_num, total=total_sections),
                    current_section=section.title,
                    completed_sections=completed_section_titles
                )

                if progress_callback:
                    progress_callback(
                        "generating",
                        base_progress,
                        t('progress.generatingSection', title=section.title, current=section_num, total=total_sections)
                    )
                
                # Generate the main section body.
                section_content = self._generate_section_react(
                    section=section,
                    outline=outline,
                    previous_sections=generated_sections,
                    progress_callback=lambda stage, prog, msg:
                        progress_callback(
                            stage, 
                            base_progress + int(prog * 0.7 / total_sections),
                            msg
                        ) if progress_callback else None,
                    section_index=section_num
                )
                
                section.content = section_content
                generated_sections.append(f"## {section.title}\n\n{section_content}")

                # Persist the section.
                ReportManager.save_section(report_id, section_num, section)
                completed_section_titles.append(section.title)

                full_section_content = f"## {section.title}\n\n{section_content}"

                if self.report_logger:
                    self.report_logger.log_section_full_complete(
                        section_title=section.title,
                        section_index=section_num,
                        full_content=full_section_content.strip()
                    )

                logger.info(t('report.sectionSaved', reportId=report_id, sectionNum=f"{section_num:02d}"))

                # Update progress.
                ReportManager.update_progress(
                    report_id, "generating",
                    base_progress + int(70 / total_sections),
                    t('progress.sectionDone', title=section.title),
                    current_section=None,
                    completed_sections=completed_section_titles
                )
            
            # Stage 3: assemble the full report.
            if progress_callback:
                progress_callback("generating", 95, t('progress.assemblingReport'))
            
            ReportManager.update_progress(
                report_id, "generating", 95, t('progress.assemblingReport'),
                completed_sections=completed_section_titles
            )
            
            # Assemble the full report via ReportManager.
            report.markdown_content = ReportManager.assemble_full_report(report_id, outline)
            report.status = ReportStatus.COMPLETED
            report.completed_at = datetime.now().isoformat()
            
            # Compute total elapsed time.
            total_time_seconds = (datetime.now() - start_time).total_seconds()

            if self.report_logger:
                self.report_logger.log_report_complete(
                    total_sections=total_sections,
                    total_time_seconds=total_time_seconds
                )
            
            # Save the final report.
            ReportManager.save_report(report)
            ReportManager.update_progress(
                report_id, "completed", 100, t('progress.reportComplete'),
                completed_sections=completed_section_titles
            )
            
            if progress_callback:
                progress_callback("completed", 100, t('progress.reportComplete'))
            
            logger.info(t('report.reportGenDone', reportId=report_id))
            
            # Close the console logger.
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None

            return report

        except Exception as e:
            logger.error(t('report.reportGenFailed', error=str(e)))
            report.status = ReportStatus.FAILED
            report.error = str(e)

            if self.report_logger:
                self.report_logger.log_error(str(e), "failed")

            # Persist the failed status.
            try:
                ReportManager.save_report(report)
                ReportManager.update_progress(
                    report_id, "failed", -1, t('progress.reportFailed', error=str(e)),
                    completed_sections=completed_section_titles
                )
            except Exception:
                pass  # Ignore failures while persisting the failure state.

            # Close the console logger.
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            
            return report
    
    def chat(
        self, 
        message: str,
        chat_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Chat with the Report Agent.

        In chat mode the agent can autonomously call retrieval tools to answer
        the user's question.

        Args:
            message: User message.
            chat_history: Conversation history.

        Returns:
            ``{
                "response": "Agent reply",
                "tool_calls": [list of tools that were invoked],
                "sources": [information sources]
            }``
        """
        logger.info(t('report.agentChat', message=message[:50]))
        
        chat_history = chat_history or []
        
        # Fetch the already-generated report content.
        report_content = ""
        try:
            report = ReportManager.get_report_by_simulation(self.simulation_id)
            if report and report.markdown_content:
                # Cap the report length to keep the context window manageable.
                report_content = report.markdown_content[:15000]
                if len(report.markdown_content) > 15000:
                    report_content += "\n\n... [report content truncated] ..."
        except Exception as e:
            logger.warning(t('report.fetchReportFailed', error=e))

        system_prompt = CHAT_SYSTEM_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            report_content=report_content if report_content else "(no report yet)",
            tools_description=self._get_tools_description(),
        )
        system_prompt = f"{system_prompt}\n\n{get_language_instruction()}"

        # Build the messages list.
        messages = [{"role": "system", "content": system_prompt}]

        # Append conversation history.
        for h in chat_history[-10:]:  # Cap the history length.
            messages.append(h)

        # Append the user's new message.
        messages.append({
            "role": "user",
            "content": message
        })

        # Simplified ReACT loop.
        tool_calls_made = []
        max_iterations = 2  # Fewer iterations than the section loop.
        
        for iteration in range(max_iterations):
            response = self.llm.chat(
                messages=messages,
                temperature=0.5
            )
            
            # Parse tool calls.
            tool_calls = self._parse_tool_calls(response)

            if not tool_calls:
                # No tool calls — return the response directly.
                clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', response, flags=re.DOTALL)
                clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
                
                return {
                    "response": clean_response.strip(),
                    "tool_calls": tool_calls_made,
                    "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
                }
            
            # Execute tool calls (with a hard cap).
            tool_results = []
            for call in tool_calls[:1]:  # At most one tool call per iteration.
                if len(tool_calls_made) >= self.MAX_TOOL_CALLS_PER_CHAT:
                    break
                result = self._execute_tool(call["name"], call.get("parameters", {}))
                tool_results.append({
                    "tool": call["name"],
                    "result": result[:1500]  # Cap the result length.
                })
                tool_calls_made.append(call)

            # Append the result back into the message stream.
            messages.append({"role": "assistant", "content": response})
            observation = "\n".join([f"[{r['tool']} result]\n{r['result']}" for r in tool_results])
            messages.append({
                "role": "user",
                "content": observation + CHAT_OBSERVATION_SUFFIX
            })
        
        # Iteration cap reached — fetch a final response.
        final_response = self.llm.chat(
            messages=messages,
            temperature=0.5
        )
        
        # Clean up the response.
        clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', final_response, flags=re.DOTALL)
        clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
        
        return {
            "response": clean_response.strip(),
            "tool_calls": tool_calls_made,
            "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
        }


class ReportManager:
    """
    Report manager.

    Handles persistence and retrieval of reports.

    File layout (one folder per report)::

        reports/
          {report_id}/
            meta.json          - Report metadata and status.
            outline.json       - Report outline.
            progress.json      - Generation progress.
            section_01.md      - Section 1.
            section_02.md      - Section 2.
            ...
            full_report.md     - Full report.
    """

    # Root directory where reports are stored.
    REPORTS_DIR = os.path.join(Config.UPLOAD_FOLDER, 'reports')

    @classmethod
    def _ensure_reports_dir(cls):
        """Ensure the reports root directory exists."""
        os.makedirs(cls.REPORTS_DIR, exist_ok=True)
    
    @classmethod
    def _get_report_folder(cls, report_id: str) -> str:
        """Return the report folder path."""
        return os.path.join(cls.REPORTS_DIR, report_id)
    
    @classmethod
    def _ensure_report_folder(cls, report_id: str) -> str:
        """Ensure the report folder exists and return its path."""
        folder = cls._get_report_folder(report_id)
        os.makedirs(folder, exist_ok=True)
        return folder
    
    @classmethod
    def _get_report_path(cls, report_id: str) -> str:
        """Return the path of the report metadata file."""
        return os.path.join(cls._get_report_folder(report_id), "meta.json")
    
    @classmethod
    def _get_report_markdown_path(cls, report_id: str) -> str:
        """Return the path of the full-report Markdown file."""
        return os.path.join(cls._get_report_folder(report_id), "full_report.md")
    
    @classmethod
    def _get_outline_path(cls, report_id: str) -> str:
        """Return the path of the outline file."""
        return os.path.join(cls._get_report_folder(report_id), "outline.json")
    
    @classmethod
    def _get_progress_path(cls, report_id: str) -> str:
        """Return the path of the progress file."""
        return os.path.join(cls._get_report_folder(report_id), "progress.json")
    
    @classmethod
    def _get_section_path(cls, report_id: str, section_index: int) -> str:
        """Return the path of the section Markdown file."""
        return os.path.join(cls._get_report_folder(report_id), f"section_{section_index:02d}.md")
    
    @classmethod
    def _get_agent_log_path(cls, report_id: str) -> str:
        """Return the path of the Agent log file."""
        return os.path.join(cls._get_report_folder(report_id), "agent_log.jsonl")
    
    @classmethod
    def _get_console_log_path(cls, report_id: str) -> str:
        """Return the path of the console log file."""
        return os.path.join(cls._get_report_folder(report_id), "console_log.txt")
    
    @classmethod
    def get_console_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Read the console log content.

        These are the console-style log records (INFO, WARNING, etc.) emitted
        during report generation, distinct from the structured
        ``agent_log.jsonl`` entries.

        Args:
            report_id: Report ID.
            from_line: Line number to start reading from (0 = from the start);
                used for incremental fetches.

        Returns:
            ``{
                "logs": [list of log lines],
                "total_lines": total line count,
                "from_line": starting line number,
                "has_more": whether more log content is still available
            }``
        """
        log_path = cls._get_console_log_path(report_id)
        
        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }
        
        logs = []
        total_lines = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    # Preserve the original log line, stripping trailing newlines.
                    logs.append(line.rstrip('\n\r'))

        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # Already at end-of-file.
        }

    @classmethod
    def get_console_log_stream(cls, report_id: str) -> List[str]:
        """
        Fetch the entire console log in one call.

        Args:
            report_id: Report ID.

        Returns:
            List of log lines.
        """
        result = cls.get_console_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def get_agent_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Read the Agent log content.

        Args:
            report_id: Report ID.
            from_line: Line number to start reading from (0 = from the start);
                used for incremental fetches.

        Returns:
            ``{
                "logs": [list of log entries],
                "total_lines": total line count,
                "from_line": starting line number,
                "has_more": whether more log content is still available
            }``
        """
        log_path = cls._get_agent_log_path(report_id)
        
        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }
        
        logs = []
        total_lines = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    try:
                        log_entry = json.loads(line.strip())
                        logs.append(log_entry)
                    except json.JSONDecodeError:
                        # Skip lines that fail to parse.
                        continue

        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # Already at end-of-file.
        }

    @classmethod
    def get_agent_log_stream(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        Fetch the entire Agent log in one call.

        Args:
            report_id: Report ID.

        Returns:
            List of log entries.
        """
        result = cls.get_agent_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def save_outline(cls, report_id: str, outline: ReportOutline) -> None:
        """
        Persist the report outline.

        Called as soon as the planning stage finishes.
        """
        cls._ensure_report_folder(report_id)
        
        with open(cls._get_outline_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(outline.to_dict(), f, ensure_ascii=False, indent=2)
        
        logger.info(t('report.outlineSaved', reportId=report_id))
    
    @classmethod
    def save_section(
        cls,
        report_id: str,
        section_index: int,
        section: ReportSection
    ) -> str:
        """
        Persist a single section.

        Called as soon as each section finishes generating to provide streamed,
        section-by-section output.

        Args:
            report_id: Report ID.
            section_index: Section index (1-based).
            section: The section object.

        Returns:
            The path of the saved file.
        """
        cls._ensure_report_folder(report_id)

        # Build the section Markdown — strip any duplicate title lines.
        cleaned_content = cls._clean_section_content(section.content, section.title)
        md_content = f"## {section.title}\n\n"
        if cleaned_content:
            md_content += f"{cleaned_content}\n\n"

        # Persist the file.
        file_suffix = f"section_{section_index:02d}.md"
        file_path = os.path.join(cls._get_report_folder(report_id), file_suffix)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        logger.info(t('report.sectionFileSaved', reportId=report_id, fileSuffix=file_suffix))
        return file_path
    
    @classmethod
    def _clean_section_content(cls, content: str, section_title: str) -> str:
        """
        Clean a section's content.

        1. Remove a leading Markdown heading line that duplicates the section title.
        2. Convert any ``###`` or deeper headings to bold text.

        Args:
            content: Raw content.
            section_title: Section title.

        Returns:
            The cleaned content.
        """
        import re
        
        if not content:
            return content
        
        content = content.strip()
        lines = content.split('\n')
        cleaned_lines = []
        skip_next_empty = False
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Detect a Markdown heading line.
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)

            if heading_match:
                level = len(heading_match.group(1))
                title_text = heading_match.group(2).strip()

                # Drop a heading that duplicates the section title (only check the first 5 lines).
                if i < 5:
                    if title_text == section_title or title_text.replace(' ', '') == section_title.replace(' ', ''):
                        skip_next_empty = True
                        continue

                # Convert headings of every level (#, ##, ###, ####, etc.) into bold text,
                # because the section title is added by the system and the body should have no headings.
                cleaned_lines.append(f"**{title_text}**")
                cleaned_lines.append("")  # Append a blank line.
                continue

            # Skip the blank line that immediately follows a dropped heading.
            if skip_next_empty and stripped == '':
                skip_next_empty = False
                continue
            
            skip_next_empty = False
            cleaned_lines.append(line)
        
        # Strip leading blank lines.
        while cleaned_lines and cleaned_lines[0].strip() == '':
            cleaned_lines.pop(0)

        # Strip leading horizontal-rule lines.
        while cleaned_lines and cleaned_lines[0].strip() in ['---', '***', '___']:
            cleaned_lines.pop(0)
            # Also strip blank lines that follow the rule.
            while cleaned_lines and cleaned_lines[0].strip() == '':
                cleaned_lines.pop(0)
        
        return '\n'.join(cleaned_lines)
    
    @classmethod
    def update_progress(
        cls, 
        report_id: str, 
        status: str, 
        progress: int, 
        message: str,
        current_section: str = None,
        completed_sections: List[str] = None
    ) -> None:
        """
        Update report-generation progress.

        The frontend reads ``progress.json`` to display realtime progress.
        """
        cls._ensure_report_folder(report_id)
        
        progress_data = {
            "status": status,
            "progress": progress,
            "message": message,
            "current_section": current_section,
            "completed_sections": completed_sections or [],
            "updated_at": datetime.now().isoformat()
        }
        
        with open(cls._get_progress_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def get_progress(cls, report_id: str) -> Optional[Dict[str, Any]]:
        """Return the report's generation progress."""
        path = cls._get_progress_path(report_id)
        
        if not os.path.exists(path):
            return None
        
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    @classmethod
    def get_generated_sections(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        Return the list of sections that have already been generated.

        The result describes each section file that has been saved so far.
        """
        folder = cls._get_report_folder(report_id)
        
        if not os.path.exists(folder):
            return []
        
        sections = []
        for filename in sorted(os.listdir(folder)):
            if filename.startswith('section_') and filename.endswith('.md'):
                file_path = os.path.join(folder, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Derive the section index from the filename.
                parts = filename.replace('.md', '').split('_')
                section_index = int(parts[1])

                sections.append({
                    "filename": filename,
                    "section_index": section_index,
                    "content": content
                })

        return sections
    
    @classmethod
    def assemble_full_report(cls, report_id: str, outline: ReportOutline) -> str:
        """
        Assemble the full report.

        Combines all saved section files into the complete report and applies
        title-cleanup post-processing.
        """
        folder = cls._get_report_folder(report_id)
        
        # Build the report header.
        md_content = f"# {outline.title}\n\n"
        md_content += f"> {outline.summary}\n\n"
        md_content += f"---\n\n"

        # Read every section file in order.
        sections = cls.get_generated_sections(report_id)
        for section_info in sections:
            md_content += section_info["content"]

        # Post-process to fix heading issues across the whole report.
        md_content = cls._post_process_report(md_content, outline)

        # Persist the full report.
        full_path = cls._get_report_markdown_path(report_id)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        logger.info(t('report.fullReportAssembled', reportId=report_id))
        return md_content
    
    @classmethod
    def _post_process_report(cls, content: str, outline: ReportOutline) -> str:
        """
        Post-process the report content.

        1. Remove duplicate headings.
        2. Keep the report's main heading (``#``) and section headings (``##``);
           drop any deeper headings (``###``, ``####``, etc.).
        3. Tidy up extra blank lines and horizontal rules.

        Args:
            content: Raw report content.
            outline: Report outline.

        Returns:
            The processed content.
        """
        import re
        
        lines = content.split('\n')
        processed_lines = []
        prev_was_heading = False
        
        # Collect every section title from the outline.
        section_titles = set()
        for section in outline.sections:
            section_titles.add(section.title)
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Detect a heading line.
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)

            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()

                # Detect a duplicate heading — same text appearing within the previous 5 lines.
                is_duplicate = False
                for j in range(max(0, len(processed_lines) - 5), len(processed_lines)):
                    prev_line = processed_lines[j].strip()
                    prev_match = re.match(r'^(#{1,6})\s+(.+)$', prev_line)
                    if prev_match:
                        prev_title = prev_match.group(2).strip()
                        if prev_title == title:
                            is_duplicate = True
                            break
                
                if is_duplicate:
                    # Skip the duplicate heading and any blank lines that follow it.
                    i += 1
                    while i < len(lines) and lines[i].strip() == '':
                        i += 1
                    continue

                # Heading-level handling:
                # - # (level=1): keep only the report's main heading.
                # - ## (level=2): keep section headings.
                # - ### and deeper (level>=3): convert to bold text.

                if level == 1:
                    if title == outline.title:
                        # Keep the report's main heading.
                        processed_lines.append(line)
                        prev_was_heading = True
                    elif title in section_titles:
                        # A section heading mistakenly used ``#``; rewrite it to ``##``.
                        processed_lines.append(f"## {title}")
                        prev_was_heading = True
                    else:
                        # Other H1 headings become bold text.
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                elif level == 2:
                    if title in section_titles or title == outline.title:
                        # Keep the section heading.
                        processed_lines.append(line)
                        prev_was_heading = True
                    else:
                        # Non-section H2 headings become bold text.
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                else:
                    # H3 and deeper headings become bold text.
                    processed_lines.append(f"**{title}**")
                    processed_lines.append("")
                    prev_was_heading = False
                
                i += 1
                continue
            
            elif stripped == '---' and prev_was_heading:
                # Drop a horizontal rule that immediately follows a heading.
                i += 1
                continue

            elif stripped == '' and prev_was_heading:
                # Keep at most one blank line after a heading.
                if processed_lines and processed_lines[-1].strip() != '':
                    processed_lines.append(line)
                prev_was_heading = False
            
            else:
                processed_lines.append(line)
                prev_was_heading = False
            
            i += 1
        
        # Collapse consecutive blank lines, keeping at most two.
        result_lines = []
        empty_count = 0
        for line in processed_lines:
            if line.strip() == '':
                empty_count += 1
                if empty_count <= 2:
                    result_lines.append(line)
            else:
                empty_count = 0
                result_lines.append(line)
        
        return '\n'.join(result_lines)
    
    @classmethod
    def save_report(cls, report: Report) -> None:
        """Persist the report metadata and the full report."""
        cls._ensure_report_folder(report.report_id)

        # Save the metadata JSON.
        with open(cls._get_report_path(report.report_id), 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)

        # Save the outline.
        if report.outline:
            cls.save_outline(report.report_id, report.outline)

        # Save the full Markdown report.
        if report.markdown_content:
            with open(cls._get_report_markdown_path(report.report_id), 'w', encoding='utf-8') as f:
                f.write(report.markdown_content)
        
        logger.info(t('report.reportSaved', reportId=report.report_id))
    
    @classmethod
    def get_report(cls, report_id: str) -> Optional[Report]:
        """Fetch a report."""
        path = cls._get_report_path(report_id)
        
        if not os.path.exists(path):
            # Legacy format: check for a file stored directly under the reports root.
            old_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
            if os.path.exists(old_path):
                path = old_path
            else:
                return None
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Reconstruct the Report object.
        outline = None
        if data.get('outline'):
            outline_data = data['outline']
            sections = []
            for s in outline_data.get('sections', []):
                sections.append(ReportSection(
                    title=s['title'],
                    content=s.get('content', '')
                ))
            outline = ReportOutline(
                title=outline_data['title'],
                summary=outline_data['summary'],
                sections=sections
            )
        
        # When markdown_content is empty, fall back to reading full_report.md.
        markdown_content = data.get('markdown_content', '')
        if not markdown_content:
            full_report_path = cls._get_report_markdown_path(report_id)
            if os.path.exists(full_report_path):
                with open(full_report_path, 'r', encoding='utf-8') as f:
                    markdown_content = f.read()
        
        return Report(
            report_id=data['report_id'],
            simulation_id=data['simulation_id'],
            graph_id=data['graph_id'],
            simulation_requirement=data['simulation_requirement'],
            status=ReportStatus(data['status']),
            outline=outline,
            markdown_content=markdown_content,
            created_at=data.get('created_at', ''),
            completed_at=data.get('completed_at', ''),
            error=data.get('error')
        )
    
    @classmethod
    def get_report_by_simulation(cls, simulation_id: str) -> Optional[Report]:
        """Look up a report by its simulation ID."""
        cls._ensure_reports_dir()
        
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # New format: folder.
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report and report.simulation_id == simulation_id:
                    return report
            # Legacy format: JSON file.
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report and report.simulation_id == simulation_id:
                    return report

        return None

    @classmethod
    def list_reports(cls, simulation_id: Optional[str] = None, limit: int = 50) -> List[Report]:
        """List reports."""
        cls._ensure_reports_dir()

        reports = []
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # New format: folder.
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
            # Legacy format: JSON file.
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)

        # Sort by creation time, newest first.
        reports.sort(key=lambda r: r.created_at, reverse=True)
        
        return reports[:limit]
    
    @classmethod
    def delete_report(cls, report_id: str) -> bool:
        """Delete a report (the entire folder)."""
        import shutil
        
        folder_path = cls._get_report_folder(report_id)
        
        # New format: remove the entire folder.
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            shutil.rmtree(folder_path)
            logger.info(t('report.reportFolderDeleted', reportId=report_id))
            return True

        # Legacy format: remove the standalone files.
        deleted = False
        old_json_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
        old_md_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.md")
        
        if os.path.exists(old_json_path):
            os.remove(old_json_path)
            deleted = True
        if os.path.exists(old_md_path):
            os.remove(old_md_path)
            deleted = True
        
        return deleted
