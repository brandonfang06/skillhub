from pydantic import BaseModel, ConfigDict, Field


class PlaygroundContract(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class CapabilityRequest(PlaygroundContract):
    version: str = Field(min_length=1)


class CapabilityResponse(PlaygroundContract):
    token: str
    expires_at: int = Field(alias="expiresAt")


class PlaygroundSkill(PlaygroundContract):
    namespace: str
    slug: str
    display_name: str = Field(alias="displayName")
    version: str


class PlaygroundFile(PlaygroundContract):
    path: str
    content: str = ""
    included_in_prompt: bool = Field(alias="includedInPrompt", default=False)


class PlaygroundContextResponse(PlaygroundContract):
    skill: PlaygroundSkill
    files: list[PlaygroundFile]
