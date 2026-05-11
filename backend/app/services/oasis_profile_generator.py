"""
OASIS Agent Profile generator.

Converts entities from the Zep graph into the Agent Profile format required by
the OASIS simulation platform.

Improvements:
1. Call Zep retrieval to further enrich node information.
2. Optimized prompts that produce highly detailed personas.
3. Distinguishes individual entities from abstract group entities.
"""

import json
import random
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from openai import OpenAI
from .graphiti_adapter import GraphitiAdapter

from ..config import Config
from ..utils.logger import get_logger
from ..utils.locale import get_language_instruction, get_locale, set_locale, t
from .zep_entity_reader import EntityNode, ZepEntityReader

logger = get_logger('mirofish.oasis_profile')


@dataclass
class OasisAgentProfile:
    """OASIS Agent Profile data structure."""
    # Common fields
    user_id: int
    user_name: str
    name: str
    bio: str
    persona: str

    # Optional fields - Reddit style
    karma: int = 1000

    # Optional fields - Twitter style
    friend_count: int = 100
    follower_count: int = 150
    statuses_count: int = 500

    # Additional persona information
    age: Optional[int] = None
    gender: Optional[str] = None
    mbti: Optional[str] = None
    country: Optional[str] = None
    profession: Optional[str] = None
    interested_topics: List[str] = field(default_factory=list)

    # Source entity information
    source_entity_uuid: Optional[str] = None
    source_entity_type: Optional[str] = None
    
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    
    def to_reddit_format(self) -> Dict[str, Any]:
        """Convert to Reddit platform format."""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,  # OASIS 库要求字段名为 username（无下划线）
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "created_at": self.created_at,
        }

        if self.age:
            profile["age"] = self.age
        if self.gender:
            profile["gender"] = self.gender
        if self.mbti:
            profile["mbti"] = self.mbti
        if self.country:
            profile["country"] = self.country
        if self.profession:
            profile["profession"] = self.profession
        if self.interested_topics:
            profile["interested_topics"] = self.interested_topics

        return profile

    def to_twitter_format(self) -> Dict[str, Any]:
        """Convert to Twitter platform format."""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,  # OASIS 库要求字段名为 username（无下划线）
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "created_at": self.created_at,
        }

        if self.age:
            profile["age"] = self.age
        if self.gender:
            profile["gender"] = self.gender
        if self.mbti:
            profile["mbti"] = self.mbti
        if self.country:
            profile["country"] = self.country
        if self.profession:
            profile["profession"] = self.profession
        if self.interested_topics:
            profile["interested_topics"] = self.interested_topics
        
        return profile
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to a full dictionary representation."""
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "age": self.age,
            "gender": self.gender,
            "mbti": self.mbti,
            "country": self.country,
            "profession": self.profession,
            "interested_topics": self.interested_topics,
            "source_entity_uuid": self.source_entity_uuid,
            "source_entity_type": self.source_entity_type,
            "created_at": self.created_at,
        }


class OasisProfileGenerator:
    """OASIS Profile generator.

    Converts entities from the Zep graph into the Agent Profiles required by
    the OASIS simulation.

    Highlights:
    1. Uses Zep graph retrieval to gather richer context.
    2. Produces highly detailed personas (basic info, career history, traits,
       social-media behavior, etc.).
    3. Distinguishes individual entities from group/institution entities.
    """

    MBTI_TYPES = [
        "INTJ", "INTP", "ENTJ", "ENTP",
        "INFJ", "INFP", "ENFJ", "ENFP",
        "ISTJ", "ISFJ", "ESTJ", "ESFJ",
        "ISTP", "ISFP", "ESTP", "ESFP"
    ]

    COUNTRIES = [
        "China", "US", "UK", "Japan", "Germany", "France",
        "Canada", "Australia", "Brazil", "India", "South Korea"
    ]

    # Individual entity types — generate a concrete persona for each.
    INDIVIDUAL_ENTITY_TYPES = [
        "student", "alumni", "professor", "person", "publicfigure",
        "expert", "faculty", "official", "journalist", "activist"
    ]

    # Group / institution entity types — generate a representative-account persona.
    GROUP_ENTITY_TYPES = [
        "university", "governmentagency", "organization", "ngo",
        "mediaoutlet", "company", "institution", "group", "community"
    ]
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        zep_api_key: Optional[str] = None,
        graph_id: Optional[str] = None
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
        
        self.zep_client = GraphitiAdapter()
        self.graph_id = graph_id
    
    def generate_profile_from_entity(
        self, 
        entity: EntityNode, 
        user_id: int,
        use_llm: bool = True
    ) -> OasisAgentProfile:
        """Generate an OASIS Agent Profile from a Zep entity.

        Args:
            entity: The Zep entity node.
            user_id: The OASIS user id to assign.
            use_llm: Whether to use the LLM to generate a detailed persona.

        Returns:
            OasisAgentProfile
        """
        entity_type = entity.get_entity_type() or "Entity"

        name = entity.name
        user_name = self._generate_username(name)

        context = self._build_entity_context(entity)

        if use_llm:
            profile_data = self._generate_profile_with_llm(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes,
                context=context
            )
        else:
            profile_data = self._generate_profile_rule_based(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes
            )
        
        return OasisAgentProfile(
            user_id=user_id,
            user_name=user_name,
            name=name,
            bio=profile_data.get("bio", f"{entity_type}: {name}"),
            persona=profile_data.get("persona", entity.summary or f"A {entity_type} named {name}."),
            karma=profile_data.get("karma", random.randint(500, 5000)),
            friend_count=profile_data.get("friend_count", random.randint(50, 500)),
            follower_count=profile_data.get("follower_count", random.randint(100, 1000)),
            statuses_count=profile_data.get("statuses_count", random.randint(100, 2000)),
            age=profile_data.get("age"),
            gender=profile_data.get("gender"),
            mbti=profile_data.get("mbti"),
            country=profile_data.get("country"),
            profession=profile_data.get("profession"),
            interested_topics=profile_data.get("interested_topics", []),
            source_entity_uuid=entity.uuid,
            source_entity_type=entity_type,
        )
    
    def _generate_username(self, name: str) -> str:
        """Generate a username from an entity name."""
        # Strip special characters and lowercase the name.
        username = name.lower().replace(" ", "_")
        username = ''.join(c for c in username if c.isalnum() or c == '_')

        # Append a random numeric suffix to avoid collisions.
        suffix = random.randint(100, 999)
        return f"{username}_{suffix}"
    
    def _search_zep_for_entity(self, entity: EntityNode) -> Dict[str, Any]:
        """Use Zep hybrid graph search to gather rich context for an entity.

        Zep does not expose a built-in hybrid search endpoint, so we search
        edges and nodes separately and merge the results. The two searches
        run in parallel for throughput.

        Args:
            entity: The entity node to search around.

        Returns:
            A dict with keys ``facts``, ``node_summaries`` and ``context``.
        """
        import concurrent.futures
        
        if not self.zep_client:
            return {"facts": [], "node_summaries": [], "context": ""}
        
        entity_name = entity.name
        
        results = {
            "facts": [],
            "node_summaries": [],
            "context": ""
        }
        
        # A graph_id is required for any retrieval.
        if not self.graph_id:
            logger.debug(t("log.profile_generator.m001"))
            return results
        
        comprehensive_query = t('progress.zepSearchQuery', name=entity_name)
        
        def search_edges():
            """Search edges (facts / relationships) with retries."""
            max_retries = 3
            last_exception = None
            delay = 2.0
            
            for attempt in range(max_retries):
                try:
                    return self.zep_client.graph.search(
                        query=comprehensive_query,
                        graph_id=self.graph_id,
                        limit=30,
                        scope="edges",
                    )
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.debug(t("log.profile_generator.m002", attempt=attempt + 1, str=str(e)[:80]))
                        time.sleep(delay)
                        delay *= 2
                    else:
                        logger.debug(t("log.profile_generator.m003", max_retries=max_retries, e=e))
            return None
        
        def search_nodes():
            """Search nodes (entity summaries) with retries."""
            max_retries = 3
            last_exception = None
            delay = 2.0
            
            for attempt in range(max_retries):
                try:
                    return self.zep_client.graph.search(
                        query=comprehensive_query,
                        graph_id=self.graph_id,
                        limit=20,
                        scope="nodes",
                    )
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.debug(t("log.profile_generator.m004", attempt=attempt + 1, str=str(e)[:80]))
                        time.sleep(delay)
                        delay *= 2
                    else:
                        logger.debug(t("log.profile_generator.m005", max_retries=max_retries, e=e))
            return None
        
        try:
            # Run edge and node searches in parallel.
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                edge_future = executor.submit(search_edges)
                node_future = executor.submit(search_nodes)

                edge_result = edge_future.result(timeout=30)
                node_result = node_future.result(timeout=30)

            # Process edge-search results.
            all_facts = set()
            if edge_result and hasattr(edge_result, 'edges') and edge_result.edges:
                for edge in edge_result.edges:
                    if hasattr(edge, 'fact') and edge.fact:
                        all_facts.add(edge.fact)
            results["facts"] = list(all_facts)

            # Process node-search results.
            all_summaries = set()
            if node_result and hasattr(node_result, 'nodes') and node_result.nodes:
                for node in node_result.nodes:
                    if hasattr(node, 'summary') and node.summary:
                        all_summaries.add(node.summary)
                    if hasattr(node, 'name') and node.name and node.name != entity_name:
                        all_summaries.add(f"Related entity: {node.name}")
            results["node_summaries"] = list(all_summaries)

            # Assemble the combined context block.
            context_parts = []
            if results["facts"]:
                context_parts.append("Facts:\n" + "\n".join(f"- {f}" for f in results["facts"][:20]))
            if results["node_summaries"]:
                context_parts.append("Related entities:\n" + "\n".join(f"- {s}" for s in results["node_summaries"][:10]))
            results["context"] = "\n\n".join(context_parts)
            
            logger.info(t("log.profile_generator.m006", entity_name=entity_name, len=len(results['facts']), len_2=len(results['node_summaries'])))
            
        except concurrent.futures.TimeoutError:
            logger.warning(t("log.profile_generator.m007", entity_name=entity_name))
        except Exception as e:
            logger.warning(t("log.profile_generator.m008", entity_name=entity_name, e=e))
        
        return results
    
    def _build_entity_context(self, entity: EntityNode) -> str:
        """Assemble the full context block for an entity.

        Includes:
        1. The entity's own edge information (facts).
        2. Detailed information about related nodes.
        3. Additional context retrieved from Zep hybrid search.
        """
        context_parts = []

        # 1. Entity attributes.
        if entity.attributes:
            attrs = []
            for key, value in entity.attributes.items():
                if value and str(value).strip():
                    attrs.append(f"- {key}: {value}")
            if attrs:
                context_parts.append("### Entity attributes\n" + "\n".join(attrs))
        
        # 2. Related edges (facts / relationships).
        existing_facts = set()
        if entity.related_edges:
            relationships = []
            for edge in entity.related_edges:  # No cap on count.
                fact = edge.get("fact", "")
                edge_name = edge.get("edge_name", "")
                direction = edge.get("direction", "")
                
                if fact:
                    relationships.append(f"- {fact}")
                    existing_facts.add(fact)
                elif edge_name:
                    if direction == "outgoing":
                        relationships.append(f"- {entity.name} --[{edge_name}]--> (related entity)")
                    else:
                        relationships.append(f"- (related entity) --[{edge_name}]--> {entity.name}")

            if relationships:
                context_parts.append("### Related facts and relationships\n" + "\n".join(relationships))
        
        # 3. Detailed information for related nodes.
        if entity.related_nodes:
            related_info = []
            for node in entity.related_nodes:  # No cap on count.
                node_name = node.get("name", "")
                node_labels = node.get("labels", [])
                node_summary = node.get("summary", "")

                # Drop the default labels added by the graph store.
                custom_labels = [l for l in node_labels if l not in ["Entity", "Node"]]
                label_str = f" ({', '.join(custom_labels)})" if custom_labels else ""
                
                if node_summary:
                    related_info.append(f"- **{node_name}**{label_str}: {node_summary}")
                else:
                    related_info.append(f"- **{node_name}**{label_str}")
            
            if related_info:
                context_parts.append("### Related entity information\n" + "\n".join(related_info))
        
        # 4. Augment with Zep hybrid retrieval.
        zep_results = self._search_zep_for_entity(entity)

        if zep_results.get("facts"):
            # Deduplicate against already-known facts.
            new_facts = [f for f in zep_results["facts"] if f not in existing_facts]
            if new_facts:
                context_parts.append("### Facts retrieved from the graph\n" + "\n".join(f"- {f}" for f in new_facts[:15]))

        if zep_results.get("node_summaries"):
            context_parts.append("### Related nodes retrieved from the graph\n" + "\n".join(f"- {s}" for s in zep_results["node_summaries"][:10]))
        
        return "\n\n".join(context_parts)
    
    def _is_individual_entity(self, entity_type: str) -> bool:
        """Return True if the entity type represents an individual."""
        return entity_type.lower() in self.INDIVIDUAL_ENTITY_TYPES

    def _is_group_entity(self, entity_type: str) -> bool:
        """Return True if the entity type represents a group or institution."""
        return entity_type.lower() in self.GROUP_ENTITY_TYPES
    
    def _generate_profile_with_llm(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> Dict[str, Any]:
        """Generate a highly detailed persona using the LLM.

        Branches on entity type:
        - Individual entities: produces a concrete persona for a person.
        - Group / institution entities: produces a representative-account persona.
        """

        is_individual = self._is_individual_entity(entity_type)
        
        if is_individual:
            prompt = self._build_individual_persona_prompt(
                entity_name, entity_type, entity_summary, entity_attributes, context
            )
        else:
            prompt = self._build_group_persona_prompt(
                entity_name, entity_type, entity_summary, entity_attributes, context
            )

        # Retry generation up to max_attempts times.
        max_attempts = 3
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt(is_individual)},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7 - (attempt * 0.1)  # Lower the temperature on each retry.
                    # No max_tokens cap so the LLM can produce a full persona.
                )

                content = response.choices[0].message.content

                # Detect truncation (finish_reason other than 'stop').
                finish_reason = response.choices[0].finish_reason
                if finish_reason == 'length':
                    logger.warning(t("log.profile_generator.m009", attempt=attempt + 1))
                    content = self._fix_truncated_json(content)
                
                # Parse the JSON payload.
                try:
                    result = json.loads(content)

                    # Backfill required fields when missing.
                    if "bio" not in result or not result["bio"]:
                        result["bio"] = entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}"
                    if "persona" not in result or not result["persona"]:
                        result["persona"] = entity_summary or f"{entity_name} is a {entity_type}."
                    
                    return result
                    
                except json.JSONDecodeError as je:
                    logger.warning(t("log.profile_generator.m010", attempt=attempt + 1, str=str(je)[:80]))

                    # Attempt to repair the JSON.
                    result = self._try_fix_json(content, entity_name, entity_type, entity_summary)
                    if result.get("_fixed"):
                        del result["_fixed"]
                        return result
                    
                    last_error = je
                    
            except Exception as e:
                logger.warning(t("log.profile_generator.m011", attempt=attempt + 1, str=str(e)[:80]))
                last_error = e
                import time
                time.sleep(1 * (attempt + 1))  # Exponential backoff.
        
        logger.warning(t("log.profile_generator.m012", max_attempts=max_attempts, last_error=last_error))
        return self._generate_profile_rule_based(
            entity_name, entity_type, entity_summary, entity_attributes
        )
    
    def _fix_truncated_json(self, content: str) -> str:
        """Repair JSON output truncated by a max_tokens limit."""
        import re

        # Trim whitespace before closing the structure.
        content = content.strip()

        # Count unbalanced brackets and braces.
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')

        # Heuristic: if the last char is not a quote, comma, or closing bracket,
        # the trailing string value was likely truncated mid-token.
        if content and content[-1] not in '",}]':
            # Close the dangling string.
            content += '"'

        # Close any open brackets and braces.
        content += ']' * open_brackets
        content += '}' * open_braces

        return content
    
    def _try_fix_json(self, content: str, entity_name: str, entity_type: str, entity_summary: str = "") -> Dict[str, Any]:
        """Best-effort repair of damaged JSON output."""
        import re

        # 1. Repair truncation first.
        content = self._fix_truncated_json(content)

        # 2. Extract the JSON object span.
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            json_str = json_match.group()

            # 3. Fix newlines inside string values.
            def fix_string_newlines(match):
                s = match.group(0)
                # Replace literal newlines inside string values with spaces.
                s = s.replace('\n', ' ').replace('\r', ' ')
                # Collapse runs of whitespace.
                s = re.sub(r'\s+', ' ', s)
                return s

            # Match JSON string values.
            json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', fix_string_newlines, json_str)

            # 4. Try to parse.
            try:
                result = json.loads(json_str)
                result["_fixed"] = True
                return result
            except json.JSONDecodeError as e:
                # 5. Fall back to a more aggressive repair pass.
                try:
                    # Strip control characters.
                    json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                    # Collapse all consecutive whitespace.
                    json_str = re.sub(r'\s+', ' ', json_str)
                    result = json.loads(json_str)
                    result["_fixed"] = True
                    return result
                except:
                    pass

        # 6. Last resort: scrape partial fields out of the content.
        bio_match = re.search(r'"bio"\s*:\s*"([^"]*)"', content)
        persona_match = re.search(r'"persona"\s*:\s*"([^"]*)', content)  # May be truncated.
        
        bio = bio_match.group(1) if bio_match else (entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}")
        persona = persona_match.group(1) if persona_match else (entity_summary or f"{entity_name} is a {entity_type}.")
        
        # If we recovered something meaningful, mark the result as fixed.
        if bio_match or persona_match:
            logger.info(t("log.profile_generator.m013"))
            return {
                "bio": bio,
                "persona": persona,
                "_fixed": True
            }
        
        # 7. Total failure: return a minimal fallback structure.
        logger.warning(t("log.profile_generator.m014"))
        return {
            "bio": entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}",
            "persona": entity_summary or f"{entity_name} is a {entity_type}."
        }
    
    def _get_system_prompt(self, is_individual: bool) -> str:
        """Return the system prompt for persona generation."""
        base_prompt = "You are an expert at generating social-media user personas. Produce detailed, realistic personas for opinion-simulation, faithfully grounded in the supplied real-world context. You MUST return valid JSON; no string value may contain unescaped newline characters."
        return f"{base_prompt}\n\n{get_language_instruction()}"

    def _build_individual_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> str:
        """Build the detailed persona prompt for an individual entity."""

        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "None"
        context_str = context[:3000] if context else "No additional context"

        return f"""Generate a detailed social-media user persona for an entity, faithfully grounded in the supplied real-world context.


