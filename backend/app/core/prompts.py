import json

from app.models import Agent, Skill


def build_effective_system_prompt(
    agent: Agent,
    platform_instructions: str = "",
    skills: list[Skill] | None = None,
) -> str:
    sections: list[str] = []
    if platform_instructions:
        sections.append("PLATFORM RULES\n" + platform_instructions.strip())
    if agent.system_prompt:
        sections.append("AGENT INSTRUCTIONS\n" + agent.system_prompt.strip())

    skill_sections: list[str] = []
    for skill in agent.skills if skills is None else skills:
        content = [f"Skill: {skill.name}", skill.instructions.strip()]
        if skill.output_schema:
            content.append(
                "Expected output schema:\n" + json.dumps(skill.output_schema, ensure_ascii=False, indent=2)
            )
        skill_sections.append("\n".join(content))
    if skill_sections:
        sections.append("ACTIVE SKILLS\n\n" + "\n\n".join(skill_sections))
    return "\n\n".join(sections)
