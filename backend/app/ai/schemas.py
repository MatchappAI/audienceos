"""Validated structured outputs for each AI stage."""
from typing import Literal

from pydantic import BaseModel, Field

SignalType = Literal["question", "frustration", "unmet_need", "resource_request", "dislikes_existing_solution",
                     "repetitive_task", "desired_outcome"]
IntentLevel = Literal["engagement", "curiosity", "free_info_request", "existing_spending", "buying_question",
                      "paid_solution_request", "verified_purchase"]
ProductType = Literal["digital template", "toolkit", "course", "workshop", "research report", "membership",
                      "community", "calculator/tool", "software", "guide/ebook", "coaching", "productized service",
                      "physical product", "other"]


class Topic(BaseModel):
    name: str
    weight: Literal["major", "minor"]


class Characteristic(BaseModel):
    claim: str = Field(description="An audience characteristic, phrased cautiously")
    basis: str = Field(description="Why the material supports this")
    refs: list[str] = Field(description="Unit refs (e.g. C3, D2) that support it")


class Profile(BaseModel):
    summary: str = Field(description="2-3 sentences: what this creator/business covers and for whom")
    topics: list[Topic]
    intended_audience: str
    problem_types: list[str] = Field(description="Kinds of problems the content addresses")
    content_categories: list[str]
    credibility_signals: list[str] = Field(description="Expertise/credibility evident in the material only")
    audience_characteristics: list[Characteristic]
    unknowns: list[str] = Field(description="Important things the material does not reveal")


class ExtractedSignal(BaseModel):
    ref: str = Field(description="The unit ref the quote comes from, e.g. C12 or D3")
    signal_type: SignalType
    intent_level: IntentLevel
    summary: str = Field(description="Plain-English summary of the need in under 20 words")
    quote: str = Field(description="An exact, verbatim excerpt (max ~35 words) copied from that unit")


class ExtractionResult(BaseModel):
    signals: list[ExtractedSignal]


class Theme(BaseModel):
    label: str = Field(description="Short problem name, 2-6 words")
    description: str = Field(description="One sentence describing the shared problem")
    signal_ids: list[int]


class ClusterResult(BaseModel):
    themes: list[Theme]


class ModelScores(BaseModel):
    audience_fit: int = Field(ge=1, le=5)
    distribution_fit: int = Field(ge=1, le=5)
    competition: int = Field(ge=1, le=5, description="5 = lots of room vs alternatives")
    delivery_feasibility: int = Field(ge=1, le=5)
    cost_to_produce: int = Field(ge=1, le=5, description="5 = cheap to produce and support")
    margin_potential: int = Field(ge=1, le=5)
    recurring_potential: int = Field(ge=1, le=5)
    experiment_feasibility: int = Field(ge=1, le=5)
    rationale: str = Field(description="One or two sentences explaining the scores")


class OpportunityDraft(BaseModel):
    name: str
    buyer: str = Field(description="Which audience segment buys it")
    problem: str = Field(description="The painful job it solves")
    product_type: ProductType
    format_rationale: str = Field(description="Why this delivery format fits this audience")
    price: float = Field(ge=0, description="A price to TEST, in USD")
    price_model: Literal["one-time", "monthly", "annual", "per-session"]
    price_rationale: str
    theme_ids: list[int] = Field(description="Problem theme numbers (T#) this addresses")
    evidence_ids: list[int] = Field(description="Evidence numbers (E#) that support demand")
    alternatives: str = Field(description="Existing alternatives/competitor types; say these are from general knowledge")
    production: str = Field(description="What must be created")
    production_cost_estimate: float = Field(ge=0, description="One-time USD cost estimate (time valued at cost) — an assumption")
    fulfillment_cost_per_unit: float = Field(ge=0, description="Variable USD cost per sale excluding payment fees — an assumption")
    delivery_difficulty: Literal["low", "medium", "high"]
    recurring: str = Field(description="Repeat purchase or recurring revenue characteristics")
    distribution: str = Field(description="How the creator would promote it")
    validation_experiment: str = Field(description="A concrete test that would show real purchasing intent")
    risks: list[str]
    supported: list[str] = Field(description="Findings directly supported by the evidence")
    assumed: list[str] = Field(description="Assumptions not yet supported")
    unknown: list[str] = Field(description="Missing evidence that would change the decision")
    scores: ModelScores


class Gap(BaseModel):
    gap: str
    theme_ids: list[int]


class OpportunityResult(BaseModel):
    opportunities: list[OpportunityDraft]
    market_gaps: list[Gap]


class CompetitorQueries(BaseModel):
    queries: list[str]


class AssetDraft(BaseModel):
    title: str = ""  # optional: small models sometimes omit it; the caller falls back to "<Kind> — <product>"
    markdown: str


class LandingCopy(BaseModel):
    headline: str
    subheadline: str
    problem: str
    bullets: list[str]
    whats_inside: list[str]
    who_its_for: str
    who_its_not_for: str
    price_line: str
    cta: str = Field(description="Button label only, 2-5 words (e.g. 'Join the membership')")
    faq: list["FAQ"]


class FAQ(BaseModel):
    q: str
    a: str


class Issue(BaseModel):
    claim: str
    problem: str
    suggestion: str


class ClaimReview(BaseModel):
    issues: list[Issue] = Field(description="Unsupported or risky claims")
    overall: str


class CalcInput(BaseModel):
    name: str = Field(description="snake_case identifier")
    label: str
    default: float = 0


class CalcOutput(BaseModel):
    label: str
    expression: str = Field(description="Uses only input names, numbers and + - * / ( )")


class CalculatorSpec(BaseModel):
    title: str = "Calculator"
    description: str = ""
    inputs: list[CalcInput]
    outputs: list[CalcOutput]
    notes: str = ""


LandingCopy.model_rebuild()
