"""
Intelligent simulation-configuration generator.

Uses an LLM to derive detailed simulation parameters from the simulation
requirement, document content, and knowledge-graph information, fully
automating parameter setup without manual intervention.

Employs a step-wise generation strategy to avoid failures caused by
producing too much content in a single call:
1. Generate time configuration
2. Generate event configuration
3. Generate agent configurations in batches
4. Generate platform configuration
"""

import json
import math
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime

from openai import OpenAI

from ..config import Config
from ..utils.logger import get_logger
from ..utils.locale import get_language_instruction, t
from .graph_entity_reader import EntityNode, GraphEntityReader

logger = get_logger('mirofish.simulation_config')

# Daily-rhythm config for China (Beijing time, UTC+8).
CHINA_TIMEZONE_CONFIG = {
    # Late-night hours: almost no activity.
    "dead_hours": [0, 1, 2, 3, 4, 5],
    # Morning hours: gradually waking up.
    "morning_hours": [6, 7, 8],
    # Working hours.
    "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
    # Evening peak: most active.
    "peak_hours": [19, 20, 21, 22],
    # Late-evening hours: activity declining.
    "night_hours": [23],
    # Activity multipliers.
    "activity_multipliers": {
        "dead": 0.05,      # Overnight: almost no one online.
        "morning": 0.4,    # Morning ramp-up.
        "work": 0.7,       # Working hours: moderate activity.
        "peak": 1.5,       # Evening peak.
        "night": 0.5       # Late-night decline.
    }
}


@dataclass
class AgentActivityConfig:
    """Activity configuration for a single agent."""
    agent_id: int
    entity_uuid: str
    entity_name: str
    entity_type: str

    # Activity configuration (0.0-1.0).
    activity_level: float = 0.5  # Overall activity level.

    # Posting frequency (expected posts per hour).
    posts_per_hour: float = 1.0
    comments_per_hour: float = 2.0

    # Active hours (24-hour clock, 0-23).
    active_hours: List[int] = field(default_factory=lambda: list(range(8, 23)))

    # Response speed: latency to react to hot events, in simulated minutes.
    response_delay_min: int = 5
    response_delay_max: int = 60

    # Sentiment bias (-1.0 to 1.0, negative to positive).
    sentiment_bias: float = 0.0

    # Stance: attitude toward a given topic.
    stance: str = "neutral"  # supportive, opposing, neutral, observer

    # Influence weight: probability of an agent's post being seen by others.
    influence_weight: float = 1.0


@dataclass  
class TimeSimulationConfig:
    """Time-simulation configuration (modelled on a Chinese daily rhythm)."""
    # Total simulated duration (simulated hours).
    total_simulation_hours: int = 72  # Default: 72 simulated hours (3 days).

    # Time represented by each round (simulated minutes); default 60 (1 hour) to speed up the simulated clock.
    minutes_per_round: int = 60

    # Range of agents activated per hour.
    agents_per_hour_min: int = 5
    agents_per_hour_max: int = 20

    # Peak hours (evenings 19:00-22:00, most active for the modelled audience).
    peak_hours: List[int] = field(default_factory=lambda: [19, 20, 21, 22])
    peak_activity_multiplier: float = 1.5

    # Off-peak hours (00:00-05:00, almost no activity).
    off_peak_hours: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5])
    off_peak_activity_multiplier: float = 0.05  # Overnight activity is very low.

    # Morning hours.
    morning_hours: List[int] = field(default_factory=lambda: [6, 7, 8])
    morning_activity_multiplier: float = 0.4

    # Working hours.
    work_hours: List[int] = field(default_factory=lambda: [9, 10, 11, 12, 13, 14, 15, 16, 17, 18])
    work_activity_multiplier: float = 0.7


@dataclass
class EventConfig:
    """Event configuration."""
    # Initial events: triggers fired when the simulation begins.
    initial_posts: List[Dict[str, Any]] = field(default_factory=list)

    # Scheduled events: events fired at specific times.
    scheduled_events: List[Dict[str, Any]] = field(default_factory=list)

    # Hot-topic keywords.
    hot_topics: List[str] = field(default_factory=list)

    # Narrative direction for public-opinion guidance.
    narrative_direction: str = ""


