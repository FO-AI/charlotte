from langgraph.graph import StateGraph, START, END

from services.banking.outside_scholarships.state import OrchestratorState
from services.banking.outside_scholarships.nodes import (
    pair_pages_node,
    dispatch,
    di_extract_node,
    llm_verify_node,
    reconcile_node,
    aggregate_node,
)


def build_graph():
    """Compile and return the outside-scholarship check-processing graph."""
    builder = StateGraph(OrchestratorState)

    builder.add_node("pair_pages", pair_pages_node)
    builder.add_node("di_extract", di_extract_node)
    builder.add_node("llm_verify", llm_verify_node)
    builder.add_node("reconcile", reconcile_node)
    builder.add_node("aggregate", aggregate_node)

    builder.add_edge(START, "pair_pages")
    # Fan-out: one worker branch per check pair, routed via Send
    builder.add_conditional_edges("pair_pages", dispatch, ["di_extract"])
    builder.add_edge("di_extract", "llm_verify")
    builder.add_edge("llm_verify", "reconcile")
    # Fan-in: all worker branches converge here; check_results are merged by operator.add
    builder.add_edge("reconcile", "aggregate")
    builder.add_edge("aggregate", END)

    return builder.compile()
