from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from jira import JIRA
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

try:  # Optional local credentials fallback
    import settings  # type: ignore
except Exception:  # pragma: no cover - optional import
    settings = None

CLAIMS_DIR = Path("claims")


@dataclass
class JiraCredentials:
    server: str | None = None
    username: str | None = None
    password: str | None = None
    project_key: str = "EXP"
    issue_type: str = "Task"

    @classmethod
    def from_env(cls) -> JiraCredentials:
        return cls(
            server=os.getenv("JIRA_SERVER", "https://pyconjp.atlassian.net"),
            username=os.getenv(
                "JIRA_USERNAME",
                getattr(settings, "username", None) if settings else None,
            ),
            password=os.getenv(
                "JIRA_PASSWORD",
                getattr(settings, "password", None) if settings else None,
            ),
            project_key=os.getenv("JIRA_PROJECT_KEY", "ISSHA"),
            issue_type=os.getenv("JIRA_ISSUE_TYPE", "Task"),
        )

    def require(self) -> JiraCredentials:
        missing = [
            name
            for name, value in (
                ("server", self.server),
                ("username", self.username),
                ("password", self.password),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"Missing JIRA config: {', '.join(missing)}")
        return self


class ExpenseItemSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    paid_date: date = Field(alias="支払日")
    store: str = Field(alias="店名")
    amount: float = Field(alias="金額")
    content: str | None = Field(default="", alias="内容")

    @field_validator("store")
    def store_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("店名は必須です")
        return value.strip()

    @field_validator("amount")
    def amount_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("金額は 0 より大きい必要があります")
        return float(value)


class ClaimSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    claim_id: str
    claim_date: date = Field(alias="申請日")
    applicant: str = Field(alias="申請者名")
    title: str = Field(alias="タイトル")
    expense_type: str = Field(alias="経費種別")
    total_amount: float = Field(alias="合計金額")
    items: list[ExpenseItemSchema] = Field(alias="経費項目リスト")
    note: str | None = Field(default="", alias="備考")
    attachments: list[str] = Field(default_factory=list, alias="attachments")
    bank_name: str = Field(alias="銀行名")
    branch_name: str = Field(alias="支店名")
    account_type: str = Field(alias="口座種別")
    account_number: str = Field(alias="口座番号")
    account_holder: str = Field(alias="口座名義")
    created_at: str | None = Field(default=None, alias="created_at")

    @field_validator("applicant", "title", "bank_name", "branch_name", "account_holder")
    def required_text(cls, value: str) -> str:
        if not (value or "").strip():
            raise ValueError("必須項目が入力されていません")
        return value.strip()

    @field_validator("account_number")
    def account_number_digits(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("口座番号は数字のみで入力してください")
        if len(value) < 7:
            raise ValueError("口座番号は7桁以上で入力してください")
        return value

    @model_validator(mode="after")
    def check_total(cls, values: ClaimSchema) -> ClaimSchema:
        calc_sum = sum(item.amount for item in values.items)
        if abs(calc_sum - float(values.total_amount)) > 0.01:
            raise ValueError("合計金額が明細の合計と一致していません")
        return values


@dataclass
class Claim:
    claim_id: str
    applicant: str
    title: str
    expense_type: str
    total_amount: float
    claim_date: str
    items: list[dict[str, Any]]
    note: str
    bank_name: str
    branch_name: str
    account_type: str
    account_number: str
    account_holder: str
    attachments: list[str] = field(default_factory=list)
    created_at: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Claim:
        validated = ClaimSchema.model_validate(data)
        validated_items = [item.model_dump(by_alias=True) for item in validated.items]
        return cls(
            claim_id=validated.claim_id,
            applicant=validated.applicant,
            title=validated.title,
            expense_type=validated.expense_type,
            total_amount=float(validated.total_amount),
            claim_date=validated.claim_date.isoformat(),
            items=validated_items,
            note=validated.note or "",
            bank_name=validated.bank_name,
            branch_name=validated.branch_name,
            account_type=validated.account_type,
            account_number=validated.account_number,
            account_holder=validated.account_holder,
            attachments=validated.attachments,
            created_at=validated.created_at,
            raw=validated.model_dump(by_alias=True),
        )

    def to_description(self) -> str:
        lines = [
            f"申請日: {self.claim_date}",
            f"申請者名: {self.applicant}",
            f"経費種別: {self.expense_type}",
            f"合計金額: {self.total_amount:.0f} JPY",
            f"振込先: {self.bank_name} {self.branch_name} / {self.account_type} {self.account_number} / {self.account_holder}",
        ]
        if self.note:
            lines.append(f"備考: {self.note}")
        lines.append("明細:")
        for idx, item in enumerate(self.items, start=1):
            lines.append(
                f"- {idx}: {item.get('支払日', '')} {item.get('店名', '')} {item.get('金額', 0)} {item.get('内容', '')}".strip()
            )
        return "\n".join(lines)


def load_claim(claim_id: str, claims_dir: Path = CLAIMS_DIR) -> Claim:
    claim_path = claims_dir / claim_id / "claim.json"
    if not claim_path.exists():
        raise FileNotFoundError(f"Claim not found: {claim_path}")
    with open(claim_path, encoding="utf-8") as fp:
        data: dict[str, Any] = json.load(fp)
    return Claim.from_json(data)


def list_claims(claims_dir: Path = CLAIMS_DIR) -> list[Claim]:
    results: list[Claim] = []
    if not claims_dir.exists():
        return results
    for claim_file in claims_dir.glob("*/claim.json"):
        try:
            with open(claim_file, encoding="utf-8") as fp:
                data: dict[str, Any] = json.load(fp)
            results.append(Claim.from_json(data))
        except Exception:
            continue
    results.sort(key=lambda c: c.created_at or "", reverse=True)
    return results


def validate_claim_dict(data: dict[str, Any]) -> dict[str, Any]:
    validated = ClaimSchema.model_validate(data)
    return validated.model_dump(by_alias=True)


class JiraBackend:
    def __init__(self, credentials: JiraCredentials | None = None) -> None:
        self.credentials = (credentials or JiraCredentials.from_env()).require()
        self.client = JIRA(
            server=self.credentials.server,
            basic_auth=(self.credentials.username, self.credentials.password),
        )

    def _build_issue_url(self, issue_key: str) -> str:
        if self.credentials.server:
            return f"{self.credentials.server.rstrip('/')}/browse/{issue_key}"
        return ""

    def create_issue_for_claim(self, claim: Claim) -> tuple[str, str]:
        fields = {
            "project": {"key": self.credentials.project_key},
            "summary": f"経費精算: {claim.title}",
            "description": claim.to_description(),
            "issuetype": {"name": self.credentials.issue_type},
        }
        issue = self.client.create_issue(fields=fields)
        for attachment in claim.attachments:
            path = Path(attachment)
            if not path.exists():
                continue
            with open(path, "rb") as fp:
                self.client.add_attachment(
                    issue=issue, attachment=fp, filename=path.name
                )
        return issue.key, self._build_issue_url(issue.key)

    def create_issue_from_claim_id(self, claim_id: str) -> tuple[str, str]:
        claim = load_claim(claim_id)
        return self.create_issue_for_claim(claim)


__all__ = [
    "Claim",
    "JiraBackend",
    "JiraCredentials",
    "load_claim",
    "list_claims",
    "validate_claim_dict",
]
