"""Ontology generation service.

Pipeline step 1: analyze the source text and propose entity and relationship
types that fit a social-media opinion simulation.
"""

import json
import logging
import re
from typing import Dict, Any, List, Optional
from ..utils.llm_client import LLMClient
from ..utils.locale import get_language_instruction

logger = logging.getLogger(__name__)


def _to_pascal_case(name: str) -> str:
    """Convert an arbitrary identifier to PascalCase (e.g. ``works_for`` -> ``WorksFor``)."""
    # Split on non-alphanumeric separators first.
    parts = re.split(r'[^a-zA-Z0-9]+', name)
    # Then split on camelCase boundaries (e.g. ``camelCase`` -> ``['camel', 'Case']``).
    words = []
    for part in parts:
        words.extend(re.sub(r'([a-z])([A-Z])', r'\1_\2', part).split('_'))
    # Title-case each non-empty word and concatenate.
    result = ''.join(word.capitalize() for word in words if word)
    return result if result else 'Unknown'


# System prompt template for ontology generation.
ONTOLOGY_SYSTEM_PROMPT = """You are a professional knowledge-graph ontology designer. Your task is to analyze the supplied text and simulation requirement and design entity types and relationship types suitable for a **social-media public-opinion simulation**.

**Important: you must output valid JSON data and nothing else.**

## Core Task Background

We are building a **social-media public-opinion simulation system**. In this system:
- Every entity is an "account" or "actor" that can post on social media, interact with other accounts, and propagate information.
- Entities influence each other, repost, comment on, and respond to one another.
- We need to simulate how each side of a public-opinion event reacts and how information flows.

Therefore, **entities must be real-world subjects that can plausibly post on social media and interact with others**:

**Acceptable**:
- Specific individuals (public figures, parties to the event, opinion leaders, experts and scholars, ordinary people)
- Companies and businesses (including their official accounts)
- Organizations (universities, associations, NGOs, unions, etc.)
- Government departments and regulators
- Media organizations (newspapers, broadcasters, independent media, websites)
- Social-media platforms themselves
- Representatives of specific groups (alumni associations, fan communities, advocacy groups, etc.)

**Not acceptable**:
- Abstract concepts (such as "public opinion", "sentiment", "trend")
- Topics or subjects (such as "academic integrity", "education reform")
- Viewpoints or stances (such as "supporters", "opponents")

## Output Format

Return JSON with the following structure:

```json
{
    "entity_types": [
        {
            "name": "entity type name (English, PascalCase)",
            "description": "short description (English, no more than 100 characters)",
            "attributes": [
                {
                    "name": "attribute name (English, snake_case)",
                    "type": "text",
                    "description": "attribute description"
                }
            ],
            "examples": ["example entity 1", "example entity 2"]
        }
    ],
    "edge_types": [
        {
            "name": "relationship type name (English, UPPER_SNAKE_CASE)",
            "description": "short description (English, no more than 100 characters)",
            "source_targets": [
                {"source": "source entity type", "target": "target entity type"}
            ],
            "attributes": []
        }
    ],
    "analysis_summary": "brief analytical summary of the text content"
}
```

## Design Guidelines (must be followed)

### 1. Entity Type Design - strictly required

**Count requirement: exactly 10 entity types.**

**Hierarchy requirement (must include both concrete types and fallback types)**:

Your 10 entity types must form the following hierarchy:

A. **Fallback types (mandatory; placed as the last 2 entries)**:
   - `Person`: the fallback type for any individual. When a person does not fit any more specific person type, classify them here.
   - `Organization`: the fallback type for any organization. When an organization does not fit any more specific organization type, classify it here.

B. **Concrete types (8 entries, designed from the text content)**:
   - Define more specific types for the major roles that appear in the text.
   - Example: for an academic event, you might use `Student`, `Professor`, `University`.
   - Example: for a business event, you might use `Company`, `CEO`, `Employee`.

**Why fallback types are required**:
- The text will mention many kinds of people, e.g. "primary-school teachers", "passersby", "an anonymous netizen".
- When no dedicated type fits, they should fall into `Person`.
- Likewise, small organizations and ad-hoc groups should fall into `Organization`.

**Principles for concrete types**:
- Identify the high-frequency or pivotal role types in the text.
- Each concrete type should have a clear boundary and avoid overlap.
- The description must clearly state how the concrete type differs from the corresponding fallback type.

### 2. Relationship Type Design

- Count: 6 to 10.
- Relationships should reflect realistic interactions on social media.
- Ensure each relationship's source_targets cover the entity types you defined.

### 3. Attribute Design

- 1 to 3 key attributes per entity type.
- **Note**: attribute names must not use `name`, `uuid`, `group_id`, `created_at`, or `summary` (these are reserved by the system).
- Recommended names: `full_name`, `title`, `role`, `position`, `location`, `description`, etc.

## Entity Type Reference

**Individuals (concrete)**:
- Student: a student.
- Professor: a professor or scholar.
- Journalist: a journalist.
- Celebrity: a celebrity or internet personality.
- Executive: a senior business leader.
- Official: a government official.
- Lawyer: a lawyer.
- Doctor: a physician.

**Individuals (fallback)**:
- Person: any individual person (use when no concrete person type above applies).

**Organizations (concrete)**:
- University: a university or higher-education institution.
- Company: a company or business.
- GovernmentAgency: a government agency.
- MediaOutlet: a media organization.
- Hospital: a hospital.
- School: a primary or secondary school.
- NGO: a non-governmental organization.

**Organizations (fallback)**:
- Organization: any organization (use when no concrete organization type above applies).

## Relationship Type Reference

- WORKS_FOR: works for.
- STUDIES_AT: studies at.
- AFFILIATED_WITH: is affiliated with.
- REPRESENTS: represents.
- REGULATES: regulates.
- REPORTS_ON: reports on.
- COMMENTS_ON: comments on.
- RESPONDS_TO: responds to.
- SUPPORTS: supports.
- OPPOSES: opposes.
- COLLABORATES_WITH: collaborates with.
- COMPETES_WITH: competes with.
"""


