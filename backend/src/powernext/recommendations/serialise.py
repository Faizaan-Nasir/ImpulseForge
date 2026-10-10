"""Expand identical per-stage recipes into physical component and node identities."""


def generator_stage_records(evaluation):
    candidate = evaluation["candidate"]
    physics = evaluation["physics"]
    stages = []
    for index in range(1, candidate["N"] + 1):
        prefix = f"stage_{index:02d}/"
        assemblies = {}
        for role in ("front", "tail"):
            assembly = candidate[role]
            assemblies[role + "_assembly"] = {
                **assembly,
                "netlist": [
                    {
                        **leaf,
                        "component_id": prefix + leaf["component_id"],
                        "node_a": prefix + role + "/" + leaf["node_a"],
                        "node_b": prefix + role + "/" + leaf["node_b"],
                    }
                    for leaf in assembly["netlist"]
                ],
            }
        stages.append(
            {
                "generator_stage_index": index,
                "active": True,
                "charge_V": candidate["U_charge_V"],
                "C_stage_F": physics["derived"]["C1_F"] * candidate["N"],
                "stored_energy_J": physics["stage_energy_J"],
                "stage_voltage_utilisation": physics.get("voltage_utilisation"),
                **assemblies,
                "component_stresses": [
                    c for c in physics["component_stresses"] if c["generator_stage_index"] == index
                ],
                "equal_sharing_assumed": True,
                "stage_connection_model": physics["derived"]["topology"],
                "assembly_terminal_scope": "local_stage_recipe",
                "constraints": physics["constraints"],
            }
        )
    return stages
