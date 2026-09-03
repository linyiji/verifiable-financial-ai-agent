"""In-memory Foundation registries for agents and skills."""

from src.agentic.skill import Skill
from src.agentic.specialist import SpecialistAgent


class DuplicateRegistrationError(ValueError):
    pass


class RegistrationNotFoundError(LookupError):
    pass


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, SpecialistAgent] = {}

    def register(self, agent: SpecialistAgent) -> None:
        if agent.agent_id in self._agents:
            raise DuplicateRegistrationError(f"agent already registered: {agent.agent_id}")
        self._agents[agent.agent_id] = agent

    def get(self, agent_id: str) -> SpecialistAgent:
        try:
            return self._agents[agent_id]
        except KeyError as exc:
            raise RegistrationNotFoundError(f"agent not registered: {agent_id}") from exc

    def for_task_type(self, task_type: str) -> tuple[SpecialistAgent, ...]:
        return tuple(
            agent
            for agent in self._agents.values()
            if task_type in agent.supported_task_types
        )

    def registered_ids(self) -> tuple[str, ...]:
        return tuple(self._agents)


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        skill_id = skill.definition.skill_id
        if skill_id in self._skills:
            raise DuplicateRegistrationError(f"skill already registered: {skill_id}")
        self._skills[skill_id] = skill

    def get(self, skill_id: str) -> Skill:
        try:
            return self._skills[skill_id]
        except KeyError as exc:
            raise RegistrationNotFoundError(f"skill not registered: {skill_id}") from exc

    def registered_ids(self) -> tuple[str, ...]:
        return tuple(self._skills)