class OntologyGenerator:
    """Generate an entity- and edge-type ontology from arbitrary input text."""
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()
    
    def generate(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate an ontology definition.

        Args:
            document_texts: Source document text segments.
            simulation_requirement: Description of the simulation goal.
            additional_context: Optional supplemental context.

        Returns:
            The ontology dict with ``entity_types``, ``edge_types``, and a summary.
        """
        # Compose the user message that frames the LLM request.
        user_message = self._build_user_message(
            document_texts, 
            simulation_requirement,
            additional_context
        )
        
        lang_instruction = get_language_instruction()
        system_prompt = f"{ONTOLOGY_SYSTEM_PROMPT}\n\n{lang_instruction}\nIMPORTANT: Entity type names MUST be in English PascalCase (e.g., 'PersonEntity', 'MediaOrganization'). Relationship type names MUST be in English UPPER_SNAKE_CASE (e.g., 'WORKS_FOR'). Attribute names MUST be in English snake_case. Only description fields and analysis_summary should use the specified language above."
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        # Invoke the LLM.
        result = self.llm_client.chat_json(
            messages=messages,
            temperature=0.3,
            max_tokens=4096
        )
        
        # Validate the LLM response and post-process it.
        result = self._validate_and_process(result)
        
        return result
    
    # Maximum length of source text passed to the LLM (50k characters).
    MAX_TEXT_LENGTH_FOR_LLM = 50000
    
    def _build_user_message(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str]
    ) -> str:
        """Build the user-message string for the ontology LLM call."""

        # Concatenate the source documents into a single string.
        combined_text = "\n\n---\n\n".join(document_texts)
        original_length = len(combined_text)

        # If the combined text exceeds the LLM input cap, truncate it for the
        # LLM call only. The full text is still used for graph construction.
        if len(combined_text) > self.MAX_TEXT_LENGTH_FOR_LLM:
            combined_text = combined_text[:self.MAX_TEXT_LENGTH_FOR_LLM]
            combined_text += f"\n\n...(original text is {original_length} characters; only the first {self.MAX_TEXT_LENGTH_FOR_LLM} characters were used for ontology analysis)..."

        message = f"""## Simulation Requirement

{simulation_requirement}

## Document Content

{combined_text}
"""

        if additional_context:
            message += f"""
## Additional Context

{additional_context}
"""

        message += """
Based on the content above, design entity types and relationship types suitable for a social-media public-opinion simulation.

**Rules that must be followed**:
1. You must output exactly 10 entity types.
2. The last 2 must be fallback types: Person (individual fallback) and Organization (organization fallback).
3. The first 8 are concrete types designed from the text content.
4. Every entity type must be a real-world subject that can post on social media; abstract concepts are not allowed.
5. Attribute names must not use reserved words such as name, uuid, group_id; use alternatives such as full_name, org_name, etc.
"""

        return message
    
    def _validate_and_process(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and post-process the LLM-generated ontology dict."""

        # Ensure required top-level fields exist.
        if "entity_types" not in result:
            result["entity_types"] = []
        if "edge_types" not in result:
            result["edge_types"] = []
        if "analysis_summary" not in result:
            result["analysis_summary"] = ""
        
        # Validate entity types.
        # Track original-name -> PascalCase mapping so edge source_targets
        # references can be fixed up consistently below.
        entity_name_map = {}
        for entity in result["entity_types"]:
            # Force entity names to PascalCase (required by the Zep API).
            if "name" in entity:
                original_name = entity["name"]
                entity["name"] = _to_pascal_case(original_name)
                if entity["name"] != original_name:
                    logger.warning(f"Entity type name '{original_name}' auto-converted to '{entity['name']}'")
                entity_name_map[original_name] = entity["name"]
            if "attributes" not in entity:
                entity["attributes"] = []
            if "examples" not in entity:
                entity["examples"] = []
            # Truncate descriptions longer than 100 characters.
            if len(entity.get("description", "")) > 100:
                entity["description"] = entity["description"][:97] + "..."

        # Validate edge types.
        for edge in result["edge_types"]:
            # Force edge names to SCREAMING_SNAKE_CASE (required by the Zep API).
            if "name" in edge:
                original_name = edge["name"]
                edge["name"] = original_name.upper()
                if edge["name"] != original_name:
                    logger.warning(f"Edge type name '{original_name}' auto-converted to '{edge['name']}'")
            # Rewrite source_targets entity-name references to match the
            # PascalCase-normalized entity names.
            for st in edge.get("source_targets", []):
                if st.get("source") in entity_name_map:
                    st["source"] = entity_name_map[st["source"]]
                if st.get("target") in entity_name_map:
                    st["target"] = entity_name_map[st["target"]]
            if "source_targets" not in edge:
                edge["source_targets"] = []
            if "attributes" not in edge:
                edge["attributes"] = []
            if len(edge.get("description", "")) > 100:
                edge["description"] = edge["description"][:97] + "..."
        
        # Zep API caps: at most 10 custom entity types and 10 custom edge types.
        MAX_ENTITY_TYPES = 10
        MAX_EDGE_TYPES = 10

        # Deduplicate by name, keeping the first occurrence.
        seen_names = set()
        deduped = []
        for entity in result["entity_types"]:
            name = entity.get("name", "")
            if name and name not in seen_names:
                seen_names.add(name)
                deduped.append(entity)
            elif name in seen_names:
                logger.warning(f"Duplicate entity type '{name}' removed during validation")
        result["entity_types"] = deduped

        # Fallback entity-type definitions used when the LLM omits them.
        person_fallback = {
            "name": "Person",
            "description": "Any individual person not fitting other specific person types.",
            "attributes": [
                {"name": "full_name", "type": "text", "description": "Full name of the person"},
                {"name": "role", "type": "text", "description": "Role or occupation"}
            ],
            "examples": ["ordinary citizen", "anonymous netizen"]
        }
        
        organization_fallback = {
            "name": "Organization",
            "description": "Any organization not fitting other specific organization types.",
            "attributes": [
                {"name": "org_name", "type": "text", "description": "Name of the organization"},
                {"name": "org_type", "type": "text", "description": "Type of organization"}
            ],
            "examples": ["small business", "community group"]
        }
        
        # Check whether the fallback types are already present.
        entity_names = {e["name"] for e in result["entity_types"]}
        has_person = "Person" in entity_names
        has_organization = "Organization" in entity_names

        # Collect missing fallback types to add below.
        fallbacks_to_add = []
        if not has_person:
            fallbacks_to_add.append(person_fallback)
        if not has_organization:
            fallbacks_to_add.append(organization_fallback)

        if fallbacks_to_add:
            current_count = len(result["entity_types"])
            needed_slots = len(fallbacks_to_add)

            # If adding the fallbacks would exceed the cap, drop some existing types.
            if current_count + needed_slots > MAX_ENTITY_TYPES:
                to_remove = current_count + needed_slots - MAX_ENTITY_TYPES
                # Drop trailing types first; the more specific types come earlier.
                result["entity_types"] = result["entity_types"][:-to_remove]

            result["entity_types"].extend(fallbacks_to_add)

        # Defensive cap enforcement: hard-trim if anything slipped through.
        if len(result["entity_types"]) > MAX_ENTITY_TYPES:
            result["entity_types"] = result["entity_types"][:MAX_ENTITY_TYPES]
        
        if len(result["edge_types"]) > MAX_EDGE_TYPES:
            result["edge_types"] = result["edge_types"][:MAX_EDGE_TYPES]
        
        return result
    
    def generate_python_code(self, ontology: Dict[str, Any]) -> str:
        """Render the ontology definition as Python source code.

        Args:
            ontology: Ontology definition dict.

        Returns:
            Python source code as a single string.
        """
        code_lines = [
            '"""',
            '自定义实体类型定义',
            '由MiroFish自动生成，用于社会舆论模拟',
            '"""',
            '',
            'from pydantic import Field',
            'from zep_cloud.external_clients.ontology import EntityModel, EntityText, EdgeModel',
            '',
            '',
            '# ============== 实体类型定义 ==============',
            '',
        ]
        
        # Emit each entity type as a Python class.
        for entity in ontology.get("entity_types", []):
            name = entity["name"]
            desc = entity.get("description", f"A {name} entity.")
            
            code_lines.append(f'class {name}(EntityModel):')
            code_lines.append(f'    """{desc}"""')
            
            attrs = entity.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr["name"]
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f'    {attr_name}: EntityText = Field(')
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append(f'        default=None')
                    code_lines.append(f'    )')
            else:
                code_lines.append('    pass')
            
            code_lines.append('')
            code_lines.append('')
        
        code_lines.append('# ============== 关系类型定义 ==============')
        code_lines.append('')
        
        # Emit each edge type as a Python class.
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            # Convert SCREAMING_SNAKE_CASE -> PascalCase for the class name.
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            desc = edge.get("description", f"A {name} relationship.")
            
            code_lines.append(f'class {class_name}(EdgeModel):')
            code_lines.append(f'    """{desc}"""')
            
            attrs = edge.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr["name"]
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f'    {attr_name}: EntityText = Field(')
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append(f'        default=None')
                    code_lines.append(f'    )')
            else:
                code_lines.append('    pass')
            
            code_lines.append('')
            code_lines.append('')
        
        # Emit the type registries.
        code_lines.append('# ============== 类型配置 ==============')
        code_lines.append('')
        code_lines.append('ENTITY_TYPES = {')
        for entity in ontology.get("entity_types", []):
            name = entity["name"]
            code_lines.append(f'    "{name}": {name},')
        code_lines.append('}')
        code_lines.append('')
        code_lines.append('EDGE_TYPES = {')
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            code_lines.append(f'    "{name}": {class_name},')
        code_lines.append('}')
        code_lines.append('')
        
        # Emit the edge source_targets map.
        code_lines.append('EDGE_SOURCE_TARGETS = {')
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            source_targets = edge.get("source_targets", [])
            if source_targets:
                st_list = ', '.join([
                    f'{{"source": "{st.get("source", "Entity")}", "target": "{st.get("target", "Entity")}"}}'
                    for st in source_targets
                ])
                code_lines.append(f'    "{name}": [{st_list}],')
        code_lines.append('}')
        
        return '\n'.join(code_lines)

