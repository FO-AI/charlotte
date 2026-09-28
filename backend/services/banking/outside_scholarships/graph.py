from langgraph.graph import StateGraph, START, END

from services.banking.outside_scholarships.state import OrchestratorState
from services.banking.outside_scholarships.nodes import (
    pair_pages_node,
    dispatch,
    process_check_node,
    aggregate_node,
)


def build_graph():
    """Compile and return the outside-scholarship check-processing graph."""
    builder = StateGraph(OrchestratorState)

    builder.add_node("pair_pages", pair_pages_node)
    builder.add_node("process_check", process_check_node)
    builder.add_node("aggregate", aggregate_node)

    builder.add_edge(START, "pair_pages")
    # Fan-out: one worker branch per check pair, routed via Send. Each worker renders its
    # check and reads the fields with one vision LLM call, and writes only check_results.
    builder.add_conditional_edges("pair_pages", dispatch, ["process_check"])
    # Fan-in: all worker branches converge here; check_results are merged by operator.add
    builder.add_edge("process_check", "aggregate")
    builder.add_edge("aggregate", END)

    return builder.compile()
