from pydantic import BaseModel, Field, HttpUrl
from typing import Optional
class AgentRequest(BaseModel): request: str = Field(min_length=1,max_length=4000)
class DeploymentCreate(BaseModel):
    name: str=Field(min_length=1,max_length=160)
    repo_url: HttpUrl
    branch: str=Field(default='main',min_length=1,max_length=120)
    container_port: int=Field(default=8000,ge=1,le=65535)
    host_port: int=Field(default=8080,ge=1,le=65535)
class CreateTextFile(BaseModel): key: str=Field(min_length=1,max_length=1000); content: str=''
class CreateFolder(BaseModel): key: str=Field(min_length=1,max_length=1000)
class RenameRequest(BaseModel): new_key: str=Field(min_length=1,max_length=1000)

class IncidentAnalyzeRequest(BaseModel):
    title: str = Field(default='Application incident', min_length=1, max_length=220)
    logs: str = Field(min_length=1, max_length=200000)

class ApprovalRequest(BaseModel):
    request: str = Field(min_length=1, max_length=4000)
    tool: str = Field(min_length=1, max_length=120)
    reason: str = Field(default='', max_length=2000)

class ApprovalDecision(BaseModel):
    decision: str = Field(pattern='^(approve|reject)$')