@dataclass
class PlatformConfig:
    """Platform-specific configuration."""
    platform: str  # twitter or reddit

    # Recommendation-algorithm weights.
    recency_weight: float = 0.4  # Recency.
    popularity_weight: float = 0.3  # Popularity.
    relevance_weight: float = 0.3  # Relevance.

    # Viral-spread threshold: number of interactions required to trigger spreading.
    viral_threshold: int = 10

    # Echo-chamber strength: how strongly similar viewpoints cluster together.
    echo_chamber_strength: float = 0.5


@dataclass
class SimulationParameters:
    """Complete simulation-parameter configuration."""
    # Basic identifiers.
    simulation_id: str
    project_id: str
    graph_id: str
    simulation_requirement: str

    # Time configuration.
    time_config: TimeSimulationConfig = field(default_factory=TimeSimulationConfig)

    # Agent configuration list.
    agent_configs: List[AgentActivityConfig] = field(default_factory=list)

    # Event configuration.
    event_config: EventConfig = field(default_factory=EventConfig)

    # Platform configurations.
    twitter_config: Optional[PlatformConfig] = None
    reddit_config: Optional[PlatformConfig] = None

    # LLM configuration.
    llm_model: str = ""
    llm_base_url: str = ""

    # Generation metadata.
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    generation_reasoning: str = ""  # LLM-provided rationale.

    def to_dict(self) -> Dict[str, Any]:
        """Return the parameters as a dictionary."""
        time_dict = asdict(self.time_config)
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "time_config": time_dict,
            "agent_configs": [asdict(a) for a in self.agent_configs],
            "event_config": asdict(self.event_config),
            "twitter_config": asdict(self.twitter_config) if self.twitter_config else None,
            "reddit_config": asdict(self.reddit_config) if self.reddit_config else None,
            "llm_model": self.llm_model,
            "llm_base_url": self.llm_base_url,
            "generated_at": self.generated_at,
            "generation_reasoning": self.generation_reasoning,
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Return the parameters as a JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


