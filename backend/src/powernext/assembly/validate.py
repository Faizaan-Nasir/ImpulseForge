"""Validate exact recipes/stock/identities at every direct physics boundary."""

from powernext.assembly.dp import to_assembly
from powernext.contracts.models import DomainError
from powernext.profiles.registry import digest


def candidate_identity(context, N, front, tail):
    return digest(
        {
            "context": context.context_hash,
            "N": N,
            "U_charge_V": context.charge,
            "front": front.assembly_id,
            "tail": tail.assembly_id,
        }
    )[:32]


def validate_candidate(context, candidate):
    if candidate.context_hash != context.context_hash or candidate.U_charge_V != context.charge:
        raise DomainError(
            "candidate_context_mismatch", "Candidate must match immutable context", "physics"
        )
    if candidate.N != candidate.proposal.N:
        raise DomainError("candidate_stage_mismatch", "Proposal/stages disagree", "physics")
    for role in ("front", "tail"):
        actual = getattr(candidate, role)
        reduced = to_assembly(actual.recipe, role)
        if reduced.model_dump() != actual.model_dump():
            raise DomainError(
                "invalid_assembly_record",
                "Assembly must match canonical recipe/netlist",
                "assembly",
            )
        types = {t.type_id: t for t in getattr(context.inventory, role)}
        for type_id, count in actual.type_counts.items():
            resistor = types.get(type_id)
            if resistor is None or count > resistor.capacity(candidate.N):
                raise DomainError(
                    "inventory_exceeded", "Assembly uses unavailable stock", "assembly"
                )
        for leaf in actual.netlist:
            if leaf["nominal_ohm"] != types[leaf["type_id"]].nominal_ohm:
                raise DomainError(
                    "inventory_value_mismatch", "Recipe differs from inventory value", "assembly"
                )
    if candidate.candidate_id != candidate_identity(
        context, candidate.N, candidate.front, candidate.tail
    ):
        raise DomainError(
            "candidate_identity_mismatch", "Candidate ID does not match realised setup", "assembly"
        )
