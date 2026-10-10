from typing import Any, Protocol

from powernext.contracts.models import Candidate, Proposal
from powernext.profiles.resolve import Context


class ProposalAdapter(Protocol):
    def ask(self, index: int) -> tuple[Any, Proposal]: ...
    def tell(self, trial: Any, cost: float) -> None: ...


class AssemblyAdapter(Protocol):
    def realise(
        self, context: Context, proposal: Proposal, forbidden_pairs=()
    ) -> tuple[Candidate, dict]: ...


class CorrectionAdapter(Protocol):
    def correct(self, context: Context, candidate: Candidate, baseline: dict) -> dict: ...
    def report(self) -> dict: ...
