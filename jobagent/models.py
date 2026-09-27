"""Pydantic schemas shared by the LLM calls (structured outputs) and the rest of the app."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------- Resume ----------

class Link(BaseModel):
    label: str = Field(description="e.g. LinkedIn, GitHub, Portfolio")
    url: str


class SkillGroup(BaseModel):
    category: str = Field(description="e.g. Languages, Frameworks, Cloud & DevOps")
    items: list[str]


class Experience(BaseModel):
    company: str
    title: str = Field(description="Job title only, e.g. 'IT Analyst (SDE-2 Equivalent)'")
    team: str | None = Field(default=None, description="Team / product / platform line shown under the title, if any")
    location: str | None
    start: str = Field(description="As written on the resume, e.g. 'Jan 2023'")
    end: str = Field(description="As written, e.g. 'Present'")
    bullets: list[str]


class Project(BaseModel):
    name: str
    tech: list[str]
    url: str | None
    bullets: list[str]


class Education(BaseModel):
    institution: str
    degree: str
    start: str | None
    end: str | None
    details: str | None = Field(description="GPA, honours, relevant coursework")


class Resume(BaseModel):
    name: str
    headline: str | None = Field(default=None, description="Tagline under the name, e.g. 'Software Engineer - Java, Spring Boot'")
    email: str
    phone: str | None
    location: str | None
    links: list[Link]
    summary: str | None
    skills: list[SkillGroup]
    experience: list[Experience]
    projects: list[Project]
    education: list[Education]
    certifications: list[str]
    achievements: list[str]


# ---------- Matching ----------

class MatchResult(BaseModel):
    score: int = Field(description="0-100 fit of the candidate for this job")
    verdict: Literal["apply", "maybe", "skip"]
    reasons: list[str] = Field(description="2-4 short reasons for the score")
    missing_requirements: list[str] = Field(description="Hard requirements the candidate lacks")


# ---------- Tailoring ----------

class TailoredResume(BaseModel):
    resume: Resume
    changes: list[str] = Field(description="Short list of what was changed and why")
    added_skills: list[str] = Field(default_factory=list, description="Skills put on this resume that are NOT in the master resume")
    cover_letter: str = Field(description="Plain-text cover letter, 150-250 words, no placeholders")


# ---------- Form filling ----------

class FieldAnswer(BaseModel):
    field_id: str
    value: str = Field(
        description="Text to type; for select/radio the exact option label; for checkbox 'true'/'false'; "
        "for file inputs 'resume' or 'cover_letter'"
    )


class FormAnswers(BaseModel):
    answers: list[FieldAnswer]
    needs_human: list[str] = Field(
        description="field_ids that are required but cannot be answered truthfully from the provided facts"
    )