class SimulationConfigGenerator:
    """
    Intelligent simulation-configuration generator.

    Uses an LLM to analyse the simulation requirement, document content,
    and graph entity information to automatically derive the best
    simulation parameter configuration.

    Step-wise generation strategy:
    1. Generate time and event configurations (lightweight).
    2. Generate agent configurations in batches (10-20 per batch).
    3. Generate platform configuration.
    """

    # Maximum context length (characters).
    MAX_CONTEXT_LENGTH = 50000
    # Number of agents generated per batch.
    AGENTS_PER_BATCH = 15

    # Per-step context truncation lengths (characters).
    TIME_CONFIG_CONTEXT_LENGTH = 10000   # Time configuration.
    EVENT_CONFIG_CONTEXT_LENGTH = 8000   # Event configuration.
    ENTITY_SUMMARY_LENGTH = 300          # Entity summary.
    AGENT_SUMMARY_LENGTH = 300           # Entity summary used in agent configs.
    ENTITIES_PER_TYPE_DISPLAY = 20       # Number of entities displayed per type.
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model_name = model_name or Config.LLM_MODEL_NAME
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY 未配置")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
    
    def generate_config(
        self,
        simulation_id: str,
        project_id: str,
        graph_id: str,
        simulation_requirement: str,
        document_text: str,
        entities: List[EntityNode],
        enable_twitter: bool = True,
        enable_reddit: bool = True,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> SimulationParameters:
        """Intelligently generate a complete simulation configuration (step-wise).

        Args:
            simulation_id: Simulation ID.
            project_id: Project ID.
            graph_id: Graph ID.
            simulation_requirement: Description of the simulation requirement.
            document_text: Original document content.
            entities: Filtered list of entities.
            enable_twitter: Whether to enable Twitter.
            enable_reddit: Whether to enable Reddit.
            progress_callback: Progress callback (current_step, total_steps, message).

        Returns:
            SimulationParameters: The complete simulation parameters.
        """
        logger.info(t("log.simulation_config.m001", simulation_id=simulation_id, len=len(entities)))
        
        # Compute total step count.
        num_batches = math.ceil(len(entities) / self.AGENTS_PER_BATCH)
        total_steps = 3 + num_batches  # Time config + event config + N agent batches + platform config.
        current_step = 0
        
        def report_progress(step: int, message: str):
            nonlocal current_step
            current_step = step
            if progress_callback:
                progress_callback(step, total_steps, message)
            logger.info(f"[{step}/{total_steps}] {message}")
        
        # 1. Build base context information.
        context = self._build_context(
            simulation_requirement=simulation_requirement,
            document_text=document_text,
            entities=entities
        )
        
        reasoning_parts = []
        
        # ========== Step 1: generate time configuration ==========
        report_progress(1, t('progress.generatingTimeConfig'))
        num_entities = len(entities)
        time_config_result = self._generate_time_config(context, num_entities)
        time_config = self._parse_time_config(time_config_result, num_entities)
        reasoning_parts.append(f"{t('progress.timeConfigLabel')}: {time_config_result.get('reasoning', t('common.success'))}")
        
        # ========== Step 2: generate event configuration ==========
        report_progress(2, t('progress.generatingEventConfig'))
        event_config_result = self._generate_event_config(context, simulation_requirement, entities)
        event_config = self._parse_event_config(event_config_result)
        reasoning_parts.append(f"{t('progress.eventConfigLabel')}: {event_config_result.get('reasoning', t('common.success'))}")
        
        # ========== Steps 3-N: generate agent configurations in batches ==========
        all_agent_configs = []
        for batch_idx in range(num_batches):
            start_idx = batch_idx * self.AGENTS_PER_BATCH
            end_idx = min(start_idx + self.AGENTS_PER_BATCH, len(entities))
            batch_entities = entities[start_idx:end_idx]
            
            report_progress(
                3 + batch_idx,
                t('progress.generatingAgentConfig', start=start_idx + 1, end=end_idx, total=len(entities))
            )
            
            batch_configs = self._generate_agent_configs_batch(
                context=context,
                entities=batch_entities,
                start_idx=start_idx,
                simulation_requirement=simulation_requirement
            )
            all_agent_configs.extend(batch_configs)
        
        reasoning_parts.append(t('progress.agentConfigResult', count=len(all_agent_configs)))
        
        # ========== Assign poster agents to initial posts ==========
        logger.info(t("log.simulation_config.m002"))
        event_config = self._assign_initial_post_agents(event_config, all_agent_configs)
        assigned_count = len([p for p in event_config.initial_posts if p.get("poster_agent_id") is not None])
        reasoning_parts.append(t('progress.postAssignResult', count=assigned_count))
        
        # ========== Final step: generate platform configuration ==========
        report_progress(total_steps, t('progress.generatingPlatformConfig'))
        twitter_config = None
        reddit_config = None
        
        if enable_twitter:
            twitter_config = PlatformConfig(
                platform="twitter",
                recency_weight=0.4,
                popularity_weight=0.3,
                relevance_weight=0.3,
                viral_threshold=10,
                echo_chamber_strength=0.5
            )
        
        if enable_reddit:
            reddit_config = PlatformConfig(
                platform="reddit",
                recency_weight=0.3,
                popularity_weight=0.4,
                relevance_weight=0.3,
                viral_threshold=15,
                echo_chamber_strength=0.6
            )
        
        # Build final parameters.
        params = SimulationParameters(
            simulation_id=simulation_id,
            project_id=project_id,
            graph_id=graph_id,
            simulation_requirement=simulation_requirement,
            time_config=time_config,
            agent_configs=all_agent_configs,
            event_config=event_config,
            twitter_config=twitter_config,
            reddit_config=reddit_config,
            llm_model=self.model_name,
            llm_base_url=self.base_url,
            generation_reasoning=" | ".join(reasoning_parts)
        )
        
        logger.info(t("log.simulation_config.m003", len=len(params.agent_configs)))
        
        return params
    
    def _build_context(
        self,
        simulation_requirement: str,
        document_text: str,
        entities: List[EntityNode]
    ) -> str:
        """Build the LLM context, truncated to the maximum length."""

        # Entity summary.
        entity_summary = self._summarize_entities(entities)

        # Build the context.
        context_parts = [
            f"## Simulation Requirement\n{simulation_requirement}",
            f"\n## Entities ({len(entities)})\n{entity_summary}",
        ]

        current_length = sum(len(p) for p in context_parts)
        remaining_length = self.MAX_CONTEXT_LENGTH - current_length - 500  # Reserve 500-char headroom.

        if remaining_length > 0 and document_text:
            doc_text = document_text[:remaining_length]
            if len(document_text) > remaining_length:
                doc_text += "\n...(document truncated)"
            context_parts.append(f"\n## Source Document Content\n{doc_text}")

        return "\n".join(context_parts)
    
    def _summarize_entities(self, entities: List[EntityNode]) -> str:
        """Generate an entity summary."""
        lines = []

        # Group by type.
        by_type: Dict[str, List[EntityNode]] = {}
        for e in entities:
            t = e.get_entity_type() or "Unknown"
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(e)
        
        for entity_type, type_entities in by_type.items():
            lines.append(f"\n### {entity_type} ({len(type_entities)})")
            # Use configured display count and summary length.
            display_count = self.ENTITIES_PER_TYPE_DISPLAY
            summary_len = self.ENTITY_SUMMARY_LENGTH
            for e in type_entities[:display_count]:
                summary_preview = (e.summary[:summary_len] + "...") if len(e.summary) > summary_len else e.summary
                lines.append(f"- {e.name}: {summary_preview}")
            if len(type_entities) > display_count:
                lines.append(f"  ... and {len(type_entities) - display_count} more")
        
        return "\n".join(lines)
    
    def _call_llm_with_retry(self, prompt: str, system_prompt: str) -> Dict[str, Any]:
        """LLM call with retries, including JSON repair logic."""
        import re
        
        max_attempts = 3
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7 - (attempt * 0.1)  # Lower temperature on each retry.
                    # max_tokens is intentionally unset so the LLM can use its full budget.
                )

                content = response.choices[0].message.content
                finish_reason = response.choices[0].finish_reason

                # Detect truncation.
                if finish_reason == 'length':
                    logger.warning(t("log.simulation_config.m004", attempt=attempt + 1))
                    content = self._fix_truncated_json(content)
                
                # Attempt to parse JSON.
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    logger.warning(t("log.simulation_config.m005", attempt=attempt + 1, str=str(e)[:80]))

                    # Attempt to repair the JSON.
                    fixed = self._try_fix_config_json(content)
                    if fixed:
                        return fixed
                    
                    last_error = e
                    
            except Exception as e:
                logger.warning(t("log.simulation_config.m006", attempt=attempt + 1, str=str(e)[:80]))
                last_error = e
                import time
                time.sleep(2 * (attempt + 1))
        
        raise last_error or Exception("LLM调用失败")
    
    def _fix_truncated_json(self, content: str) -> str:
        """Repair truncated JSON."""
        content = content.strip()

        # Count unclosed brackets.
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')

        # Check for an unclosed string.
        if content and content[-1] not in '",}]':
            content += '"'

        # Close brackets.
        content += ']' * open_brackets
        content += '}' * open_braces
        
        return content
    
    def _try_fix_config_json(self, content: str) -> Optional[Dict[str, Any]]:
        """Attempt to repair a configuration JSON payload."""
        import re

        # Repair truncation first.
        content = self._fix_truncated_json(content)

        # Extract the JSON portion.
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            json_str = json_match.group()

            # Remove line breaks from inside strings.
            def fix_string(match):
                s = match.group(0)
                s = s.replace('\n', ' ').replace('\r', ' ')
                s = re.sub(r'\s+', ' ', s)
                return s
            
            json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', fix_string, json_str)
            
            try:
                return json.loads(json_str)
            except:
                # Strip all control characters and try again.
                json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                json_str = re.sub(r'\s+', ' ', json_str)
                try:
                    return json.loads(json_str)
                except:
                    pass
        
        return None
    
    def _generate_time_config(self, context: str, num_entities: int) -> Dict[str, Any]:
        """Generate the time configuration."""
        # Use the configured context truncation length.
        context_truncated = context[:self.TIME_CONFIG_CONTEXT_LENGTH]

        # Compute the upper bound (90% of the agent count).
        max_agents_allowed = max(1, int(num_entities * 0.9))
        
        prompt = f"""Based on the simulation requirement below, generate a time-simulation configuration.

{context_truncated}

## Task
Produce a time-configuration JSON.

### Guiding principles (illustrative only — adapt to the specific event and audience):
- Infer the timezone and daily rhythm of the target audience from the simulation scenario. The following are example values for the UTC+8 timezone.
- 00:00-05:00: almost no activity (activity multiplier 0.05).
- 06:00-08:00: gradually waking up (activity multiplier 0.4).
- 09:00-18:00: working hours, moderate activity (activity multiplier 0.7).
- 19:00-22:00: evening peak (activity multiplier 1.5).
- After 23:00: activity declines (activity multiplier 0.5).
- General rule of thumb: low overnight, ramping up in the morning, moderate during working hours, peaking in the evening.
- **Important**: the example values above are only a reference. Tailor the schedule to the nature of the event and the audience's habits.
  - For example: a student-heavy audience may peak from 21:00-23:00; news outlets may stay active all day; official agencies are only active during working hours.
  - For example: a breaking-news topic may keep discussion going late at night, in which case off_peak_hours can be shortened.

### Return strict JSON (no markdown)

Example:
{{
    "total_simulation_hours": 72,
    "minutes_per_round": 60,
    "agents_per_hour_min": 5,
    "agents_per_hour_max": 50,
    "peak_hours": [19, 20, 21, 22],
    "off_peak_hours": [0, 1, 2, 3, 4, 5],
    "morning_hours": [6, 7, 8],
    "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
    "reasoning": "Time configuration rationale for this event"
}}

Field guide:
- total_simulation_hours (int): total simulated duration, 24-168 hours; short for breaking events, long for sustained topics.
- minutes_per_round (int): minutes per round, 30-120; recommended 60.
- agents_per_hour_min (int): minimum number of agents activated per hour (allowed range: 1-{max_agents_allowed}).
- agents_per_hour_max (int): maximum number of agents activated per hour (allowed range: 1-{max_agents_allowed}).
- peak_hours (int array): peak hours, adjusted to the audience.
- off_peak_hours (int array): off-peak hours, typically overnight.
- morning_hours (int array): morning hours.
- work_hours (int array): working hours.
- reasoning (string): brief explanation of why this configuration was chosen."""

        system_prompt = "You are a social-media simulation expert. Return plain JSON. The time configuration should match the daily rhythm of the simulation's target audience."
        system_prompt = f"{system_prompt}\n\n{get_language_instruction()}"

        try:
            return self._call_llm_with_retry(prompt, system_prompt)
        except Exception as e:
            logger.warning(t("log.simulation_config.m007", e=e))
            return self._get_default_time_config(num_entities)
    
    def _get_default_time_config(self, num_entities: int) -> Dict[str, Any]:
        """Return the default time configuration (Chinese daily rhythm)."""
        return {
            "total_simulation_hours": 72,
            "minutes_per_round": 60,  # 1 hour per round to speed up the simulated clock.
            "agents_per_hour_min": max(1, num_entities // 15),
            "agents_per_hour_max": max(5, num_entities // 5),
            "peak_hours": [19, 20, 21, 22],
            "off_peak_hours": [0, 1, 2, 3, 4, 5],
            "morning_hours": [6, 7, 8],
            "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
            "reasoning": "Default circadian-pattern config (1h per round)"
        }
    
    def _parse_time_config(self, result: Dict[str, Any], num_entities: int) -> TimeSimulationConfig:
        """Parse the time-configuration result and ensure agents_per_hour values do not exceed the total agent count."""
        # Pull raw values.
        agents_per_hour_min = result.get("agents_per_hour_min", max(1, num_entities // 15))
        agents_per_hour_max = result.get("agents_per_hour_max", max(5, num_entities // 5))

        # Validate and correct: ensure values do not exceed the total agent count.
        if agents_per_hour_min > num_entities:
            logger.warning(t("log.simulation_config.m008", agents_per_hour_min=agents_per_hour_min, num_entities=num_entities))
            agents_per_hour_min = max(1, num_entities // 10)
        
        if agents_per_hour_max > num_entities:
            logger.warning(t("log.simulation_config.m009", agents_per_hour_max=agents_per_hour_max, num_entities=num_entities))
            agents_per_hour_max = max(agents_per_hour_min + 1, num_entities // 2)
        
        # Ensure min < max.
        if agents_per_hour_min >= agents_per_hour_max:
            agents_per_hour_min = max(1, agents_per_hour_max // 2)
            logger.warning(t("log.simulation_config.m010", agents_per_hour_min=agents_per_hour_min))
        
        return TimeSimulationConfig(
            total_simulation_hours=result.get("total_simulation_hours", 72),
            minutes_per_round=result.get("minutes_per_round", 60),  # Default: 1 simulated hour per round.
            agents_per_hour_min=agents_per_hour_min,
            agents_per_hour_max=agents_per_hour_max,
            peak_hours=result.get("peak_hours", [19, 20, 21, 22]),
            off_peak_hours=result.get("off_peak_hours", [0, 1, 2, 3, 4, 5]),
            off_peak_activity_multiplier=0.05,  # Overnight: almost no one online.
            morning_hours=result.get("morning_hours", [6, 7, 8]),
            morning_activity_multiplier=0.4,
            work_hours=result.get("work_hours", list(range(9, 19))),
            work_activity_multiplier=0.7,
            peak_activity_multiplier=1.5
        )
    
    def _generate_event_config(
        self, 
        context: str, 
        simulation_requirement: str,
        entities: List[EntityNode]
    ) -> Dict[str, Any]:
        """Generate the event configuration."""

        # Build the list of available entity types for the LLM to reference.
        entity_types_available = list(set(
            e.get_entity_type() or "Unknown" for e in entities
        ))

        # Collect representative entity names per type.
        type_examples = {}
        for e in entities:
            etype = e.get_entity_type() or "Unknown"
            if etype not in type_examples:
                type_examples[etype] = []
            if len(type_examples[etype]) < 3:
                type_examples[etype].append(e.name)
        
        type_info = "\n".join([
            f"- {t}: {', '.join(examples)}" 
            for t, examples in type_examples.items()
        ])
        
        # Use the configured context truncation length.
        context_truncated = context[:self.EVENT_CONFIG_CONTEXT_LENGTH]
        
        prompt = f"""Based on the simulation requirement below, generate an event configuration.

Simulation requirement: {simulation_requirement}

{context_truncated}

## Available entity types and examples
{type_info}

## Task
Produce an event-configuration JSON:
- Extract hot-topic keywords.
- Describe the direction in which public opinion is expected to evolve.
- Design the initial posts. **Every post must specify a poster_type (the type of the entity that publishes it).**

**Important**: poster_type MUST be one of the values listed in "Available entity types" above so each initial post can be assigned to an appropriate agent.
For example: official statements should be published by Official/University, news by MediaOutlet, student opinions by Student.

Return strict JSON (no markdown):
{{
    "hot_topics": ["keyword 1", "keyword 2", ...],
    "narrative_direction": "<description of how public opinion is expected to evolve>",
    "initial_posts": [
        {{"content": "post content", "poster_type": "entity type (must be one of the available types)"}},
        ...
    ],
    "reasoning": "<brief rationale>"
}}"""

        system_prompt = "You are a public-opinion analyst. Return plain JSON. Note that poster_type must exactly match one of the available entity types."
        system_prompt = f"{system_prompt}\n\n{get_language_instruction()}\nIMPORTANT: The 'poster_type' field value MUST be in English PascalCase exactly matching the available entity types. Only 'content', 'narrative_direction', 'hot_topics' and 'reasoning' fields should use the specified language."

        try:
            return self._call_llm_with_retry(prompt, system_prompt)
        except Exception as e:
            logger.warning(t("log.simulation_config.m011", e=e))
            return {
                "hot_topics": [],
                "narrative_direction": "",
                "initial_posts": [],
                "reasoning": "Used default config"
            }
    
    def _parse_event_config(self, result: Dict[str, Any]) -> EventConfig:
        """Parse the event-configuration result."""
        return EventConfig(
            initial_posts=result.get("initial_posts", []),
            scheduled_events=[],
            hot_topics=result.get("hot_topics", []),
            narrative_direction=result.get("narrative_direction", "")
        )
    
    def _assign_initial_post_agents(
        self,
        event_config: EventConfig,
        agent_configs: List[AgentActivityConfig]
    ) -> EventConfig:
        """Assign a suitable poster agent to each initial post.

        Matches the most appropriate agent_id for each post based on its
        poster_type.
        """
        if not event_config.initial_posts:
            return event_config

        # Build an agent index keyed by entity type.
        agents_by_type: Dict[str, List[AgentActivityConfig]] = {}
        for agent in agent_configs:
            etype = agent.entity_type.lower()
            if etype not in agents_by_type:
                agents_by_type[etype] = []
            agents_by_type[etype].append(agent)
        
        # Type alias map (handles the different formats the LLM might emit).
        type_aliases = {
            "official": ["official", "university", "governmentagency", "government"],
            "university": ["university", "official"],
            "mediaoutlet": ["mediaoutlet", "media"],
            "student": ["student", "person"],
            "professor": ["professor", "expert", "teacher"],
            "alumni": ["alumni", "person"],
            "organization": ["organization", "ngo", "company", "group"],
            "person": ["person", "student", "alumni"],
        }
        
        # Track the next agent index used per type to avoid reusing the same agent twice.
        used_indices: Dict[str, int] = {}
        
        updated_posts = []
        for post in event_config.initial_posts:
            poster_type = post.get("poster_type", "").lower()
            content = post.get("content", "")
            
            # Try to find a matching agent.
            matched_agent_id = None

            # 1. Direct match.
            if poster_type in agents_by_type:
                agents = agents_by_type[poster_type]
                idx = used_indices.get(poster_type, 0) % len(agents)
                matched_agent_id = agents[idx].agent_id
                used_indices[poster_type] = idx + 1
            else:
                # 2. Match via aliases.
                for alias_key, aliases in type_aliases.items():
                    if poster_type in aliases or alias_key == poster_type:
                        for alias in aliases:
                            if alias in agents_by_type:
                                agents = agents_by_type[alias]
                                idx = used_indices.get(alias, 0) % len(agents)
                                matched_agent_id = agents[idx].agent_id
                                used_indices[alias] = idx + 1
                                break
                    if matched_agent_id is not None:
                        break
            
            # 3. If still unresolved, fall back to the most influential agent.
            if matched_agent_id is None:
                logger.warning(t("log.simulation_config.m012", poster_type=poster_type))
                if agent_configs:
                    # Sort by influence and pick the highest.
                    sorted_agents = sorted(agent_configs, key=lambda a: a.influence_weight, reverse=True)
                    matched_agent_id = sorted_agents[0].agent_id
                else:
                    matched_agent_id = 0
            
            updated_posts.append({
                "content": content,
                "poster_type": post.get("poster_type", "Unknown"),
                "poster_agent_id": matched_agent_id
            })
            
            logger.info(t("log.simulation_config.m013", poster_type=poster_type, matched_agent_id=matched_agent_id))
        
        event_config.initial_posts = updated_posts
        return event_config
    
    def _generate_agent_configs_batch(
        self,
        context: str,
        entities: List[EntityNode],
        start_idx: int,
        simulation_requirement: str
    ) -> List[AgentActivityConfig]:
        """Generate agent configurations in batches."""

        # Build entity information (using the configured summary length).
        entity_list = []
        summary_len = self.AGENT_SUMMARY_LENGTH
        for i, e in enumerate(entities):
            entity_list.append({
                "agent_id": start_idx + i,
                "entity_name": e.name,
                "entity_type": e.get_entity_type() or "Unknown",
                "summary": e.summary[:summary_len] if e.summary else ""
            })
        
        prompt = f"""Based on the information below, generate a social-media activity configuration for each entity.

Simulation requirement: {simulation_requirement}

## Entity list
```json
{json.dumps(entity_list, ensure_ascii=False, indent=2)}
```

## Task
Generate an activity configuration for each entity. Notes:
- **Times must match the daily rhythm of the target audience** — the following are reference values for the UTC+8 timezone; adapt them to the simulation scenario.
- **Officials** (University/GovernmentAgency): low activity (0.1-0.3), active during working hours (9-17), slow response (60-240 minutes), high influence (2.5-3.0).
- **Media** (MediaOutlet): medium activity (0.4-0.6), active throughout the day (8-23), fast response (5-30 minutes), high influence (2.0-2.5).
- **Individuals** (Student/Person/Alumni): high activity (0.6-0.9), mainly active in the evening (18-23), fast response (1-15 minutes), low influence (0.8-1.2).
- **Public figures / experts**: medium activity (0.4-0.6), mid-to-high influence (1.5-2.0).

Return strict JSON (no markdown):
{{
    "agent_configs": [
        {{
            "agent_id": <must match the input>,
            "activity_level": <0.0-1.0>,
            "posts_per_hour": <posting frequency>,
            "comments_per_hour": <commenting frequency>,
            "active_hours": [<list of active hours, matching the audience's daily rhythm>],
            "response_delay_min": <minimum response delay in minutes>,
            "response_delay_max": <maximum response delay in minutes>,
            "sentiment_bias": <-1.0 to 1.0>,
            "stance": "<supportive/opposing/neutral/observer>",
            "influence_weight": <influence weight>
        }},
        ...
    ]
}}"""

        system_prompt = "You are a social-media behaviour analyst. Return plain JSON. The configuration should match the daily rhythm of the simulation's target audience."
        system_prompt = f"{system_prompt}\n\n{get_language_instruction()}\nIMPORTANT: The 'stance' field value MUST be one of the English strings: 'supportive', 'opposing', 'neutral', 'observer'. All JSON field names and numeric values must remain unchanged. Only natural language text fields should use the specified language."

        try:
            result = self._call_llm_with_retry(prompt, system_prompt)
            llm_configs = {cfg["agent_id"]: cfg for cfg in result.get("agent_configs", [])}
        except Exception as e:
            logger.warning(t("log.simulation_config.m014", e=e))
            llm_configs = {}
        
        # Build AgentActivityConfig objects.
        configs = []
        for i, entity in enumerate(entities):
            agent_id = start_idx + i
            cfg = llm_configs.get(agent_id, {})

            # If the LLM did not produce a config, fall back to rule-based generation.
            if not cfg:
                cfg = self._generate_agent_config_by_rule(entity)
            
            config = AgentActivityConfig(
                agent_id=agent_id,
                entity_uuid=entity.uuid,
                entity_name=entity.name,
                entity_type=entity.get_entity_type() or "Unknown",
                activity_level=cfg.get("activity_level", 0.5),
                posts_per_hour=cfg.get("posts_per_hour", 0.5),
                comments_per_hour=cfg.get("comments_per_hour", 1.0),
                active_hours=cfg.get("active_hours", list(range(9, 23))),
                response_delay_min=cfg.get("response_delay_min", 5),
                response_delay_max=cfg.get("response_delay_max", 60),
                sentiment_bias=cfg.get("sentiment_bias", 0.0),
                stance=cfg.get("stance", "neutral"),
                influence_weight=cfg.get("influence_weight", 1.0)
            )
            configs.append(config)
        
        return configs
    
    def _generate_agent_config_by_rule(self, entity: EntityNode) -> Dict[str, Any]:
        """Rule-based generation for a single agent's configuration (Chinese daily rhythm)."""
        entity_type = (entity.get_entity_type() or "Unknown").lower()

        if entity_type in ["university", "governmentagency", "ngo"]:
            # Official institutions: active during working hours, low frequency, high influence.
            return {
                "activity_level": 0.2,
                "posts_per_hour": 0.1,
                "comments_per_hour": 0.05,
                "active_hours": list(range(9, 18)),  # 09:00-17:59
                "response_delay_min": 60,
                "response_delay_max": 240,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 3.0
            }
        elif entity_type in ["mediaoutlet"]:
            # Media: active throughout the day, medium frequency, high influence.
            return {
                "activity_level": 0.5,
                "posts_per_hour": 0.8,
                "comments_per_hour": 0.3,
                "active_hours": list(range(7, 24)),  # 07:00-23:59
                "response_delay_min": 5,
                "response_delay_max": 30,
                "sentiment_bias": 0.0,
                "stance": "observer",
                "influence_weight": 2.5
            }
        elif entity_type in ["professor", "expert", "official"]:
            # Experts / professors: active during work and evening, medium frequency.
            return {
                "activity_level": 0.4,
                "posts_per_hour": 0.3,
                "comments_per_hour": 0.5,
                "active_hours": list(range(8, 22)),  # 08:00-21:59
                "response_delay_min": 15,
                "response_delay_max": 90,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 2.0
            }
        elif entity_type in ["student"]:
            # Students: mostly evening, high frequency.
            return {
                "activity_level": 0.8,
                "posts_per_hour": 0.6,
                "comments_per_hour": 1.5,
                "active_hours": [8, 9, 10, 11, 12, 13, 18, 19, 20, 21, 22, 23],  # Morning + evening.
                "response_delay_min": 1,
                "response_delay_max": 15,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 0.8
            }
        elif entity_type in ["alumni"]:
            # Alumni: mostly evening.
            return {
                "activity_level": 0.6,
                "posts_per_hour": 0.4,
                "comments_per_hour": 0.8,
                "active_hours": [12, 13, 19, 20, 21, 22, 23],  # Lunch break + evening.
                "response_delay_min": 5,
                "response_delay_max": 30,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 1.0
            }
        else:
            # General public: evening peak.
            return {
                "activity_level": 0.7,
                "posts_per_hour": 0.5,
                "comments_per_hour": 1.2,
                "active_hours": [9, 10, 11, 12, 13, 18, 19, 20, 21, 22, 23],  # Daytime + evening.
                "response_delay_min": 2,
                "response_delay_max": 20,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 1.0
            }
    