Entity name: {entity_name}
Entity type: {entity_type}
Entity summary: {entity_summary}
Entity attributes: {attrs_str}

Context:
{context_str}

Produce a JSON object with the following fields:

1. bio: ~200-character social-media bio.
2. persona: detailed persona description as a single coherent ~2000-character plain-text passage covering:
   - basic info (age, profession, educational background, location)
   - background (notable experiences, link to the focal event, social relationships)
   - personality (MBTI type, core traits, emotional expression style)
   - social-media behaviour (posting frequency, content preferences, interaction style, voice)
   - stance and opinions (attitude toward the topic, content likely to provoke or move them)
   - distinctive traits (catchphrases, unusual experiences, hobbies)
   - personal memories (a key part of the persona; describe this individual's link to the focal event and any actions / reactions they have already taken in connection with it)
3. age: an integer.
4. gender: must be the literal English token "male" or "female".
5. mbti: MBTI type (e.g. INTJ, ENFP).
6. country: free-form country name.
7. profession: free-form occupation.
8. interested_topics: array of topic strings.

Important:
- All field values must be strings or numbers; do not include newline characters in any string value.
- persona must be a single coherent prose passage.
- {get_language_instruction()} (the gender field must remain English: male/female.)
- The content must remain consistent with the supplied entity information.
- age must be a valid integer; gender must be exactly "male" or "female".
"""

    def _build_group_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> str:
        """Build the detailed persona prompt for a group or institution entity."""

        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "None"
        context_str = context[:3000] if context else "No additional context"

        return f"""Generate a detailed social-media account profile for an institutional or group entity, faithfully grounded in the supplied real-world context.


Entity name: {entity_name}
Entity type: {entity_type}
Entity summary: {entity_summary}
Entity attributes: {attrs_str}

Context:
{context_str}

Produce a JSON object with the following fields:

1. bio: ~200-character official-account bio, polished and professional.
2. persona: detailed account profile as a single coherent ~2000-character plain-text passage covering:
   - institution basics (formal name, type of institution, founding background, primary functions)
   - account positioning (account type, target audience, core purpose)
   - voice (linguistic style, common expressions, taboo topics)
   - content patterns (content types, posting frequency, active hours)
   - stance (official position on the focal topic, how disputes are handled)
   - special notes (the group profile it represents, operational habits)
   - institutional memory (a key part of the persona; describe this institution's link to the focal event and any actions / reactions it has already taken in connection with it)
3. age: must be the integer 30 (a virtual age used for institutional accounts).
4. gender: must be the literal English token "other" (institutional accounts use "other" to indicate non-individual).
5. mbti: MBTI type used to describe the account's voice (e.g. ISTJ for a rigorous, conservative tone).
6. country: free-form country name.
7. profession: free-form description of the institution's role.
8. interested_topics: array of focus areas.

Important:
- All field values must be strings or numbers; null values are not allowed.
- persona must be a single coherent prose passage; do not include newline characters in any string value.
- {get_language_instruction()} (the gender field must remain English: "other".)
- age must be the integer 30; gender must be exactly the string "other".
- The institutional account's voice must match its identity."""
    
    def _generate_profile_rule_based(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Rule-based fallback that generates a basic persona."""

        # Branch on entity type to pick a persona shape.
        entity_type_lower = entity_type.lower()
        
        if entity_type_lower in ["student", "alumni"]:
            return {
                "bio": f"{entity_type} with interests in academics and social issues.",
                "persona": f"{entity_name} is a {entity_type.lower()} who is actively engaged in academic and social discussions. They enjoy sharing perspectives and connecting with peers.",
                "age": random.randint(18, 30),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(self.MBTI_TYPES),
                "country": random.choice(self.COUNTRIES),
                "profession": "Student",
                "interested_topics": ["Education", "Social Issues", "Technology"],
            }
        
        elif entity_type_lower in ["publicfigure", "expert", "faculty"]:
            return {
                "bio": f"Expert and thought leader in their field.",
                "persona": f"{entity_name} is a recognized {entity_type.lower()} who shares insights and opinions on important matters. They are known for their expertise and influence in public discourse.",
                "age": random.randint(35, 60),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(["ENTJ", "INTJ", "ENTP", "INTP"]),
                "country": random.choice(self.COUNTRIES),
                "profession": entity_attributes.get("occupation", "Expert"),
                "interested_topics": ["Politics", "Economics", "Culture & Society"],
            }
        
        elif entity_type_lower in ["mediaoutlet", "socialmediaplatform"]:
            return {
                "bio": f"Official account for {entity_name}. News and updates.",
                "persona": f"{entity_name} is a media entity that reports news and facilitates public discourse. The account shares timely updates and engages with the audience on current events.",
                "age": 30,  # 机构虚拟年龄
                "gender": "other",  # 机构使用other
                "mbti": "ISTJ",  # 机构风格：严谨保守
                "country": "中国",
                "profession": "Media",
                "interested_topics": ["General News", "Current Events", "Public Affairs"],
            }
        
        elif entity_type_lower in ["university", "governmentagency", "ngo", "organization"]:
            return {
                "bio": f"Official account of {entity_name}.",
                "persona": f"{entity_name} is an institutional entity that communicates official positions, announcements, and engages with stakeholders on relevant matters.",
                "age": 30,  # 机构虚拟年龄
                "gender": "other",  # 机构使用other
                "mbti": "ISTJ",  # 机构风格：严谨保守
                "country": "中国",
                "profession": entity_type,
                "interested_topics": ["Public Policy", "Community", "Official Announcements"],
            }
        
        else:
            # Default persona for unrecognised entity types.
            return {
                "bio": entity_summary[:150] if entity_summary else f"{entity_type}: {entity_name}",
                "persona": entity_summary or f"{entity_name} is a {entity_type.lower()} participating in social discussions.",
                "age": random.randint(25, 50),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(self.MBTI_TYPES),
                "country": random.choice(self.COUNTRIES),
                "profession": entity_type,
                "interested_topics": ["General", "Social Issues"],
            }
    
    def set_graph_id(self, graph_id: str):
        """Set the graph id used for Zep retrieval."""
        self.graph_id = graph_id
    
    def generate_profiles_from_entities(
        self,
        entities: List[EntityNode],
        use_llm: bool = True,
        progress_callback: Optional[callable] = None,
        graph_id: Optional[str] = None,
        parallel_count: int = 5,
        realtime_output_path: Optional[str] = None,
        output_platform: str = "reddit"
    ) -> List[OasisAgentProfile]:
        """Batch-generate Agent Profiles from entities (in parallel).

        Args:
            entities: The entities to convert.
            use_llm: Whether to use the LLM to generate detailed personas.
            progress_callback: Progress callback ``(current, total, message)``.
            graph_id: Graph id used for Zep retrieval to gather richer context.
            parallel_count: Number of profiles to generate concurrently (default 5).
            realtime_output_path: If set, profiles are flushed to this path after
                each successful generation.
            output_platform: Output platform format, ``"reddit"`` or ``"twitter"``.

        Returns:
            The generated list of Agent Profiles.
        """
        import concurrent.futures
        from threading import Lock
        
        # Set the graph id used for Zep retrieval.
        if graph_id:
            self.graph_id = graph_id

        total = len(entities)
        profiles = [None] * total  # Preallocate to keep insertion order.
        completed_count = [0]  # List wrapper so closures can mutate the count.
        lock = Lock()

        def save_profiles_realtime():
            """Flush the profiles generated so far to ``realtime_output_path``."""
            if not realtime_output_path:
                return
            
            with lock:
                existing_profiles = [p for p in profiles if p is not None]
                if not existing_profiles:
                    return

                try:
                    if output_platform == "reddit":
                        # Reddit JSON format.
                        profiles_data = [p.to_reddit_format() for p in existing_profiles]
                        with open(realtime_output_path, 'w', encoding='utf-8') as f:
                            json.dump(profiles_data, f, ensure_ascii=False, indent=2)
                    else:
                        # Twitter CSV format.
                        import csv
                        profiles_data = [p.to_twitter_format() for p in existing_profiles]
                        if profiles_data:
                            fieldnames = list(profiles_data[0].keys())
                            with open(realtime_output_path, 'w', encoding='utf-8', newline='') as f:
                                writer = csv.DictWriter(f, fieldnames=fieldnames)
                                writer.writeheader()
                                writer.writerows(profiles_data)
                except Exception as e:
                    logger.warning(t("log.profile_generator.m015", e=e))
        
        # Capture locale before spawning thread pool workers
        current_locale = get_locale()

        def generate_single_profile(idx: int, entity: EntityNode) -> tuple:
            """Worker function that generates a single profile."""
            set_locale(current_locale)
            entity_type = entity.get_entity_type() or "Entity"
            
            try:
                profile = self.generate_profile_from_entity(
                    entity=entity,
                    user_id=idx,
                    use_llm=use_llm
                )
                
                # Stream the generated persona to the console and log.
                self._print_generated_profile(entity.name, entity_type, profile)
                
                return idx, profile, None
                
            except Exception as e:
                logger.error(t("log.profile_generator.m016", entity=entity.name, str=str(e)))
                # Build a minimal fallback profile.
                fallback_profile = OasisAgentProfile(
                    user_id=idx,
                    user_name=self._generate_username(entity.name),
                    name=entity.name,
                    bio=f"{entity_type}: {entity.name}",
                    persona=entity.summary or f"A participant in social discussions.",
                    source_entity_uuid=entity.uuid,
                    source_entity_type=entity_type,
                )
                return idx, fallback_profile, str(e)
        
        logger.info(t("log.profile_generator.m017", total=total, parallel_count=parallel_count))
        print(f"\n{'='*60}")
        print(t("log.profile_generator.m024", total=total, parallel_count=parallel_count))
        print(f"{'='*60}\n")
        
        # Run generation across a thread pool.
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_count) as executor:
            future_to_entity = {
                executor.submit(generate_single_profile, idx, entity): (idx, entity)
                for idx, entity in enumerate(entities)
            }

            for future in concurrent.futures.as_completed(future_to_entity):
                idx, entity = future_to_entity[future]
                entity_type = entity.get_entity_type() or "Entity"
                
                try:
                    result_idx, profile, error = future.result()
                    profiles[result_idx] = profile
                    
                    with lock:
                        completed_count[0] += 1
                        current = completed_count[0]
                    
                    # Flush profiles to disk in real time.
                    save_profiles_realtime()

                    if progress_callback:
                        progress_callback(
                            current, 
                            total, 
                            f"Completed {current}/{total}: {entity.name} ({entity_type})"
                        )
                    
                    if error:
                        logger.warning(t("log.profile_generator.m018", current=current, total=total, entity=entity.name, error=error))
                    else:
                        logger.info(t("log.profile_generator.m019", current=current, total=total, entity=entity.name, entity_type=entity_type))
                        
                except Exception as e:
                    logger.error(t("log.profile_generator.m020", entity=entity.name, str=str(e)))
                    with lock:
                        completed_count[0] += 1
                    profiles[idx] = OasisAgentProfile(
                        user_id=idx,
                        user_name=self._generate_username(entity.name),
                        name=entity.name,
                        bio=f"{entity_type}: {entity.name}",
                        persona=entity.summary or "A participant in social discussions.",
                        source_entity_uuid=entity.uuid,
                        source_entity_type=entity_type,
                    )
                    # Flush profiles to disk even when only the fallback was produced.
                    save_profiles_realtime()
        
        print(f"\n{'='*60}")
        print(t("log.profile_generator.m025", count=len([p for p in profiles if p])))
        print(f"{'='*60}\n")
        
        return profiles
    
    def _print_generated_profile(self, entity_name: str, entity_type: str, profile: OasisAgentProfile):
        """Stream the generated persona to the console (full content, untruncated)."""
        separator = "-" * 70

        # Assemble the full output (no truncation).
        topics_str = ', '.join(profile.interested_topics) if profile.interested_topics else 'None'


        output_lines = [
            f"\n{separator}",
            t('progress.profileGenerated', name=entity_name, type=entity_type),
            f"{separator}",
            f"Username: {profile.user_name}",
            f"",
            f"[Bio]",
            f"{profile.bio}",
            f"",
            f"[Persona]",
            f"{profile.persona}",
            f"",
            f"[Basic attributes]",
            f"Age: {profile.age} | Gender: {profile.gender} | MBTI: {profile.mbti}",
            f"Profession: {profile.profession} | Country: {profile.country}",
            f"Interested topics: {topics_str}",
            separator
        ]
        
        output = "\n".join(output_lines)
        
        # Print to the console only — the logger no longer emits the full content
        # to avoid duplicate output.
        print(output)
    
    def save_profiles(
        self,
        profiles: List[OasisAgentProfile],
        file_path: str,
        platform: str = "reddit"
    ):
        """Save profiles to a file using the platform-specific format.

        OASIS format requirements:
        - Twitter: CSV format.
        - Reddit: JSON format.

        Args:
            profiles: The profiles to save.
            file_path: Destination file path.
            platform: Platform type, ``"reddit"`` or ``"twitter"``.
        """
        if platform == "twitter":
            self._save_twitter_csv(profiles, file_path)
        else:
            self._save_reddit_json(profiles, file_path)
    
    def _save_twitter_csv(self, profiles: List[OasisAgentProfile], file_path: str):
        """Save Twitter profiles as CSV (matches OASIS's official format).

        Required CSV fields for OASIS Twitter:
        - user_id: User id (zero-indexed by CSV row order).
        - name: User's real-world display name.
        - username: System username.
        - user_char: Detailed persona text injected into the LLM system prompt
          to drive agent behavior.
        - description: Short public bio shown on the profile page.

        ``user_char`` vs ``description``:
        - user_char: Internal — LLM system prompt that controls how the agent
          thinks and acts.
        - description: External — short bio visible to other users.
        """
        import csv

        # Ensure the file extension is .csv.
        if not file_path.endswith('.csv'):
            file_path = file_path.replace('.json', '.csv')

        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)

            # Write the OASIS-required header row.
            headers = ['user_id', 'name', 'username', 'user_char', 'description']
            writer.writerow(headers)

            for idx, profile in enumerate(profiles):
                # user_char: full persona (bio + persona), used in the LLM system prompt.
                user_char = profile.bio
                if profile.persona and profile.persona != profile.bio:
                    user_char = f"{profile.bio} {profile.persona}"
                # Replace newlines with spaces for CSV compatibility.
                user_char = user_char.replace('\n', ' ').replace('\r', ' ')

                # description: short bio used for external display.
                description = profile.bio.replace('\n', ' ').replace('\r', ' ')

                row = [
                    idx,                    # user_id: zero-based sequential id
                    profile.name,           # name: real-world display name
                    profile.user_name,      # username: system username
                    user_char,              # user_char: full persona (internal LLM use)
                    description             # description: short bio (external display)
                ]
                writer.writerow(row)
        
        logger.info(t("log.profile_generator.m021", len=len(profiles), file_path=file_path))
    
    def _normalize_gender(self, gender: Optional[str]) -> str:
        """Normalize the gender field into the English form required by OASIS.

        OASIS requires one of: ``male``, ``female``, ``other``.
        """
        if not gender:
            return "other"

        gender_lower = gender.lower().strip()

        # Mapping from Chinese values to the English literals.
        gender_map = {
            "男": "male",
            "女": "female",
            "机构": "other",
            "其他": "other",
            # Already in English — pass through.
            "male": "male",
            "female": "female",
            "other": "other",
        }
        
        return gender_map.get(gender_lower, "other")
    
    def _save_reddit_json(self, profiles: List[OasisAgentProfile], file_path: str):
        """Save Reddit profiles as JSON.

        Uses the same shape as ``to_reddit_format()`` to ensure OASIS can read
        the file. The ``user_id`` field is mandatory — it is what
        ``agent_graph.get_agent()`` matches against.

        Required fields:
        - user_id: User id (integer; matches ``poster_agent_id`` in
          ``initial_posts``).
        - username: System username.
        - name: Display name.
        - bio: Short bio.
        - persona: Detailed persona.
        - age: Age (integer).
        - gender: One of ``"male"``, ``"female"``, ``"other"``.
        - mbti: MBTI type.
        - country: Country.
        """
        data = []
        for idx, profile in enumerate(profiles):
            # Match the shape of to_reddit_format().
            item = {
                "user_id": profile.user_id if profile.user_id is not None else idx,  # Critical: must include user_id.
                "username": profile.user_name,
                "name": profile.name,
                "bio": profile.bio[:150] if profile.bio else f"{profile.name}",
                "persona": profile.persona or f"{profile.name} is a participant in social discussions.",
                "karma": profile.karma if profile.karma else 1000,
                "created_at": profile.created_at,
                # OASIS-required fields — make sure each has a default.
                "age": profile.age if profile.age else 30,
                "gender": self._normalize_gender(profile.gender),
                "mbti": profile.mbti if profile.mbti else "ISTJ",
                "country": profile.country if profile.country else "中国",
            }

            # Optional fields.
            if profile.profession:
                item["profession"] = profile.profession
            if profile.interested_topics:
                item["interested_topics"] = profile.interested_topics
            
            data.append(item)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(t("log.profile_generator.m022", len=len(profiles), file_path=file_path))
    
    # Retained as an alias for the old method name (backwards compatibility).
    def save_profiles_to_json(
        self,
        profiles: List[OasisAgentProfile],
        file_path: str,
        platform: str = "reddit"
    ):
        """[Deprecated] Use ``save_profiles()`` instead."""
        logger.warning(t("log.profile_generator.m023"))
        self.save_profiles(profiles, file_path, platform)

